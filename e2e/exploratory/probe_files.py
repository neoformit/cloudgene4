"""T07a probe 2 — file / folder uploads (API level, queue paused)."""
import copy
import time

import pytest

from e2e.exploratory.conftest import brief

pytestmark = pytest.mark.serial

BASE = dict(workflow='all-inputs', text_in='t', number_in='5', terms='true', choice='b', mode='fast')
CSV = b'a,b\n1,2\n'


@pytest.fixture(scope='module')
def paused_stack(stack):
    original = copy.deepcopy(stack.read_settings())
    data = copy.deepcopy(original)
    data['queue']['paused'] = True
    data['server']['max_queue_size'] = 0
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
    for job in c.get_json('/api/jobs/?state=waiting&page_size=200')['results']:
        c.post('/api/jobs/%s/cancel/' % job['id'])
    c.close()


def submit(alice, files, **over):
    return alice.post('/api/jobs/', data={**BASE, **over}, files=files)


def workspace(stack, job_id):
    return stack.home / 'jobs' / job_id


def tree(path):
    if not path.exists():
        return '<missing>'
    return sorted(p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file())


def test_single_file_names(alice, paused_stack, report):
    cases = {
        'plain': 'data.csv',
        'spaces': 'my data file.csv',
        'unicode': 'dätä ü 🚀.csv',
        'traversal': '../../../../etc/passwd.csv',
        'windows traversal': '..\\..\\evil.csv',
        'absolute': '/etc/shadow.csv',
        'leading dot': '.hidden.csv',
        'only dots': '....csv',
        'very long': ('n' * 300) + '.csv',
        'newline in name': 'ev\nil.csv',
        'semicolon': 'a;rm -rf /.csv',
        'quote': 'a"b\'c.csv',
        'wrong extension': 'notes.txt',
        'uppercase ext': 'DATA.CSV',
        'double ext': 'evil.sh.csv',
        'html': '<img src=x onerror=alert(1)>.csv',
    }
    for label, name in cases.items():
        r = submit(alice, [('data_file', (name, CSV))], job_name='probe-file-%s' % label)
        if r.status_code != 201:
            report(label, brief(r, 120))
            continue
        job = r.json()
        files = tree(workspace(paused_stack, job['id']))
        shown = [f['name'] for i in job['inputs'] if i['id'] == 'data_file' for f in i['files']]
        report(label, 'on disk=%s shown=%s' % (files, shown))


def test_empty_and_missing_files(alice, paused_stack, report):
    r = submit(alice, [('data_file', ('empty.csv', b''))], job_name='probe-empty')
    report('0-byte file', '%s %s' % (r.status_code, tree(workspace(paused_stack, r.json()['id']))
                                     if r.status_code == 201 else brief(r, 150)))
    r = submit(alice, [('data_file', ('', b''))], job_name='probe-noname')
    report('empty filename', brief(r, 150))
    r = alice.post('/api/jobs/', data={**BASE, 'job_name': 'probe-nofile'})
    report('required file omitted', brief(r, 150))
    r = submit(alice, [('data_file', ('a.csv', CSV)), ('data_file', ('b.csv', CSV))],
               job_name='probe-two-in-file')
    report('two files for a single-file input', brief(r, 150))


def test_folder_input(alice, paused_stack, report):
    r = submit(alice, [('data_file', ('a.csv', CSV)),
                       ('data_folder', ('x.txt', b'1')), ('data_folder', ('x.txt', b'2')),
                       ('data_folder', ('sub/y.txt', b'3'))], job_name='probe-folder-dupes')
    report('folder: duplicate + sub/ names',
           '%s %s' % (r.status_code, tree(workspace(paused_stack, r.json()['id']))
                      if r.status_code == 201 else brief(r, 150)))

    for count in (99, 100, 101, 150):
        files = [('data_file', ('a.csv', CSV))] + [('data_folder', ('f%03d.txt' % i, b'x'))
                                                   for i in range(count)]
        r = submit(alice, files, job_name='probe-folder-%d' % count)
        n = len(tree(workspace(paused_stack, r.json()['id']))) if r.status_code == 201 else None
        report('folder with %d files' % count,
               '%s files_on_disk=%s %s' % (r.status_code, n,
                                           '' if r.status_code == 201 else brief(r, 200)))


def test_accept_and_types(alice, report):
    r = submit(alice, [('data_file', ('a.csv', CSV))], job_name='probe-text-for-file',
               data_folder='not a file')
    report('text value for a folder input', brief(r, 150))
    r = alice.post('/api/jobs/', data={**BASE, 'job_name': 'probe-file-as-text'},
                   files=[('data_file', ('a.csv', CSV)), ('text_in', ('t.txt', b'x'))])
    report('file for text_in (overrides text)',
           '%s %s' % (r.status_code, [i for i in r.json().get('inputs', []) if i['id'] == 'text_in']))


@pytest.mark.serial
def test_upload_size_limit(alice, paused_stack, report):
    settings = copy.deepcopy(paused_stack.read_settings())
    original = copy.deepcopy(settings)
    settings['server']['max_upload_mb'] = 1
    paused_stack.write_settings(settings)
    time.sleep(1.5)
    try:
        big = b'x' * (2 * 1024 * 1024)
        r = submit(alice, [('data_file', ('big.csv', big))], job_name='probe-too-big')
        report('2 MB with max_upload_mb=1', brief(r, 200))
        small = b'y' * (512 * 1024)
        r = submit(alice, [('data_file', ('ok.csv', small))], job_name='probe-small')
        report('0.5 MB with max_upload_mb=1', brief(r, 120))
        r = submit(alice, [('data_file', ('a.csv', CSV))] +
                   [('data_folder', ('p%d.bin' % i, b'z' * (300 * 1024))) for i in range(5)],
                   job_name='probe-folder-too-big')
        report('5x300 KB folder with max_upload_mb=1', brief(r, 200))
        report('max_upload_mb in workflow payload',
               alice.get_json('/api/workflows/all-inputs/').get('max_upload_mb'))
    finally:
        paused_stack.write_settings(original)
        time.sleep(1.5)
