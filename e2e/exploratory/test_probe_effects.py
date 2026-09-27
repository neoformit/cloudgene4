"""T07c probe 2: do the saved settings actually take effect?"""
import json
import os
import time
from pathlib import Path

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial


def _wait(pred, timeout=30, what='condition'):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = pred()
        if last:
            return last
        time.sleep(0.3)
    return last


def test_max_queue_size_rejects(stack, api, server_settings, requires_worker):
    c = api('admin')
    server_settings.update('queue', paused=True)
    server_settings.update('server', max_queue_size=1)
    ids = []
    try:
        j1 = c.submit_job('hello', name='probe-qsize-1', params={'message': 'a'})
        ids.append(j1['id'])
        r = c.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'probe-qsize-2',
                                       'message': 'b'})
        print('second submit ->', r.status_code, r.text[:200])
        # unlimited
        server_settings.update('server', max_queue_size=0)
        r2 = c.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'probe-qsize-3',
                                        'message': 'c'})
        print('with max_queue_size=0 ->', r2.status_code, r2.text[:120])
        if r2.status_code < 300:
            ids.append(r2.json()['id'])
    finally:
        for jid in ids:
            c.post('/api/jobs/%s/cancel/' % jid)
        server_settings.restore()


def test_max_upload_mb_rejects(stack, api, server_settings, tmp_path):
    c = api('alice')
    big = tmp_path / 'big.csv'
    big.write_bytes(b'a,b\n' + b'x' * (2 * 1024 * 1024))
    server_settings.update('server', max_upload_mb=1)
    with open(big, 'rb') as fh:
        r = c.post('/api/jobs/', data={'workflow': 'all-inputs', 'job_name': 'probe-upload',
                                       'text_in': 't', 'number_in': '5', 'terms': 'true'},
                   files=[('data_file', ('big.csv', fh))])
    print('2MB upload with max_upload_mb=1 ->', r.status_code, r.text[:200])
    server_settings.restore()


def test_max_running_jobs_concurrency(stack, api, server_settings, requires_worker):
    """max_running_jobs=1 must limit the worker; raising it must take effect without restart."""
    c = api('admin')
    server_settings.update('server', max_running_jobs=1)
    ids = []
    try:
        for i in range(3):
            j = c.submit_job('slow', name='probe-conc-%d' % i, params={'seconds': 40})
            ids.append(j['id'])
        time.sleep(8)
        states = {jid: c.job_status(jid)['state'] for jid in ids}
        print('with max_running_jobs=1:', states)
        running = [s for s in states.values() if s == 'running']
        print('running count =', len(running))
        server_settings.update('server', max_running_jobs=3)
        time.sleep(6)
        states2 = {jid: c.job_status(jid)['state'] for jid in ids}
        print('after raising to 3:', states2)
        print('running count =', sum(1 for s in states2.values() if s == 'running'))
    finally:
        for jid in ids:
            c.post('/api/jobs/%s/cancel/' % jid)
        server_settings.restore()
        time.sleep(2)


def test_pause_and_maintenance_live(stack, api, server_settings, requires_worker):
    c = api('admin')
    alice = api('alice')
    print('pause ->', c.post('/api/admin/queue/pause/').status_code)
    j = c.submit_job('hello', name='probe-paused', params={'message': 'x'})
    time.sleep(4)
    print('state while paused:', c.job_status(j['id'])['state'])
    print('resume ->', c.post('/api/admin/queue/resume/').status_code)
    st = _wait(lambda: c.job_status(j['id'])['state'] in ('running', 'success'), 25)
    print('state after resume:', c.job_status(j['id'])['state'])
    helpers.wait_job_state(c, j['id'], ('success',), timeout=90)

    r = c.post('/api/admin/maintenance/enter/', json={'message': 'probe maintenance'})
    print('maintenance enter ->', r.status_code)
    r = alice.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'probe-maint',
                                       'message': 'x'})
    print('alice submit during maintenance ->', r.status_code, r.text[:150])
    r = c.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'probe-maint-admin',
                                   'message': 'x'})
    print('admin submit during maintenance ->', r.status_code, r.text[:120])
    if r.status_code < 300:
        c.post('/api/jobs/%s/cancel/' % r.json()['id'])
    print('public /api/server maintenance:', api().get_json('/api/server/')['maintenance'])
    print('maintenance exit ->', c.post('/api/admin/maintenance/exit/').status_code)
    server_settings.restore()


def test_mail_settings_used_by_activation(stack, api, server_settings):
    c = api('admin')
    c.put('/api/admin/settings/mail/', json={'from_email': 'probe-sender@e2e.test'})
    anon = api()
    r = anon.post('/api/auth/register/', json={
        'username': 'probemailer', 'email': 'probemailer@e2e.test',
        'full_name': 'Probe Mailer', 'password': 'Probe1234',
        'password_confirm': 'Probe1234'})
    print('register ->', r.status_code, r.text[:200])
    msg = helpers.latest_email(stack.outbox_dir, to='probemailer@e2e.test')
    print('From:', msg['From'] if msg else None)
    print('Subject:', msg['Subject'] if msg else None)
    r = c.post('/api/admin/settings/mail/test/', json={'to': 'probe-test@e2e.test'})
    print('test mail ->', r.status_code, r.text[:200])
    m2 = helpers.latest_email(stack.outbox_dir, to='probe-test@e2e.test')
    print('test mail From:', m2['From'] if m2 else None)
    server_settings.restore()


def test_mail_file_path_setting(stack, api, server_settings):
    c = api('admin')
    c.put('/api/admin/settings/mail/', json={'file_path': 'mail-probe'})
    r = c.post('/api/admin/settings/mail/test/', json={'to': 'probe-path@e2e.test'})
    print('test mail ->', r.status_code, r.text[:160])
    alt = stack.home / 'mail-probe'
    print('alt outbox exists:', alt.exists(), 'files:', list(alt.glob('*')) if alt.exists() else [])
    server_settings.restore()


def test_job_retention_cleanup(stack, api, server_settings, requires_worker):
    c = api('admin')
    j = c.submit_job('hello', name='probe-retention', params={'message': 'r'})
    helpers.wait_job_state(c, j['id'], ('success',), timeout=120)
    workspace = stack.home / 'jobs' / j['id']
    print('workspace exists:', workspace.exists())
    stack.django_shell(
        "from jobs.models import Job; from django.utils import timezone; "
        "from datetime import timedelta; "
        "Job.objects.filter(pk='%s').update(finished_at=timezone.now()-timedelta(days=30))" % j['id'])
    server_settings.update('server', job_retention_days=0)
    out = stack.manage('cleanup_jobs', check=False)
    print('cleanup with retention 0 ->', out.returncode, out.stdout[-400:], out.stderr[-300:])
    print('workspace exists:', workspace.exists())
    server_settings.update('server', job_retention_days=1)
    out = stack.manage('cleanup_jobs', check=False)
    print('cleanup with retention 1 ->', out.returncode, out.stdout[-400:], out.stderr[-300:])
    print('workspace exists:', workspace.exists())
    detail = c.get_json('/api/jobs/%s' % j['id'])
    print('expires_at:', detail.get('expires_at'), 'purged_at:', detail.get('purged_at'))
    server_settings.restore()
