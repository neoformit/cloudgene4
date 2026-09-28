"""T07b exploratory QA — security & access control (plans/QA_FINDINGS.md § T07b).

`test_permission_matrix` is green regression cover for the endpoint x role matrix; the other
tests are the red repros of B-01..B-05 and must be un-xfailed by whoever fixes them.
"""
import uuid

import pytest
import requests

from e2e.constants import USERS
from e2e.helpers import ApiClient

pytestmark = pytest.mark.filterwarnings('ignore::DeprecationWarning')


# -- shared, module-scoped clients / fixture data --------------------------------------------------

@pytest.fixture(scope='module')
def clients(stack):
    made = []

    def _client(user=None):
        c = ApiClient(stack.base_url)
        c.get('/api/auth/me/')
        if user:
            c.login(user)
        made.append(c)
        return c
    yield _client
    for c in made:
        c.close()


@pytest.fixture(scope='module')
def alice_job(clients):
    """A waiting job of alice's — enough for every permission check (no worker needed)."""
    alice = clients('alice')
    job = alice.submit_job('hello', name='T07b permission fixture', params={'message': 'secret'})
    yield job
    alice.post('/api/jobs/%s/cancel/' % job['id'])
    alice.delete('/api/jobs/%s/' % job['id'])


# -- green: endpoint x role permission matrix ------------------------------------------------------

ADMIN_ENDPOINTS = [
    ('GET', '/api/admin/dashboard/'),
    ('GET', '/api/admin/groups/'),
    ('POST', '/api/admin/groups/'),
    ('DELETE', '/api/admin/groups/1/'),
    ('GET', '/api/admin/jobs/'),
    ('POST', '/api/admin/jobs/{job}/cancel/'),
    ('POST', '/api/admin/jobs/{job}/restart/'),
    ('GET', '/api/admin/logs/'),
    ('POST', '/api/admin/maintenance/enter/'),
    ('POST', '/api/admin/maintenance/exit/'),
    ('GET', '/api/admin/pages/'),
    ('GET', '/api/admin/pages/about/'),
    ('PUT', '/api/admin/pages/about/'),
    ('DELETE', '/api/admin/pages/about/'),
    ('POST', '/api/admin/queue/pause/'),
    ('POST', '/api/admin/queue/resume/'),
    ('GET', '/api/admin/settings/general/'),
    ('PUT', '/api/admin/settings/general/'),
    ('GET', '/api/admin/settings/mail/'),
    ('PUT', '/api/admin/settings/mail/'),
    ('POST', '/api/admin/settings/mail/test/'),
    ('GET', '/api/admin/settings/navbar/'),
    ('PUT', '/api/admin/settings/navbar/'),
    ('GET', '/api/admin/settings/nextflow/'),
    ('PUT', '/api/admin/settings/nextflow/'),
    ('GET', '/api/admin/users/'),
    ('GET', '/api/admin/users/2/'),
    ('PATCH', '/api/admin/users/2/'),
    ('DELETE', '/api/admin/users/2/'),
    ('GET', '/api/admin/workflows/'),
    ('GET', '/api/admin/workflows/hello/'),
    ('PATCH', '/api/admin/workflows/hello/'),
    ('DELETE', '/api/admin/workflows/hello/'),
    ('GET', '/api/admin/workflows/hello/nextflow/'),
    ('PUT', '/api/admin/workflows/hello/nextflow/'),
    ('POST', '/api/admin/workflows/hello/reload/'),
    ('POST', '/api/admin/workflows/install/'),
    ('POST', '/api/admin/workflows/sync/'),
]

OWNED_ENDPOINTS = [
    ('GET', '/api/jobs/{job}/'),
    ('GET', '/api/jobs/{job}/status/'),
    ('GET', '/api/jobs/{job}/log/'),
    ('GET', '/api/jobs/{job}/outputs/1/'),
    ('POST', '/api/jobs/{job}/cancel/'),
    ('DELETE', '/api/jobs/{job}/'),
]

AUTH_ONLY_ENDPOINTS = [
    ('GET', '/api/jobs/'),
    ('POST', '/api/jobs/'),
    ('GET', '/api/me/'),
    ('PATCH', '/api/me/'),
    ('POST', '/api/me/token/'),
    ('DELETE', '/api/me/token/'),
    ('DELETE', '/api/me/'),
]

PUBLIC_ENDPOINTS = [
    ('GET', '/api/auth/me/'),
    ('GET', '/api/health/'),
    ('GET', '/api/server/'),
    ('GET', '/api/pages/about/'),
    ('GET', '/api/workflows/'),
    ('GET', '/api/workflows/hello/'),
]


