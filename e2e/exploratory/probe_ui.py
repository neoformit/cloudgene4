"""T07a probe 4 — run form and job page in the browser."""
import re
import time

import pytest

from e2e.pages import JobPage, RunPage

pytestmark = pytest.mark.serial

XSS_NAME = '<img src=x onerror="window.__xss=1">A&B'


def submit_hello(page, name, message='ui probe'):
    run = RunPage(page).open('hello')
    run.job_name.fill(name)
    run.fill('message', message)
    return run.submit()


def test_xss_job_name(page, login, api, report):
    client = api('alice')
    job = client.post('/api/jobs/', data={'workflow': 'hello', 'job_name': XSS_NAME,
                                          'message': 'x'}).json()
    login(page, 'alice')
    for url in ('/jobs', '/jobs/%s' % job['id']):
        page.goto(url)
        page.wait_for_timeout(1200)
        report('%s window.__xss' % url, page.evaluate('window.__xss'))
        report('%s img count' % url, page.locator('img[src="x"]').count())
        report('%s text present' % url, XSS_NAME in page.content() or
               '&lt;img src=x' in page.content())
    # the confirm dialog renders its message with v-html
    page.goto('/jobs/%s' % job['id'])
    page.wait_for_timeout(800)
    if page.get_by_test_id('job-cancel').count():
        page.get_by_test_id('job-cancel').click()
        page.wait_for_timeout(500)
        report('confirm dialog window.__xss', page.evaluate('window.__xss'))
        report('confirm dialog body', page.locator('.modal-body').inner_text()[:80])
    client.post('/api/jobs/%s/cancel/' % job['id'])


def test_xss_job_name_admin(page, login, api, report):
    client = api('alice')
    job = client.post('/api/jobs/', data={'workflow': 'hello', 'job_name': XSS_NAME,
                                          'message': 'x'}).json()
    login(page, 'admin')
    page.goto('/admin/jobs')
    page.wait_for_timeout(1500)
    report('admin jobs window.__xss', page.evaluate('window.__xss'))
    report('admin jobs img count', page.locator('img[src="x"]').count())
    client.post('/api/jobs/%s/cancel/' % job['id'])


def test_double_click_submit(page, login, api, report):
    login(page, 'alice')
    client = api('alice')
    before = client.get_json('/api/jobs/?page_size=200')['count']
    page.goto('/run/hello')
    page.get_by_test_id('job-name').fill('probe-double-click')
    page.get_by_test_id('input-message').locator('input, textarea').fill('dbl')
    page.get_by_test_id('job-submit').dblclick()
    page.wait_for_timeout(4000)
    after = client.get_json('/api/jobs/?page_size=200')
    made = [j for j in after['results'] if j['name'] == 'probe-double-click']
    report('jobs created by a double click', len(made))
    report('count before/after', (before, after['count']))
    for j in made:
        client.post('/api/jobs/%s/cancel/' % j['id'])


def test_back_button_resubmit(page, login, api, report):
    login(page, 'alice')
    client = api('alice')
    job_id = submit_hello(page, 'probe-back-1')
    page.go_back()
    page.wait_for_timeout(1500)
    report('url after back', page.url)
    report('job name field after back', page.get_by_test_id('job-name').input_value()
           if page.get_by_test_id('job-name').count() else '<no form>')
    if page.get_by_test_id('job-submit').count():
        page.get_by_test_id('job-submit').click()
        page.wait_for_timeout(3000)
        report('url after resubmit', page.url)
    jobs = client.get_json('/api/jobs/?page_size=200')['results']
    report('jobs named probe-back-1', len([j for j in jobs if j['name'] == 'probe-back-1']))
    for j in jobs:
        if j['state'] in ('waiting', 'running'):
            client.post('/api/jobs/%s/cancel/' % j['id'])


def test_polling_stops_when_finished(page, login, api, stack, report):
    stack.require_worker()
    login(page, 'alice')
    calls = []
    page.on('request', lambda r: calls.append((time.monotonic(), r.url)) if '/status' in r.url else None)
    job_id = submit_hello(page, 'probe-poll')
    deadline = time.monotonic() + 150
    state = None
    while time.monotonic() < deadline:
        state = page.get_by_test_id('job-state').get_attribute('data-state')
        if state in ('success', 'failed', 'cancelled'):
            break
        page.wait_for_timeout(1000)
    report('final state in UI', state)
    n_at_finish = len(calls)
    page.wait_for_timeout(12000)
    report('status polls after the job finished', len(calls) - n_at_finish)
    report('total status polls', len(calls))
    report('badge matches API', (state, api('alice').job_status(job_id)['state']))


def test_two_tabs_and_reload(page, login, user_page, api, stack, report):
    stack.require_worker()
    client = api('admin')
    job = client.post('/api/jobs/', data={'workflow': 'slow', 'job_name': 'probe-two-tabs',
                                          'seconds': '60'}).json()
    from e2e.helpers import wait_job_state
    wait_job_state(client, job['id'], ('running',), timeout=90)
    login(page, 'admin')
    tab2 = user_page('admin')
    page.goto('/jobs/%s' % job['id'])
    tab2.goto('/jobs/%s' % job['id'])
    page.wait_for_timeout(1500)
    report('tab1 state', page.get_by_test_id('job-state').get_attribute('data-state'))
    report('tab2 state', tab2.get_by_test_id('job-state').get_attribute('data-state'))
    JobPage(page).cancel()
    page.wait_for_timeout(20000)
    report('tab1 after cancel', page.get_by_test_id('job-state').get_attribute('data-state'))
    report('tab2 after cancel (no reload)', tab2.get_by_test_id('job-state').get_attribute('data-state'))
    tab2.reload()
    tab2.wait_for_timeout(1500)
    report('tab2 after reload', tab2.get_by_test_id('job-state').get_attribute('data-state'))
    report('cancel button still there in tab2', tab2.get_by_test_id('job-cancel').count())
    tab2.close()


def test_many_files_in_folder_input(page, login, tmp_path, expect_api_error, expect_console_error, report):
    expect_api_error(None, '/api/jobs*')
    expect_console_error(re.compile('.'))
    login(page, 'alice')
    files = []
    for i in range(120):
        p = tmp_path / ('f%03d.txt' % i)
        p.write_text('x')
        files.append(str(p))
    csv = tmp_path / 'data.csv'
    csv.write_text('a,b\n1,2\n')
    run = RunPage(page).open('all-inputs')
    run.job_name.fill('probe-many-files')
    run.set_files('data_file', [csv])
    run.set_files('data_folder', files)
    run.set_checked('terms', True)
    run.submit_button.click()
    page.wait_for_timeout(8000)
    report('url', page.url)
    report('run-error shown', page.get_by_test_id('run-error').inner_text()[:200]
           if page.get_by_test_id('run-error').count() else '<none>')
