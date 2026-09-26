"""T07b: what the seeded superuser sees in /django-admin/ (other users' API token keys?).

    BASE=... venv/bin/python -m e2e.exploratory.probes_djangoadmin2
"""
import re

import requests

from e2e.constants import USERS
from e2e.exploratory.probe import BASE, Client
from e2e.exploratory.probes_djangoadmin import dj_login


def main():
    victim = Client(user='alice')
    key = victim.post('/api/me/token/').json()['token']
    s, r = dj_login('admin', USERS['admin']['password'])
    print('django-admin login as the seeded admin ->', r.status_code, r.headers.get('Location'))
    for path in ('/django-admin/', '/django-admin/authtoken/tokenproxy/',
                 '/django-admin/accounts/user/', '/django-admin/auth/group/',
                 '/django-admin/jobs/job/'):
        rr = requests.get(BASE + path, cookies=s.cookies, timeout=20)
        print('%-44s -> %s (%d bytes)' % (path, rr.status_code, len(rr.content)))
    rr = requests.get(BASE + '/django-admin/authtoken/tokenproxy/', cookies=s.cookies, timeout=20)
    print("alice's token key readable in the Django admin:", key in rr.text)
    print('  sample:', re.findall(r'[0-9a-f]{40}', rr.text)[:2])
    rr = requests.get(BASE + '/django-admin/accounts/user/2/change/', cookies=s.cookies, timeout=20)
    print('user change form:', rr.status_code, '| password hash rendered:',
          bool(re.search(r'(pbkdf2_sha256|md5)\$', rr.text)),
          '| is_superuser checkbox:', 'is_superuser' in rr.text)


if __name__ == '__main__':
    main()
