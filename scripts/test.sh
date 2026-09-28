#!/usr/bin/env bash
# Single entry point for all test suites (plans/SPEC.md §5).
#
#   scripts/test.sh unit             Django checks + tests (incl. schema staleness) + vitest, SQLite
#   scripts/test.sh unit --postgres  same, but Django tests run against Postgres (see below)
#   scripts/test.sh e2e    Playwright E2E suite (pytest e2e), if e2e/ exists
#   scripts/test.sh all    unit, then e2e (default)
#
# --postgres (unit mode only): runs `manage.py test` with DATABASE_URL set to $TEST_DATABASE_URL
# (default postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene, matching the local role/db set
# up per plans/TASKS.md T09b). The vitest/check/migrations steps are unaffected (they don't touch
# a real DB). Requires a running, reachable Postgres server; nothing here starts one.
#
# Extra arguments after the mode are passed to pytest in e2e mode.
# Python: $PYTHON, else ./venv/bin/python, else python3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-all}"
[[ $# -gt 0 ]] && shift

USE_POSTGRES=0
ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--postgres" ]]; then
    USE_POSTGRES=1
  else
    ARGS+=("$arg")
  fi
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
  PY="$ROOT/venv/bin/python"
else
  PY="python3"
fi

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

run_unit() {
  step "Django system checks"
  "$PY" manage.py check
  step "Migrations up to date"
  "$PY" manage.py makemigrations --check --dry-run
  if [[ "$USE_POSTGRES" == "1" ]]; then
    DB_URL="${TEST_DATABASE_URL:-postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene}"
    step "Django tests (incl. schema.yaml staleness) — Postgres ($DB_URL)"
    DATABASE_URL="$DB_URL" "$PY" manage.py test
  else
    step "Django tests (incl. schema.yaml staleness)"
    "$PY" manage.py test
  fi
  step "Frontend unit tests (vitest)"
  if [[ ! -d frontend/node_modules ]]; then
    (cd frontend && npm ci)
  fi
  (cd frontend && npx vitest run)
}

run_e2e() {
  if [[ ! -d e2e ]]; then
    step "E2E: no e2e/ directory yet - skipped"
    return 0
  fi
  step "E2E tests (pytest e2e)"
  "$PY" -m pytest e2e "$@"
}

case "$MODE" in
  unit) run_unit ;;
  e2e) run_e2e "$@" ;;
  all) run_unit; run_e2e "$@" ;;
  *) echo "usage: $0 [unit|e2e|all] [pytest args...]" >&2; exit 2 ;;
esac

step "OK ($MODE)"
