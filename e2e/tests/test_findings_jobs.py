"""Red tests for the exploratory QA findings of T07a (run form & job lifecycle).

Every test here reproduces a confirmed defect recorded in `plans/QA_FINDINGS.md` and is
marked `xfail(strict=True)`: it stays XFAIL while the defect exists and turns the suite red
(XPASS) the moment it is fixed — remove the marker in the fixing task.

Keep them fast: no Nextflow run unless the finding needs one.
"""
import time

import pytest

ALL_INPUTS = dict(workflow='all-inputs', text_in='t', number_in='5', terms='true',
                  choice='b', mode='fast')
CSV = b'a,b\n1,2\n'


def _cancel(client, payload):
    if isinstance(payload, dict) and payload.get('id'):
        client.post('/api/jobs/%s/cancel/' % payload['id'])


# --------------------------------------------------------------------------------------------
# A-01
# --------------------------------------------------------------------------------------------

def test_a01_file_part_for_text_input_is_rejected(api):
    """A `text` input must not accept a multipart *file* part (and must never silently use the
    file's name as the value, overriding what the user typed)."""
    client = api('alice')
    r = client.post('/api/jobs/', data={'workflow': 'hello', 'message': 'typed by the user'},
                    files=[('message', ('m.txt', b'contents of a file'))])
    try:
        assert r.status_code == 400, 'expected a 400 for a file sent into a text input, got %s: %s' % (
            r.status_code, r.text[:200])
    finally:
        if r.status_code == 201:
            body = r.json()
            _cancel(client, body)
            value = next((i['value'] for i in body['inputs'] if i['id'] == 'message'), None)
            assert value == 'm.txt', 'unexpected stored value %r' % value  # documents the actual bug


# --------------------------------------------------------------------------------------------
# A-02
# --------------------------------------------------------------------------------------------

def test_a02_many_files_in_folder_input_is_a_client_error(api):
    """Uploading more files than Django's DATA_UPLOAD_MAX_NUMBER_FILES must be a 4xx with a
    usable message, never a 500 "Internal server error."."""
    client = api('alice')
    files = [('data_file', ('a.csv', CSV))]
    files += [('data_folder', ('f%03d.txt' % i, b'x')) for i in range(120)]
    r = client.post('/api/jobs/', data=ALL_INPUTS, files=files)
    _cancel(client, r.json() if r.ok else None)
    assert r.status_code < 500, 'submitting 121 file parts returned %s: %s' % (
        r.status_code, r.text[:200])


# --------------------------------------------------------------------------------------------
# A-03
# --------------------------------------------------------------------------------------------

def test_a03_admin_workflow_list_does_not_write_on_every_read(api, stack):
    """A read-only list must not run a full registry sync (a DB write per row) on every call.

    SPEC §3.2 triggers a sync from the API only "when settings.yaml or an installed
    cloudgene.yaml changed". Writing on every read is what puts the web process in write
    contention with the worker on SQLite (observed: `OperationalError: database is locked`
    -> 500 on the admin pages and failed worker ticks).
    """
    client = api('admin')
    read = ("from workflows.models import Workflow;"
            "print(sorted((w.pk, str(w.synced_at)) for w in Workflow.objects.all()))")
    before = stack.django_shell(read).strip()
    assert client.get('/api/admin/workflows/').status_code == 200
    after = stack.django_shell(read).strip()
    assert after == before, 'the registry was rewritten by a plain GET:\n%s\n%s' % (before, after)


# --------------------------------------------------------------------------------------------
# A-04
# --------------------------------------------------------------------------------------------

WORK_DIR_PROBE = '''
import uuid
from jobs import outputs, runner, workflow_bridge
from jobs.models import Job
from workflows.models import Workflow

wf = Workflow.objects.get(pk='hello')
job = Job(id=uuid.UUID('11111111-1111-1111-1111-111111111111'), workflow=wf)
work = runner.work_dir_for(job, workflow_bridge.nextflow_work_dir(wf)).resolve()
roots = outputs._allowed_roots(job)
print('WORK=%s' % work)
print('ROOTS=%s' % [str(r) for r in roots])
print('ALLOWED=%s' % any(work == r or r in work.parents for r in roots))
'''


@pytest.mark.serial
def test_a04_per_app_work_dir_is_an_allowed_output_root(stack, server_settings):
    """`jobs.runner.work_dir_for` honours `apps[].work_dir`; `jobs.outputs._allowed_roots`
    only knows the global `nextflow.work_dir`. When they disagree, `collect_outputs()` drops
    every published symlink and the job finishes "successfully" with no results at all
    (full reproduction: e2e/exploratory/probe_workdir.py)."""
    data = stack.read_settings()
    for app in data['apps']:
        if app.get('path') == 'hello':
            app['work_dir'] = 'custom-work'
    stack.write_settings(data)
    time.sleep(1.2)
    out = stack.django_shell(WORK_DIR_PROBE)
    assert 'ALLOWED=True' in out, ('the runner would use a work dir that output collection '
                                   'rejects:\n%s' % out)


# --------------------------------------------------------------------------------------------
# A-05
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize('value', ['1_0', '٥'])
def test_a05_number_input_rejects_values_the_form_rejects(api, value):
    """formModel.js validates numbers with /^[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?$/ and
    rejects both of these; the API must agree (SPEC §3.7)."""
    client = api('alice')
    r = client.post('/api/jobs/', data={**ALL_INPUTS, 'number_in': value},
                    files=[('data_file', ('a.csv', CSV))])
    _cancel(client, r.json() if r.ok else None)
    assert r.status_code == 400, 'number_in=%r was accepted (%s)' % (value, r.status_code)
