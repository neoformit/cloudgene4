"""T07a probe 7 — SQLite write contention: does a normal page hit return 500?

`GET /api/admin/workflows/` runs `workflows.registry.sync_all()` (writes `Workflow` rows)
inside the request, while the worker writes a heartbeat and job progress every ~1 s.
One such request already returned `OperationalError: database is locked` -> 500 during the
UI probe; this probe tries to reproduce it deterministically.
"""
import concurrent.futures as cf
import time

import pytest

from e2e.helpers import wait_job_state

pytestmark = pytest.mark.serial


@pytest.fixture(scope='module')
def admin(stack):
    from e2e.helpers import ApiClient
    c = ApiClient(stack.base_url)
    c.login('admin')
    yield c
    c.close()


def _client(stack, user):
    from e2e.helpers import ApiClient
    c = ApiClient(stack.base_url)
    c.login(user)
    return c


def test_concurrent_requests_while_jobs_run(admin, stack, report):
    stack.require_worker()
    jobs = [admin.post('/api/jobs/', data={'workflow': 'multi-process',
                                           'job_name': 'probe-lock-%d' % i,
                                           'tasks': '5'}).json() for i in range(2)]
    wait_job_state(admin, jobs[0]['id'], ('running',), timeout=120)

    paths = ['/api/admin/workflows/', '/api/admin/dashboard/', '/api/jobs/',
             '/api/jobs/%s/status' % jobs[0]['id'], '/api/workflows/']
    clients = [_client(stack, 'admin') for _ in range(5)]
    results = []
    deadline = time.monotonic() + 25

    def hammer(client, path):
        out = []
        while time.monotonic() < deadline:
            try:
                r = client.get(path)
                out.append((path, r.status_code, r.text[:120] if r.status_code >= 400 else ''))
            except Exception as exc:  # noqa: BLE001
                out.append((path, 'EXC', repr(exc)[:120]))
            time.sleep(0.15)
        return out

    with cf.ThreadPoolExecutor(max_workers=len(paths)) as pool:
        futures = [pool.submit(hammer, clients[i], paths[i]) for i in range(len(paths))]
        for f in futures:
            results += f.result()
    for c in clients:
        c.close()

    total = len(results)
    bad = [r for r in results if r[1] == 'EXC' or (isinstance(r[1], int) and r[1] >= 500)]
    report('requests issued', total)
    report('5xx / exceptions', len(bad))
    for path, code, body in bad[:8]:
        report('  %s' % path, '%s %s' % (code, body))
    log = (stack.log_dir / 'server.log').read_text(errors='replace')
    report('"database is locked" in server.log', log.count('database is locked'))
    report('"Internal Server Error" in server.log', log.count('Internal Server Error'))
    for j in jobs:
        admin.post('/api/jobs/%s/cancel/' % j['id'])
