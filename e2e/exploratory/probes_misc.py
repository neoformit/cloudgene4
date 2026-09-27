"""T07b misc probes: cookie flags, security headers, error handling with DEBUG off,
upload limits, unpaginated lists, admin-only file reach, cross-user data in payloads.

    BASE=... venv/bin/python -m e2e.exploratory.probes_misc <CLOUDGENE_HOME>
"""
import io
import json
import sys
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
    home = Path(sys.argv[1])
    alice, admin = Client(user='alice'), Client(user='admin')
    anon = Client()
    anon.get('/api/auth/me/')

    # --- cookies & headers
    s = requests.Session()
    s.get(BASE + '/api/auth/me/', timeout=20)
    r = s.post(BASE + '/api/auth/login/', json={'username': 'alice', 'password': 'Alice1234'},
               headers={'X-CSRFToken': s.cookies.get('csrftoken'), 'Referer': BASE + '/'},
               timeout=20)
    raw = '; '.join(r.raw.headers.getlist('Set-Cookie'))
    check('cookies: sessionid HttpOnly + SameSite', 'HttpOnly' in raw and 'SameSite=Lax' in raw,
          raw[:200])
    spa = requests.get(BASE + '/jobs', timeout=20)
    info('SPA headers', json.dumps({k: v for k, v in spa.headers.items()
                                    if k.lower().startswith(('x-', 'referrer', 'content-sec',
                                                             'strict'))}))
    check('headers: clickjacking + sniffing protection on the SPA',
          spa.headers.get('X-Frame-Options') == 'DENY'
          and spa.headers.get('X-Content-Type-Options') == 'nosniff', '')
    check('headers: no Content-Security-Policy (hardening gap)',
          'Content-Security-Policy' not in spa.headers,
          'CSP=%s' % spa.headers.get('Content-Security-Policy'))

    # --- error handling with DEBUG off
    for path, params in (('/api/jobs/', {'page': 'abc'}), ('/api/jobs/', {'page': '999999'}),
                         ('/api/jobs/', {'page_size': '-1'}), ('/api/jobs/', {'state': 'bogus'}),
                         ('/api/admin/logs/', {'min_level': 'bogus'}),
                         ('/api/admin/users/', {'is_active': 'maybe'}),
                         ('/api/workflows/', {'category': "' OR 1=1--"})):
        c = admin if path.startswith('/api/admin') else alice
        r = c.get(path, params=params)
        ok = r.status_code < 500 and 'Traceback' not in r.text and 'DJANGO_SETTINGS' not in r.text
        check('errors: %s %s -> %s, no traceback' % (path, params, r.status_code), ok, r.text[:90])

    r = alice.post('/api/jobs/', data={'workflow': 'hello'},
                   files={'message': ('x.txt', io.BytesIO(b'x'))})
    check('errors: file sent for a text input -> 4xx', 400 <= r.status_code < 500, r.text[:100])
    r = alice.post('/api/jobs/', data={'workflow': 'hello', 'message': 'x' * 200000})
    check('errors: oversized text input rejected', r.status_code == 400, r.text[:100])
    r = requests.post(BASE + '/api/auth/register/', data=b'x' * (11 * 1024 * 1024),
                      headers={'Content-Type': 'application/json', 'Referer': BASE + '/'},
                      timeout=60)
    check('limits: 11 MB JSON body rejected (DATA_UPLOAD_MAX_MEMORY_SIZE)',
          r.status_code in (400, 403, 413), '%s %s' % (r.status_code, r.text[:80]))

    # --- unpaginated list + page_size on it
    r = admin.get('/api/admin/groups/?page_size=100000')
    check('limits: groups list unpaginated array', isinstance(r.json(), list), r.text[:80])

    # --- cross-user data in non-admin payloads
    body = alice.get('/api/jobs/').text + alice.get('/api/workflows/').text \
        + alice.get('/api/server/').text
    check('privacy: no foreign e-mail addresses in non-admin payloads',
          'bob@e2e.test' not in body and 'admin@e2e.test' not in body, '')
    r = alice.get('/api/me/')
    check('privacy: own profile has no password/hash fields',
          'password' not in r.text and 'activation' not in r.text, r.text[:120])

    # --- admin file reach (documented trust boundary)
    r = admin.post('/api/admin/workflows/install/', json={'path': '/etc'})
    check('admin: installing /etc as an app is refused', r.status_code in (400, 404),
          '%s %s' % (r.status_code, r.text[:120]))
    r = admin.post('/api/admin/workflows/install/',
                   json={'path': str(home / '..' / '..' / 'etc')})
    check('admin: installing a traversal path is refused', r.status_code in (400, 404),
          '%s %s' % (r.status_code, r.text[:120]))
    r = admin.get('/api/admin/settings/nextflow/')
    secret = (home / 'config' / 'secret_key')
    info('admin: nextflow settings keys', ','.join(sorted(r.json())))
    check('admin: nextflow settings do not expose the secret key',
          not secret.exists() or secret.read_text().strip() not in r.text, '')
    r = admin.get('/api/admin/pages/')
    check('admin: page list only lists pages/*.html',
          all(row['slug'].isidentifier() or '-' in row['slug'] for row in r.json()),
          json.dumps(r.json())[:160])

    failed = [n for n, ok in RESULTS if not ok]
    print('\n%d/%d checks passed' % (len(RESULTS) - len(failed), len(RESULTS)))
    for n in failed:
        print('  FAILED:', n)


if __name__ == '__main__':
    main()
