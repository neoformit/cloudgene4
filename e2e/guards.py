"""Automatic failure guards for browser tests (pytest plugin, loaded by e2e/conftest.py).

Every test that uses the `page` fixture fails — after its body passed — if the browser saw:
  * a console message of type "error" (except Chromium's generic "Failed to load resource",
    which is covered by the response check below),
  * an uncaught exception / unhandled rejection (page "weberror"),
  * a same-origin response with status >= 400 (API or asset), or a failed same-origin request,
unless the test declared it first:

    def test_bad_login(page, expect_api_error):
        expect_api_error(400, '/api/auth/login*')      # status may be an int, a tuple or None (=any)
        expect_console_error('Invalid credentials')    # substring or compiled regex

Declared expectations only *allow* errors; they don't require them.
Guard findings are also attached to the test report ("e2e-guard" section) when the body failed.
"""
import fnmatch
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import pytest

GENERIC_RESOURCE_ERROR = 'Failed to load resource'


@dataclass
class ErrorGuard:
    origin: str = None  # scheme://host:port of the app; None = learn from first navigation
    issues: list = field(default_factory=list)
    allowed_api: list = field(default_factory=list)
    allowed_console: list = field(default_factory=list)
    contexts: list = field(default_factory=list)

    # -- declarations ----------------------------------------------------------------------------
    def expect_api_error(self, status, path_glob):
        """Allow responses with `status` (int, iterable of ints, or None = any >= 400) whose URL
        path (+query) matches `path_glob` (fnmatch, e.g. '/api/jobs/*/status')."""
        statuses = None if status is None else ({status} if isinstance(status, int) else set(status))
        self.allowed_api.append((statuses, path_glob))

    def expect_console_error(self, pattern):
        self.allowed_console.append(pattern)

    # -- wiring ----------------------------------------------------------------------------------
    def attach(self, context):
        context.on('console', self._on_console)
        context.on('weberror', self._on_weberror)
        context.on('response', self._on_response)
        context.on('requestfailed', self._on_requestfailed)
        self.contexts.append(context)

    def _same_origin(self, url):
        p = urlparse(url)
        origin = '%s://%s' % (p.scheme, p.netloc)
        if self.origin is None and p.scheme in ('http', 'https'):
            self.origin = origin
        return origin == self.origin

    @staticmethod
    def _path(url):
        p = urlparse(url)
        return p.path + ('?' + p.query if p.query else '')

    def _api_allowed(self, status, path):
        for statuses, glob in self.allowed_api:
            if (statuses is None or status in statuses) and (
                    fnmatch.fnmatchcase(path, glob) or fnmatch.fnmatchcase(path.split('?')[0], glob)):
                return True
        return False

    def _console_allowed(self, text):
        for pat in self.allowed_console:
            if (pat.search(text) if isinstance(pat, re.Pattern) else pat in text):
                return True
        return False

    def _on_console(self, msg):
        if msg.type != 'error':
            return
        text = msg.text
        if text.startswith(GENERIC_RESOURCE_ERROR):
            return  # reported (with URL + status) by _on_response
        if self._console_allowed(text):
            return
        loc = msg.location or {}
        self.issues.append('console.error: %s  (at %s:%s)' % (text, loc.get('url', '?'), loc.get('lineNumber', '?')))

    def _on_weberror(self, web_error):
        err = web_error.error
        text = '%s: %s' % (getattr(err, 'name', 'Error'), getattr(err, 'message', err))
        if self._console_allowed(text):
            return
        stack = (getattr(err, 'stack', '') or '').splitlines()[1:4]
        self.issues.append('uncaught page error: %s %s' % (text, ' | '.join(s.strip() for s in stack)))

    def _on_response(self, response):
        if response.status < 400 or not self._same_origin(response.url):
            return
        path = self._path(response.url)
        if self._api_allowed(response.status, path):
            return
        method = response.request.method
        kind = 'API' if path.startswith('/api/') else 'resource'
        body = ''
        if kind == 'API':
            try:
                body = response.text()[:300]
            except Exception:  # noqa: BLE001 - body may be gone after navigation
                body = '<body unavailable>'
        self.issues.append('unexpected %s response: %s %s %s  %s' % (kind, response.status, method, path, body))

    def _on_requestfailed(self, request):
        if not self._same_origin(request.url):
            return
        failure = request.failure or ''
        if 'ERR_ABORTED' in failure:  # navigation away / cancelled fetches: not a bug signal
            return
        self.issues.append('request failed: %s %s (%s)' % (request.method, self._path(request.url), failure))

    # -- verdict ---------------------------------------------------------------------------------
    def settle(self):
        """Let in-flight events reach the listeners before judging."""
        for ctx in self.contexts:
            for pg in ctx.pages:
                try:
                    pg.wait_for_timeout(150)
                except Exception:  # noqa: BLE001 - page may be closed
                    pass

    def report(self):
        if not self.issues:
            return ''
        return ('%d unexpected browser error(s):\n  - ' % len(self.issues)) + '\n  - '.join(self.issues) + (
            '\nIf an error is intended, declare it in the test with expect_api_error(status, path_glob) '
            'or expect_console_error(pattern).')


# ------------------------------------------------------------------------------------------------
# pytest wiring
# ------------------------------------------------------------------------------------------------

@pytest.fixture
def guard(request):
    base_url = None
    try:
        base_url = request.getfixturevalue('base_url')
    except pytest.FixtureLookupError:
        pass
    g = ErrorGuard(origin=base_url.rstrip('/') if base_url else None)
    return g


@pytest.fixture
def expect_api_error(guard):
    return guard.expect_api_error


@pytest.fixture
def expect_console_error(guard):
    return guard.expect_console_error


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    g = getattr(item, 'funcargs', {}).get('guard')
    try:
        result = yield
    except BaseException:
        if g is not None:
            g.settle()
            if g.issues:
                item.add_report_section('call', 'e2e-guard', g.report())
        raise
    if g is not None:
        g.settle()
        if g.issues:
            item.add_report_section('call', 'e2e-guard', g.report())
            pytest.fail(g.report(), pytrace=False)
    return result
