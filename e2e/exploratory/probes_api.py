"""T07b API security probes: CSRF, privilege escalation, IDOR, traversal, secrets, DoS-ish.

    BASE=... venv/bin/python -m e2e.exploratory.probes_api ids.json

Every check prints ``PASS``/``FAIL``/``INFO`` plus the evidence; nothing is destructive except
what it creates itself (throw-away users/jobs).
"""
import json
import sys
import uuid
from pathlib import Path

import requests

from e2e.exploratory.probe import BASE, Client

RESULTS = []


def check(name, ok, evidence=''):
    RESULTS.append((name, ok))
    print('%-5s %-58s %s' % ('PASS' if ok else 'FAIL', name, evidence), flush=True)


def info(name, evidence=''):
    print('%-5s %-58s %s' % ('INFO', name, evidence), flush=True)


def main():
    ids = json.loads(Path(sys.argv[1]).read_text())
    job = ids['alice_job']
    out_id = ids['alice_output']
    alice, bob, admin = Client(user='alice'), Client(user='bob'), Client(user='admin')
    anon = Client()
    anon.get('/api/auth/me/')

    # ---------------------------------------------------------------- CSRF
    r = bob.post('/api/me/token/', csrf=False)
    check('csrf: POST without X-CSRFToken refused', r.status_code == 403, r.text[:120])
    r = bob.post('/api/me/token/', headers={'X-CSRFToken': 'wrong'}, csrf=False)
    check('csrf: POST with wrong token refused', r.status_code == 403, r.text[:120])
    r = bob.patch('/api/me/', json={'full_name': 'x'}, headers={'Origin': 'http://evil.example'})
    check('csrf: cross-origin Origin refused', r.status_code == 403, r.text[:120])
    r = anon.post('/api/auth/login/', json={'username': 'bob', 'password': 'Bob12345'}, csrf=False)
    check('csrf: login without token refused', r.status_code == 403, r.text[:120])
    r = bob.post('/api/auth/logout/', csrf=False)
    check('csrf: logout without token refused', r.status_code == 403, r.text[:120])
    bob = Client(user='bob')

    # token auth must be CSRF exempt
    key = bob.post('/api/me/token/').json()['token']
    tok = Client(token=key)
    r = tok.patch('/api/me/', json={'full_name': 'Bob Nogroup'})
    check('csrf: token auth exempt (no cookie, no header)', r.status_code == 200, r.text[:120])
    r = tok.get('/api/jobs/%s/' % job)
    check('token auth: still object-scoped (alice job hidden)', r.status_code == 404, r.text[:80])

    # ---------------------------------------------------------- privilege escalation
    payload = {'is_staff': True, 'is_superuser': True, 'is_active': True, 'is_admin': True,
               'groups': ['admin'], 'username': 'root', 'user': {'is_superuser': True},
               'full_name': 'Bob Nogroup'}
    r = bob.patch('/api/me/', json=payload)
    me = bob.get('/api/me/').json()
    check('escalation: self-PATCH privilege fields ignored',
          r.status_code == 200 and me['username'] == 'bob' and not me['is_admin']
          and me['groups'] == [], json.dumps(me))
    raw = requests.get(BASE + '/api/admin/users/%s/' % ids['users']['bob'],
                       headers={'Authorization': 'Token ' + key}, timeout=20)
    check('escalation: admin user row hidden from token auth', raw.status_code == 403,
          raw.text[:100])

    uname = 'evil%s' % uuid.uuid4().hex[:6]
    r = anon.post('/api/auth/register/', json={
        'username': uname, 'email': '%s@e2e.test' % uname, 'full_name': 'Evil User',
        'password': 'Passw0rd', 'password_confirm': 'Passw0rd',
        'is_staff': True, 'is_superuser': True, 'is_active': True, 'groups': ['admin']})
    created = r.json().get('user', {}) if r.status_code == 201 else {}
    check('escalation: register cannot set privileges',
          r.status_code == 201 and not created.get('is_admin') and created.get('groups') == []
          and created.get('is_active') is False, '%s %s' % (r.status_code, r.text[:160]))

    # admin PATCH must not hand out the admin group through `groups`
    r = admin.patch('/api/admin/users/%s/' % ids['users']['bob'], json={'groups': ['admin']})
    check('escalation: admin `groups` cannot add the admin group',
          r.status_code == 200 and 'admin' not in r.json()['groups'] and not r.json()['is_admin'],
          r.text[:160])

    # ---------------------------------------------------------------- IDOR
    r = bob.get('/api/jobs/%s/outputs/%s/' % (ids['bob_job'], out_id))
    check("idor: alice's output id under bob's job -> 404", r.status_code == 404, r.text[:80])
    for path in ('/api/jobs/%s/' % job, '/api/jobs/%s/status/' % job, '/api/jobs/%s/log/' % job,
                 '/api/jobs/%s/outputs/%s/' % (job, out_id)):
        r = bob.get(path)
        check('idor: bob GET %s -> 404' % path.replace(job, '<alice job>'), r.status_code == 404,
              r.text[:80])
    r = bob.post('/api/jobs/%s/cancel/' % job)
    check('idor: bob cancel alice job -> 404', r.status_code == 404, r.text[:80])
    r = bob.delete('/api/jobs/%s/' % job)
    check('idor: bob delete alice job -> 404', r.status_code == 404, r.text[:80])
    r = bob.post('/api/admin/jobs/%s/restart/' % job)
    check('idor: bob restart alice job -> 403', r.status_code == 403, r.text[:80])
    r = bob.get('/api/jobs/?user=%s' % ids['users']['alice'])
    body = r.json()
    check('idor: ?user= on own job list is ignored',
          all(j['user']['username'] == 'bob' for j in body['results']),
          '%d jobs' % body['count'])
    r = bob.get('/api/jobs/%s/' % uuid.uuid4())
    check('idor: unknown job uuid -> 404', r.status_code == 404, r.text[:80])
    r = bob.get('/api/jobs/not-a-uuid/')
    check('idor: malformed job id -> 404', r.status_code == 404, r.text[:80])

    # ---------------------------------------------------------------- traversal
    for slug in ('..%2f..%2fconfig%2fsettings', '%2e%2e%2f%2e%2e%2fconfig%2fsecret_key',
                 '....//config/secret_key', 'home%00', '/etc/passwd', 'HOME', 'home.html'):
        r = anon.get('/api/pages/%s/' % slug)
        ok = r.status_code == 404 or (r.status_code == 200 and 'E2E-HOME-MARKER' not in r.text
                                      and 'secret' not in r.text.lower())
        check('traversal: /api/pages/%s -> no file leak' % slug, ok,
              '%s %s' % (r.status_code, r.text[:60]))
    for slug in ('../../config/secret_key', '..%2f..%2fconfig%2fsecret_key', 'nope'):
        r = admin.put('/api/admin/pages/%s/' % slug, json={'html': '<b>x</b>'})
        check('traversal: admin PUT page %r stays inside pages/' % slug,
              r.status_code in (400, 404) or slug == 'nope', '%s %s' % (r.status_code, r.text[:80]))
    admin.delete('/api/admin/pages/nope/')
    r = alice.get('/api/jobs/%s/outputs/999999/' % job)
    check('traversal: unknown output id -> 404', r.status_code == 404, r.text[:80])
    r = alice.get('/api/jobs/%s/outputs/-1/' % job)
    check('traversal: negative output id -> 404', r.status_code == 404, r.text[:80])

    # ---------------------------------------------------------------- secrets
    admin.put('/api/admin/settings/mail/', json={'backend': 'file', 'file_path': 'mail',
                                                 'from_email': 'noreply@e2e.test',
                                                 'password': 'sup3rs3cret-smtp'})
    body = admin.get('/api/admin/settings/mail/').text
    check('secrets: mail password never returned',
          'sup3rs3cret-smtp' not in body and '"password_set": true' in body.replace(' ', ' '),
          body[:200])
    logs = admin.get('/api/admin/logs/?page_size=200').text
    check('secrets: mail password not in the admin log', 'sup3rs3cret-smtp' not in logs)
    check('secrets: passwords not in the admin log',
          'Bob12345' not in logs and 'Alice1234' not in logs)
    admin.put('/api/admin/settings/mail/', json={'backend': 'file', 'file_path': 'mail',
                                                 'from_email': 'noreply@e2e.test',
                                                 'clear_password': True})
    prof = bob.get('/api/me/').text
    check('secrets: profile has no token key / hashes',
          'api_token' in prof and key not in prof, prof[:160])
    r = bob.get('/api/workflows/')
    check('secrets: public workflow list has no filesystem paths',
          'yaml_path' not in r.text and '/apps/' not in r.text, r.text[:120])
    r = anon.get('/api/health/')
    info('health payload (public)', r.text[:160])
    r = anon.get('/api/nosuchendpoint/')
    check('errors: unknown /api path -> JSON 404 envelope',
          r.status_code == 404 and r.json().get('error', {}).get('code') == 'not_found',
          r.text[:120])
    r = anon.post('/api/auth/login/', data='{bad json', headers={'Content-Type': 'application/json'})
    check('errors: broken JSON -> 400, no traceback',
          r.status_code == 400 and 'Traceback' not in r.text, r.text[:120])

    # ---------------------------------------------------------------- injection
    for term in ("' OR 1=1--", '" OR ""="', '%', '_', "\\", "'); DROP TABLE jobs;--"):
        r = admin.get('/api/admin/users/', params={'search': term})
        r2 = admin.get('/api/admin/jobs/', params={'search': term})
        check('sqli: search %r handled' % term,
              r.status_code == 200 and r2.status_code == 200,
              '%s/%s' % (r.status_code, r2.status_code))
    r = admin.get('/api/admin/jobs/', params={'user': "1 OR 1=1"})
    check('sqli: admin jobs ?user= non-numeric handled', r.status_code == 200, r.text[:100])

    # ---------------------------------------------------------------- pagination / limits
    r = bob.get('/api/jobs/?page_size=100000')
    check('limits: page_size capped', r.status_code == 200 and len(r.json()['results']) <= 200,
          'results=%d' % len(r.json()['results']))
    r = admin.get('/api/admin/logs/?page_size=100000')
    check('limits: admin log page_size capped',
          r.status_code == 200 and len(r.json()['results']) <= 200,
          'results=%d' % len(r.json()['results']))
    deep = json.loads('{"a":' * 200 + '1' + '}' * 200)
    r = bob.patch('/api/me/', json=deep)
    check('limits: deeply nested JSON -> 4xx, no 500', 400 <= r.status_code < 500,
          '%s %s' % (r.status_code, r.text[:80]))
    r = bob.patch('/api/me/', json={'full_name': 'x' * 100000})
    check('limits: very long full_name rejected', r.status_code == 400, r.text[:120])
    r = bob.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'n' * 5000,
                                     'message': 'hi'})
    check('limits: over-long job name rejected', r.status_code == 400, r.text[:120])

    # ---------------------------------------------------------------- workflow access
    for wf in ('all-inputs', 'fail', 'slow', 'multi-process'):
        r = bob.post('/api/jobs/', data={'workflow': wf, 'message': 'x'})
        check('access: bob cannot submit %r' % wf, r.status_code == 404, r.text[:100])
        r = bob.get('/api/workflows/%s/' % wf)
        check('access: bob cannot read %r definition' % wf, r.status_code == 404, r.text[:80])

    failed = [n for n, ok in RESULTS if not ok]
    print('\n%d/%d checks passed' % (len(RESULTS) - len(failed), len(RESULTS)))
    for n in failed:
        print('  FAILED:', n)


if __name__ == '__main__':
    main()
