"""Cloudgene 3 ``type: command`` steps (T10), with a tiny Taxodactyl-shaped fixture app:

C1 run form shows `details`, a `help` link and `accept` on the file input
C2 Nextflow step + command steps run in order; steps with `stdout: true` show their output on the
   job page (a `bash: true` pipeline included), unflagged output stays hidden; a value with shell
   metacharacters reaches the script literally; `reports.zip` written by a command step is downloadable
C3 a failing command step fails the job with its exit code (its unflagged stderr stays hidden)
   and later steps do not run
C4 cancelling during a long command step stops it (and its children)
"""
import time
from pathlib import Path
import zipfile

import pytest
from playwright.sync_api import expect

from e2e.helpers import job_state, wait_job_state, wait_no_job_processes
from e2e.pages import JobPage, RunPage

TRICKY = 'sample; $(touch /tmp/cg-e2e-pwned) `id` "q" \'s\''


def _cleanup(client, job_id):
    try:
        if job_state(client.job_status(job_id)) in ('waiting', 'running'):
            client.cancel_job(job_id)
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass


def test_run_form_shows_details_help_and_accept(page, login):
    """C1"""
    login(page, 'alice')
    run = RunPage(page).open('command-steps')
    label = page.get_by_test_id('input-label')
    expect(label).to_contain_text('never through a shell')
    help_link = label.locator('a[title="Help"]')
    expect(help_link).to_have_attribute('href', 'https://example.org/command-steps/help.html')
    seq = page.get_by_test_id('input-sequences')
    expect(seq.locator('input[type=file]')).to_have_attribute('accept', '.fasta, .fa')
    expect(seq).to_contain_text('Only .fasta / .fa files are accepted.')
    expect(seq.locator('a[title="Help"]')).to_have_attribute('href', 'https://example.org/command-steps/example.fasta')
    assert run.field('sequences') is not None


@pytest.mark.worker
def test_command_steps_run_and_show_output(page, login, api, requires_worker):
    """C2"""
    login(page, 'alice')
    run = RunPage(page).open('command-steps')
    run.job_name.fill('C2 command steps')
    run.fill('label', TRICKY)
    job_id = run.submit()
    job = JobPage(page)
    job.expect_state('success', timeout=150_000)

    alice = api('alice')
    detail = alice.get_job(job_id)
    assert [s['state'] for s in detail['steps']] == ['success'] * 5
    assert [s['name'] for s in detail['steps']][1] == 'Show retrieved secrets'
    texts = [m['text'] for m in detail['messages']]
    assert 'Vault: key-a\nVault: key-b' in texts                       # bash: true pipeline over $outdir/run.log
    assert any(t.startswith('collect_errors: dir=outdir label=[%s]' % TRICKY) for t in texts), texts
    assert 'collect_errors: 0 error lines' in ' '.join(texts)
    assert 'zip_reports: wrote reports.zip' in texts
    assert not any('quiet step done' in t for t in texts)              # stdout: false -> hidden
    warnings = [m['text'] for m in detail['messages'] if m['level'] == 'warning']
    assert 'collect_errors: note on stderr' in warnings
    assert not Path('/tmp/cg-e2e-pwned').exists()

    # the same output on the job page
    expect(job.messages('info').filter(has_text='Vault: key-a')).to_have_count(1)
    expect(job.messages('info').filter(has_text='collect_errors: dir=outdir')).to_have_count(1)
    expect(job.messages('warning').filter(has_text='note on stderr')).to_have_count(1)
    expect(page.get_by_test_id('job-step')).to_have_count(5)
    assert 'Vault: key-a' in job.open_logs().inner_text()

    job.open_results()
    link = page.locator('[data-testid="job-output-link"][data-filename$="reports.zip"]')
    expect(link).to_be_visible()
    with page.expect_download() as download_info:
        link.click()
    with zipfile.ZipFile(download_info.value.path()) as z:
        assert sorted(z.namelist()) == ['result.txt', 'run.log']
        assert z.read('result.txt').decode() == 'analyst=alice@e2e.test\n'
    expect(page.locator('[data-testid="job-output-link"][data-filename$="run.log"]')).to_be_visible()


@pytest.mark.worker
def test_failing_command_step_fails_the_job(page, login, api, requires_worker):
    """C3"""
    alice = api('alice')
    job_id = alice.submit_job('command-steps', name='C3 fail', params={'label': 'x', 'mode': 'fail'})['id']
    try:
        wait_job_state(alice, job_id, 'failed', timeout=150)
        login(page, 'alice')
        job = JobPage(page).open(job_id)
        job.expect_state('failed')
        expect(job.messages('error').filter(has_text='failed (exit code 7)')).not_to_have_count(0)
        expect(job.messages().filter(has_text='about to fail')).to_have_count(0)   # stderr: false -> hidden
        detail = alice.get_job(job_id)
        assert [s['state'] for s in detail['steps']] == ['success', 'success', 'success', 'failed', 'cancelled']
        assert 'failed (exit code 7)' in detail['error_message']
        assert not any('zip_reports' in m['text'] for m in detail['messages'])
        assert 'about to fail' not in str(detail)
        assert 'about to fail' not in alice.get('/api/jobs/%s/log' % job_id).text
    finally:
        _cleanup(alice, job_id)


@pytest.mark.worker
def test_cancel_during_long_command_step(page, login, api, requires_worker):
    """C4"""
    alice = api('alice')
    job_id = alice.submit_job('command-steps', name='C4 cancel',
                              params={'label': 'x', 'mode': 'sleep', 'sleep': 300})['id']
    try:
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            steps = alice.job_status(job_id)['steps']
            if len(steps) >= 4 and steps[3]['state'] == 'running':
                break
            time.sleep(0.5)
        else:
            pytest.fail('the long command step never started')
        login(page, 'alice')
        job = JobPage(page).open(job_id)
        started = time.monotonic()
        job.cancel()
        job.expect_state('cancelled', timeout=30_000)
        assert time.monotonic() - started < 30
        assert wait_no_job_processes(job_id, timeout=20) == []
        assert [s['state'] for s in alice.get_job(job_id)['steps']][3:] == ['cancelled', 'cancelled']
    finally:
        _cleanup(alice, job_id)
