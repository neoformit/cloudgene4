"""T07c probe 4: workflow admin round-trips (install/reload/disable/uninstall/duplicates)."""
import json
import shutil
import time
from pathlib import Path

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial

SRC = Path(__file__).parent / 'apps' / 'probe-env'


def _copy_app(tmp_path, app_id='probe-env', name='Probe Env'):
    dst = tmp_path / app_id
    shutil.copytree(SRC, dst)
    y = (dst / 'cloudgene.yaml').read_text()
    y = y.replace('id: probe-env', 'id: %s' % app_id).replace('name: Probe Env', 'name: %s' % name)
    (dst / 'cloudgene.yaml').write_text(y)
    return dst


def _ids(payload):
    if isinstance(payload, dict):
        payload = payload.get('results', [])
    return [w['id'] for w in payload]


def test_reload_after_yaml_edit(stack, api, server_settings, tmp_path):
    c = api('admin')
    app = _copy_app(tmp_path)
    print('install ->', c.post('/api/admin/workflows/install/',
                               json={'path': str(app), 'public': True}).status_code)
    try:
        print('inputs before:', [i['id'] for i in
                                 c.get_json('/api/workflows/probe-env/')['inputs']])
        # add an input
        y = (app / 'cloudgene.yaml').read_text().replace(
            '    - id: note', '    - id: extra\n      description: Extra\n      type: text\n'
                              '      required: false\n    - id: note')
        (app / 'cloudgene.yaml').write_text(y)
        r = c.post('/api/admin/workflows/probe-env/reload/')
        print('reload ->', r.status_code)
        print('inputs after reload:', [i['id'] for i in
                                       c.get_json('/api/workflows/probe-env/')['inputs']])
        # break the YAML
        (app / 'cloudgene.yaml').write_text('id: probe-env\nname: [unclosed\n')
        r = c.post('/api/admin/workflows/probe-env/reload/')
        print('reload broken ->', r.status_code, r.text[:300])
        row = [w for w in c.get_json('/api/admin/workflows/') if w['id'] == 'probe-env']
        print('admin row after break:', json.dumps(row, indent=1)[:600])
        pub = c.get('/api/workflows/probe-env/')
        print('public detail after break ->', pub.status_code, pub.text[:200])
        r = c.post('/api/jobs/', data={'workflow': 'probe-env', 'job_name': 'x', 'note': 'y'})
        print('submit after break ->', r.status_code, r.text[:200])
        # repair
        shutil.copy(SRC / 'cloudgene.yaml', app / 'cloudgene.yaml')
        r = c.post('/api/admin/workflows/probe-env/reload/')
        print('reload repaired ->', r.status_code)
        row = [w for w in c.get_json('/api/admin/workflows/') if w['id'] == 'probe-env']
        print('valid again:', row and row[0]['valid'], 'enabled:', row and row[0]['enabled'])
    finally:
        c.delete('/api/admin/workflows/probe-env/')


def test_app_dir_disappears(stack, api, server_settings, tmp_path):
    c = api('admin')
    app = _copy_app(tmp_path)
    c.post('/api/admin/workflows/install/', json={'path': str(app), 'public': True})
    try:
        shutil.rmtree(app)
        r = c.get('/api/admin/workflows/')
        print('admin list ->', r.status_code)
        row = [w for w in r.json() if 'probe-env' in w['id']]
        print('row:', json.dumps(row, indent=1)[:500])
        print('public ids:', _ids(api('bob').get_json('/api/workflows/')))
        d = c.get('/api/admin/workflows/probe-env/')
        print('admin detail ->', d.status_code, d.text[:200])
        r = c.post('/api/jobs/', data={'workflow': 'probe-env', 'job_name': 'x', 'note': 'y'})
        print('submit ->', r.status_code, r.text[:160])
        print('dashboard workflows:', c.get_json('/api/admin/dashboard/')['workflows'])
    finally:
        c.delete('/api/admin/workflows/probe-env/')


def test_duplicate_id_install(stack, api, server_settings, tmp_path):
    c = api('admin')
    a = _copy_app(tmp_path / 'one', 'probe-env', 'First')
    b = _copy_app(tmp_path / 'two', 'probe-env', 'Second')
    print('install A ->', c.post('/api/admin/workflows/install/',
                                 json={'path': str(a), 'public': True}).status_code)
    try:
        r = c.post('/api/admin/workflows/install/', json={'path': str(b), 'public': True})
        print('install duplicate ->', r.status_code, r.text[:200])
        # now add the duplicate straight into settings.yaml (hand edit)
        data = stack.read_settings()
        data['apps'].append({'path': str(b), 'enabled': True, 'public': True, 'groups': []})
        stack.write_settings(data)
        time.sleep(1.1)
        rows = c.get_json('/api/admin/workflows/')
        print('rows:', [(w['id'], w['valid'], w['errors'][:1]) for w in rows])
        print('public ids:', _ids(api('bob').get_json('/api/workflows/')))
        r = c.post('/api/jobs/', data={'workflow': 'probe-env', 'job_name': 'dup', 'note': 'y'})
        print('submit ->', r.status_code, r.text[:160])
        if r.status_code < 300:
            c.post('/api/jobs/%s/cancel/' % r.json()['id'])
        print('dashboard:', c.get_json('/api/admin/dashboard/')['workflows'])
    finally:
        server_settings.restore()
        time.sleep(1.1)
        c.get('/api/admin/workflows/')


