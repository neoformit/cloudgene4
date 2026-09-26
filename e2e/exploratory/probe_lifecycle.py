"""T07a probe 3 — job lifecycle races and finished-job actions (API level, worker running)."""
import time

import pytest

from e2e.exploratory.conftest import brief
from e2e.helpers import wait_job_state

pytestmark = pytest.mark.serial


@pytest.fixture(scope='module')
def alice(stack):
    from e2e.helpers import ApiClient
    c = ApiClient(stack.base_url)
    c.login('alice')
    yield c
    c.close()


@pytest.fixture(scope='module')
def admin(stack):
    from e2e.helpers import ApiClient
    c = ApiClient(stack.base_url)
    c.login('admin')
    yield c
    c.close()


def hello(client, name):
    return client.post('/api/jobs/', data={'workflow': 'hello', 'job_name': name,
                                           'message': 'probe'}).json()


def test_cancel_races(alice, stack, report):
    stack.require_worker()
    job = hello(alice, 'probe-cancel-race')
    r1 = alice.post('/api/jobs/%s/cancel/' % job['id'])
    r2 = alice.post('/api/jobs/%s/cancel/' % job['id'])
    report('cancel #1 (immediately after submit)', brief(r1, 100).split(',')[0])
    report('cancel #1 state', r1.json().get('state') if r1.ok else '-')
    report('cancel #2 (same job)', '%s state=%s' % (r2.status_code, r2.json().get('state')
                                                    if r2.ok else brief(r2, 120)))
    time.sleep(3)
    after = alice.get_json('/api/jobs/%s/status' % job['id'])
    report('state 3 s later', after['state'])
    report('cancel #3 after it is final', brief(alice.post('/api/jobs/%s/cancel/' % job['id']), 150))
    report('delete cancelled job', alice.delete('/api/jobs/%s/' % job['id']).status_code)


def test_delete_guards(alice, stack, report):
    stack.require_worker()
    job = hello(alice, 'probe-delete-guard')
    report('delete while waiting/running', brief(alice.delete('/api/jobs/%s/' % job['id']), 160))
    final = wait_job_state(alice, job['id'], ('success', 'failed'), timeout=120)
    report('final state', final['state'])
    report('delete finished', alice.delete('/api/jobs/%s/' % job['id']).status_code)
    report('GET after delete', alice.get('/api/jobs/%s/' % job['id']).status_code)
    report('cancel after delete', alice.post('/api/jobs/%s/cancel/' % job['id']).status_code)
    report('delete twice', alice.delete('/api/jobs/%s/' % job['id']).status_code)
    report('workspace still there', (stack.home / 'jobs' / job['id']).exists())
    report('job in list', any(j['id'] == job['id'] for j in
                              alice.get_json('/api/jobs/?page_size=200')['results']))


def test_outputs_and_downloads(alice, stack, report):
    stack.require_worker()
    job = hello(alice, 'probe-outputs')
    done = wait_job_state(alice, job['id'], ('success',), timeout=120)
    detail = alice.get_json('/api/jobs/%s/' % job['id'])
    outs = detail['outputs']
    report('outputs', [(o['id'], o['path'], o['size']) for o in outs])
    oid = outs[0]['id']
    r = alice.get(outs[0]['url'])
    report('download', '%s %r %s' % (r.status_code, r.content[:40],
                                     r.headers.get('Content-Disposition')))
    report('download inline', alice.get(outs[0]['url'] + '?inline=1')
           .headers.get('Content-Disposition'))
    report('download count after 2', alice.get_json('/api/jobs/%s/' % job['id'])['outputs'][0]['download_count'])
    report('bogus file id', alice.get('/api/jobs/%s/outputs/999999/' % job['id']).status_code)
    report('negative file id', alice.get('/api/jobs/%s/outputs/-1/' % job['id']).status_code)
    report('other job id + my file id',
           alice.get('/api/jobs/%s/outputs/%s/' % ('00000000-0000-0000-0000-000000000000', oid)).status_code)
    report('log', '%s %r' % (alice.get('/api/jobs/%s/log/' % job['id']).status_code,
                             alice.get('/api/jobs/%s/log/' % job['id']).text[:60]))
    # retention: pretend it finished long ago, then purge
    stack.django_shell(
        "from jobs.models import Job; from django.utils import timezone; from datetime import timedelta;"
        "Job.objects.filter(pk='%s').update(finished_at=timezone.now()-timedelta(days=30))" % job['id'])
    out = stack.manage('cleanup_jobs').stdout.strip()
    report('cleanup_jobs', out.splitlines()[-1] if out else '')
    purged = alice.get_json('/api/jobs/%s/' % job['id'])
    report('after purge: purged_at/outputs/can_restart',
           (bool(purged['purged_at']), purged['outputs'], purged['can_restart']))
    report('download after purge', alice.get('/api/jobs/%s/outputs/%s/' % (job['id'], oid)).status_code)
    report('log after purge', '%s %r' % (alice.get('/api/jobs/%s/log/' % job['id']).status_code,
                                         alice.get('/api/jobs/%s/log/' % job['id']).text[:60]))
    report('delete purged job', alice.delete('/api/jobs/%s/' % job['id']).status_code)


def test_restart_guards(admin, stack, report):
    stack.require_worker()
    job = admin.post('/api/jobs/', data={'workflow': 'fail', 'job_name': 'probe-restart',
                                         'note': 'x'}).json()
    final = wait_job_state(admin, job['id'], ('failed',), timeout=120)
    report('failed', '%s %r' % (final['state'], final.get('error_message', '')[:60]))
    detail = admin.get_json('/api/jobs/%s/' % job['id'])
    report('outputs of a failed job', detail['outputs'])
    report('log has nextflow output', '::error::' in admin.get('/api/jobs/%s/log/' % job['id']).text)
    report('messages', [(m['level'], m['text'][:40]) for m in detail['messages']])
    # disable the workflow, then try to restart
    admin.patch('/api/admin/workflows/fail/', json={'enabled': False})
    time.sleep(1.2)
    report('restart while workflow disabled',
           brief(admin.post('/api/admin/jobs/%s/restart/' % job['id']), 160))
    admin.patch('/api/admin/workflows/fail/', json={'enabled': True})
    time.sleep(1.2)
    r = admin.post('/api/admin/jobs/%s/restart/' % job['id'])
    report('restart after re-enabling', '%s state=%s' % (r.status_code, r.json().get('state')))
    report('double restart (now waiting/running)',
           brief(admin.post('/api/admin/jobs/%s/restart/' % job['id']), 160))
    wait_job_state(admin, job['id'], ('failed',), timeout=120)
    report('restart by a non-admin owner',
           brief(admin.post('/api/jobs/%s/restart/' % job['id']), 100))


def test_submit_while_workflow_disabled(admin, stack, report):
    admin.patch('/api/admin/workflows/hello/', json={'enabled': False})
    time.sleep(1.2)
    try:
        r = admin.post('/api/jobs/', data={'workflow': 'hello', 'message': 'x'})
        report('submit to disabled workflow (admin)', brief(r, 160))
        from e2e.helpers import ApiClient
        c = ApiClient(stack.base_url)
        c.login('alice')
        report('submit to disabled workflow (user)',
               brief(c.post('/api/jobs/', data={'workflow': 'hello', 'message': 'x'}), 160))
        report('workflow visible to user', c.get('/api/workflows/hello/').status_code)
        c.close()
    finally:
        admin.patch('/api/admin/workflows/hello/', json={'enabled': True})
        time.sleep(1.2)
