"""Endpoint x role permission matrix (T07b).

Enumerates every path/method in schema.yaml, substitutes real ids, and calls each one as
anonymous / bob (plain user, not the owner) / alice (owner of the fixture job) / admin.

Endpoints that would destroy the fixture data (DELETE of the job / the account / the token,
logout, admin writes) are only exercised with the roles that must be refused; for the roles
that are allowed to run them they are reported as ``n/a``.

    BASE=... venv/bin/python -m e2e.exploratory.matrix ids.json
"""
import json
import sys
from pathlib import Path

import yaml

from e2e.exploratory.probe import Client

REPO = Path(__file__).resolve().parents[2]

SAFE = ('GET', 'HEAD', 'OPTIONS')

# (method, path) -> roles for which the call is skipped because it would destroy fixture state.
DESTRUCTIVE = {
    ('DELETE', '/api/jobs/{id}/'): {'alice', 'admin'},
    ('DELETE', '/api/me/'): {'bob', 'alice', 'admin'},
    ('DELETE', '/api/me/token/'): {'bob', 'alice', 'admin'},
    ('POST', '/api/auth/logout/'): {'bob', 'alice', 'admin'},
    ('POST', '/api/auth/login/'): {'bob', 'alice', 'admin'},
    ('PATCH', '/api/me/'): {'admin'},
}


def endpoints(ids):
    doc = yaml.safe_load((REPO / 'schema.yaml').read_text())
    subs = {
        'id': ids['alice_job'], 'file_id': str(ids['alice_output'] or 1),
        'slug': 'about', 'workflow_id': 'hello', 'activation_key': 'nosuchkey',
        'token': 'nosuchtoken',
    }
    out = []
    for path, item in doc['paths'].items():
        concrete = path
        if path.startswith('/api/admin/users/'):
            concrete = concrete.replace('{id}', str(ids['users']['alice']))
        elif path.startswith('/api/admin/groups/'):
            concrete = concrete.replace('{id}', str(ids['groups']['researchers']))
        elif path.startswith('/api/categories/'):
            concrete = concrete.replace('{id}', '1')
        elif path.startswith('/api/workflows/'):
            concrete = concrete.replace('{id}', 'hello')
        for key, value in subs.items():
            concrete = concrete.replace('{%s}' % key, value)
        for method in item:
            if method in ('parameters', 'servers'):
                continue
            out.append((method.upper(), path, concrete))
    return sorted(out)


def main():
    ids = json.loads(Path(sys.argv[1]).read_text())
    roles = ['anon', 'bob', 'alice', 'admin']
    clients = {'anon': Client(), 'bob': Client(user='bob'), 'alice': Client(user='alice'),
               'admin': Client(user='admin')}
    clients['anon'].get('/api/auth/me/')
    rows = []
    for method, template, path in endpoints(ids):
        row = {'method': method, 'path': template, 'concrete': path}
        for role in roles:
            client = clients[role]
            if role in DESTRUCTIVE.get((method, template), ()) or (
                    role == 'admin' and method not in SAFE and template.startswith('/api/admin/')):
                row[role] = 'n/a'
                continue
            if role != 'anon' and not client.cookies.get('sessionid'):
                client.login(role)
            r = client.request(method, path,
                               json={} if method in ('POST', 'PUT', 'PATCH') else None)
            row[role] = r.status_code
        rows.append(row)
        print('%-6s %-45s anon=%-6s bob=%-6s alice=%-6s admin=%s'
              % (method, template, row['anon'], row['bob'], row['alice'], row['admin']), flush=True)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('matrix.json')
    out.write_text(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