def _call(client, method, path, job_id):
    path = path.replace('{job}', job_id)
    kwargs = {'json': {}} if method in ('POST', 'PUT', 'PATCH') else {}
    return client.request(method, path, **kwargs)


@pytest.mark.parametrize('method,path', ADMIN_ENDPOINTS)
def test_permission_matrix_admin_endpoints(clients, alice_job, method, path):
    """Anonymous -> 401 (never 403), a plain user -> 403 on every admin operation (SPEC §3.6)."""
    anon = clients()
    bob = clients('bob')
    r = _call(anon, method, path, alice_job['id'])
    assert r.status_code == 401, 'anon %s %s -> %s %s' % (method, path, r.status_code, r.text[:200])
    r = _call(bob, method, path, alice_job['id'])
    assert r.status_code == 403, 'bob %s %s -> %s %s' % (method, path, r.status_code, r.text[:200])
    assert r.json()['error']['code'] == 'permission_denied'


@pytest.mark.parametrize('method,path', OWNED_ENDPOINTS)
def test_permission_matrix_object_access(clients, alice_job, method, path):
    """Someone else's job: anonymous -> 401, another user -> 404 (never 403 — SPEC §3.6)."""
    anon = clients()
    bob = clients('bob')
    r = _call(anon, method, path, alice_job['id'])
    assert r.status_code == 401, '%s %s -> %s' % (method, path, r.status_code)
    r = _call(bob, method, path, alice_job['id'])
    assert r.status_code == 404, 'bob %s %s -> %s %s' % (method, path, r.status_code, r.text[:200])
    assert b'secret' not in r.content


@pytest.mark.parametrize('method,path', AUTH_ONLY_ENDPOINTS)
def test_permission_matrix_requires_authentication(clients, method, path):
    r = _call(clients(), method, path, '')
    assert r.status_code == 401, '%s %s -> %s' % (method, path, r.status_code)
    assert r.headers.get('WWW-Authenticate', '').startswith('Token')


@pytest.mark.parametrize('method,path', PUBLIC_ENDPOINTS)
def test_permission_matrix_public(clients, method, path):
    r = _call(clients(), method, path, '')
    assert r.status_code == 200, '%s %s -> %s' % (method, path, r.status_code)


def test_foreign_output_id_under_own_job(clients, alice_job):
    """B-0 regression: alice's JobOutput id addressed through bob's own job is a 404."""
    bob = clients('bob')
    job = bob.submit_job('hello', name='T07b bob job', params={'message': 'hi'})
    try:
        alice = clients('alice')
        outputs = alice.get_json('/api/jobs/%s/' % alice_job['id'])['outputs']
        file_id = outputs[0]['id'] if outputs else 1
        r = bob.get('/api/jobs/%s/outputs/%s/' % (job['id'], file_id))
        assert r.status_code == 404, r.text[:200]
    finally:
        bob.post('/api/jobs/%s/cancel/' % job['id'])
        bob.delete('/api/jobs/%s/' % job['id'])


# -- red repros ------------------------------------------------------------------------------------

def _make_staff_user(stack, username, password):
    stack.django_shell(
        "from django.contrib.auth import get_user_model\n"
        "U = get_user_model()\n"
        "u = U.objects.filter(username__iexact=%r).first() or U(username=%r, email=%r,"
        " full_name='T07b staff')\n"
        "u.is_staff = True\n"
        "u.is_active = True\n"
        "u.login_attempts = 0\n"
        "u.locked_until = None\n"
        "u.set_password(%r)\n"
        "u.save()\n" % (username, username, username + '@e2e.test', password))


def _django_admin_login(base_url, username, password):
    s = requests.Session()
    s.get(base_url + '/django-admin/login/', timeout=20)
    r = s.post(base_url + '/django-admin/login/',
               data={'username': username, 'password': password,
                     'csrfmiddlewaretoken': s.cookies.get('csrftoken'), 'next': '/django-admin/'},
               headers={'Referer': base_url + '/django-admin/login/'}, timeout=20,
               allow_redirects=False)
    return s, r


@pytest.mark.serial
@pytest.mark.xfail(strict=True, reason='B-01: /django-admin/login/ ignores the lockout and its '
                                       'session is accepted by the API')
def test_b01_django_admin_login_bypasses_lockout(stack, clients):
    username, password = 't07bstaff', 'Staff1234'
    _make_staff_user(stack, username, password)
    anon = clients()
    attempts = int(stack.read_settings()['security']['max_login_attempts']) + 1
    for _ in range(attempts):
        anon.post('/api/auth/login/', json={'username': username, 'password': 'Wrong123'})
    locked = anon.post('/api/auth/login/', json={'username': username, 'password': password})
    assert locked.status_code == 429, 'account should be locked, got %s' % locked.status_code

    session, response = _django_admin_login(stack.base_url, username, password)
    me = requests.get(stack.base_url + '/api/auth/me/', cookies=session.cookies, timeout=20).json()
    assert not me['authenticated'], (
        'a locked account logged in at /django-admin/login/ (%s) and the API accepted the session '
        'as %s' % (response.status_code, me.get('user', {}).get('username')))


