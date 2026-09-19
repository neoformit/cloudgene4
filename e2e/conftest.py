"""E2E fixtures. See e2e/README.md for usage.

Fixtures other tests use:
  stack            session  running Stack (base_url, home, outbox_dir, manage(), django_shell(), ...)
  base_url         session  stack.base_url (pytest-playwright resolves page.goto('/x') against it)
  page             function pytest-playwright page with the error guard attached (guards.py)
  expect_api_error function expect_api_error(status, path_glob) -> allow an API/resource error
  expect_console_error      expect_console_error(substring_or_regex)
  login            function login(page, 'alice', fresh=False): UI login once per user, then reuse
                            the storage state; fresh=True always goes through the UI, uncached
  user_page        function user_page('bob') -> new guarded context+page logged in as bob
  api              function api('alice') / api() -> helpers.ApiClient (arrange/assert only)
  requires_worker  function skip unless `manage.py run_worker` is running
  server_settings  function read/update settings.yaml; restored after the test (mark serial!)
"""
import copy
import os
import time

import pytest

from e2e import stack as stack_mod
from e2e.constants import USERS
from e2e.helpers import ApiClient
from e2e.pages import LoginPage, Navbar

pytest_plugins = ['e2e.guards', 'pytester']

ARTIFACTS = stack_mod.ARTIFACTS
_results = []


def pytest_configure(config):
    # Playwright traces/screenshots go under e2e/.artifacts/playwright unless --output is given.
    if getattr(config.option, 'output', None) == 'test-results':
        config.option.output = str(ARTIFACTS / 'playwright')


# -- stack -----------------------------------------------------------------------------------------

@pytest.fixture(scope='session')
def stack():
    name = os.environ.get('PYTEST_XDIST_WORKER', 'main')
    s = stack_mod.start_stack(name)
    yield s
    s.stop()


@pytest.fixture(scope='session')
def base_url(stack):
    return stack.base_url


@pytest.fixture(scope='session', autouse=True)
def _verify_url():
    """Neutralise pytest-base-url's autouse check so tests that don't need the stack don't boot it."""


@pytest.fixture
def page(context, guard):
    """pytest-playwright's `page`, with the error guard (e2e/guards.py) attached to its context."""
    guard.attach(context)
    return context.new_page()


@pytest.fixture
def requires_worker(stack):
    stack.require_worker()


# -- auth ------------------------------------------------------------------------------------------

@pytest.fixture(scope='session')
def _auth_states():
    return {}


def _apply_state(page, base_url, state):
    page.context.add_cookies(state.get('cookies', []))
    for origin in state.get('origins', []):
        items = origin.get('localStorage') or []
        if not items:
            continue
        # Set localStorage on the app origin without hitting the server (no guard noise).
        blank = origin['origin'] + '/__e2e_blank__'
        page.route(blank, lambda route: route.fulfill(status=200, content_type='text/html', body='<html></html>'))
        page.goto(blank)
        page.evaluate('items => items.forEach(i => localStorage.setItem(i.name, i.value))', items)
        page.unroute(blank)


@pytest.fixture
def login(base_url, _auth_states):
    def _login(page, user, fresh=False):
        if not fresh and user in _auth_states:
            _apply_state(page, base_url, _auth_states[user])
            return page
        LoginPage(page).open().login(user, USERS[user]['password'])
        page.wait_for_url(lambda url: '/login' not in url)
        Navbar(page).expect_logged_in(user)
        if not fresh:
            _auth_states[user] = page.context.storage_state()
        return page
    return _login


@pytest.fixture
def user_page(new_context, guard, login):
    def _user_page(user=None):
        ctx = new_context()
        guard.attach(ctx)
        pg = ctx.new_page()
        if user:
            login(pg, user)
        return pg
    return _user_page


@pytest.fixture
def api(stack):
    clients = []

    def _api(user=None):
        client = ApiClient(stack.base_url)
        if user:
            client.login(user)
        clients.append(client)
        return client
    yield _api
    for c in clients:
        c.close()


# -- settings.yaml -----------------------------------------------------------------------------

class ServerSettings:
    def __init__(self, stack):
        self.stack = stack
        self.original = stack.read_settings()

    def read(self):
        return self.stack.read_settings()

    def update(self, section, **values):
        data = self.stack.read_settings()
        data.setdefault(section, {}).update(values)
        self.stack.write_settings(data)
        time.sleep(1.1)  # mtime-based caches need a newer second

    def restore(self):
        self.stack.write_settings(copy.deepcopy(self.original))


@pytest.fixture
def server_settings(stack):
    s = ServerSettings(stack)
    yield s
    s.restore()


# -- human-readable summary ------------------------------------------------------------------------

def pytest_runtest_logreport(report):
    if report.when == 'call' or (report.when == 'setup' and report.outcome != 'passed') or \
            (report.when == 'teardown' and report.failed):
        _results.append(report)


def _outcome(rep):
    if hasattr(rep, 'wasxfail'):
        return 'XPASS' if rep.passed else 'XFAIL'
    if rep.failed:
        return 'ERROR' if rep.when != 'call' else 'FAILED'
    return rep.outcome.upper()


def pytest_terminal_summary(terminalreporter, config):
    if hasattr(config, 'workerinput') or not _results:
        return
    from slugify import slugify
    out_dir = getattr(config.option, 'output', str(ARTIFACTS / 'playwright'))
    lines = ['E2E summary (%s)' % time.strftime('%Y-%m-%d %H:%M:%S'), '']
    counts = {}
    for rep in _results:
        oc = _outcome(rep)
        counts[oc] = counts.get(oc, 0) + 1
        lines.append('%-7s %6.1fs  %s' % (oc, rep.duration, rep.nodeid))
        if oc in ('FAILED', 'ERROR'):
            crash = getattr(rep.longrepr, 'reprcrash', None)
            msg = crash.message if crash else str(rep.longrepr).strip().splitlines()[-1]
            lines.append('          first error: %s' % msg.splitlines()[0][:300])
            for title, content in rep.sections:
                if 'e2e-guard' in title:
                    lines.extend('          ' + ln for ln in content.splitlines()[:8])
            trace = os.path.join(out_dir, slugify(rep.nodeid), 'trace.zip')
            if os.path.exists(trace):
                lines.append('          trace: %s  (python -m playwright show-trace <file>)' % trace)
        elif oc in ('XFAIL', 'SKIPPED'):
            reason = rep.wasxfail if oc == 'XFAIL' else (rep.longrepr[2] if isinstance(rep.longrepr, tuple) else '')
            lines.append('          reason: %s' % reason)
    lines.insert(1, 'totals: ' + ', '.join('%s=%d' % kv for kv in sorted(counts.items())))
    lines.append('')
    lines.append('stack logs: %s/stack-*/logs/   playwright artefacts: %s' % (ARTIFACTS, out_dir))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / 'summary.txt').write_text('\n'.join(lines) + '\n')
    terminalreporter.write_line('E2E summary written to %s' % (ARTIFACTS / 'summary.txt'))
