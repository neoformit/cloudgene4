"""Job lifecycle through the UI (E2E_TEST_PLAN §3):

J1 submit `hello` with a job name containing spaces & unicode (K3) → success → download output
J2 all-inputs: file upload with spaces/unicode name, folder (multi-file), textarea writeFile
J4 live progress of a multi-process job (per-process task counts, ::message::) without reload
J5 failing workflow: state failed, ::error:: shown, Logs tab has the Nextflow log
J6 cancel a running job from the job page: cancelled quickly, no process left
J7 cancel a waiting job from the job list; delete a finished job
"""
import json
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from e2e.helpers import FINAL_STATES, job_state, wait_job_state, wait_no_job_processes
from e2e.pages import JobPage, RunPage

FILES = Path(__file__).resolve().parent.parent / 'fixtures' / 'files'
JOB_NAME = 'My first run  with spaces – ünïcödé 🚀'
MESSAGE = 'Grüße "quoted" it\'s $HOME `x` 🚀'


def _cancel_if_active(client, job_id):
    try:
        if job_state(client.job_status(job_id)) not in FINAL_STATES:
            client.cancel_job(job_id)
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass


@pytest.mark.worker
def test_submit_hello_with_unicode_job_name(page, login, stack, api):
    """J1 (K3)."""
    login(page, 'alice')
    run = RunPage(page).open('hello')
    run.job_name.fill(JOB_NAME)
    run.fill('message', MESSAGE)
    job_id = run.submit()

    job = JobPage(page)
    expect(job.title).to_have_text(JOB_NAME)
    alice = api('alice')
    # The API stores the name verbatim too (no `_` substitution, no trimming of inner spaces).
    assert alice.get_job(job_id)['name'] == JOB_NAME

    stack.require_worker()  # everything below needs the worker to run Nextflow
    job.expect_state('waiting', 'running', 'success', timeout=10_000)
    job.expect_state('success', timeout=120_000)  # page updates itself (polling), no reload
    assert job_state(alice.job_status(job_id)) == 'success'
    expect(job.messages('info').filter(has_text='Hello from the hello fixture')).to_have_count(1)

    job.open_results()
    link = page.locator('[data-testid="job-output-link"][data-filename$="hello.txt"]')
    expect(link).to_be_visible()
    with page.expect_download() as download_info:
        link.click()
    download = download_info.value
    assert download.suggested_filename.endswith('hello.txt')
    assert Path(download.path()).read_text(encoding='utf-8') == MESSAGE + '\n'


@pytest.mark.worker
def test_all_inputs_uploads_folder_and_write_file(page, login, api, requires_worker):
    """J2: files arrive in the workspace, params.json is typed, outputs downloadable."""
    login(page, 'alice')
    run = RunPage(page).open('all-inputs')
    run.job_name.fill('J2 uploads')
    run.fill('text_in', 'some text')
    run.fill('number_in', '7')
    run.field('notes').fill('line one\nline two ü')
    run.set_files('data_file', [FILES / 'my data ü.csv'])
    run.set_files('data_folder', [FILES / 'folder' / 'a.txt', FILES / 'folder' / 'b.txt'])
    run.set_checked('flag', False)
    run.set_checked('terms', True)
    job_id = run.submit()

    job = JobPage(page)
    job.expect_state('success', timeout=150_000)
    alice = api('alice')
    detail = alice.get_job(job_id)
    inputs = {i['id']: i for i in detail['inputs']}
    assert inputs['data_file']['value'] == 'my data ü.csv'
    assert sorted(f['name'] for f in inputs['data_folder']['files']) == ['a.txt', 'b.txt']

    outputs = {o['name']: o for o in detail['outputs']}
    received = json.loads(alice.get(outputs['params-received.json']['url']).content)
    files = json.loads(alice.get(outputs['files-received.json']['url']).content)
    assert received['text_in'] == 'some text'
    assert received['number_in'] == 7                       # typed number (F4)
    assert received['flag'] == 'no'                        # unchecked checkbox → mapped value (F4)
    assert received['terms'] is True
    assert received['choice'] == 'b' and received['mode'] == 'fast'
    assert received['hidden_param'] == 'hidden-default'
    assert 'not_serialized' not in received
    assert received['step_param'] == 'from-step'
    assert received['outdir'].endswith('/output/outdir')
    assert files['data_file']['exists'] and files['data_file']['content'] == (FILES / 'my data ü.csv').read_text()
    assert files['data_file']['name'].endswith('.csv') and ' ' not in files['data_file']['name']
    assert files['data_folder']['files'] == ['a.txt', 'b.txt']
    assert files['notes']['content'] == 'line one\nline two ü'
    assert files['notes']['name'] == 'notes.txt'

    job.open_results()
    expect(page.locator('[data-testid="job-output-link"][data-filename$="params-received.json"]')).to_be_visible()


