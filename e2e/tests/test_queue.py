"""Queue & worker (E2E_TEST_PLAN §3, K2):

Q1 max_running_jobs=2: 4 slow jobs → 2 running + 2 waiting (positions 1, 2); cancelling a running
   job lets the oldest waiting job start without any further HTTP request
Q2 queue full → submission rejected with a clear message
Q3 worker killed mid-job and restarted → orphan marked failed, its processes killed, queue continues
Q4 queue paused → new job stays waiting → resumed → runs
Q5 maintenance mode: users can't submit (clear message), admins still can
"""
import os
import signal
import time

import pytest
from playwright.sync_api import expect

from e2e.constants import MAX_RUNNING_JOBS
from e2e.helpers import FINAL_STATES, job_processes, job_state, wait_job_state, wait_no_job_processes
from e2e.pages import JobPage, RunPage


def _queue_position(payload):
    for key in ('queue_position', 'position', 'positionInQueue'):
        if payload.get(key) is not None:
            return int(payload[key])
    return None


def _states(client, job_ids):
    return {jid: client.job_status(jid) for jid in job_ids}


def _wait_for(predicate, timeout, what):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        ok, last = predicate()
        if ok:
            return last
        time.sleep(0.5)
    raise AssertionError('timed out after %ss waiting for %s; last: %s' % (timeout, what, last))


@pytest.fixture
def slow_jobs(api):
    """Submits slow jobs as admin; cancels whatever is still active at teardown."""
    admin = api('admin')
    created = []

    def _submit(n, seconds=60, prefix='Q slow job'):
        ids = []
        for i in range(n):
            job = admin.submit_job('slow', name='%s %d' % (prefix, i + 1), params={'seconds': seconds})
            created.append(job['id'])
            ids.append(job['id'])
        return ids
    yield admin, _submit
    for jid in created:
        try:
            if job_state(admin.job_status(jid)) not in FINAL_STATES:
                admin.cancel_job(jid)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
    for jid in created:
        try:
            wait_job_state(admin, jid, FINAL_STATES, timeout=60)
        except AssertionError:
            pass


@pytest.mark.serial
@pytest.mark.worker
def test_queue_limits_and_advances_after_cancel(stack, requires_worker, slow_jobs, page, login):
    """Q1 (K2)."""
    admin, submit = slow_jobs
    job_ids = submit(4, prefix='Q1 slow job')

    def two_running_two_waiting():
        states = _states(admin, job_ids)
        by_state = {}
        for jid, p in states.items():
            by_state.setdefault(job_state(p), []).append(jid)
        ok = len(by_state.get('running', [])) == MAX_RUNNING_JOBS and len(by_state.get('waiting', [])) == 2
        return ok, states
    states = _wait_for(two_running_two_waiting, 60, '2 running / 2 waiting')

    running = [j for j in job_ids if job_state(states[j]) == 'running']
    waiting = [j for j in job_ids if job_state(states[j]) == 'waiting']
    assert sorted(_queue_position(states[j]) for j in waiting) == [1, 2], states

    # The job page shows the queue position of a waiting job.
    login(page, 'admin')
    first_waiting = min(waiting, key=lambda j: _queue_position(states[j]))
    JobPage(page).open(first_waiting)
    expect(page.get_by_test_id('job-queue-position')).to_contain_text('1')
    page.goto('/')  # leave the job page so its polling can't be what advances the queue

    admin.cancel_job(running[0])
    wait_job_state(admin, running[0], 'cancelled', timeout=30)

    # No HTTP request for a few worker ticks: only the worker may advance the queue.
    time.sleep(5)
    after = _states(admin, job_ids)
    now_running = [j for j in job_ids if job_state(after[j]) == 'running']
    assert len(now_running) == MAX_RUNNING_JOBS, after
    assert first_waiting in now_running, 'oldest waiting job should start first: %s' % after


@pytest.mark.serial
def test_queue_full_rejects_submission(page, login, api, server_settings, expect_api_error):
    """Q2."""
    server_settings.update('queue', paused=True)
    server_settings.update('server', max_queue_size=1)
    alice = api('alice')
    first = alice.submit_job('hello', name='Q2 fills the queue', params={'message': 'x'})
    try:
        login(page, 'alice')
        run = RunPage(page).open('hello')
        run.job_name.fill('Q2 rejected')
        expect_api_error(429, '/api/jobs*')
        run.submit_button.click()
        expect(run.error).to_contain_text('queue is full')
        assert '/run/hello' in page.url
    finally:
        alice.cancel_job(first['id'])


@pytest.mark.serial
@pytest.mark.worker
def test_worker_restart_fails_orphans_and_queue_continues(stack, requires_worker, slow_jobs, api):
    """Q3 (K2): SIGKILL the worker mid-job; after restart the orphan is failed and its Nextflow
    process group killed, and new jobs still run."""
    admin, submit = slow_jobs
    [job_id] = submit(1, seconds=300, prefix='Q3 orphan')
    wait_job_state(admin, job_id, 'running', timeout=120)
    deadline = time.monotonic() + 60
    while not job_processes(job_id) and time.monotonic() < deadline:
        time.sleep(0.5)
    assert job_processes(job_id), 'nextflow did not start'

    worker = stack.procs['worker']
    os.kill(worker.pid, signal.SIGKILL)          # the worker only; Nextflow runs in its own group
    worker.wait(timeout=10)
    assert job_processes(job_id), 'the Nextflow process group must survive a worker crash'
    assert job_state(admin.job_status(job_id)) == 'running'

    stack._spawn('worker', ['run_worker'])
    stack.wait_worker_heartbeat()
    payload = wait_job_state(admin, job_id, 'failed', timeout=30)
    assert 'worker was restarted' in payload['error_message']
    assert wait_no_job_processes(job_id, timeout=20) == []

    alice = api('alice')
    new = alice.submit_job('hello', name='Q3 after restart', params={'message': 'still works'})
    wait_job_state(alice, new['id'], 'success', timeout=150)


@pytest.mark.serial
@pytest.mark.worker
def test_pause_and_resume_queue(page, login, api, server_settings, requires_worker):
    """Q4: settings.yaml `queue.paused` is honoured by the worker without a restart."""
    server_settings.update('queue', paused=True)
    login(page, 'alice')
    run = RunPage(page).open('hello')
    run.job_name.fill('Q4 paused')
    job_id = run.submit()
    job = JobPage(page)
    job.expect_state('waiting')
    expect(job.queue_position).to_be_visible()
    time.sleep(4)                                   # several worker ticks
    alice = api('alice')
    assert job_state(alice.job_status(job_id)) == 'waiting'
    server_settings.update('queue', paused=False)
    job.expect_state('success', timeout=150_000)


@pytest.mark.serial
def test_maintenance_blocks_users_not_admins(page, login, api, server_settings, expect_api_error):
    """Q5: 503 with the configured message for users; admins may still submit."""
    message = 'E2E maintenance: back in 5 minutes'
    server_settings.update('server', maintenance=True, maintenance_message=message)
    server_settings.update('queue', paused=True)       # keep the admin's job from running
    login(page, 'alice')
    run = RunPage(page).open('hello')
    run.job_name.fill('Q5 blocked')
    expect_api_error(503, '/api/jobs*')
    run.submit_button.click()
    expect(run.error).to_contain_text(message)

    admin = api('admin')
    job = admin.submit_job('hello', name='Q5 admin submits', params={'message': 'x'})
    assert job_state(job) == 'waiting'
    admin.cancel_job(job['id'])
