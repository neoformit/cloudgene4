"""Red tests for the T07c exploratory findings (admin, configuration & multi-user).

Every test here asserts the behaviour the SPEC (or plain sanity) asks for and is expected to
fail until the finding is fixed — see `plans/QA_FINDINGS.md` section "T07c". Remove the
`xfail` marker in the task that fixes the finding.
"""
import copy
import json
import os
import signal
import time

import pytest
import requests

from e2e import helpers
from e2e.helpers import ApiClient

pytestmark = pytest.mark.serial


@pytest.fixture
def keep_settings(stack):
    """Restore settings.yaml after the test (mtime bumped so the caches reload)."""
    original = copy.deepcopy(stack.read_settings())
    yield
    stack.write_settings(original)
    time.sleep(1.1)


@pytest.fixture
def restart_web(stack):
    """Restart the Django process; always restart it again with sane settings afterwards."""
    original = copy.deepcopy(stack.read_settings())

    def restart():
        proc = stack.procs['server']
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=30)
        port = stack.base_url.rsplit(':', 1)[1]
        stack._spawn('server', ['runserver', '127.0.0.1:%s' % port, '--noreload', '--insecure'])
        stack.wait_ready()

    yield restart
    stack.write_settings(original)
    time.sleep(1.1)
    restart()
    requests.get(stack.base_url + '/api/server/', timeout=10)


# ---------------------------------------------------------------------------------------------
# C-01 — a partial mail PUT bypasses the TLS/SSL mutual exclusion
# ---------------------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason='C-01: PUT /api/admin/settings/mail/ {use_ssl: true} '
                                       'alone leaves use_tls AND use_ssl true, which makes '
                                       'every SMTP mail fail')
def test_c01_mail_tls_and_ssl_cannot_both_be_enabled(stack, api, keep_settings):
    admin = api('admin')
    admin.put('/api/admin/settings/mail/', json={'use_tls': True, 'use_ssl': False})
    # The same pair in one request is rejected...
    both = admin.put('/api/admin/settings/mail/', json={'use_tls': True, 'use_ssl': True})
    assert both.status_code == 400
    # ...but ticking only SSL on top of the stored TLS is accepted.
    admin.put('/api/admin/settings/mail/', json={'use_ssl': True})
    mail = stack.read_settings()['mail']
    assert not (mail['use_tls'] and mail['use_ssl']), \
        'settings.yaml has use_tls and use_ssl both true: %s' % json.dumps(mail)


# ---------------------------------------------------------------------------------------------
# C-02 — one out-of-range value in settings.yaml takes the whole site down after a restart
# ---------------------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason='C-02: a single invalid value in settings.yaml makes '
                                       'every endpoint 500 once the web process restarts, '
                                       'while /api/health still reports "ok"')
def test_c02_invalid_settings_value_does_not_take_the_site_down(stack, restart_web):
    data = stack.read_settings()
    data['server']['max_running_jobs'] = 0          # valid YAML, outside the schema range
    stack.write_settings(data)
    restart_web()
    server = requests.get(stack.base_url + '/api/server/', timeout=10)
    health = requests.get(stack.base_url + '/api/health', timeout=10)
    assert health.json()['status'] != 'ok' or server.status_code == 200, (
        'GET /api/server/ -> %s while /api/health reports %s'
        % (server.status_code, health.json()))


# ---------------------------------------------------------------------------------------------
# C-03 — deleting a user leaves the workspace of their running job on disk
# ---------------------------------------------------------------------------------------------

def test_c03_deleting_user_removes_the_workspace_of_a_running_job(stack, api, requires_worker):
    import shutil

    admin = api('admin')
    uid = int(stack.django_shell(
        "from django.contrib.auth import get_user_model as g;"
        "u, _ = g().objects.get_or_create(username='c03victim',"
        " defaults={'email': 'c03victim@e2e.test', 'full_name': 'C03 Victim'});"
        "u.is_active = True; u.set_password('Probe1234'); u.save(); print(u.pk)"
    ).strip().splitlines()[-1])
    victim = ApiClient(stack.base_url)
    victim.login('c03victim', 'Probe1234')
    job = victim.submit_job('hello', name='C-03 victim job', params={'message': 'x'})
    workspace = stack.home / 'jobs' / job['id']
    try:
        helpers.wait_job_state(victim, job['id'], ('running',), timeout=120)
        assert workspace.is_dir()
        assert admin.delete('/api/admin/users/%d/' % uid).status_code == 204
        time.sleep(10)          # let the dying execution write again
        assert not workspace.exists(), \
            'workspace still on disk after the user was deleted: %s' % sorted(
                p.name for p in workspace.iterdir())
    finally:
        victim.close()
        shutil.rmtree(workspace, ignore_errors=True)
        stack.django_shell("from django.contrib.auth import get_user_model as g;"
                           "g().objects.filter(username='c03victim').delete()")


# ---------------------------------------------------------------------------------------------
# C-04 — log components do not match SPEC §3.8 (nothing is filed under "auth" or "jobs")
# ---------------------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason='C-04: authentication logs use the component "accounts" '
                                       'and job logs "worker", so the components named in '
                                       'SPEC §3.8 and in the Logs filter hint find nothing')
def test_c04_log_components_follow_the_spec(stack, api):
    admin = api('admin')
    anon = api()
    anon.get('/api/auth/me')
    anon.post('/api/auth/login/', json={'username': 'alice', 'password': 'definitely-wrong'})
    time.sleep(0.5)
    counts = {c: admin.get_json('/api/admin/logs/?component=%s&page_size=1' % c)['count']
              for c in ('auth', 'jobs')}
    present = sorted({row['component'] for row in
                      admin.get_json('/api/admin/logs/?page_size=200')['results']})
    assert counts['auth'] > 0, 'no log rows with component "auth"; present: %s' % present


# ---------------------------------------------------------------------------------------------
# C-05 — navbar URLs are not validated (a javascript: URL is stored and served to everyone)
# ---------------------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason='C-05: /api/admin/settings/navbar/ accepts any string as '
                                       'url (server.url is validated), so a javascript: URL is '
                                       'stored and rendered as an <a href> for every visitor')
def test_c05_navbar_url_is_validated(stack, api, keep_settings):
    admin = api('admin')
    r = admin.put('/api/admin/settings/navbar/',
                  json={'navbar': [{'title': 'Bad', 'url': 'javascript:alert(1)'}]})
    served = [i['url'] for i in api().get_json('/api/server/')['navbar']]
    assert r.status_code == 400, 'accepted; /api/server/ now serves %s' % served
