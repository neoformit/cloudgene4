"""J1: submit `hello` through the run form with a job name containing spaces & unicode (K3),
watch it succeed on the job page, and download the output."""
from pathlib import Path

import pytest
from playwright.sync_api import expect

from e2e.helpers import job_state
from e2e.pages import JobPage, RunPage

JOB_NAME = 'My first run  with spaces – ünïcödé 🚀'
MESSAGE = 'Grüße "quoted" it\'s $HOME `x` 🚀'


@pytest.mark.worker
@pytest.mark.xfail(strict=False, reason='needs T03: job name kept verbatim (K3), Nextflow execution, '
                                        'states waiting/running/success, authenticated output downloads')
def test_submit_hello_with_unicode_job_name(page, login, stack, api):
    login(page, 'alice')
    run = RunPage(page).open('hello')
    run.job_name.fill(JOB_NAME)
    run.fill('message', MESSAGE)
    job_id = run.submit()

    job = JobPage(page)
    expect(job.title).to_have_text(JOB_NAME)
    # The API stores the name verbatim too (no `_` substitution, no trimming of inner spaces).
    assert api('alice').get_job(job_id)['name'] == JOB_NAME

    stack.require_worker()  # everything below needs the worker to run Nextflow
    job.expect_state('waiting', 'running', 'success', timeout=10_000)
    job.expect_state('success', timeout=120_000)  # page updates itself (polling), no reload
    assert job_state(api('alice').job_status(job_id)) == 'success'

    job.open_results()
    link = page.locator('[data-testid="job-output-link"][data-filename$="hello.txt"]')
    expect(link).to_be_visible()
    with page.expect_download() as download_info:
        link.click()
    download = download_info.value
    assert download.suggested_filename.endswith('hello.txt')
    assert Path(download.path()).read_text(encoding='utf-8') == MESSAGE + '\n'
