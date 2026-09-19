"""Self-tests of the harness itself: prove the automatic browser guards fail tests.

Runs an inner pytest session (pytester, subprocess) against a fake origin served by
`page.route`, so no Django stack is needed.
"""
import os

from e2e.stack import REPO

# Resolved at import time: pytester later points HOME at a temp dir.
BROWSERS_PATH = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', os.path.expanduser('~/.cache/ms-playwright'))

INNER_CONFTEST = '''
import pytest
pytest_plugins = ['e2e.guards']

@pytest.fixture(scope='session')
def base_url():
    return 'http://guard.test'

@pytest.fixture
def page(context, guard):
    guard.attach(context)
    return context.new_page()
'''

INNER_TESTS = r'''
import re
import pytest

SCRIPTS = {
    'clean': "fetch('/api/ok')",
    'api500': "fetch('/api/boom')",
    'api404': "fetch('/api/missing')",
    'console': "console.error('something broke')",
    'throw': "setTimeout(() => { throw new Error('kaboom') }, 0)",
    'asset404': "var s = document.createElement('script'); s.src = '/static/missing.js'; document.head.appendChild(s)",
}

def serve(route):
    url = route.request.url
    if url.endswith('/api/ok'):
        return route.fulfill(status=200, content_type='application/json', body='{}')
    if url.endswith('/api/boom'):
        return route.fulfill(status=500, content_type='application/json', body='{"error": "boom"}')
    if url.endswith('/api/missing') or url.endswith('/missing.js'):
        return route.fulfill(status=404, content_type='text/plain', body='nope')
    name = url.rsplit('/', 1)[-1]
    route.fulfill(status=200, content_type='text/html',
                  body='<html><body><h1 id="done">%s</h1><script>%s</script></body></html>' % (name, SCRIPTS[name]))

def visit(page, name):
    page.route('http://guard.test/**', serve)
    page.goto('/' + name)
    page.wait_for_timeout(300)

def test_clean_page_passes(page):
    visit(page, 'clean')

def test_api_500_fails(page):
    visit(page, 'api500')

def test_console_error_fails(page):
    visit(page, 'console')

def test_uncaught_exception_fails(page):
    visit(page, 'throw')

def test_asset_404_fails(page):
    visit(page, 'asset404')

def test_declared_api_error_passes(page, expect_api_error):
    expect_api_error(500, '/api/boom')
    visit(page, 'api500')

def test_declared_wrong_status_still_fails(page, expect_api_error):
    expect_api_error(500, '/api/*')
    visit(page, 'api404')

def test_declared_console_error_passes(page, expect_console_error):
    expect_console_error(re.compile('something br[o]ke'))
    visit(page, 'console')

@pytest.mark.xfail(reason='guard failure inside an xfail test counts as xfailed')
def test_guard_failure_respects_xfail(page):
    visit(page, 'api500')
'''


def test_guards_fail_tests_on_browser_errors(pytester):
    pytester.makeconftest(INNER_CONFTEST)
    pytester.makepyfile(test_inner=INNER_TESTS)
    env_path = str(REPO) + os.pathsep + os.environ.get('PYTHONPATH', '')
    pytester._monkeypatch.setenv('PYTHONPATH', env_path)
    pytester._monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', BROWSERS_PATH)
    result = pytester.runpytest_subprocess('-p', 'no:cacheprovider', '-v', timeout=180)
    result.assert_outcomes(passed=3, failed=5, xfailed=1)
    out = result.stdout.str()
    for expected in [
        'test_api_500_fails[chromium] FAILED',
        'unexpected API response: 500 GET /api/boom',
        'console.error: something broke',
        'uncaught page error: Error: kaboom',
        'unexpected resource response: 404 GET /static/missing.js',
        'unexpected API response: 404 GET /api/missing',
        'declare it in the test with expect_api_error',
    ]:
        assert expected in out, expected
