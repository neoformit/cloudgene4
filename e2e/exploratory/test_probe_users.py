"""T07c probe 5: users, groups and multi-actor interference."""
import json
import time

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial


def _user_id(c, username):
    return [u['id'] for u in c.get_json('/api/admin/users/?search=%s' % username)['results']
            if u['username'] == username][0]


def _group_id(c, name):
    ids = [g['id'] for g in c.get_json('/api/admin/groups/') if g['name'] == name]
    return ids[0] if ids else None


def test_delete_group_prunes_workflow_access(stack, api, server_settings):
    c = api('admin')
    print('create group ->', c.post('/api/admin/groups/', json={'name': 'probe-acl'}).status_code)
    # grant it access to an enabled and to a disabled workflow
    print('grant hello ->', c.patch('/api/admin/workflows/hello/',
                                    json={'public': False, 'groups': ['probe-acl']}).status_code)
    print('disable+grant slow ->', c.patch('/api/admin/workflows/slow/',
                                           json={'enabled': False,
                                                 'groups': ['probe-acl', 'admin']}).status_code)
    before = {a['path']: a.get('groups') for a in stack.read_settings()['apps']}
    print('apps before:', before)
    gid = _group_id(c, 'probe-acl')
    print('delete group ->', c.delete('/api/admin/groups/%d/' % gid).status_code)
    time.sleep(0.5)
    after = {a['path']: a.get('groups') for a in stack.read_settings()['apps']}
    print('apps after :', after)
    rows = {w['id']: w['groups'] for w in c.get_json('/api/admin/workflows/')}
    print('admin rows groups:', rows)
    server_settings.restore()
    time.sleep(1.1)
    c.get('/api/admin/workflows/')


def test_delete_group_with_members(stack, api, server_settings):
    c = api('admin')
    c.post('/api/admin/groups/', json={'name': 'probe-members'})
    bob = _user_id(c, 'bob')
    print('add bob ->', c.patch('/api/admin/users/%d/' % bob,
                                json={'groups': ['probe-members']}).status_code)
    gid = _group_id(c, 'probe-members')
    print('members:', [g for g in c.get_json('/api/admin/groups/') if g['id'] == gid])
    print('delete ->', c.delete('/api/admin/groups/%d/' % gid).status_code)
    print('bob after:', c.get_json('/api/admin/users/%d/' % bob)['groups'])
    print('users list ->', c.get('/api/admin/users/').status_code)


def test_duplicate_and_bad_group_names(stack, api):
    c = api('admin')
    for name in ('probe-dupe', 'PROBE-DUPE', 'probe dupe', '', ' ', 'a' * 100,
                 'grüppe', '../evil', 'admin'):
        r = c.post('/api/admin/groups/', json={'name': name})
        print('create %r -> %s %s' % (name, r.status_code, r.text[:130]))
    gid = _group_id(c, 'probe-dupe')
    if gid:
        c.delete('/api/admin/groups/%d/' % gid)


def test_self_demote_and_last_admin(stack, api):
    c = api('admin')
    me = _user_id(c, 'admin')
    print('demote self ->', c.patch('/api/admin/users/%d/' % me, json={'is_admin': False}).text[:200])
    print('deactivate self ->', c.patch('/api/admin/users/%d/' % me,
                                        json={'is_active': False}).text[:200])
    print('delete self ->', c.delete('/api/admin/users/%d/' % me).text[:200])
    r = c.delete('/api/me/', json={'password': 'Admin1234'})
    print('delete own account (last admin) ->', r.status_code, r.text[:200])
    print('still admin:', c.get('/api/admin/dashboard/').status_code)


def test_second_admin_demotes_first(stack, api):
    """Two admins: one demotes the other; the demoted session must lose admin at once."""
    c = api('admin')
    alice = api('alice')
    alice_id = _user_id(c, 'alice')
    print('promote alice ->', c.patch('/api/admin/users/%d/' % alice_id,
                                      json={'is_admin': True}).status_code)
    print('alice dashboard ->', alice.get('/api/admin/dashboard/').status_code)
    print('alice /api/auth/me is_admin:', alice.get_json('/api/auth/me')['user']['is_admin'])
    admin_id = _user_id(alice, 'admin')
    r = alice.patch('/api/admin/users/%d/' % admin_id, json={'is_admin': False})
    print('alice demotes admin ->', r.status_code, r.text[:200])
    print('admin dashboard after demote ->', c.get('/api/admin/dashboard/').status_code)
    # restore
    if r.status_code < 300:
        print('re-promote ->', alice.patch('/api/admin/users/%d/' % admin_id,
                                           json={'is_admin': True}).status_code)
    print('demote alice ->', c.patch('/api/admin/users/%d/' % alice_id,
                                     json={'is_admin': False}).status_code)
    print('alice dashboard ->', alice.get('/api/admin/dashboard/').status_code)


