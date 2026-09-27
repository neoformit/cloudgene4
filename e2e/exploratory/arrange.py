"""Arrange fixture data for the T07b probes and print the ids as JSON.

    BASE=... venv/bin/python -m e2e.exploratory.arrange
"""
import json
import sys
import time

from e2e.exploratory.probe import Client


def wait_state(c, job_id, states, timeout=180):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = c.get('/api/jobs/%s/status/' % job_id).json()
        if last.get('state') in states:
            return last
        time.sleep(1)
    raise SystemExit('job %s stuck in %s' % (job_id, last and last.get('state')))


def main():
    alice = Client(user='alice')
    bob = Client(user='bob')
    admin = Client(user='admin')

    r = alice.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'alice secret job',
                                       'message': 'hello from alice'})
    job = r.json()
    assert r.status_code == 201, r.text[:400]
    wait_state(alice, job['id'], ('success', 'failed', 'cancelled'))
    detail = alice.get('/api/jobs/%s/' % job['id']).json()
    outputs = detail.get('outputs') or []

    # a finished job owned by bob too (for cross checks)
    rb = bob.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'bob job',
                                      'message': 'hi'})
    bob_job = rb.json()
    wait_state(bob, bob_job['id'], ('success', 'failed', 'cancelled'))

    users = {u['username']: u['id'] for u in admin.get('/api/admin/users/?page_size=100').json()['results']}
    groups = {g['name']: g['id'] for g in admin.get('/api/admin/groups/').json()}
    logs = admin.get('/api/admin/logs/').json()['results']

    out = {
        'alice_job': job['id'],
        'alice_job_state': detail.get('state'),
        'alice_output': outputs[0]['id'] if outputs else None,
        'bob_job': bob_job['id'],
        'users': users,
        'groups': groups,
        'log_id': logs[0]['id'] if logs else 1,
    }
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == '__main__':
    main()
