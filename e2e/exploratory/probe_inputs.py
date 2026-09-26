"""T07a probe 1 — odd values in the run form (API level).

The queue is paused and unlimited for the whole module so submissions are cheap (jobs stay
`waiting` and are cancelled at the end); nothing here starts Nextflow.
"""
import copy
import time

import pytest

from e2e.exploratory.conftest import brief

pytestmark = pytest.mark.serial


@pytest.fixture(scope='module')
def paused_stack(stack):
    original = copy.deepcopy(stack.read_settings())
    data = copy.deepcopy(original)
    data['queue']['paused'] = True
    data['server']['max_queue_size'] = 0  # unlimited
    stack.write_settings(data)
    time.sleep(1.5)
    yield stack
    stack.write_settings(original)
    time.sleep(1.5)


@pytest.fixture(scope='module')
def alice(paused_stack):
    from e2e.helpers import ApiClient
    c = ApiClient(paused_stack.base_url)
    c.login('alice')
    yield c
    # tidy up: cancel everything alice left waiting
    for job in c.get_json('/api/jobs/?state=waiting&page_size=200')['results']:
        c.post('/api/jobs/%s/cancel/' % job['id'])
    c.close()


def post(client, **fields):
    files = fields.pop('_files', None)
    return client.post('/api/jobs/', data=fields, files=files)


# ---------------------------------------------------------------- job names

def test_job_names(alice, report):
    cases = {
        'plain': 'probe plain',
        'leading/trailing space': '   padded   ',
        'newlines': 'line1\nline2\ttab',
        'html': '<img src=x onerror=alert(1)>',
        'script': '<script>alert("xss")</script>',
        'unicode/emoji/RTL': 'Jöb 🚀 مرحبا שלום',
        'nul byte': 'a\x00b',
        'only control chars': '\n\t\r',
        '255 chars': 'x' * 255,
        '256 chars': 'x' * 256,
        '1000 chars': 'x' * 1000,
        'only spaces': '     ',
        'name=': None,  # sent via the `name` alias below
    }
    for label, value in cases.items():
        if value is None:
            r = post(alice, workflow='hello', name='via name alias', message='hi')
        else:
            r = post(alice, workflow='hello', job_name=value, message='hi')
        stored = r.json().get('name') if r.status_code == 201 else None
        report(label, '%s -> %r' % (r.status_code, stored if stored is None else stored[:80]))


# ---------------------------------------------------------------- text inputs

def test_text_input_values(alice, report):
    cases = {
        'empty': '',
        'spaces only': '    ',
        'html': '<b>bold</b><script>alert(1)</script>',
        'newlines': 'a\nb\nc',
        'nul byte': 'a\x00b',
        'unicode': '💥 ünïcødé العربية',
        '100k chars': 'y' * 100_000,
        '100k+1 chars': 'y' * 100_001,
        'looks like a path': '../../etc/passwd',
        'shell metachars': '$(touch /tmp/pwned); rm -rf /',
    }
    for label, value in cases.items():
        r = post(alice, workflow='hello', job_name='probe-text-%s' % label, message=value)
        stored = None
        if r.status_code == 201:
            stored = next((i['value'] for i in r.json()['inputs'] if i['id'] == 'message'), None)
            stored = stored if not isinstance(stored, str) else stored[:60]
        report(label, '%s -> %r' % (r.status_code, stored if r.status_code == 201 else brief(r, 150)))


def test_missing_and_extra_fields(alice, report):
    report('no workflow', brief(post(alice, job_name='x', message='hi'), 200))
    report('unknown workflow', brief(post(alice, workflow='nope', message='hi'), 200))
    report('workflow alice cannot access', brief(post(alice, workflow='fail', note='hi'), 200))
    report('missing required input', brief(post(alice, workflow='hello'), 200))
    report('extra unknown field', brief(post(alice, workflow='hello', message='hi', bogus='x'), 120))
    report('duplicate message field',
           brief(alice.post('/api/jobs/', data=[('workflow', 'hello'), ('message', 'one'),
                                                ('message', 'two')]), 120))
    report('workflow sent twice',
           brief(alice.post('/api/jobs/', data=[('workflow', 'hello'), ('workflow', 'all-inputs'),
                                                ('message', 'x')]), 120))
    report('json body instead of multipart',
           brief(alice.post('/api/jobs/', json={'workflow': 'hello', 'message': 'hi'}), 120))
    r = alice.post('/api/jobs/', data={'workflow': 'hello'},
                   files=[('message', ('m.txt', b'hello from a file'))])
    report('file sent for a text input',
           '%s inputs=%s params=%s' % (r.status_code,
                                       r.json().get('inputs') if r.status_code == 201 else brief(r, 120),
                                       ''))
    r2 = alice.post('/api/jobs/', data={'workflow': 'hello', 'message': 'typed'},
                    files=[('message', ('m.txt', b'x'))])
    report('file AND text for the same input',
           '%s %s' % (r2.status_code, r2.json().get('inputs') if r2.status_code == 201 else brief(r2, 120)))


# ---------------------------------------------------------------- numbers

NUMBER_CASES = ['5', '1', '10', '0', '11', '-1', '5.5', '1e1', '-1e999', '1e999', 'nan', 'inf',
                'Infinity', '0x10', '1_0', ' 7 ', '', 'abc', '+5', '5e0', '999999999999999999999',
                '1.0000000000000001', '٥', '1,5', 'true']


def test_number_input(alice, report):
    """all-inputs.number_in: min 1, max 10, required."""
    base = dict(workflow='all-inputs', text_in='t', terms='true', choice='b', mode='fast')
    for value in NUMBER_CASES:
        r = alice.post('/api/jobs/', data={**base, 'number_in': value, 'job_name': 'probe-num'},
                       files=[('data_file', ('small.csv', b'a,b\n1,2\n'))])
        stored = None
        if r.status_code == 201:
            stored = next((i['value'] for i in r.json()['inputs'] if i['id'] == 'number_in'), None)
        report('number=%r' % value, '%s -> %r' % (r.status_code, stored if r.status_code == 201
                                                  else r.json().get('error', {}).get('message', '')[:80]))


# ---------------------------------------------------------------- choices / checkboxes

def test_list_radio_checkbox(alice, report):
    base = dict(workflow='all-inputs', text_in='t', number_in='5', terms='true',
                choice='b', mode='fast')
    files = [('data_file', ('small.csv', b'a,b\n1,2\n'))]

    def run(label, **over):
        r = alice.post('/api/jobs/', data={**base, **over, 'job_name': 'probe-choice'}, files=files)
        values = {i['id']: i['value'] for i in r.json()['inputs']} if r.status_code == 201 else {}
        report(label, '%s %s' % (r.status_code, {k: values.get(k) for k in ('choice', 'mode', 'flag', 'agb', 'terms')}
                                 if r.status_code == 201 else brief(r, 120)))

    run('defaults')
    run('choice=bogus', choice='zzz')
    run('choice empty', choice='')
    run('flag unchecked', flag='false')
    run('flag omitted', **{})
    run('flag=yes (mapped label)', flag='yes')
    run('flag=1', flag='1')
    run('terms=false', terms='false')
    run('terms omitted', terms=None)
    run('mode injected', mode='fast; rm -rf /')
    run('hidden_param override attempt', hidden_param='OVERRIDDEN')
    run('not_serialized override', not_serialized='OVERRIDDEN')
