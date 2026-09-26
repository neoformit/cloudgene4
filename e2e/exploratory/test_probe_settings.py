"""T07c probe 1: admin settings round-trips and validation."""
import json

import pytest


def test_general_roundtrip(stack, api, server_settings):
    c = api('admin')
    before = c.get_json('/api/admin/settings/general/')
    print('GENERAL GET:', json.dumps(before, indent=1))
    payload = {'name': 'Probe Servis OK', 'url': 'http://127.0.0.1:1/', 'max_running_jobs': 3,
               'max_queue_size': 9, 'job_retention_days': 3, 'max_upload_mb': 7,
               'maintenance': False, 'maintenance_message': 'msg unicode ✓'}
    r = c.put('/api/admin/settings/general/', json=payload)
    print('PUT ->', r.status_code, r.text[:400])
    after = c.get_json('/api/admin/settings/general/')
    print('GENERAL after:', json.dumps(after, indent=1))
    print('YAML server:', json.dumps(stack.read_settings()['server'], indent=1))
    srv = c.get_json('/api/server/')
    print('PUBLIC /api/server name:', srv['name'])


@pytest.mark.parametrize('field,value', [
    ('max_running_jobs', 0), ('max_running_jobs', -1), ('max_running_jobs', 10**9),
    ('max_running_jobs', 'abc'), ('max_running_jobs', 2.5), ('max_running_jobs', None),
    ('max_queue_size', -5), ('job_retention_days', -1), ('max_upload_mb', 0),
    ('max_upload_mb', 10**12), ('name', ''), ('name', 'x' * 300), ('url', 'ftp://x'),
    ('url', 'javascript:alert(1)'), ('maintenance', 'yes'), ('maintenance_message', ''),
])
def test_general_invalid(stack, api, server_settings, field, value):
    c = api('admin')
    r = c.put('/api/admin/settings/general/', json={field: value})
    print('PUT %s=%r -> %s %s' % (field, value, r.status_code, r.text[:200]))
    h = c.get('/api/admin/settings/general/')
    print('   reread ->', h.status_code, h.text[:160])
    print('   yaml   ->', stack.read_settings()['server'].get(field))


def test_mail_roundtrip(stack, api, server_settings):
    c = api('admin')
    print('MAIL GET:', c.get_json('/api/admin/settings/mail/'))
    r = c.put('/api/admin/settings/mail/', json={'backend': 'file', 'file_path': 'mail',
                                                 'host': 'mail.example.org', 'port': 2525,
                                                 'user': 'u', 'password': 's3cret',
                                                 'use_tls': True, 'use_ssl': False,
                                                 'from_email': 'probe@e2e.test'})
    print('PUT ->', r.status_code, r.text[:300])
    print('MAIL after:', c.get_json('/api/admin/settings/mail/'))
    print('YAML mail:', stack.read_settings()['mail'])


def test_mail_tls_ssl_conflict(stack, api, server_settings):
    """use_tls is already true in the file; PUT only use_ssl -> both true?"""
    c = api('admin')
    r = c.put('/api/admin/settings/mail/', json={'use_tls': True})
    print('set tls ->', r.status_code)
    r = c.put('/api/admin/settings/mail/', json={'use_ssl': True})
    print('set ssl only ->', r.status_code, r.text[:300])
    print('YAML mail:', stack.read_settings()['mail'])


def test_nextflow_roundtrip(stack, api, server_settings):
    c = api('admin')
    before = c.get_json('/api/admin/settings/nextflow/')
    print('NF GET keys:', sorted(before))
    r = c.put('/api/admin/settings/nextflow/', json={
        'binary': before['binary'], 'profile': 'probeprofile', 'work_dir': '',
        'config': '// probe marker\nparams.probe_global = "yes"\n',
        'env': 'PROBE_GLOBAL=hello-global\n'})
    print('PUT ->', r.status_code, r.text[:200])
    after = c.get_json('/api/admin/settings/nextflow/')
    print('profile:', after['profile'], '| config:', repr(after['config']),
          '| env:', repr(after['env']))
    print('YAML nextflow:', stack.read_settings()['nextflow'])


def test_navbar_roundtrip(stack, api, server_settings):
    c = api('admin')
    nav = c.get_json('/api/admin/settings/navbar/')['navbar']
    print('NAVBAR:', nav)
    items = nav + [{'title': 'Probe item', 'url': '/pages/nope', 'icon': '',
                    'admin_only': False, 'auth_only': True}]
    r = c.put('/api/admin/settings/navbar/', json={'navbar': items})
    print('PUT ->', r.status_code, r.text[:200])
    for user in (None, 'bob', 'admin'):
        cc = api(user) if user else api()
        print('  /api/server as %s:' % user,
              [i['title'] for i in cc.get_json('/api/server/')['navbar']])
    for bad in ([{'title': '', 'url': '/x'}], [{'url': '/x'}], [{'title': 't'}],
                [{'title': 't', 'url': 'javascript:alert(1)'}], 'notalist'):
        r = c.put('/api/admin/settings/navbar/', json={'navbar': bad})
        print('  bad %r -> %s %s' % (bad, r.status_code, r.text[:140]))
