"""T07c probe 7: multi-actor interference, restarts and a broken settings.yaml."""
import json
import os
import signal
import subprocess
import time

import pytest

from e2e import helpers, stack as stack_mod
from e2e.pages import JobPage

pytestmark = pytest.mark.serial


def test_fair_ordering_two_users(stack, api, server_settings, requires_worker):
    """max_running_jobs=1: alice submits 2, bob 1. Nobody may starve; order must be FIFO."""
    alice, bob, admin = api('alice'), api('bob'), api('admin')
    server_settings.update('server', max_running_jobs=1)
    ids = []
    try:
        a1 = alice.submit_job('hello', name='probe-fair-a1', params={'message': '1'})
        a2 = alice.submit_job('hello', name='probe-fair-a2', params={'message': '2'})
        b1 = bob.submit_job('hello', name='probe-fair-b1', params={'message': '3'})
        ids = [a1['id'], a2['id'], b1['id']]
        order = []
        end = time.monotonic() + 240
        seen = set()
        while time.monotonic() < end and len(seen) < 3:
            for jid, who in ((a1['id'], 'alice1'), (a2['id'], 'alice2'), (b1['id'], 'bob1')):
                st = admin.job_status(jid)
                if st['state'] in ('running', 'success') and jid not in seen:
                    seen.add(jid)
                    order.append((who, st['state']))
            time.sleep(0.5)
        print('start order:', order)
        for jid in ids:
            print('  final', jid[:8], admin.job_status(jid)['state'],
                  'queue_position', admin.job_status(jid).get('queue_position'))
    finally:
        for jid in ids:
            admin.post('/api/jobs/%s/cancel/' % jid)
        server_settings.restore()


def test_admin_cancels_while_user_watches(stack, api, page, login, requires_worker):
    """Alice watches her job page; the admin cancels it. Her page must reflect it."""
    alice = api('alice')
    admin = api('admin')
    job = alice.submit_job('slow', name='probe-watch', params={'seconds': 60}) \
        if False else None
    # slow is admin-only; use hello for alice and cancel fast, or let admin submit slow.
    job = admin.submit_job('slow', name='probe-watch', params={'seconds': 60})
    helpers.wait_job_state(admin, job['id'], ('running',), timeout=60)
    login(page, 'admin')
    jp = JobPage(page).open(job['id'])
    jp.expect_state('running', timeout=30_000)
    r = admin.post('/api/admin/jobs/%s/cancel/' % job['id'])
    print('admin cancel ->', r.status_code, r.text[:150])
    jp.expect_state('cancelled', timeout=60_000)
    print('page state after cancel: cancelled')


def test_job_list_pagination_during_churn(stack, api, server_settings, requires_worker):
    admin = api('admin')
    admin.post('/api/admin/queue/pause/')
    ids = []
    try:
        server_settings.update('server', max_queue_size=0)
        for i in range(7):
            ids.append(admin.submit_job('hello', name='probe-page-%02d' % i,
                                        params={'message': str(i)})['id'])
        p1 = admin.get_json('/api/admin/jobs/?page_size=3&page=1')
        ids.append(admin.submit_job('hello', name='probe-page-new',
                                    params={'message': 'n'})['id'])
        p2 = admin.get_json('/api/admin/jobs/?page_size=3&page=2')
        names1 = [j['name'] for j in p1['results']]
        names2 = [j['name'] for j in p2['results']]
        print('page1:', names1, 'count', p1['count'])
        print('page2:', names2, 'count', p2['count'])
        print('overlap:', set(names1) & set(names2))
        print('page_size cap:', len(admin.get_json('/api/admin/jobs/?page_size=1000')['results']))
        bad = admin.get('/api/admin/jobs/?state=bogus')
        print('bad state filter ->', bad.status_code, bad.text[:120])
        print('filter by user:', [j['name'] for j in
                                  admin.get_json('/api/admin/jobs/?user=admin&page_size=50')['results']][:3])
    finally:
        for jid in ids:
            admin.post('/api/jobs/%s/cancel/' % jid)
            admin.delete('/api/jobs/%s/' % jid)
        admin.post('/api/admin/queue/resume/')
        server_settings.restore()


def test_settings_survive_server_restart(stack, api, server_settings):
    c = api('admin')
    c.put('/api/admin/settings/general/', json={'name': 'Probe Restart', 'max_queue_size': 4})
    c.put('/api/admin/settings/navbar/', json={'navbar': [
        {'title': 'Restart Item', 'url': '/'}]})
    c.put('/api/admin/pages/home/', json={'html': '<p>PROBE-RESTART-HOME</p>'})
    proc = stack.procs['server']
    os.killpg(proc.pid, __import__('signal').SIGTERM)
    proc.wait(timeout=20)
    port = stack.base_url.rsplit(':', 1)[1]
    stack._spawn('server', ['runserver', '127.0.0.1:%s' % port, '--noreload', '--insecure'])
    stack.wait_ready()
    c2 = api('admin')
    print('after restart general:', c2.get_json('/api/admin/settings/general/'))
    print('after restart navbar:', [i['title'] for i in api().get_json('/api/server/')['navbar']])
    print('after restart home page:', api().get_json('/api/pages/home/')['html'][:60])
    server_settings.restore()


def test_broken_settings_file(stack, api, server_settings):
    """A hand-broken settings.yaml must not take the site down (SPEC §3.2: keep last valid)."""
    c = api('admin')
    path = stack.settings_path
    good = path.read_text()
    path.write_text('server: [this is not a mapping\n  broken: : :\n')
    time.sleep(1.1)
    for url in ('/api/health', '/api/server/', '/api/workflows/', '/api/admin/dashboard/',
                '/api/admin/settings/general/'):
        r = c.get(url)
        print('  %-32s -> %s %s' % (url, r.status_code, r.text[:110].replace('\n', ' ')))
    r = c.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'x', 'message': 'y'})
    print('  submit -> %s %s' % (r.status_code, r.text[:120]))
    r = c.put('/api/admin/settings/general/', json={'name': 'Recovered'})
    print('  admin save over broken file ->', r.status_code, r.text[:160])
    print('  yaml now:', path.read_text()[:120].replace('\n', ' '))
    # restart the server with a broken file: cold cache
    path.write_text('::: not yaml :::\n')
    proc = stack.procs['server']
    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(timeout=20)
    port = stack.base_url.rsplit(':', 1)[1]
    stack._spawn('server', ['runserver', '127.0.0.1:%s' % port, '--noreload', '--insecure'])
    time.sleep(6)
    for url in ('/api/health', '/api/server/', '/'):
        try:
            r = c.get(url)
            print('  cold %-14s -> %s %s' % (url, r.status_code, r.text[:110].replace('\n', ' ')))
        except Exception as exc:
            print('  cold %-14s -> EXC %r' % (url, exc))
    path.write_text(good)
    time.sleep(1.1)
    print('  after repair /api/server ->', c.get('/api/server/').status_code)
    print('  worker alive:', stack._alive('worker'))
    print('  worker log tail:')
    for line in (stack.log_dir / 'worker.log').read_text(errors='replace').splitlines()[-6:]:
        print('    ', line)