def test_concurrent_user_edits(stack, api):
    """Two admins edit the same user; last write must not silently drop the other's change."""
    c = api('admin')
    alice_id = _user_id(c, 'alice')
    c.post('/api/admin/groups/', json={'name': 'probe-a'})
    c.post('/api/admin/groups/', json={'name': 'probe-b'})
    print('A sets probe-a ->', c.patch('/api/admin/users/%d/' % alice_id,
                                       json={'groups': ['probe-a']}).json()['groups'])
    print('B sets probe-b ->', c.patch('/api/admin/users/%d/' % alice_id,
                                       json={'groups': ['probe-b']}).json()['groups'])
    print('deactivate ->', c.patch('/api/admin/users/%d/' % alice_id,
                                   json={'is_active': False}).json()['is_active'])
    print('reactivate ->', c.patch('/api/admin/users/%d/' % alice_id,
                                   json={'is_active': True, 'groups': ['researchers']}).json())
    for g in ('probe-a', 'probe-b'):
        gid = _group_id(c, g)
        if gid:
            c.delete('/api/admin/groups/%d/' % gid)


def test_deactivate_user_with_running_job(stack, api, server_settings, requires_worker):
    c = api('admin')
    alice = api('alice')
    j = alice.submit_job('hello', name='probe-deact', params={'message': 'x'})
    alice_id = _user_id(c, 'alice')
    print('deactivate alice ->', c.patch('/api/admin/users/%d/' % alice_id,
                                         json={'is_active': False}).status_code)
    print('alice session still works?', alice.get('/api/jobs/%s' % j['id']).status_code)
    print('alice can submit?', alice.post('/api/jobs/', data={'workflow': 'hello',
                                                              'job_name': 'x',
                                                              'message': 'y'}).status_code)
    state = helpers.wait_job_state(c, j['id'], ('success', 'failed', 'cancelled'), timeout=180)
    print('job of deactivated user ended as:', state if isinstance(state, str) else
          c.job_status(j['id'])['state'])
    print('reactivate ->', c.patch('/api/admin/users/%d/' % alice_id,
                                   json={'is_active': True}).status_code)


def test_delete_user_with_running_job(stack, api, server_settings, requires_worker):
    """SPEC: deleting the Job row removes the workspace; the worker must survive."""
    c = api('admin')
    stack.run_seed('users')  # make sure alice/bob exist
    code = ("from django.contrib.auth import get_user_model as g;"
            "u=g().objects.create_user(username='probevictim', email='probevictim@e2e.test',"
            " password='Probe1234', full_name='Probe Victim');"
            "u.is_active=True;u.save();print(u.pk)")
    uid = int(stack.django_shell(code).strip().splitlines()[-1])
    victim = api()
    victim.login('probevictim', 'Probe1234')
    j = victim.submit_job('hello', name='probe-victim', params={'message': 'x'})
    helpers.wait_job_state(victim, j['id'], ('running',), timeout=60)
    workspace = stack.home / 'jobs' / j['id']
    print('workspace before:', workspace.exists())
    print('delete user ->', c.delete('/api/admin/users/%d/' % uid).status_code)
    time.sleep(6)
    print('workspace after:', workspace.exists())
    print('health:', stack.health()[1])
    print('worker alive:', stack._alive('worker'))
    # the worker must keep scheduling
    j2 = c.submit_job('hello', name='probe-after-delete', params={'message': 'y'})
    print('next job:', helpers.wait_job_state(c, j2['id'], ('success',), timeout=180))
    print('worker log tail:')
    log = (stack.log_dir / 'worker.log').read_text(errors='replace').splitlines()[-15:]
    for line in log:
        print('   ', line)
