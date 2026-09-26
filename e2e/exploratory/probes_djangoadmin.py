"""T07b: what the (undocumented) /django-admin/ surface allows.

    BASE=... venv/bin/python -m e2e.exploratory.probes_djangoadmin <outbox>
"""
import re
import sys
import uuid
from pathlib import Path

import requests

from e2e.exploratory.probe import BASE, Client
from e2e.exploratory.probes_auth import make_user, _user_id


def dj_login(username, password):
    s = requests.Session()
    s.get(BASE + '/django-admin/login/', timeout=20)
    r = s.post(BASE + '/django-admin/login/',
               data={'username': username, 'password': password,
                     'csrfmiddlewaretoken': s.cookies.get('csrftoken'), 'next': '/django-admin/'},
               headers={'Referer': BASE + '/django-admin/login/'}, timeout=20,
               allow_redirects=False)
    return s, r


def main():
    outbox = Path(sys.argv[1])
    admin = Client(user='admin')

    # a fresh admin account we can lock without hurting the rest of the probes
    user, password, _ = make_user(admin, outbox, prefix='dja')
    uid = _user_id(admin, user)
    admin.patch('/api/admin/users/%s/' % uid, json={'is_admin': True})

    # lock the account through the documented login endpoint
    api = Client()
    api.get('/api/auth/me/')
    for _ in range(6):
        api.post('/api/auth/login/', json={'username': user, 'password': 'Wrong123'})
    locked = api.post('/api/auth/login/', json={'username': user, 'password': password})
    print('API login while locked:', locked.status_code, locked.text[:90])

    s, r = dj_login(user, password)
    print('django-admin login while locked ->', r.status_code, r.headers.get('Location'))
    me = requests.get(BASE + '/api/auth/me/', cookies=s.cookies, timeout=20).json()
    print('/api/auth/me with that cookie:', me.get('authenticated'), me.get('user', {}).get('username'))
    dash = requests.get(BASE + '/api/admin/dashboard/', cookies=s.cookies, timeout=20)
    print('/api/admin/dashboard with that cookie:', dash.status_code)

    # what the Django admin exposes
    for path in ('/django-admin/', '/django-admin/authtoken/tokenproxy/',
                 '/django-admin/accounts/user/', '/django-admin/auth/group/'):
        rr = requests.get(BASE + path, cookies=s.cookies, timeout=20)
        print('%-44s -> %s (%d bytes)' % (path, rr.status_code, len(rr.content)))

    # does the token list show other users' keys?
    victim = Client(user='bob')
    key = victim.post('/api/me/token/').json()['token']
    rr = requests.get(BASE + '/django-admin/authtoken/tokenproxy/', cookies=s.cookies, timeout=20)
    print('bob token key visible in the Django admin token list:', key in rr.text)
    if key not in rr.text:
        m = re.findall(r'field-key[^<]*<[^>]*>([0-9a-f]{6,40})', rr.text)
        print('  key-ish strings found:', m[:3])

    # password hashes of other users
    rr = requests.get(BASE + '/django-admin/accounts/user/%s/change/' % 3, cookies=s.cookies,
                      timeout=20)
    print('user change form:', rr.status_code, 'hash shown:',
          bool(re.search(r'(pbkdf2_sha256|md5)\$', rr.text)))


if __name__ == '__main__':
    main()
