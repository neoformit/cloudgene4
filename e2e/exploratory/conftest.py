"""Exploratory probes from the charter-based QA sessions (T07a/b/c).

These reuse the fixtures from ``e2e/conftest.py`` but are scratch scripts, not regression
tests: they are slow, they print rather than assert, and they mutate global server state.
`pytest e2e` therefore skips them; run them explicitly with

    E2E_EXPLORATORY=1 E2E_SKIP_BUILD=1 venv/bin/python -m pytest e2e/exploratory -q -s

Confirmed findings live in ``plans/QA_FINDINGS.md``, each with a red test under
``e2e/tests/test_findings_*.py``.
"""
import json
import os

import pytest

collect_ignore_glob = [] if os.environ.get('E2E_EXPLORATORY') == '1' else ['test_probe_*.py']


@pytest.fixture
def report(request):
    """Collect observations and print them at the end of the probe."""
    lines = []

    def _add(label, value):
        lines.append('  %-42s %s' % (label, value))
        return value
    _add.lines = lines
    yield _add
    print('\n--- %s ---' % request.node.name)
    print('\n'.join(lines))


def brief(resp, limit=300):
    try:
        body = json.dumps(resp.json())
    except Exception:
        body = resp.text
    return '%s %s' % (resp.status_code, body[:limit].replace('\n', ' '))
