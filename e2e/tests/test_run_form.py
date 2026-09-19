"""Run form (E2E_TEST_PLAN §3):

W2 the all-inputs form renders every input type with YAML defaults, help and required markers
J3 client & server validation: missing required, number out of range, unchecked terms → field
   errors, no job created
"""
from pathlib import Path

from playwright.sync_api import expect

from e2e.pages import RunPage

FILES = Path(__file__).resolve().parent.parent / 'fixtures' / 'files'


def test_all_input_types_render_with_defaults(page, login):
    """W2."""
    login(page, 'alice')
    run = RunPage(page).open('all-inputs')
    expect(page.get_by_test_id('workflow-title')).to_have_text('All Inputs')
    tid = page.get_by_test_id

    expect(tid('input-sep_general')).to_be_visible()
    expect(tid('input-info_intro')).to_contain_text('every input type')
    expect(tid('input-info_intro').locator('b')).to_have_text('every')      # HTML description
    expect(tid('input-label_note')).to_contain_text('Labels are display-only.')

    expect(run.field('text_in')).to_have_value('default text')
    expect(tid('input-text_in')).to_contain_text('*')                        # required marker
    expect(tid('input-text_in')).to_contain_text('Any printable text.')      # help
    expect(run.field('string_in')).to_have_value('default string')
    expect(run.field('number_in')).to_have_value('5')
    expect(run.field('number_in')).to_have_attribute('type', 'number')
    expect(run.field('number_in')).to_have_attribute('min', '1')
    expect(run.field('number_in')).to_have_attribute('max', '10')
    expect(run.field('notes')).to_have_value('first line')
    expect(run.field('choice')).to_have_value('b')
    expect(tid('input-choice').locator('option[value="c"]')).to_have_text('Gamma')
    expect(tid('input-mode').locator('input[value="fast"]')).to_be_checked()
    expect(tid('input-mode').locator('input[value="accurate"]')).not_to_be_checked()
    expect(tid('input-flag').locator('input[type=checkbox]')).to_be_checked()   # YAML default true (F4)
    expect(tid('input-data_file').locator('input[type=file]')).to_have_attribute('accept', '.csv')
    expect(tid('input-data_folder').locator('input[type=file]')).to_have_attribute('multiple', '')
    expect(tid('input-local_file').locator('input[type=file]')).to_be_visible()
    expect(tid('input-local_folder').locator('input[type=file]')).to_be_visible()
    expect(tid('input-agb').locator('input[type=checkbox]')).not_to_be_checked()
    expect(tid('input-terms').locator('input[type=checkbox]')).not_to_be_checked()
    expect(tid('input-hidden_param')).to_have_count(0)                         # visible: false
    expect(run.job_name).to_have_value('')                                     # optional (J7 bug)


def test_client_validation_blocks_submit(page, login, api):
    """J3 (client side): no request is sent, errors shown per field."""
    login(page, 'alice')
    alice = api('alice')
    before = alice.get_json('/api/jobs/')['count']
    run = RunPage(page).open('all-inputs')
    run.fill('text_in', '')
    run.fill('number_in', '11')
    requests = []
    page.on('request', lambda r: requests.append(r) if r.method == 'POST' and '/api/jobs' in r.url else None)
    run.submit_button.click()
    expect(run.field_error('text_in')).to_have_text('This field is required.')
    expect(run.field_error('number_in')).to_have_text('Must be at most 10.')
    expect(run.field_error('data_file')).to_have_text('Please select a file.')
    expect(run.field_error('terms')).to_have_text('You must accept this to submit the job.')
    expect(run.error).to_be_visible()
    assert requests == []
    assert '/run/all-inputs' in page.url
    assert alice.get_json('/api/jobs/')['count'] == before


def test_server_validation_field_errors(api):
    """J3 (server side): the API rejects the same input with envelope field errors."""
    alice = api('alice')
    before = alice.get_json('/api/jobs/')['count']
    r = alice.post('/api/jobs/', data={'workflow': 'all-inputs', 'job_name': 'J3', 'text_in': '',
                                       'number_in': '0', 'choice': 'zzz', 'terms': 'false'})
    assert r.status_code == 400, r.text
    fields = r.json()['error']['fields']
    assert fields['text_in'] == ['This field is required.']
    assert fields['number_in'] == ['Must be at least 1.']
    assert fields['choice'] == ['Select a valid choice.']
    assert fields['terms'] == ['You must accept this to submit the job.']
    assert fields['data_file'] == ['Please select a file.']
    assert alice.get_json('/api/jobs/')['count'] == before


def test_server_field_errors_are_shown_in_the_form(page, login, expect_api_error):
    """J3: when the server rejects a value (here: a request tampered after client validation),
    its envelope field error is shown next to the input."""
    login(page, 'alice')
    run = RunPage(page).open('all-inputs')
    run.set_checked('terms', True)
    run.set_files('data_file', [FILES / 'small.csv'])
    run.fill('number_in', '3')
    expect_api_error(400, '/api/jobs*')
    page.evaluate("""() => {
        const orig = window.FormData.prototype.append;
        window.FormData.prototype.append = function (k, v, ...rest) {
            if (k === 'number_in') v = '99';
            return orig.call(this, k, v, ...rest);
        };
    }""")
    run.submit_button.click()
    expect(run.field_error('number_in')).to_have_text('Must be at most 10.')
    expect(run.error).to_contain_text('number_in')
