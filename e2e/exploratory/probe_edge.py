"""T07a probe 5 — remaining edges: oversized fields, duplicated messages, list filters, NUL bytes."""
import copy
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


def test_oversized_non_file_field(alice, report):
    """Django DATA_UPLOAD_MAX_MEMORY_SIZE (10 MB here) applies to non-file multipart fields."""
    for size, label in ((5 * 1024 * 1024, '5 MB text field'), (11 * 1024 * 1024, '11 MB text field')):
        r = alice.post('/api/jobs/', data={'workflow': 'hello', 'message': 'x' * size})
        report(label, brief(r, 160))
    r = alice.post('/api/jobs/', json={'workflow': 'hello', 'message': 'x' * (11 * 1024 * 1024)})
    report('11 MB JSON body', brief(r, 160))


def test_list_filters(alice, report):
    report('state=bogus', brief(alice.get('/api/jobs/?state=bogus'), 160))
    report('state=success,waiting', alice.get('/api/jobs/?state=success,waiting').status_code)
    report('state=success,bogus', brief(alice.get('/api/jobs/?state=success,bogus'), 120))
    report('state= (empty)', alice.get('/api/jobs/?state=').status_code)
    report('page_size=99999', len(alice.get_json('/api/jobs/?page_size=99999')['results']))
    report('page=99999', alice.get('/api/jobs/?page=99999').status_code)
    report('page=abc', alice.get('/api/jobs/?page=abc').status_code)
    report('non-uuid job id', alice.get('/api/jobs/not-a-uuid/').status_code)
    report('uuid-shaped but unknown',
           alice.get('/api/jobs/11111111-1111-1111-1111-111111111111/').status_code)
    report('admin endpoint as user', alice.get('/api/admin/jobs/').status_code)


def test_nul_byte_runs_through_nextflow(alice, stack, report):
    stack.require_worker()
    job = alice.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'probe-nul',
                                         'message': 'before\x00after'}).json()
    final = wait_job_state(alice, job['id'], ('success', 'failed'), timeout=180)
    report('state', final['state'])
    report('error', (final.get('error_message') or '')[:120])
    detail = alice.get_json('/api/jobs/%s/' % job['id'])
    if detail['outputs']:
        r = alice.get(detail['outputs'][0]['url'])
        report('output bytes', r.content[:40])
    else:
        report('outputs', [])
        report('log tail', alice.get('/api/jobs/%s/log/' % job['id']).text[-300:])


def test_duplicate_error_messages(admin, stack, report):
    stack.require_worker()
    job = admin.post('/api/jobs/', data={'workflow': 'fail', 'job_name': 'probe-dup',
                                         'note': 'x'}).json()
    wait_job_state(admin, job['id'], ('failed',), timeout=180)
    detail = admin.get_json('/api/jobs/%s/' % job['id'])
    msgs = [(m['level'], m['text']) for m in detail['messages']]
    report('messages', msgs)
    report('"Intentional failure" message rows',
           sum(1 for _, t in msgs if t.strip() == 'Intentional failure'))
    stdout = (stack.home / 'jobs' / job['id'] / 'logs' / 'stdout.txt').read_text(errors='replace')
    report('"::error::Intentional failure" lines in stdout.txt',
           sum(1 for ln in stdout.splitlines() if ln.strip() == '::error::Intentional failure'))
    report('any occurrence in stdout.txt', stdout.count('Intentional failure'))
    work = stack.home / 'jobs' / job['id'] / 'work'
    outs = list(work.rglob('.command.out')) if work.exists() else []
    report('.command.out files', [(p.parent.name[:8], p.read_text(errors='replace').count('Intentional failure'))
                                  for p in outs])


def test_queue_position_and_elapsed(admin, stack, report):
    """A waiting job: queue_position, duration_seconds and expires_at."""
    settings = copy.deepcopy(stack.read_settings())
    original = copy.deepcopy(settings)
    settings['queue']['paused'] = True
    stack.write_settings(settings)
    time.sleep(1.5)
    try:
        ids = [admin.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'probe-q%d' % i,
                                              'message': 'x'}).json()['id'] for i in range(3)]
        rows = {j['id']: j for j in admin.get_json('/api/jobs/?state=waiting&page_size=100')['results']}
        report('queue positions', [rows[i]['queue_position'] for i in ids])
        report('duration_seconds while waiting', [rows[i]['duration_seconds'] for i in ids])
        report('expires_at while waiting', [rows[i]['expires_at'] for i in ids])
        report('can_cancel/can_delete', [(rows[i]['can_cancel'], rows[i]['can_delete']) for i in ids])
        admin.post('/api/jobs/%s/cancel/' % ids[0])
        rows = {j['id']: j for j in admin.get_json('/api/jobs/?state=waiting&page_size=100')['results']}
        report('positions after cancelling #1', [rows.get(i, {}).get('queue_position') for i in ids])
        for i in ids[1:]:
            admin.post('/api/jobs/%s/cancel/' % i)
    finally:
        stack.write_settings(original)
        time.sleep(1.5)
