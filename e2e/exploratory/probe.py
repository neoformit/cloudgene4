"""Shared helpers for the T07b exploratory security probes.

Usage:
    BASE=http://127.0.0.1:PORT venv/bin/python -m e2e.exploratory.<script>
"""
import os

import requests

from e2e.constants import USERS

BASE = os.environ.get('BASE', '').rstrip('/')


class Client(requests.Session):
    """Session-cookie + CSRF client (the SPA's auth), or token auth with `token=`."""

    def __init__(self, base=None, user=None, token=None):
        super().__init__()
        self.base = (base or BASE).rstrip('/')
        self.user = user
        self.headers['Referer'] = self.base + '/'
        self.headers['Origin'] = self.base
        if token:
            self.headers['Authorization'] = 'Token ' + token
        if user:
            self.login(user)

    def request(self, method, url, *a, csrf=True, **kw):
        if url.startswith('/'):
            url = self.base + url
        if csrf and method.upper() not in ('GET', 'HEAD', 'OPTIONS'):
            t = self.cookies.get('csrftoken')
            if t:
                kw.setdefault('headers', {}).setdefault('X-CSRFToken', t)
        kw.setdefault('timeout', 30)
        return super().request(method, url, *a, **kw)

    def login(self, user, password=None):
        self.get('/api/auth/me/')
        r = self.post('/api/auth/login/', json={'username': user,
                                                'password': password or USERS[user]['password']})
        assert r.status_code == 200, 'login %s: %s %s' % (user, r.status_code, r.text[:200])
        self.user = user
        return r


def short(r, n=160):
    body = r.text.replace('\n', ' ')[:n]
    return '%s %s' % (r.status_code, body)
