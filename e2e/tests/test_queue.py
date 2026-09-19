"""Q1: the queue is advanced by the worker, not by web requests (K2).

settings.yaml has max_running_jobs = 2. Four slow jobs -> 2 running + 2 waiting (positions 1, 2).
Cancelling a running job must let a waiting job start without any further HTTP request.
"""
import time

import pytest
from playwright.sync_api import expect

from e2e.constants import MAX_RUNNING_JOBS
from e2e.helpers import FINAL_STATES, job_state, wait_job_state
from e2e.pages import JobPage


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

    def _submit(n, seconds=60):
        for i in range(n):
            job = admin.submit_job('slow', name='Q1 slow job %d' % (i + 1), params={'seconds': seconds})
            created.append(job['id'])
        return list(created)
    yield admin, _submit
    for jid in created:
        try:
            if job_state(admin.job_status(jid)) not in FINAL_STATES:
                admin.cancel_job(jid)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass


@pytest.mark.serial
@pytest.mark.worker
@pytest.mark.xfail(strict=False, reason='needs T03: run_worker scheduling with max_running_jobs, '
                                        'queue positions, cancel via /api/jobs/{id}/cancel (K2)')
def test_queue_limits_and_advances_after_cancel(stack, requires_worker, slow_jobs, page, login):
    admin, submit = slow_jobs
    job_ids = submit(4)

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
    wait_job_state(admin, running[0], 'cancelled', timeout=15)

    # No HTTP request for a few worker ticks: only the worker may advance the queue.
    time.sleep(5)
    after = _states(admin, job_ids)
    now_running = [j for j in job_ids if job_state(after[j]) == 'running']
    assert len(now_running) == MAX_RUNNING_JOBS, after
    assert first_waiting in now_running, 'oldest waiting job should start first: %s' % after
