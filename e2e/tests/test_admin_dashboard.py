"""D1: admin dashboard numbers match the DB; queue pause/resume and maintenance mode from the
dashboard write settings.yaml, and maintenance shows a banner to users.
D2: admin jobs — filter by state/user, cancel another user's job, restart a failed job.
D7: the Logs page shows entries written by the app (admin actions; job failures/logins once
T03/T04 log them through `cloudgene.*` loggers).
"""
import copy

import pytest
from playwright.sync_api import expect

from e2e.admin_helpers import create_jobs, delete_jobs, job_state_counts

pytestmark = pytest.mark.serial


@pytest.fixture
def restore_settings(stack):
    original = copy.deepcopy(stack.read_settings())
    yield
    stack.write_settings(original)


@pytest.fixture
def seeded_jobs(stack):
    ids = create_jobs(stack, [
        ('alice', 'hello', 'failed', 'D-alice failed'),
        ('alice', 'hello', 'success', 'D-alice ok'),
        ('bob', 'hello', 'waiting', 'D-bob waiting'),
        ('admin', 'slow', 'cancelled', 'D-admin cancelled'),
    ])
    yield ids
    delete_jobs(stack, ids)


def test_d1_dashboard_counts_match_db(page, login, stack, seeded_jobs):
    counts = job_state_counts(stack)
    total = sum(counts.values())
    login(page, 'admin')
    page.goto('/admin')
    expect(page.get_by_test_id('count-jobs-total')).to_have_text(str(total))
    expect(page.get_by_test_id('count-jobs-failed')).to_contain_text(str(counts.get('failed', 0)))
    expect(page.get_by_test_id('count-jobs-success')).to_contain_text(str(counts.get('success', 0)))
    expect(page.get_by_test_id('queue-waiting')).to_have_text(str(counts.get('waiting', 0)))
    expect(page.get_by_test_id('count-users-total')).to_have_text('3')
    expect(page.get_by_test_id('count-workflows-enabled')).to_have_text('5')
    expect(page.locator('[data-testid="recent-job"]').filter(has_text='D-bob waiting')).to_have_count(1)
    expect(page.get_by_test_id('worker-status')).to_have_attribute(
        'data-worker', 'ok' if stack.worker_available else 'down')


def test_d1_pause_resume_queue(page, login, stack, restore_settings):
    login(page, 'admin')
    page.goto('/admin')
    page.get_by_test_id('queue-pause').click()
    expect(page.get_by_test_id('queue-state')).to_have_attribute('data-paused', 'true')
    assert stack.read_settings()['queue']['paused'] is True
    page.reload()
    page.get_by_test_id('queue-resume').click()
    expect(page.get_by_test_id('queue-state')).to_have_attribute('data-paused', 'false')
    assert stack.read_settings()['queue']['paused'] is False


def test_d1_maintenance_mode_banner(page, login, user_page, stack, restore_settings):
    login(page, 'admin')
    page.goto('/admin')
    page.get_by_test_id('maintenance-message').fill('E2E maintenance window')
    page.get_by_test_id('maintenance-enter').click()
    expect(page.get_by_test_id('maintenance-state')).to_have_attribute('data-maintenance', 'true')
    expect(page.get_by_test_id('maintenance-banner')).to_contain_text('E2E maintenance window')
    server = stack.read_settings()['server']
    assert (server['maintenance'], server['maintenance_message']) == (True, 'E2E maintenance window')

    alice = user_page('alice')
    alice.goto('/')
    expect(alice.get_by_test_id('maintenance-banner')).to_contain_text('E2E maintenance window')

    page.get_by_test_id('maintenance-exit').click()
    expect(page.get_by_test_id('maintenance-state')).to_have_attribute('data-maintenance', 'false')
    expect(page.get_by_test_id('maintenance-banner')).to_have_count(0)
    alice.reload()
    expect(alice.get_by_test_id('navbar')).to_be_visible()
    expect(alice.get_by_test_id('maintenance-banner')).to_have_count(0)


@pytest.mark.xfail(strict=False, reason='needs T03: GET /api/admin/jobs?state=&user=&workflow=, '
                                        'POST /api/admin/jobs/{id}/cancel|restart (SPEC §3.6)')
def test_d2_admin_jobs_filter_cancel_restart(page, login, stack, seeded_jobs):
    login(page, 'admin')
    page.goto('/admin/jobs')
    rows = page.get_by_test_id('admin-job-row')
    expect(rows.first).to_be_visible()

    page.get_by_test_id('jobs-filter-state').select_option('failed')
    page.get_by_test_id('jobs-filter-user').fill('alice')
    page.get_by_test_id('jobs-filter-apply').click()
    expect(rows.filter(has_text='D-alice failed')).to_have_count(1)
    expect(rows.filter(has_text='D-alice ok')).to_have_count(0)
    for state in rows.evaluate_all('els => els.map(e => e.dataset.state)'):
        assert state == 'failed'

    rows.filter(has_text='D-alice failed').get_by_test_id('admin-job-restart').click()
    page.get_by_test_id('confirm-ok').click()
    expect(page.get_by_test_id('jobs-success')).to_contain_text('restarted')

    page.get_by_test_id('jobs-filter-reset').click()
    page.get_by_test_id('jobs-filter-user').fill('bob')
    page.get_by_test_id('jobs-filter-apply').click()
    bob_row = rows.filter(has_text='D-bob waiting')
    bob_row.get_by_test_id('admin-job-cancel').click()
    page.get_by_test_id('confirm-ok').click()
    expect(bob_row).to_have_attribute('data-state', 'cancelled')


def test_d7_logs_show_admin_actions(page, login, stack, restore_settings):
    login(page, 'admin')
    page.goto('/admin')
    page.get_by_test_id('queue-pause').click()
    expect(page.get_by_test_id('queue-state')).to_have_attribute('data-paused', 'true')
    page.get_by_test_id('queue-resume').click()
    expect(page.get_by_test_id('queue-state')).to_have_attribute('data-paused', 'false')

    page.get_by_test_id('admin-nav-logs').click()
    expect(page.get_by_test_id('logs-table')).to_be_visible()
    page.get_by_test_id('logs-filter-component').fill('admin')
    page.get_by_test_id('logs-filter-apply').click()
    messages = page.get_by_test_id('log-message')
    expect(messages.filter(has_text='Queue paused').first).to_be_visible()
    expect(messages.filter(has_text='Queue resumed').first).to_be_visible()
    row = page.get_by_test_id('log-row').filter(has_text='Queue paused').first
    expect(row).to_have_attribute('data-level', 'info')
    expect(row).to_contain_text('admin')

    page.get_by_test_id('logs-filter-component').fill('')
    page.get_by_test_id('logs-filter-level').select_option('error')
    expect(page.get_by_test_id('log-row').filter(has_text='Queue paused')).to_have_count(0)
