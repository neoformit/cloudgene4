"""T07a probe 6 — per-app Nextflow ``work_dir`` vs. output collection / downloads.

`jobs/runner.work_dir_for` honours the per-app `apps[].work_dir`, but
`jobs/outputs._allowed_roots` only knows the GLOBAL `nextflow.work_dir`. A pipeline that
publishes with the Nextflow default `publishDir` mode (symlink) then produces outputs that
resolve outside every "allowed root".
"""
import copy
import shutil
import time
from pathlib import Path

import pytest

from e2e.helpers import wait_job_state

pytestmark = pytest.mark.serial

APP = Path(__file__).resolve().parent / 'apps' / 'symlink-out'


@pytest.fixture(scope='module')
def admin(stack):
    from e2e.helpers import ApiClient
    c = ApiClient(stack.base_url)
    c.login('admin')
    yield c
    c.close()


@pytest.fixture(scope='module')
def installed(stack):
    target = stack.home / 'apps' / 'symlink-out'
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(APP, target)
    original = copy.deepcopy(stack.read_settings())
    yield target
    stack.write_settings(original)
    time.sleep(1.5)


def install(stack, **extra):
    data = copy.deepcopy(stack.read_settings())
    data['apps'] = [a for a in data['apps'] if a.get('path') != 'symlink-out']
    data['apps'].append({'path': 'symlink-out', 'enabled': True, 'public': True,
                         'groups': [], **extra})
    stack.write_settings(data)
    time.sleep(1.5)


def run(admin, stack, name):
    job = admin.post('/api/jobs/', data={'workflow': 'symlink-out', 'job_name': name,
                                         'message': 'probe'}).json()
    assert 'id' in job, job
    wait_job_state(admin, job['id'], ('success', 'failed'), timeout=240)
    return admin.get_json('/api/jobs/%s/' % job['id'])


def test_default_work_dir(admin, stack, installed, report):
    stack.require_worker()
    install(stack)
    admin.get('/api/workflows/')  # trigger the sync middleware
    detail = run(admin, stack, 'probe-workdir-default')
    report('state', detail['state'])
    report('outputs', [(o['path'], o['size']) for o in detail['outputs']])
    if detail['outputs']:
        report('download', admin.get(detail['outputs'][0]['url']).status_code)
    published = stack.home / 'jobs' / detail['id'] / 'output' / 'outdir'
    report('published entries', [(p.name, p.is_symlink()) for p in published.iterdir()]
           if published.is_dir() else '<no output/outdir>')


def test_per_app_work_dir(admin, stack, installed, report):
    stack.require_worker()
    install(stack, work_dir='custom-work')
    admin.get('/api/workflows/')
    detail = run(admin, stack, 'probe-workdir-per-app')
    report('state', detail['state'])
    report('outputs listed', [(o['path'], o['size']) for o in detail['outputs']])
    published = stack.home / 'jobs' / detail['id'] / 'output' / 'outdir'
    report('published entries', [(p.name, p.is_symlink(), p.resolve().exists())
                                 for p in published.iterdir()] if published.is_dir()
           else '<no output/outdir>')
    report('work dir used', [str(p) for p in (stack.home / 'custom-work').glob('*')][:3]
           if (stack.home / 'custom-work').exists() else '<no custom-work>')
    if detail['outputs']:
        report('download', admin.get(detail['outputs'][0]['url']).status_code)


def test_global_work_dir(admin, stack, installed, report):
    stack.require_worker()
    install(stack)
    data = copy.deepcopy(stack.read_settings())
    data['nextflow']['work_dir'] = 'global-work'
    stack.write_settings(data)
    time.sleep(1.5)
    admin.get('/api/workflows/')
    detail = run(admin, stack, 'probe-workdir-global')
    report('state', detail['state'])
    report('outputs listed', [(o['path'], o['size']) for o in detail['outputs']])
    if detail['outputs']:
        report('download', admin.get(detail['outputs'][0]['url']).status_code)