def test_id_collision_with_existing(stack, api, server_settings, tmp_path):
    """Install an app whose id collides with an installed fixture app (hello)."""
    c = api('admin')
    app = _copy_app(tmp_path, 'hello', 'Impostor')
    r = c.post('/api/admin/workflows/install/', json={'path': str(app), 'public': True})
    print('install colliding id ->', r.status_code, r.text[:200])
    print('hello still:', c.get_json('/api/admin/workflows/hello/')['name'])
    if r.status_code < 300:
        server_settings.restore()


def test_disable_and_uninstall_with_jobs(stack, api, server_settings, requires_worker, tmp_path):
    c = api('admin')
    app = _copy_app(tmp_path)
    c.post('/api/admin/workflows/install/', json={'path': str(app), 'public': True})
    job = None
    try:
        alice = api('alice')
        job = alice.submit_job('probe-env', name='probe-disable', params={'note': 'x'})
        r = c.patch('/api/admin/workflows/probe-env/', json={'enabled': False})
        print('disable ->', r.status_code)
        print('running job state:', c.job_status(job['id'])['state'])
        helpers.wait_job_state(alice, job['id'], ('success', 'failed', 'cancelled'), timeout=180)
        print('job after disable:', alice.job_status(job['id'])['state'])
        print('alice can still read her job:', alice.get('/api/jobs/%s' % job['id']).status_code)
        print('alice public list:', _ids(alice.get_json('/api/workflows/')))
        r = alice.post('/api/jobs/', data={'workflow': 'probe-env', 'job_name': 'x', 'note': 'y'})
        print('submit while disabled ->', r.status_code, r.text[:150])
        # uninstall with a job referencing it
        r = c.delete('/api/admin/workflows/probe-env/')
        print('uninstall ->', r.status_code)
        rows = stack.django_shell(
            "from workflows.models import Workflow;"
            "print([(w.id, w.installed, w.status) for w in Workflow.objects.all()])")
        print('rows after uninstall:', rows.strip().splitlines()[-1])
        d = alice.get('/api/jobs/%s' % job['id'])
        print('job detail after uninstall ->', d.status_code, d.text[:200])
        print('admin jobs list ->', c.get('/api/admin/jobs/').status_code)
        print('dashboard ->', c.get('/api/admin/dashboard/').status_code)
    finally:
        c.delete('/api/admin/workflows/probe-env/')
        if job:
            alice.delete('/api/jobs/%s/' % job['id'])


def test_access_change_while_form_open(stack, api, server_settings, tmp_path):
    """Groups/public toggles must take effect for the next request of a normal user."""
    c = api('admin')
    bob = api('bob')
    app = _copy_app(tmp_path)
    c.post('/api/admin/workflows/install/', json={'path': str(app), 'public': True})
    try:
        print('bob sees (public):', 'probe-env' in _ids(bob.get_json('/api/workflows/')))
        c.patch('/api/admin/workflows/probe-env/', json={'public': False,
                                                         'groups': ['probe-group']})
        print('bob sees (private):', 'probe-env' in _ids(bob.get_json('/api/workflows/')))
        print('bob detail ->', bob.get('/api/workflows/probe-env/').status_code)
        r = bob.post('/api/jobs/', data={'workflow': 'probe-env', 'job_name': 'x', 'note': 'y'})
        print('bob submit ->', r.status_code, r.text[:140])
        groups = c.get_json('/api/admin/groups/')
        print('groups:', [g['name'] for g in groups])
        bob_id = [u['id'] for u in c.get_json('/api/admin/users/')['results']
                  if u['username'] == 'bob'][0]
        print('add bob ->', c.patch('/api/admin/users/%d/' % bob_id,
                                    json={'groups': ['probe-group']}).status_code)
        print('bob sees after group add:', 'probe-env' in _ids(bob.get_json('/api/workflows/')))
        r = bob.post('/api/jobs/', data={'workflow': 'probe-env', 'job_name': 'x', 'note': 'y'})
        print('bob submit after group add ->', r.status_code, r.text[:140])
        if r.status_code < 300:
            bob.post('/api/jobs/%s/cancel/' % r.json()['id'])
    finally:
        c.delete('/api/admin/workflows/probe-env/')
        gid = [g['id'] for g in c.get_json('/api/admin/groups/') if g['name'] == 'probe-group']
        for g in gid:
            c.delete('/api/admin/groups/%d/' % g)
        server_settings.restore()
