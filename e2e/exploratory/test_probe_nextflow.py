"""T07c probe 3: do nextflow.* settings and the config/env files reach a running pipeline?"""
import json
import time
from pathlib import Path

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial

PROBE_APP = Path(__file__).parent / 'apps' / 'probe-env'


def _messages(client, job_id):
    return [m['text'] for m in client.job_status(job_id)['messages']]


def _install(client, path=str(PROBE_APP), **kw):
    payload = {'path': path, 'enabled': True, 'public': True}
    payload.update(kw)
    r = client.post('/api/admin/workflows/install/', json=payload)
    return r


def _uninstall(client, app_id='probe-env'):
    return client.delete('/api/admin/workflows/%s/' % app_id)


def test_install_from_path_and_run(stack, api, server_settings, requires_worker):
    c = api('admin')
    r = _install(c)
    print('install ->', r.status_code, r.text[:300])
    try:
        print('admin list ids:', [w['id'] for w in c.get_json('/api/admin/workflows/')])
        print('public list ids:', [w['id'] for w in
                                   api('bob').get_json('/api/workflows/')['results']
                                   if True] if False else
              [w['id'] for w in _as_list(api('bob').get_json('/api/workflows/'))])
        # global config + env + profile
        c.put('/api/admin/settings/nextflow/', json={
            'profile': 'probeprofile', 'work_dir': '',
            'config': ('profiles { probeprofile { params.probe_global = "from-profile" } }\n'
                       'params.probe_global = "from-global-config"\n'),
            'env': 'PROBE_GLOBAL=global-env-value\n'})
        j = c.submit_job('probe-env', name='probe-nf-global', params={'note': 'x'})
        helpers.wait_job_state(c, j['id'], ('success', 'failed'), timeout=180)
        st = c.job_status(j['id'])
        print('state:', st['state'])
        for m in _messages(c, j['id']):
            print('  MSG:', m)
        stdout = (stack.home / 'jobs' / j['id'] / 'logs' / 'stdout.txt')
        head = stdout.read_text(errors='replace').splitlines()[:4]
        print('  CMD:', head)
    finally:
        _uninstall(c)
        server_settings.restore()


def _as_list(payload):
    if isinstance(payload, dict):
        return payload.get('results', [])
    return payload


def test_per_app_nextflow_overrides(stack, api, server_settings, requires_worker):
    c = api('admin')
    print('install ->', _install(c).status_code)
    try:
        c.put('/api/admin/settings/nextflow/', json={
            'profile': '', 'work_dir': '',
            'config': 'params.probe_global = "from-global-config"\n',
            'env': 'PROBE_GLOBAL=global-env-value\n'})
        r = c.put('/api/admin/workflows/probe-env/nextflow/', json={
            'profile': '', 'work_dir': '',
            'config': 'params.probe_app = "from-app-config"\n',
            'env': 'PROBE_APP=app-env-value\n'})
        print('per-app PUT ->', r.status_code, r.text[:200])
        print('per-app GET ->', {k: v for k, v in c.get_json(
            '/api/admin/workflows/probe-env/nextflow/').items() if k != 'variables'})
        j = c.submit_job('probe-env', name='probe-nf-app', params={'note': 'x'})
        helpers.wait_job_state(c, j['id'], ('success', 'failed'), timeout=180)
        for m in _messages(c, j['id']):
            print('  MSG:', m)
        stdout = (stack.home / 'jobs' / j['id'] / 'logs' / 'stdout.txt')
        print('  CMD:', stdout.read_text(errors='replace').splitlines()[:3])
    finally:
        _uninstall(c)
        server_settings.restore()


def test_global_work_dir(stack, api, server_settings, requires_worker, tmp_path):
    c = api('admin')
    print('install ->', _install(c).status_code)
    work = tmp_path / 'nf-work'
    try:
        r = c.put('/api/admin/settings/nextflow/', json={'work_dir': str(work), 'profile': ''})
        print('work_dir PUT ->', r.status_code)
        j = c.submit_job('probe-env', name='probe-nf-work', params={'note': 'x'})
        helpers.wait_job_state(c, j['id'], ('success', 'failed'), timeout=180)
        for m in _messages(c, j['id']):
            if 'WORKDIR' in m or 'PROFILE' in m:
                print('  MSG:', m)
        print('work dir created:', work.exists(), list(work.glob('*'))[:3])
    finally:
        _uninstall(c)
        server_settings.restore()


def test_bad_profile_and_binary(stack, api, server_settings, requires_worker):
    """A profile that does not exist / a nextflow binary that does not exist."""
    c = api('admin')
    print('install ->', _install(c).status_code)
    try:
        c.put('/api/admin/settings/nextflow/', json={'profile': 'doesnotexist', 'config': '',
                                                     'env': ''})
        j = c.submit_job('probe-env', name='probe-bad-profile', params={'note': 'x'})
        helpers.wait_job_state(c, j['id'], ('success', 'failed'), timeout=180)
        st = c.job_status(j['id'])
        print('bad profile -> state', st['state'], '|', st.get('error_message', '')[:200])

        binary = stack.read_settings()['nextflow']['binary']
        r = c.put('/api/admin/settings/nextflow/', json={'binary': '/nonexistent/nextflow',
                                                         'profile': ''})
        print('bad binary PUT ->', r.status_code)
        j2 = c.submit_job('probe-env', name='probe-bad-binary', params={'note': 'x'})
        helpers.wait_job_state(c, j2['id'], ('success', 'failed'), timeout=120)
        st2 = c.job_status(j2['id'])
        print('bad binary -> state', st2['state'], '|', st2.get('error_message', '')[:200])
        c.put('/api/admin/settings/nextflow/', json={'binary': binary})
        # the stack must still be healthy afterwards
        print('health:', stack.health()[1])
    finally:
        _uninstall(c)
        server_settings.restore()
