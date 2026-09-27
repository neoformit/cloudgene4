"""T07c probe 8: mail misconfiguration, server.name/url in mails, upload limit."""
import time

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial


def _register(anon, username):
    return anon.post('/api/auth/register/', json={
        'username': username, 'email': '%s@e2e.test' % username,
        'full_name': 'Probe %s' % username, 'password': 'Probe1234',
        'password_confirm': 'Probe1234'})


def test_server_name_and_url_in_mails(stack, api, server_settings):
    c = api('admin')
    c.put('/api/admin/settings/general/', json={'name': 'Probe Service',
                                                'url': 'https://probe.example.org'})
    anon = api()
    r = _register(anon, 'probemailurl')
    print('register ->', r.status_code)
    msg = helpers.latest_email(stack.outbox_dir, to='probemailurl@e2e.test')
    print('subject:', msg['Subject'])
    print('link:', helpers.extract_link(msg, '/activate/'))
    server_settings.restore()


def test_mail_tls_ssl_both_true_breaks_mail(stack, api, server_settings):
    """A partial PUT can leave use_tls AND use_ssl true (the combined form rejects it)."""
    c = api('admin')
    r = c.put('/api/admin/settings/mail/', json={'use_tls': True, 'use_ssl': True})
    print('both in one PUT ->', r.status_code, r.text[:160])
    r = c.put('/api/admin/settings/mail/', json={'use_ssl': True})
    print('only use_ssl ->', r.status_code)
    print('yaml:', {k: v for k, v in stack.read_settings()['mail'].items()
                    if k.startswith('use_')})
    print('GET shows:', {k: v for k, v in c.get_json('/api/admin/settings/mail/').items()
                         if k.startswith('use_')})
    c.put('/api/admin/settings/mail/', json={'backend': 'smtp'})
    t = c.post('/api/admin/settings/mail/test/', json={'to': 'probe@e2e.test'})
    print('test mail with smtp+tls+ssl ->', t.status_code, t.text[:250])
    anon = api()
    r = _register(anon, 'probebroken')
    print('register with broken mail ->', r.status_code, r.text[:250])
    exists = stack.django_shell("from django.contrib.auth import get_user_model as g;"
                                "print(g().objects.filter(username='probebroken').count())")
    print('user created?', exists.strip().splitlines()[-1])
    r = anon.post('/api/auth/password-reset/', json={'email': 'alice@e2e.test'})
    print('password reset with broken mail ->', r.status_code, r.text[:160])
    server_settings.restore()
    time.sleep(1.1)
    print('after restore, test mail ->',
          c.post('/api/admin/settings/mail/test/', json={'to': 'probe@e2e.test'}).status_code)


def test_mail_clear_password(stack, api, server_settings):
    c = api('admin')
    c.put('/api/admin/settings/mail/', json={'password': 'topsecret'})
    print('password_set:', c.get_json('/api/admin/settings/mail/')['password_set'])
    body = c.get('/api/admin/settings/mail/').text
    print('password leaked in GET?', 'topsecret' in body)
    c.put('/api/admin/settings/mail/', json={'host': 'other.host'})
    print('after unrelated PUT, password still set:',
          c.get_json('/api/admin/settings/mail/')['password_set'],
          '| yaml:', stack.read_settings()['mail']['password'])
    c.put('/api/admin/settings/mail/', json={'clear_password': True})
    print('after clear:', c.get_json('/api/admin/settings/mail/')['password_set'])
    server_settings.restore()


def test_max_upload_mb_enforced(stack, api, server_settings, tmp_path):
    c = api('alice')
    big = tmp_path / 'big.csv'
    big.write_bytes(b'a,b\n' + b'x' * (3 * 1024 * 1024))
    data = {'workflow': 'all-inputs', 'job_name': 'probe-upload', 'text_in': 't',
            'number_in': '5', 'terms': 'true', 'choice': 'b', 'mode': 'fast', 'flag': 'true'}
    server_settings.update('server', max_upload_mb=1)
    with open(big, 'rb') as fh:
        r = c.post('/api/jobs/', data=data, files=[('data_file', ('big.csv', fh))])
    print('3MB with max_upload_mb=1 ->', r.status_code, r.text[:220])
    jobs_dir = stack.home / 'jobs'
    print('workspaces on disk:', len(list(jobs_dir.glob('*'))))
    server_settings.update('server', max_upload_mb=50)
    with open(big, 'rb') as fh:
        r = c.post('/api/jobs/', data=dict(data, job_name='probe-upload-ok'),
                   files=[('data_file', ('big.csv', fh))])
    print('3MB with max_upload_mb=50 ->', r.status_code, r.text[:160])
    if r.status_code < 300:
        c.post('/api/jobs/%s/cancel/' % r.json()['id'])
        c.delete('/api/jobs/%s/' % r.json()['id'])
    server_settings.restore()


def test_log_components(stack, api):
    """SPEC §3.8 names cloudgene.auth / cloudgene.jobs; what does Logs really show?"""
    c = api('admin')
    anon = api()
    anon.get('/api/auth/me')
    anon.post('/api/auth/login/', json={'username': 'alice', 'password': 'nope'})
    j = c.submit_job('hello', name='probe-log-job', params={'message': 'x'})
    time.sleep(2)
    rows = c.get_json('/api/admin/logs/?page_size=200')['results']
    seen = sorted({r['component'] for r in rows})
    print('components present:', seen)
    for comp in ('auth', 'accounts', 'jobs', 'worker', 'admin', 'workflows', 'api'):
        n = c.get_json('/api/admin/logs/?component=%s' % comp)['count']
        print('  filter component=%-10s -> %d' % (comp, n))
    print('job-related messages:', [r['message'][:70] for r in rows
                                    if 'ob ' in r['message']][:5])
    c.post('/api/jobs/%s/cancel/' % j['id'])
