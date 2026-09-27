"""T07c probe 6: pages, navbar enforcement, logs and dashboard counts."""
import json
import time

import pytest

from e2e import helpers

pytestmark = pytest.mark.serial


def test_page_slug_edge_cases(stack, api, server_settings):
    c = api('admin')
    anon = api()
    for slug in ('probe-page', 'Probe-Page', 'probe page', 'ünicode', '../../etc/passwd',
                 'a' * 70, 'home', 'footer', '_leading', 'trailing-', '1', 'nav%2fbar'):
        r = c.put('/api/admin/pages/%s/' % slug, json={'html': '<p>probe %s</p>' % slug})
        pub = anon.get('/api/pages/%s/' % slug)
        print('PUT %-20r -> %s %-40s | public GET -> %s' % (
            slug, r.status_code, r.text[:60].replace('\n', ' '), pub.status_code))
    print('list:', [p['slug'] for p in c.get_json('/api/admin/pages/')])
    print('delete home ->', c.delete('/api/admin/pages/home/').status_code)
    print('delete footer ->', c.delete('/api/admin/pages/footer/').status_code)
    print('delete missing ->', c.delete('/api/admin/pages/nosuchpage/').status_code)
    for slug in ('probe-page', 'a' * 70, 'trailing-', '1'):
        c.delete('/api/admin/pages/%s/' % slug)


def test_delete_page_linked_from_navbar(stack, api, server_settings):
    c = api('admin')
    c.put('/api/admin/pages/probe-linked/', json={'html': '<p>linked</p>'})
    nav = c.get_json('/api/admin/settings/navbar/')['navbar']
    c.put('/api/admin/settings/navbar/', json={'navbar': nav + [
        {'title': 'Probe Linked', 'url': '/pages/probe-linked'}]})
    print('delete page ->', c.delete('/api/admin/pages/probe-linked/').status_code)
    print('navbar still lists it:',
          [i['url'] for i in api().get_json('/api/server/')['navbar']])
    print('public page ->', api().get('/api/pages/probe-linked/').status_code)
    server_settings.restore()


def test_navbar_flags_enforced(stack, api, server_settings):
    c = api('admin')
    nav = [{'title': 'Pub', 'url': '/'},
           {'title': 'AuthOnly', 'url': '/jobs', 'auth_only': True},
           {'title': 'AdminOnly', 'url': '/admin', 'admin_only': True},
           {'title': 'Both', 'url': '/admin/logs', 'admin_only': True, 'auth_only': True}]
    print('PUT ->', c.put('/api/admin/settings/navbar/', json={'navbar': nav}).status_code)
    for user in (None, 'bob', 'alice', 'admin'):
        cc = api(user) if user else api()
        print('  %-6s ->' % user, [i['title'] for i in cc.get_json('/api/server/')['navbar']])
    server_settings.restore()


def test_page_huge_and_script(stack, api, server_settings):
    c = api('admin')
    big = '<p>' + 'x' * (512 * 1024) + '</p>'
    r = c.put('/api/admin/pages/probe-big/', json={'html': big})
    print('huge page PUT ->', r.status_code, len(r.text))
    g = api().get('/api/pages/probe-big/')
    print('public GET ->', g.status_code, len(g.text))
    print('list entry:', [p for p in c.get_json('/api/admin/pages/') if p['slug'] == 'probe-big'])
    c.delete('/api/admin/pages/probe-big/')


def test_logs_content_and_filters(stack, api, server_settings):
    c = api('admin')
    # generate a few admin actions + a failed login
    c.put('/api/admin/settings/general/', json={'name': 'Cloudgene E2E'})
    c.post('/api/admin/queue/pause/')
    c.post('/api/admin/queue/resume/')
    anon = api()
    anon.get('/api/auth/me')
    anon.post('/api/auth/login/', json={'username': 'alice', 'password': 'wrong-password'})
    time.sleep(0.5)
    page = c.get_json('/api/admin/logs/?page_size=200')
    print('log count:', page['count'])
    comps = {}
    for row in page['results']:
        comps.setdefault(row['component'], 0)
        comps[row['component']] += 1
    print('components:', comps)
    for row in page['results'][:12]:
        print('  %-8s %-7s %-10s %s' % (row['level'], row['component'],
                                        row['username'], row['message'][:90]))
    for q in ('?level=info', '?level=INFO', '?min_level=warning', '?component=auth',
              '?search=Queue', '?level=bogus', '?page_size=1000', '?page=9999'):
        r = c.get('/api/admin/logs/' + q)
        n = r.json().get('count') if r.status_code == 200 else r.text[:80]
        print('  %-22s -> %s %s' % (q, r.status_code, n))


def test_logs_huge_message(stack, api):
    c = api('admin')
    stack.django_shell("import logging; logging.getLogger('cloudgene.admin')"
                       ".error('PROBEHUGE ' + 'y'*200000)")
    r = c.get('/api/admin/logs/?search=PROBEHUGE')
    print('huge log ->', r.status_code, 'count', r.json().get('count') if r.ok else r.text[:150])
    if r.ok and r.json()['results']:
        print('stored length:', len(r.json()['results'][0]['message']))
    out = stack.manage('cleanup_logs', '--days', '0', check=False)
    print('cleanup_logs --days 0 ->', out.returncode, out.stdout[-200:], out.stderr[-200:])
    print('count after cleanup:', c.get_json('/api/admin/logs/')['count'])


def test_dashboard_counts_match_reality(stack, api, server_settings, requires_worker):
    c = api('admin')
    d = c.get_json('/api/admin/dashboard/')
    print('dashboard jobs:', d['jobs'])
    print('dashboard users:', d['users'], 'workflows:', d['workflows'])
    db = stack.django_shell(
        "import json;from jobs.models import Job;from django.contrib.auth import get_user_model;"
        "from collections import Counter;"
        "print(json.dumps({'jobs': dict(Counter(Job.objects.values_list('status', flat=True))),"
        " 'users': get_user_model().objects.count()}))")
    print('db:', db.strip().splitlines()[-1])
    total_api = d['jobs']['total']
    print('api total vs db total should match (deleted jobs?)')
    deleted = stack.django_shell(
        "from jobs.models import Job;print(Job.objects.filter(deleted_at__isnull=False).count())")
    print('soft-deleted jobs:', deleted.strip().splitlines()[-1])
