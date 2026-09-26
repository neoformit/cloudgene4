"""Red tests for the exploratory QA findings of T07a (run form & job lifecycle).

Every test here reproduces a confirmed defect recorded in `plans/QA_FINDINGS.md` and is
marked `xfail(strict=True)`: it stays XFAIL while the defect exists and turns the suite red
(XPASS) the moment it is fixed — remove the marker in the fixing task.

Keep them fast: no Nextflow run unless the finding needs one.
"""
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

@pytest.mark.xfail(strict=True, reason='A-01: a file part for a text input is accepted and '
                                       'becomes the file name')
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

@pytest.mark.xfail(strict=True, reason='A-02: >100 files in a folder input return 500 '
                                       '(TooManyFilesSent is not mapped to the error envelope)')
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
