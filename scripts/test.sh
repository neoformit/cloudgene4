#!/usr/bin/env bash
# Single entry point for all test suites (plans/SPEC.md §5).
#
#   scripts/test.sh unit   Django checks + tests (incl. schema staleness) + vitest
#   scripts/test.sh e2e    Playwright E2E suite (pytest e2e), if e2e/ exists
#   scripts/test.sh all    unit, then e2e (default)
#
# Extra arguments after the mode are passed to pytest in e2e mode.
# Python: $PYTHON, else ./venv/bin/python, else python3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-all}"
[[ $# -gt 0 ]] && shift

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
  step "Django tests (incl. schema.yaml staleness)"
  "$PY" manage.py test
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
