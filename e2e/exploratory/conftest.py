"""Exploratory probes (T07c). They reuse the fixtures from ``e2e/conftest.py``.

These are scratch scripts from a charter-based QA session, not regression tests: they are slow,
they print rather than assert, and they mutate global server state. `pytest e2e` therefore skips
them; run them explicitly with

    E2E_EXPLORATORY=1 E2E_SKIP_BUILD=1 venv/bin/python -m pytest e2e/exploratory -q -s

Confirmed findings live in ``plans/QA_FINDINGS.md`` with red tests in
``e2e/tests/test_findings_admin.py``.
"""
import os

collect_ignore_glob = [] if os.environ.get('E2E_EXPLORATORY') == '1' else ['test_probe_*.py']
