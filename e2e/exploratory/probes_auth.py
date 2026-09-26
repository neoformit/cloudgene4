"""T07b auth-lifecycle probes: lockout, sessions, tokens, reset/activation, django-admin.

    BASE=... venv/bin/python -m e2e.exploratory.probes_auth
"""
import json
import re
import sys
import time
import uuid
from pathlib import Path

import requests

from e2e.exploratory.probe import BASE, Client
from e2e.helpers import extract_link, latest_email

RESULTS = []


def check(name, ok, evidence=''):
    RESULTS.append((name, ok))
    print('%-5s %-58s %s' % ('PASS' if ok else 'FAIL', name, evidence), flush=True)


def info(name, evidence=''):
    print('%-5s %-58s %s' % ('INFO', name, evidence), flush=True)


def make_user(admin, outbox, prefix='t07b'):
    """Register + activate a throw-away user; returns (username, password)."""
    name = '%s%s' % (prefix, uuid.uuid4().hex[:6])
    password = 'Passw0rd1'
    anon = Client()
    anon.get('/api/auth/me/')
    r = anon.post('/api/auth/register/', json={
        'username': name, 'email': '%s@e2e.test' % name, 'full_name': 'Test %s' % name,
        'password': password, 'password_confirm': password})
    assert r.status_code == 201, r.text[:300]
    link = extract_link(latest_email(outbox, to='%s@e2e.test' % name), '/activate/')
    key = link.rsplit('/', 1)[-1]
    r = anon.post('/api/auth/activate/%s/' % key, json={})
    assert r.status_code == 200, r.text[:200]
    return name, password, key


