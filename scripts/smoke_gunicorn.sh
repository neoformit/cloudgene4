#!/usr/bin/env bash
# Production-server smoke test (TASKS T09a bullet 1): build the SPA, collectstatic, boot the
# real production stack (gunicorn, DEBUG=False, whitenoise serving from STATIC_ROOT) against a
# throw-away CLOUDGENE_HOME + sqlite DB, and confirm the SPA shell, a hashed static asset, and
# /api/health are all served correctly.
#
# Usage: scripts/smoke_gunicorn.sh [--skip-build]
#   --skip-build  reuse the already-built frontend/static output instead of running `npm run
#                 build` again (useful when iterating on this script).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/venv/bin/python}"
[[ -x "$PY" ]] || PY="python3"

SKIP_BUILD=0
[[ "${1:-}" == "--skip-build" ]] && SKIP_BUILD=1

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  step "Building the SPA (npm run build)"
  (cd frontend && npm run build)
fi
[[ -f "$ROOT/static/frontend/index.html" ]] || fail "static/frontend/index.html missing — build the frontend first"

WORKDIR="$(mktemp -d)"
trap 'kill "${GUNICORN_PID:-0}" 2>/dev/null || true; rm -rf "$WORKDIR"' EXIT

export DJANGO_SETTINGS_MODULE=cloudgene_django.settings
export CLOUDGENE_HOME="$WORKDIR/home"
export DATABASE_URL="sqlite:///$WORKDIR/db.sqlite3"
export DJANGO_SECRET_KEY="smoke-test-not-secret"
export DEBUG=False
export ALLOWED_HOSTS=127.0.0.1,localhost
export STATIC_ROOT_OVERRIDE=""  # placeholder, STATIC_ROOT is fixed at BASE_DIR/staticfiles

step "Migrating a throw-away DB ($DATABASE_URL)"
"$PY" manage.py migrate --noinput >"$WORKDIR/migrate.log" 2>&1 \
  || { cat "$WORKDIR/migrate.log"; fail "migrate failed"; }

step "collectstatic (DEBUG=False → gunicorn serves from STATIC_ROOT, not the finders)"
"$PY" manage.py collectstatic --noinput --clear >"$WORKDIR/collectstatic.log" 2>&1 \
  || { cat "$WORKDIR/collectstatic.log"; fail "collectstatic failed"; }
[[ -f "$ROOT/staticfiles/frontend/index.html" ]] || fail "collectstatic did not produce staticfiles/frontend/index.html"

step "manage.py check --deploy against this env (expect clean once the .env.example vars are set)"
"$PY" manage.py check --deploy >"$WORKDIR/check.log" 2>&1 || true
cat "$WORKDIR/check.log"

# Find a free port.
PORT="$("$PY" - <<'EOF'
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
print(s.getsockname()[1])
s.close()
EOF
)"
BASE_URL="http://127.0.0.1:$PORT"

step "Starting gunicorn on $BASE_URL"
GUNICORN="$(dirname "$PY")/gunicorn"
[[ -x "$GUNICORN" ]] || GUNICORN="gunicorn"
GUNICORN_BIND="127.0.0.1:$PORT" GUNICORN_WORKERS=1 \
  "$GUNICORN" -c deploy/gunicorn.conf.py cloudgene_django.wsgi:application \
  >"$WORKDIR/gunicorn.log" 2>&1 &
GUNICORN_PID=$!

step "Waiting for gunicorn to accept connections"
for _ in $(seq 1 50); do
  if curl -fsS -o /dev/null "$BASE_URL/api/health"; then
    break
  fi
  sleep 0.2
done

step "GET / (SPA shell)"
BODY="$(curl -fsS "$BASE_URL/")" || { cat "$WORKDIR/gunicorn.log"; fail "GET / failed"; }
echo "$BODY" | grep -q '<div id="app">' || fail "GET / did not return the SPA shell"

step "GET a hashed static asset"
ASSET_PATH="$(echo "$BODY" | grep -oE '/static/frontend/assets/index-[A-Za-z0-9_-]+\.js' | head -1)"
[[ -n "$ASSET_PATH" ]] || fail "could not find a hashed asset path in the SPA shell"
ASSET_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL$ASSET_PATH")"
[[ "$ASSET_STATUS" == "200" ]] || fail "GET $ASSET_PATH returned $ASSET_STATUS (expected 200)"
CACHE_CONTROL="$(curl -sI "$BASE_URL$ASSET_PATH" | grep -i '^cache-control:' || true)"
echo "asset: $ASSET_PATH -> 200 ($CACHE_CONTROL)"

step "GET /api/health"
HEALTH="$(curl -fsS "$BASE_URL/api/health")" || fail "GET /api/health failed"
echo "$HEALTH"
echo "$HEALTH" | grep -q '"status"' || fail "/api/health did not return a status field"

step "OK (gunicorn smoke test)"
