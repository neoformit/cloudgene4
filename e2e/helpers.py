"""Test helpers that don't need a browser: API client, job polling, e-mail outbox."""
import email
import email.policy
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

from e2e.constants import USERS

ACTIVE_STATES = ('waiting', 'running')
FINAL_STATES = ('success', 'failed', 'cancelled')


class ApiError(AssertionError):
    pass


class ApiClient(requests.Session):
    """`requests.Session` bound to the stack; handles session cookie + CSRF header and DRF token.

    Use it for arrange/assert steps only — never for the action under test (use the UI for that).
    """

    def __init__(self, base_url, username=None):
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.headers['Referer'] = self.base_url + '/'

    def request(self, method, url, *args, **kwargs):
        if url.startswith('/'):
            url = self.base_url + url
        if method.upper() not in ('GET', 'HEAD', 'OPTIONS'):
            token = self.cookies.get('csrftoken')
            if token:
                kwargs.setdefault('headers', {})['X-CSRFToken'] = token
        kwargs.setdefault('timeout', 30)
        return super().request(method, url, *args, **kwargs)

    # -- auth --------------------------------------------------------------------------------------
    def login(self, username, password=None):
        password = password or USERS[username]['password']
        self.get('/api/auth/me')  # sets csrftoken cookie once T01 lands; harmless 404 before
        last = None
        for path in ('/api/auth/login/', '/api/auth/login'):
            r = self.post(path, json={'username': username, 'password': password}, allow_redirects=False)
            if r.status_code == 404:
                last = r
                continue
            if r.status_code != 200:
                raise ApiError('login %s failed: %s %s' % (username, r.status_code, r.text[:300]))
            data = r.json()
            if data.get('token'):  # legacy DRF token auth (pre-T01)
                self.headers['Authorization'] = 'Token ' + data['token']
            self.username = username
            return data
        raise ApiError('no login endpoint found: %s' % (last.status_code if last is not None else None))

    # -- JSON convenience --------------------------------------------------------------------------
    def json_or_raise(self, response, expected=(200, 201, 202, 204)):
        if response.status_code not in expected:
            raise ApiError('%s %s -> %s: %s' % (response.request.method, response.request.path_url,
                                                response.status_code, response.text[:500]))
        return response.json() if response.content else None

    def get_json(self, path, **kw):
        return self.json_or_raise(self.get(path, **kw))

    def post_json(self, path, payload=None, **kw):
        return self.json_or_raise(self.post(path, json=payload, **kw))

    # -- jobs (SPEC §3.6) --------------------------------------------------------------------------
    def submit_job(self, workflow, name='', params=None, files=None):
        """POST /api/jobs as multipart. `files`: {input_id: [Path, ...]}. Returns the job JSON."""
        data = {'workflow': workflow, 'name': name}
        data.update({k: _form_value(v) for k, v in (params or {}).items()})
        upload = []
        handles = []
        try:
            for input_id, paths in (files or {}).items():
                for p in paths:
                    fh = open(p, 'rb')
                    handles.append(fh)
                    upload.append((input_id, (Path(p).name, fh)))
            r = self.post('/api/jobs/', data=data, files=upload or None)
            if r.status_code == 404:
                r = self.post('/api/jobs', data=data, files=upload or None)
        finally:
            for fh in handles:
                fh.close()
        return self.json_or_raise(r, expected=(200, 201, 202))

    def get_job(self, job_id):
        """Full job detail (GET /api/jobs/{id}; a trailing-slash redirect is followed)."""
        return self.get_json('/api/jobs/%s' % job_id)

    def job_status(self, job_id):
        """Light status payload (GET /api/jobs/{id}/status), falling back to the job detail."""
        r = self.get('/api/jobs/%s/status' % job_id)
        if r.status_code == 404:
            r = self.get('/api/jobs/%s/status/' % job_id)
        if r.status_code == 404:
            r = self.get('/api/jobs/%s/' % job_id)
        return self.json_or_raise(r)

    def cancel_job(self, job_id):
        r = self.post('/api/jobs/%s/cancel' % job_id)
        if r.status_code == 404:
            r = self.post('/api/jobs/%s/cancel/' % job_id)
        return self.json_or_raise(r, expected=(200, 202, 204))


def _form_value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return str(v)


def job_state(payload):
    return payload.get('state') or payload.get('status')


def wait_job_state(client, job_id, states, timeout=60, poll=0.5):
    """Poll until the job is in one of `states` (str or iterable). Returns the last payload.

    Fails fast if the job reaches a final state that isn't wanted.
    """
    wanted = {states} if isinstance(states, str) else set(states)
    deadline = time.monotonic() + timeout
    payload = None
    while time.monotonic() < deadline:
        payload = client.job_status(job_id)
        state = job_state(payload)
        if state in wanted:
            return payload
        if state in FINAL_STATES:
            raise AssertionError('job %s reached %r while waiting for %s: %s' % (job_id, state, sorted(wanted), payload))
        time.sleep(poll)
    raise AssertionError('job %s not in %s after %ss; last: %s' % (job_id, sorted(wanted), timeout, payload))


# -- e-mail outbox (Django file backend) ----------------------------------------------------------

def read_outbox(outbox_dir):
    """All messages in the file-backend outbox, oldest first, as `email.message.EmailMessage`."""
    messages = []
    for path in sorted(Path(outbox_dir).glob('*.log'), key=lambda p: p.stat().st_mtime):
        for chunk in path.read_text(errors='replace').split('-' * 79):
            if chunk.strip():
                messages.append(email.message_from_string(chunk.strip() + '\n', policy=email.policy.default))
    return messages


def latest_email(outbox_dir, to=None, timeout=10):
    """Newest message (optionally addressed to `to`), waiting up to `timeout` s for it to arrive."""
    deadline = time.monotonic() + timeout
    while True:
        found = [m for m in read_outbox(outbox_dir) if to is None or to.lower() in str(m['To']).lower()]
        if found:
            return found[-1]
        if time.monotonic() > deadline:
            raise AssertionError('no e-mail%s in %s' % (' to ' + to if to else '', outbox_dir))
        time.sleep(0.25)


def email_text(msg):
    part = msg.get_body(preferencelist=('plain', 'html'))
    return part.get_content() if part is not None else msg.get_payload()


def extract_link(msg_or_text, fragment):
    text = msg_or_text if isinstance(msg_or_text, str) else email_text(msg_or_text)
    for url in re.findall(r'https?://[^\s"\'<>]+', text):
        if fragment in url:
            return url
    raise AssertionError('no link containing %r in:\n%s' % (fragment, text))


def absolute(base_url, path):
    return urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
