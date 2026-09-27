"""Exploratory probes (T07a). Reuses the e2e harness fixtures from e2e/conftest.py.

Run with:  venv/bin/python -m pytest e2e/exploratory/<file>.py -q -s
These files are NOT part of the scripted suite (e2e/pytest.ini has `testpaths = tests`).
"""
import json

import pytest


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
