"""T07b XSS probes in a real browser.

Checks that user-controlled strings (job name, ``::message::`` text from the pipeline,
full name / e-mail of a registered user) are escaped everywhere the SPA shows them, and
documents where HTML *is* rendered on purpose (pages, workflow descriptions, input labels).

    BASE=... venv/bin/python -m e2e.exploratory.probes_xss <CLOUDGENE_HOME>
"""
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

from e2e.constants import USERS
from e2e.exploratory.probe import BASE, Client

PAYLOAD = '<img src=x onerror="window.__xss=(window.__xss||0)+1">'
RESULTS = []


def check(name, ok, evidence=''):
    RESULTS.append((name, ok))
    print('%-5s %-58s %s' % ('PASS' if ok else 'FAIL', name, evidence), flush=True)


def wait(c, job_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = c.get('/api/jobs/%s/status/' % job_id).json()
        if s['state'] in ('success', 'failed', 'cancelled'):
            return s
        time.sleep(1)
    raise SystemExit('timeout')


def login(page, user):
    page.goto(BASE + '/login')
    page.get_by_test_id('login-username').fill(user)
    page.get_by_test_id('login-password').fill(USERS[user]['password'])
    page.get_by_test_id('login-submit').click()
    page.wait_for_url(lambda u: '/login' not in u, timeout=15000)


def main():
    alice = Client(user='alice')
    admin = Client(user='admin')

    # a job whose name and ::message:: text are attacker-controlled
    r = alice.post('/api/jobs/', data={'workflow': 'hello',
                                       'job_name': 'XSS %s' % PAYLOAD, 'message': PAYLOAD})
    job = r.json()
    wait(alice, job['id'])
    msgs = alice.get('/api/jobs/%s/status/' % job['id']).json()['messages']
    print('INFO  pipeline message text:', [m['text'][:90] for m in msgs])

    # an account whose full name is attacker-controlled
    uname = 'xss%s' % uuid.uuid4().hex[:6]
    anon = Client()
    anon.get('/api/auth/me/')
    anon.post('/api/auth/register/', json={
        'username': uname, 'email': '%s@e2e.test' % uname, 'full_name': 'Eve %s' % PAYLOAD,
        'password': 'Passw0rd1', 'password_confirm': 'Passw0rd1'})

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(base_url=BASE)
        page = ctx.new_page()
        login(page, 'alice')
        for url, what in ((BASE + '/jobs', 'job list'),
                          (BASE + '/jobs/' + job['id'], 'job detail')):
            page.goto(url)
            page.wait_for_timeout(1500)
            fired = page.evaluate('window.__xss || 0')
            shown = PAYLOAD in page.content()
            check('xss: job name / message escaped on the %s' % what, fired == 0,
                  'handlers fired=%s, payload rendered as text=%s' % (fired, shown))
        page.goto(BASE + '/jobs/' + job['id'])
        page.wait_for_timeout(1000)
        check('xss: ::message:: from the pipeline escaped',
              page.evaluate('window.__xss || 0') == 0 and 'onerror' in page.content(),
              'text visible, no handler')

        apage = ctx.new_page()
        login(apage, 'admin')
        for url, what in ((BASE + '/admin/users', 'admin users'),
                          (BASE + '/admin/jobs', 'admin jobs')):
            apage.goto(url)
            apage.wait_for_timeout(1500)
            check('xss: user full name / job name escaped on %s' % what,
                  apage.evaluate('window.__xss || 0') == 0,
                  'handlers fired=%s' % apage.evaluate('window.__xss || 0'))

        # documented trust boundary: admin-authored page HTML *is* rendered
        admin.put('/api/admin/pages/t07bprobe/', json={'html': '<b id="t07b">bold</b>'})
        page.goto(BASE + '/pages/t07bprobe')
        page.wait_for_timeout(800)
        rendered = page.locator('#t07b').count() == 1
        check('trust boundary: admin page HTML is rendered (by design)', rendered,
              'rendered=%s' % rendered)
        admin.delete('/api/admin/pages/t07bprobe/')
        browser.close()

    alice.delete('/api/jobs/%s/' % job['id'])
    failed = [n for n, ok in RESULTS if not ok]
    print('\n%d/%d checks passed' % (len(RESULTS) - len(failed), len(RESULTS)))
    for n in failed:
        print('  FAILED:', n)


if __name__ == '__main__':
    main()
