"""T07c probe 9: security settings, unknown keys, admin job filters and restart."""
import time

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial


def test_require_activation_toggle(stack, api, server_settings):
    anon = api()
    server_settings.update('security', require_activation=False)
    r = anon.post('/api/auth/register/', json={
        'username': 'probenoact', 'email': 'probenoact@e2e.test', 'full_name': 'No Act',
        'password': 'Probe1234', 'password_confirm': 'Probe1234'})
    print('register with require_activation=false ->', r.status_code, r.text[:200])
    c2 = api()
    try:
        c2.login('probenoact', 'Probe1234')
        print('login straight after register: OK')
    except Exception as exc:
        print('login straight after register: FAILED', exc)
    server_settings.restore()


def test_unknown_keys_preserved(stack, api, server_settings):
    c = api('admin')
    data = stack.read_settings()
    data['custom_future_key'] = {'a': 1}
    data['server']['future_flag'] = 'keep me'
    stack.write_settings(data)
    time.sleep(1.1)
    r = c.put('/api/admin/settings/general/', json={'name': 'Probe Keep'})
    print('PUT ->', r.status_code)
    after = stack.read_settings()
    print('custom_future_key:', after.get('custom_future_key'))
    print('server.future_flag:', after['server'].get('future_flag'))
    server_settings.restore()


def test_admin_job_filters(stack, api, server_settings, requires_worker):
    admin = api('admin')
    alice = api('alice')
    admin.post('/api/admin/queue/pause/')
    ids = []
    try:
        ids.append(alice.submit_job('hello', name='probe-filter-alice',
                                    params={'message': 'a'})['id'])
        ids.append(admin.submit_job('hello', name='probe-filter-admin',
                                    params={'message': 'b'})['id'])
        for q in ('', '?state=waiting', '?state=waiting,running', '?user=alice',
                  '?user=2', '?workflow=hello', '?workflow=nope', '?search=probe-filter-alice',
                  '?search=alice', '?state=success'):
            r = admin.get('/api/admin/jobs/' + q)
            names = [j['name'] for j in r.json().get('results', [])] if r.ok else r.text[:80]
            print('  %-28s -> %s %s' % (q or '(none)', r.status_code, names))
        print('non-admin sees admin jobs?', alice.get('/api/admin/jobs/').status_code)
        # admin cancels alice's waiting job
        r = admin.post('/api/admin/jobs/%s/cancel/' % ids[0])
        print('admin cancel alice waiting job ->', r.status_code, r.json().get('state'))
        print('alice sees:', alice.job_status(ids[0])['state'])
    finally:
        for jid in ids:
            admin.post('/api/admin/jobs/%s/cancel/' % jid)
        admin.post('/api/admin/queue/resume/')


def test_restart_after_disable_and_uninstall(stack, api, server_settings, requires_worker):
    admin = api('admin')
    j = admin.submit_job('fail', name='probe-restart', params={})
    helpers.wait_job_state(admin, j['id'], ('failed',), timeout=180)
    r = admin.post('/api/admin/jobs/%s/restart/' % j['id'])
    print('restart failed job ->', r.status_code, r.json().get('state') if r.ok else r.text[:150])
    helpers.wait_job_state(admin, j['id'], ('failed',), timeout=180)
    admin.patch('/api/admin/workflows/fail/', json={'enabled': False})
    r = admin.post('/api/admin/jobs/%s/restart/' % j['id'])
    print('restart while disabled ->', r.status_code, r.text[:200])
    admin.delete('/api/admin/workflows/fail/')
    r = admin.post('/api/admin/jobs/%s/restart/' % j['id'])
    print('restart after uninstall ->', r.status_code, r.text[:200])
    print('job still readable:', admin.get('/api/jobs/%s' % j['id']).status_code)
    print('dashboard:', admin.get('/api/admin/dashboard/').status_code)
    server_settings.restore()
    time.sleep(1.1)
    admin.get('/api/admin/workflows/')
    admin.delete('/api/jobs/%s/' % j['id'])


def test_navbar_route_that_does_not_exist(stack, api, server_settings, page, login):
    from playwright.sync_api import expect
    c = api('admin')
    c.put('/api/admin/settings/navbar/', json={'navbar': [
        {'title': 'Ghost', 'url': '/this/route/does/not/exist'}]})
    login(page, 'admin')
    page.goto('/')
    titles = [t.strip() for t in page.get_by_test_id('nav-item').all_inner_texts()]
    print('navbar:', titles)
    page.get_by_test_id('nav-item').filter(has_text='Ghost').click()
    page.wait_for_timeout(1500)
    print('url after click:', page.url)
    print('body text:', page.locator('body').inner_text()[:200].replace('\n', ' | '))
    server_settings.restore()