@pytest.mark.xfail(strict=True, reason='B-02: the API token survives a password change / reset')
def test_b02_password_change_revokes_api_token(stack, clients):
    username, password = 't07btoken%s' % uuid.uuid4().hex[:6], 'Passw0rd1'
    stack.django_shell(
        "from django.contrib.auth import get_user_model\n"
        "U = get_user_model()\n"
        "u = U(username=%r, email=%r, full_name='T07b token', is_active=True)\n"
        "u.set_password(%r)\n"
        "u.save()\n" % (username, username + '@e2e.test', password))
    c = ApiClient(stack.base_url)
    c.get('/api/auth/me/')
    c.login(username, password)
    key = c.post_json('/api/me/token/')['token']
    r = c.patch('/api/me/', json={'password': 'Newpass1', 'password_confirm': 'Newpass1',
                                  'current_password': password})
    assert r.status_code == 200, r.text[:200]
    after = requests.get(stack.base_url + '/api/me/',
                         headers={'Authorization': 'Token ' + key}, timeout=20)
    c.close()
    assert after.status_code == 401, (
        'the API token created before the password change still works (%s)' % after.status_code)


@pytest.mark.xfail(strict=True, reason="B-03: /django-admin/ shows every user's API token key")
def test_b03_token_keys_not_readable_in_django_admin(stack, clients):
    alice = clients('alice')
    key = alice.post_json('/api/me/token/')['token']
    session, _ = _django_admin_login(stack.base_url, 'admin', USERS['admin']['password'])
    page = requests.get(stack.base_url + '/django-admin/authtoken/tokenproxy/',
                        cookies=session.cookies, timeout=20)
    alice.delete('/api/me/token/')
    assert key not in page.text, "alice's token key is printed in the Django admin token list"


@pytest.mark.xfail(strict=True, reason='B-04: ?inline=1 serves a job output as text/html on the '
                                       'application origin')
def test_b04_html_output_not_served_as_active_content(stack, clients):
    """Seed a finished job whose output is an .html file, then download it inline."""
    payload = '<script>window.__t07b=1</script>'
    out = stack.django_shell(
        "import uuid\n"
        "from django.contrib.auth import get_user_model\n"
        "from django.utils import timezone\n"
        "from core import config\n"
        "from jobs.models import Job, JobOutput, JobState\n"
        "u = get_user_model().objects.get(username='alice')\n"
        "jid = uuid.uuid4()\n"
        "ws = config.job_dir(jid) / 'output' / 'outdir'\n"
        "ws.mkdir(parents=True, exist_ok=True)\n"
        "(ws / 'report.html').write_text('<html><body>%s</body></html>')\n"
        "j = Job.objects.create(id=jid, name='T07b html output', user=u, app_id='hello',\n"
        "    app_name='Hello', status=JobState.SUCCESS, finished_at=timezone.now())\n"
        "o = JobOutput.objects.create(job=j, output_id='outdir', path='outdir/report.html',\n"
        "    size=(ws / 'report.html').stat().st_size)\n"
        "print('%%s %%s' %% (jid, o.pk))\n" % payload)
    job_id, file_id = out.strip().splitlines()[-1].split()
    alice = clients('alice')
    try:
        r = alice.get('/api/jobs/%s/outputs/%s/?inline=1' % (job_id, file_id))
        assert r.status_code == 200, r.text[:200]
        ctype = r.headers.get('Content-Type', '')
        assert 'html' not in ctype.lower(), (
            'output served as %r inline; payload present: %s' % (ctype, payload in r.text))
    finally:
        stack.django_shell("from jobs.models import Job\n"
                           "Job.objects.filter(pk=%r).delete()\n" % job_id)


def test_b05_file_upload_for_text_input_rejected(stack, clients):
    import io
    alice = clients('alice')
    r = alice.post('/api/jobs/', data={'workflow': 'hello'},
                   files={'message': ('sneaky-name.txt', io.BytesIO(b'content'))})
    if r.status_code == 201:
        alice.delete('/api/jobs/%s/' % r.json()['id'])
        value = [i for i in r.json()['inputs'] if i['id'] == 'message'][0]['value']
        pytest.fail('a file part satisfied the required text input; value=%r' % value)
    assert r.status_code == 400, r.text[:200]
    assert 'message' in r.json()['error']['fields']