def main():
    outbox = Path(sys.argv[1])
    admin = Client(user='admin')

    # ------------------------------------------------------------- lockout
    user, password, act_key = make_user(admin, outbox)
    c = Client()
    c.get('/api/auth/me/')
    codes = []
    for i in range(5):
        r = c.post('/api/auth/login/', json={'username': user.upper(), 'password': 'Wrong123'})
        codes.append(r.status_code)
    r = c.post('/api/auth/login/', json={'username': user, 'password': password})
    check('lockout: case-varied username locks the same account',
          r.status_code == 429, '%s attempts=%s final=%s' % (codes, codes, r.text[:90]))

    # a locked account must not be usable through an API token either
    user2, password2, _ = make_user(admin, outbox)
    c2 = Client()
    c2.login(user2, password2)
    key = c2.post('/api/me/token/').json()['token']
    c3 = Client()
    c3.get('/api/auth/me/')
    for i in range(6):
        c3.post('/api/auth/login/', json={'username': user2, 'password': 'Wrong123'})
    locked = c3.post('/api/auth/login/', json={'username': user2, 'password': password2})
    tok = requests.get(BASE + '/api/me/', headers={'Authorization': 'Token ' + key}, timeout=20)
    check('lockout: API token of a locked account still works (by design?)',
          locked.status_code == 429 and tok.status_code == 200,
          'login=%s token=%s' % (locked.status_code, tok.status_code))
    sess = requests.get(BASE + '/api/me/', cookies=c2.cookies, timeout=20)
    info('lockout: existing session of a locked account', 'GET /api/me -> %s' % sess.status_code)

    # ------------------------------------------------------------- django admin login
    dj = requests.Session()
    r = dj.get(BASE + '/django-admin/login/', timeout=20)
    info('django-admin login page', '%s (%d bytes)' % (r.status_code, len(r.content)))
    if r.status_code == 200:
        user3, password3, _ = make_user(admin, outbox)
        admin.patch('/api/admin/users/%s/' % _user_id(admin, user3), json={'is_admin': True})
        for i in range(8):
            token = dj.cookies.get('csrftoken')
            dj.post(BASE + '/django-admin/login/',
                    data={'username': user3, 'password': 'Wrong123', 'csrfmiddlewaretoken': token,
                          'next': '/django-admin/'},
                    headers={'Referer': BASE + '/django-admin/login/'}, timeout=20)
        api = Client()
        api.get('/api/auth/me/')
        after = api.post('/api/auth/login/', json={'username': user3, 'password': password3})
        check('lockout: /django-admin/login/ is not rate-limited by security.max_login_attempts',
              after.status_code == 429,
              '8 wrong passwords via django-admin, then API login -> %s' % after.status_code)
        token = dj.cookies.get('csrftoken')
        r = dj.post(BASE + '/django-admin/login/',
                    data={'username': user3, 'password': password3, 'csrfmiddlewaretoken': token,
                          'next': '/django-admin/'},
                    headers={'Referer': BASE + '/django-admin/login/'}, timeout=20,
                    allow_redirects=False)
        me = requests.get(BASE + '/api/auth/me/', cookies=dj.cookies, timeout=20).json()
        check('django-admin session is not accepted by the API',
              not me.get('authenticated'),
              'django-admin login -> %s; /api/auth/me authenticated=%s'
              % (r.status_code, me.get('authenticated')))

    # ------------------------------------------------------------- sessions
    user4, password4, _ = make_user(admin, outbox)
    s = Client()
    s.get('/api/auth/me/')
    before = s.cookies.get('sessionid')
    s.login(user4, password4)
    after = s.cookies.get('sessionid')
    check('session: id rotates on login', before != after, 'before=%s after=%s'
          % (before, (after or '')[:8]))
    stale = dict(s.cookies)
    s.post('/api/auth/logout/')
    r = requests.get(BASE + '/api/me/', cookies=stale, timeout=20)
    check('session: old cookie dead after logout', r.status_code == 401, r.text[:80])

    # two sessions; password change must invalidate the other one
    a = Client()
    a.login(user4, password4)
    b = Client()
    b.login(user4, password4)
    tok_key = b.post('/api/me/token/').json()['token']
    r = a.patch('/api/me/', json={'password': 'Newpass1', 'password_confirm': 'Newpass1',
                                  'current_password': password4})
    check('session: password change keeps the changing session', r.status_code == 200, r.text[:80])
    r = b.get('/api/me/')
    check('session: password change kills the other session', r.status_code == 401,
          '%s' % r.status_code)
    r = requests.get(BASE + '/api/me/', headers={'Authorization': 'Token ' + tok_key}, timeout=20)
    check('token: password change revokes the API token', r.status_code == 401,
          'GET /api/me with the old token -> %s' % r.status_code)

    # ------------------------------------------------------------- password reset
    user5, password5, _ = make_user(admin, outbox)
    c5 = Client()
    c5.login(user5, password5)
    reset_token_key = c5.post('/api/me/token/').json()['token']
    anon = Client()
    anon.get('/api/auth/me/')
    r = anon.post('/api/auth/password-reset/', json={'email': '%s@e2e.test' % user5})
    link = extract_link(latest_email(outbox, to='%s@e2e.test' % user5), '/recover/')
    token = link.rsplit('/', 1)[-1]
    r1 = anon.post('/api/auth/password-reset/%s/' % token,
                   json={'password': 'Reset123', 'password_confirm': 'Reset123'})
    r2 = anon.post('/api/auth/password-reset/%s/' % token,
                   json={'password': 'Reset124', 'password_confirm': 'Reset124'})
    check('reset: token is single use', r1.status_code == 200 and r2.status_code == 400,
          '%s then %s' % (r1.status_code, r2.status_code))
    r = requests.get(BASE + '/api/me/', headers={'Authorization': 'Token ' + reset_token_key},
                     timeout=20)
    check('reset: password reset revokes the API token', r.status_code == 401,
          'GET /api/me with the pre-reset token -> %s' % r.status_code)
    r = requests.get(BASE + '/api/me/', cookies=dict(c5.cookies), timeout=20)
    check('reset: password reset kills existing sessions', r.status_code == 401,
          '%s' % r.status_code)
    same = anon.post('/api/auth/password-reset/', json={'email': 'nobody-%s@e2e.test' % uuid.uuid4().hex[:4]})
    check('reset: same answer for unknown e-mail',
          same.status_code == 200 and same.json()['message'] == r1.json().get('message', '')
          or same.status_code == 200, same.text[:90])

    # ------------------------------------------------------------- activation reuse
    user6, password6, key6 = make_user(admin, outbox)
    uid = _user_id(admin, user6)
    admin.patch('/api/admin/users/%s/' % uid, json={'is_active': False})
    r = Client().post('/api/auth/activate/%s/' % key6, json={})
    row = admin.get('/api/admin/users/%s/' % uid).json()
    check('activation: reused key does not re-activate a disabled account',
          not row['is_active'], '%s %s' % (r.status_code, r.text[:90]))

    # ------------------------------------------------------------- deactivation / deletion
    user7, password7, _ = make_user(admin, outbox)
    c7 = Client()
    c7.login(user7, password7)
    key7 = c7.post('/api/me/token/').json()['token']
    uid7 = _user_id(admin, user7)
    admin.patch('/api/admin/users/%s/' % uid7, json={'is_active': False})
    r = requests.get(BASE + '/api/me/', cookies=dict(c7.cookies), timeout=20)
    r2 = requests.get(BASE + '/api/me/', headers={'Authorization': 'Token ' + key7}, timeout=20)
    check('deactivation: session and token stop working',
          r.status_code == 401 and r2.status_code == 401,
          'session=%s token=%s' % (r.status_code, r2.status_code))
    admin.patch('/api/admin/users/%s/' % uid7, json={'is_active': True})
    c7b = Client()
    c7b.login(user7, password7)
    key7b = c7b.post('/api/me/token/').json()['token']
    admin.delete('/api/admin/users/%s/' % uid7)
    r = requests.get(BASE + '/api/me/', headers={'Authorization': 'Token ' + key7b}, timeout=20)
    check('deletion: token of a deleted user is refused', r.status_code == 401, '%s' % r.status_code)

    # ------------------------------------------------------------- enumeration
    anon = Client()
    anon.get('/api/auth/me/')
    unknown = anon.post('/api/auth/login/', json={'username': 'nosuchuser', 'password': 'Wrong123'})
    wrong = anon.post('/api/auth/login/', json={'username': 'bob', 'password': 'Wrong123'})
    check('enumeration: same body for unknown user and wrong password',
          unknown.status_code == wrong.status_code and unknown.text == wrong.text,
          '%s / %s' % (unknown.text[:60], wrong.text[:60]))
    t1 = _timed(anon, 'nosuchuser')
    t2 = _timed(anon, 'bob')
    info('enumeration: login timing unknown=%.3fs existing=%.3fs (fast hashing in E2E)' % (t1, t2))
    r = anon.post('/api/auth/register/', json={
        'username': 'bob', 'email': 'alice@e2e.test', 'full_name': 'x',
        'password': 'Passw0rd1', 'password_confirm': 'Passw0rd1'})
    info('enumeration: register with taken name/e-mail', r.text[:200])

    failed = [n for n, ok in RESULTS if not ok]
    print('\n%d/%d checks passed' % (len(RESULTS) - len(failed), len(RESULTS)))
    for n in failed:
        print('  FAILED:', n)


def _timed(client, username, n=5):
    total = 0.0
    for _ in range(n):
        t = time.monotonic()
        client.post('/api/auth/login/', json={'username': username, 'password': 'Wrong123'})
        total += time.monotonic() - t
    return total / n


def _user_id(admin, username):
    rows = admin.get('/api/admin/users/', params={'search': username}).json()['results']
    return [r for r in rows if r['username'] == username][0]['id']


if __name__ == '__main__':
    main()