@pytest.mark.worker
def test_live_progress_multi_process(page, login, requires_worker):
    """J4: running → per-process task counts increase → success without reload."""
    login(page, 'admin')
    run = RunPage(page).open('multi-process')
    run.job_name.fill('J4 progress')
    run.submit()
    job = JobPage(page)
    job.expect_state('running', 'success', timeout=60_000)
    for name in ('ALIGN', 'CALL', 'REPORT'):
        proc = job.process(name)
        expect(proc).to_have_attribute('data-completed', '5', timeout=150_000)
        expect(proc).to_have_attribute('data-total', '5')
    expect(job.process('ALIGN')).to_contain_text('Align')      # label from the YAML
    job.expect_state('success', timeout=60_000)
    expect(job.messages('info').filter(has_text='Processing 5 chunks in 3 stages')).to_have_count(1)
    expect(job.messages('success')).to_have_count(1)
    job.open_results()
    expect(page.get_by_test_id('job-output-link')).to_have_count(5)


@pytest.mark.worker
def test_failing_workflow(page, login, requires_worker):
    """J5: failed state, ::error:: rendered, Logs tab shows the Nextflow log."""
    login(page, 'admin')
    run = RunPage(page).open('fail')
    run.job_name.fill('J5 failure')
    run.submit()
    job = JobPage(page)
    job.expect_state('failed', timeout=150_000)
    expect(job.messages('error').filter(has_text='Intentional failure').first).to_be_visible()
    expect(page.get_by_test_id('job-failure')).to_contain_text('exited with code')
    log = job.open_logs()
    expect(log).to_contain_text('nextflow.log')
    expect(log).to_contain_text('Intentional failure')


@pytest.mark.worker
def test_cancel_running_job_from_job_page(page, login, api, requires_worker):
    """J6: cancelled within seconds and no Nextflow/task process left."""
    admin = api('admin')
    job_id = admin.submit_job('slow', name='J6 cancel me', params={'seconds': 300})['id']
    try:
        wait_job_state(admin, job_id, 'running', timeout=120)
        # wait until Nextflow actually runs the task
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            steps = admin.job_status(job_id)['steps']
            if steps and steps[0]['processes']:
                break
            time.sleep(1)
        login(page, 'admin')
        job = JobPage(page).open(job_id)
        job.expect_state('running')
        started = time.monotonic()
        job.cancel()
        job.expect_state('cancelled', timeout=30_000)
        assert time.monotonic() - started < 30
        assert wait_no_job_processes(job_id, timeout=20) == []
        expect(job.messages('warning').filter(has_text='Job cancelled.')).to_have_count(1)
    finally:
        _cancel_if_active(admin, job_id)


@pytest.mark.serial
@pytest.mark.worker
def test_cancel_waiting_and_delete_finished(page, login, api, server_settings, requires_worker):
    """J7: cancel a waiting job from the list; delete a finished job from its page."""
    alice = api('alice')
    server_settings.update('queue', paused=True)
    waiting_id = alice.submit_job('hello', name='J7 waiting', params={'message': 'x'})['id']
    login(page, 'alice')
    page.goto('/jobs')
    row = page.locator('[data-testid="job-row"][data-job-id="%s"]' % waiting_id)
    expect(row).to_have_attribute('data-state', 'waiting')
    row.get_by_test_id('job-row-cancel').click()
    page.get_by_test_id('confirm-ok').click()
    expect(row).to_have_attribute('data-state', 'cancelled')
    assert job_state(alice.job_status(waiting_id)) == 'cancelled'

    # delete the (finished) cancelled job from its page
    job = JobPage(page).open(waiting_id)
    job.delete()
    page.wait_for_url('**/jobs')
    expect(page.locator('[data-testid="job-row"][data-job-id="%s"]' % waiting_id)).to_have_count(0)
    assert alice.get('/api/jobs/%s/' % waiting_id).status_code == 404
