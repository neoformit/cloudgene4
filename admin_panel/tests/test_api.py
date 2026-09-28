"""Admin panel + public server API (T05): permissions, settings round-trips via
settings.yaml on disk, pages (incl. traversal), workflows admin, dashboard, queue, logs."""
import logging
from datetime import timedelta
from io import StringIO

import yaml
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from admin_panel.models import SystemLog
from core import config
from core.models import WorkerHeartbeat
from workflows.models import Workflow
from workflows.test_registry import TempHomeMixin

User = get_user_model()
PASSWORD = 'Secret123'

# (method, path, body) for every admin endpoint.
ADMIN_ENDPOINTS = [
    ('get', '/api/admin/dashboard/', None),
    ('post', '/api/admin/queue/pause/', None),
    ('post', '/api/admin/queue/resume/', None),
    ('post', '/api/admin/maintenance/enter/', {}),
    ('post', '/api/admin/maintenance/exit/', None),
    ('get', '/api/admin/settings/general/', None),
    ('put', '/api/admin/settings/general/', {'name': 'X'}),
    ('get', '/api/admin/settings/mail/', None),
    ('put', '/api/admin/settings/mail/', {'host': 'h'}),
    ('post', '/api/admin/settings/mail/test/', {}),
    ('get', '/api/admin/settings/nextflow/', None),
    ('put', '/api/admin/settings/nextflow/', {'profile': 'p'}),
    ('get', '/api/admin/settings/navbar/', None),
    ('put', '/api/admin/settings/navbar/', {'navbar': []}),
    ('get', '/api/admin/pages/', None),
    ('get', '/api/admin/pages/home/', None),
    ('put', '/api/admin/pages/new-page/', {'html': 'x'}),
    ('delete', '/api/admin/pages/about/', None),
    ('get', '/api/admin/logs/', None),
    ('get', '/api/admin/workflows/', None),
    ('post', '/api/admin/workflows/install/', {'path': 'hello'}),
    ('post', '/api/admin/workflows/sync/', None),
    ('get', '/api/admin/workflows/hello/', None),
    ('patch', '/api/admin/workflows/hello/', {'public': True}),
    ('delete', '/api/admin/workflows/hello/', None),
    ('post', '/api/admin/workflows/hello/reload/', None),
    ('get', '/api/admin/workflows/hello/nextflow/', None),
    ('put', '/api/admin/workflows/hello/nextflow/', {'profile': 'p'}),
]


class Base(TempHomeMixin, TestCase):
    def setUp(self):
        super().setUp()
        (self.home / 'pages' / 'about.html').write_text('<h2>About</h2>')
        self.admin = User.objects.create_user(username='admin', email='admin@x.org',
                                              password=PASSWORD, is_staff=True)
        self.alice = User.objects.create_user(username='alice', email='alice@x.org',
                                              password=PASSWORD)
        self.client = APIClient()

    def as_admin(self):
        self.client.force_authenticate(self.admin)

    def as_alice(self):
        self.client.force_authenticate(self.alice)

    def disk(self):
        return yaml.safe_load(config.settings_path().read_text())

    def call(self, method, path, body=None):
        return getattr(self.client, method)(path, body, format='json')


class PermissionMatrixTest(Base):
    def test_anonymous_gets_401(self):
        for method, path, body in ADMIN_ENDPOINTS:
            with self.subTest(method=method, path=path):
                r = self.call(method, path, body)
                self.assertEqual(r.status_code, 401, r.content)
                self.assertEqual(r.json()['error']['code'], 'not_authenticated')

    def test_non_admin_gets_403_and_nothing_changes(self):
        self.as_alice()
        before = config.settings_path().read_text()
        for method, path, body in ADMIN_ENDPOINTS:
            with self.subTest(method=method, path=path):
                r = self.call(method, path, body)
                self.assertEqual(r.status_code, 403, r.content)
                self.assertEqual(r.json()['error']['code'], 'permission_denied')
        self.assertEqual(config.settings_path().read_text(), before)
        self.assertTrue((self.home / 'pages' / 'about.html').exists())

    def test_admin_via_admin_group(self):
        self.alice.groups.add(Group.objects.create(name='admin'))
        self.as_alice()
        self.assertEqual(self.client.get('/api/admin/dashboard/').status_code, 200)

    def test_admin_session_needs_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.login(username='admin', password=PASSWORD)
        r = client.put('/api/admin/settings/general/', {'name': 'X'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'csrf_failed')


class GeneralSettingsTest(Base):
    def test_round_trip_to_disk(self):
        self.as_admin()
        r = self.client.put('/api/admin/settings/general/', {
            'name': 'My Service', 'url': 'https://example.org/', 'max_running_jobs': 4,
            'max_queue_size': 9, 'job_retention_days': 3, 'max_upload_mb': 10,
            'maintenance': True, 'maintenance_message': 'Back soon'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        server = self.disk()['server']
        self.assertEqual(server['name'], 'My Service')
        self.assertEqual(server['url'], 'https://example.org')
        self.assertEqual((server['max_running_jobs'], server['max_queue_size']), (4, 9))
        self.assertEqual(server['maintenance_message'], 'Back soon')
        config.clear_cache()
        self.assertEqual(self.client.get('/api/admin/settings/general/').json(), r.json())

    def test_partial_update_keeps_other_keys(self):
        self.as_admin()
        config.set_value('server.max_queue_size', 7)
        self.client.put('/api/admin/settings/general/', {'name': 'N'}, format='json')
        self.assertEqual(self.disk()['server']['max_queue_size'], 7)

    def test_validation_errors_in_envelope_fields(self):
        self.as_admin()
        r = self.client.put('/api/admin/settings/general/',
                            {'max_running_jobs': 0, 'url': 'ftp://x'}, format='json')
        self.assertEqual(r.status_code, 400)
        fields = r.json()['error']['fields']
        self.assertIn('max_running_jobs', fields)
        self.assertIn('url', fields)
        self.assertEqual(self.disk()['server']['max_running_jobs'], 2)


class MailSettingsTest(Base):
    def test_password_write_only(self):
        self.as_admin()
        r = self.client.put('/api/admin/settings/mail/', {
            'backend': 'smtp', 'host': 'smtp.x.org', 'port': 25, 'user': 'u',
            'password': 's3cret', 'use_tls': False, 'from_email': 'no@x.org'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn('password', r.json())
        self.assertTrue(r.json()['password_set'])
        self.assertEqual(self.disk()['mail']['password'], 's3cret')
        body = self.client.get('/api/admin/settings/mail/').content.decode()
        self.assertNotIn('s3cret', body)
        # empty password = unchanged
        self.client.put('/api/admin/settings/mail/', {'password': '', 'host': 'h2'}, format='json')
        self.assertEqual(self.disk()['mail']['password'], 's3cret')
        self.assertEqual(self.disk()['mail']['host'], 'h2')
        # explicit clear
        r = self.client.put('/api/admin/settings/mail/', {'clear_password': True}, format='json')
        self.assertFalse(r.json()['password_set'])
        self.assertEqual(self.disk()['mail']['password'], '')

    def test_invalid_backend(self):
        self.as_admin()
        r = self.client.put('/api/admin/settings/mail/', {'backend': 'pigeon'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('backend', r.json()['error']['fields'])

    def test_send_test_mail_to_admin(self):
        self.as_admin()
        r = self.client.post('/api/admin/settings/mail/test/', {}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@x.org'])

    def test_send_test_mail_requires_address(self):
        self.admin.email = ''
        self.admin.save()
        self.as_admin()
        r = self.client.post('/api/admin/settings/mail/test/', {}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('to', r.json()['error']['fields'])


class NextflowSettingsTest(Base):
    def test_round_trip(self):
        self.as_admin()
        r = self.client.put('/api/admin/settings/nextflow/', {
            'binary': '/usr/local/bin/nextflow', 'profile': 'docker', 'work_dir': '/w',
            'config': 'process.executor = "local"\n', 'env': 'FOO=bar\n'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.disk()['nextflow'],
                         {'binary': '/usr/local/bin/nextflow', 'profile': 'docker',
                          'work_dir': '/w'})
        self.assertEqual(config.nextflow_config_path().read_text(),
                         'process.executor = "local"\n')
        self.assertEqual(config.nextflow_env_path().read_text(), 'FOO=bar\n')
        data = self.client.get('/api/admin/settings/nextflow/').json()
        self.assertEqual(data['env'], 'FOO=bar\n')
        self.assertIn('CLOUDGENE_SERVICE_NAME', [v['name'] for v in data['variables']])


class NavbarTest(Base):
    def test_round_trip_and_public_filtering(self):
        self.as_admin()
        items = [{'title': 'Home', 'url': '/'},
                 {'title': 'Jobs', 'url': '/jobs', 'auth_only': True},
                 {'title': 'Admin', 'url': '/admin', 'admin_only': True, 'icon': 'cog'}]
        r = self.client.put('/api/admin/settings/navbar/', {'navbar': items}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([i['title'] for i in self.disk()['navbar']], ['Home', 'Jobs', 'Admin'])

        titles = lambda: [i['title'] for i in self.client.get('/api/server/').json()['navbar']]
        self.assertEqual(titles(), ['Home', 'Jobs', 'Admin'])
        self.client.force_authenticate(None)
        self.assertEqual(titles(), ['Home'])
        self.as_alice()
        self.assertEqual(titles(), ['Home', 'Jobs'])

    def test_missing_title(self):
        self.as_admin()
        r = self.client.put('/api/admin/settings/navbar/', {'navbar': [{'url': '/'}]},
                            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('navbar[0].title', r.json()['error']['fields'])


class ServerInfoTest(Base):
    def test_public_server_info(self):
        config.update_settings({'server': {'name': 'Svc', 'maintenance': True,
                                           'maintenance_message': 'Down'}})
        r = self.client.get('/api/server/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['name'], 'Svc')
        self.assertTrue(data['maintenance'])
        self.assertEqual(data['maintenance_message'], 'Down')
        self.assertEqual(data['footer_html'], '<p>Footer</p>')
        self.assertNotIn('mail', data)


class PagesTest(Base):
    def test_public_page(self):
        r = self.client.get('/api/pages/about/')
        self.assertEqual(r.json(), {'slug': 'about', 'html': '<h2>About</h2>'})
        r = self.client.get('/api/pages/nope/')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['error']['code'], 'not_found')

    def test_public_page_traversal_rejected(self):
        (self.home / 'secret.html').write_text('SECRET')
        for slug in ('..%2Fsecret', '..', '.hidden', 'Home', 'a.b', '%2e%2e', 'x' * 65):
            with self.subTest(slug=slug):
                r = self.client.get(f'/api/pages/{slug}/')
                self.assertEqual(r.status_code, 404)
                self.assertNotIn(b'SECRET', r.content)
        self.assertEqual(self.client.get('/api/pages/../config/settings/').status_code, 404)

    def test_admin_crud(self):
        self.as_admin()
        slugs = [p['slug'] for p in self.client.get('/api/admin/pages/').json()]
        self.assertEqual(slugs, ['about', 'footer', 'home'])
        r = self.client.put('/api/admin/pages/help/', {'html': '<p>Help</p>'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual((self.home / 'pages' / 'help.html').read_text(), '<p>Help</p>')
        self.assertEqual(self.client.get('/api/pages/help/').json()['html'], '<p>Help</p>')
        r = self.client.put('/api/admin/pages/help/', {'html': '<p>v2</p>'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/admin/pages/help/').json()['html'], '<p>v2</p>')
        self.assertEqual(self.client.delete('/api/admin/pages/help/').status_code, 204)
        self.assertFalse((self.home / 'pages' / 'help.html').exists())
        self.assertEqual(self.client.delete('/api/admin/pages/help/').status_code, 404)

    def test_home_footer_not_deletable(self):
        self.as_admin()
        for slug in ('home', 'footer'):
            r = self.client.delete(f'/api/admin/pages/{slug}/')
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.json()['error']['code'], 'protected')
            self.assertTrue((self.home / 'pages' / f'{slug}.html').exists())

    def test_admin_invalid_slug(self):
        self.as_admin()
        for slug in ('..%2F..%2Fconfig%2Fsettings', 'UPPER', 'a.b', '_x'):
            with self.subTest(slug=slug):
                r = self.client.put(f'/api/admin/pages/{slug}/', {'html': 'x'}, format='json')
                self.assertIn(r.status_code, (400, 404))
        self.assertEqual(sorted(p.name for p in (self.home / 'pages').iterdir()),
                         ['about.html', 'footer.html', 'home.html'])


class AdminWorkflowsApiTest(Base):
    def test_install_list_patch_reload_uninstall(self):
        self.as_admin()
        r = self.client.post('/api/admin/workflows/install/',
                             {'path': 'hello', 'groups': ['lab']}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['groups'], ['lab'])
        self.assertIn('id: hello', r.json()['yaml'])

        config.update_settings(lambda d: {**d, 'apps': d['apps'] + [{'path': 'invalid'}]})
        rows = {w['id']: w for w in self.client.get('/api/admin/workflows/').json()}
        self.assertTrue(rows['hello']['valid'])
        self.assertFalse(rows['invalid']['valid'])
        self.assertTrue(rows['invalid']['errors'])

        r = self.client.patch('/api/admin/workflows/hello/',
                              {'enabled': False, 'public': True, 'groups': ['a', 'b']},
                              format='json')
        self.assertEqual(r.status_code, 200, r.content)
        entry = self.disk()['apps'][0]
        self.assertEqual((entry['enabled'], entry['public'], entry['groups']),
                         (False, True, ['a', 'b']))
        self.assertEqual(Workflow.objects.get(pk='hello').status, 'disabled')

        self.assertEqual(self.client.post('/api/admin/workflows/hello/reload/').status_code, 200)
        self.assertEqual(self.client.delete('/api/admin/workflows/hello/').status_code, 204)
        self.assertEqual(self.client.get('/api/admin/workflows/hello/').status_code, 404)

    def test_disabled_hidden_from_public_list_but_shown_to_admin(self):
        self.as_admin()
        self.client.post('/api/admin/workflows/install/', {'path': 'hello', 'public': True},
                         format='json')
        self.client.patch('/api/admin/workflows/hello/', {'enabled': False}, format='json')
        self.as_alice()
        public = self.client.get('/api/workflows/').json()
        ids = [w['id'] for w in public.get('results', public)]
        self.assertNotIn('hello', ids)
        self.as_admin()
        self.assertIn('hello', [w['id'] for w in self.client.get('/api/admin/workflows/').json()])

    def test_broken_app_effective_status_is_disabled_even_when_configured_enabled(self):
        # C-07: apps[].enabled stays as configured, but a broken app is never *effectively*
        # enabled — the admin list must say so explicitly rather than reporting enabled: true.
        self.as_admin()
        r = self.client.post('/api/admin/workflows/install/', {'path': 'hello'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        yaml_file = self.home / 'apps' / 'hello' / 'cloudgene.yaml'
        yaml_file.write_text(yaml_file.read_text().replace('type: text', 'type: bogus'))
        self.client.post('/api/admin/workflows/hello/reload/')
        rows = {w['id']: w for w in self.client.get('/api/admin/workflows/').json()}
        hello = rows['hello']
        self.assertTrue(hello['enabled'])           # configured value untouched
        self.assertFalse(hello['valid'])
        self.assertEqual(hello['effective_status'], 'disabled')

    def test_install_errors(self):
        self.as_admin()
        r = self.client.post('/api/admin/workflows/install/', {'path': 'invalid'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['error']['fields']['path'])
        r = self.client.post('/api/admin/workflows/install/', {'path': '/nowhere'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/admin/workflows/install/', {}, format='json')
        self.assertIn('path', r.json()['error']['fields'])
        self.client.post('/api/admin/workflows/install/', {'path': 'hello'}, format='json')
        r = self.client.post('/api/admin/workflows/install/', {'path': 'hello'}, format='json')
        self.assertEqual(r.status_code, 409)

    def test_nextflow_per_app(self):
        self.as_admin()
        self.client.post('/api/admin/workflows/install/', {'path': 'hello'}, format='json')
        r = self.client.put('/api/admin/workflows/hello/nextflow/', {
            'profile': 'docker', 'work_dir': '', 'config': 'x = 1\n', 'env': 'A=b\n'},
            format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.disk()['apps'][0]['profile'], 'docker')
        self.assertEqual((self.home / 'apps' / 'hello' / 'nextflow.env').read_text(), 'A=b\n')
        data = self.client.get('/api/admin/workflows/hello/nextflow/').json()
        self.assertEqual(data['config'], 'x = 1\n')
        self.assertIn('CLOUDGENE_JOB_ID', [v['name'] for v in data['variables']])
        self.assertEqual(self.client.get('/api/admin/workflows/nope/nextflow/').status_code, 404)


class DashboardQueueTest(Base):
    def test_dashboard_shape_and_counts(self):
        from jobs.models import Job
        self.as_admin()
        self.client.post('/api/admin/workflows/install/', {'path': 'hello'}, format='json')
        wf = Workflow.objects.get(pk='hello')
        field = 'state' if 'state' in {f.name for f in Job._meta.get_fields()} else 'status'
        legacy = field == 'status'
        for value in (['running', 'failed', 'completed' if legacy else 'success',
                       'pending' if legacy else 'waiting']):
            Job.objects.create(workflow=wf, user=self.alice, name=f'j {value}', **{field: value})
        WorkerHeartbeat.beat(pid=42)
        data = self.client.get('/api/admin/dashboard/').json()
        self.assertEqual(data['jobs'], {'total': 4, 'waiting': 1, 'running': 1, 'success': 1,
                                        'failed': 1, 'cancelled': 0})
        q = data['queue']
        self.assertEqual((q['running'], q['waiting'], q['max_running'], q['paused']),
                         (1, 1, 2, False))
        self.assertTrue(q['worker']['ok'])
        self.assertEqual(data['users']['total'], 2)
        self.assertEqual(data['users']['admins'], 1)
        self.assertEqual(data['workflows']['enabled'], 1)
        self.assertEqual(len(data['recent_jobs']), 4)
        job = data['recent_jobs'][0]
        self.assertEqual(set(job), {'id', 'name', 'state', 'workflow', 'user', 'submitted_at',
                                    'started_at', 'finished_at'})
        self.assertIn(job['state'], ('waiting', 'running', 'success', 'failed', 'cancelled'))

    def test_pause_resume_maintenance_write_settings(self):
        self.as_admin()
        r = self.client.post('/api/admin/queue/pause/')
        self.assertTrue(r.json()['paused'])
        self.assertTrue(self.disk()['queue']['paused'])
        self.client.post('/api/admin/queue/resume/')
        self.assertFalse(self.disk()['queue']['paused'])
        r = self.client.post('/api/admin/maintenance/enter/', {'message': 'Upgrade'},
                             format='json')
        self.assertTrue(r.json()['maintenance'])
        self.assertEqual(self.disk()['server']['maintenance_message'], 'Upgrade')
        self.assertTrue(self.client.get('/api/server/').json()['maintenance'])
        self.client.post('/api/admin/maintenance/exit/')
        self.assertFalse(self.disk()['server']['maintenance'])
        self.assertEqual(self.disk()['server']['maintenance_message'], 'Upgrade')
        # every action is logged (Admin → Logs)
        self.assertTrue(SystemLog.objects.filter(component='admin',
                                                 message='Queue paused').exists())


class LogsTest(Base):
    def test_handler_and_filters(self):
        logging.getLogger('cloudgene.jobs.worker').info('Job x finished', extra={
            'user': self.alice, 'data': {'job': 'x'}})
        logging.getLogger('cloudgene.auth').warning('Failed login for bob')
        logging.getLogger('cloudgene.auth').debug('not stored')
        logging.getLogger('django').warning('not a cloudgene logger')
        self.as_admin()
        data = self.client.get('/api/admin/logs/').json()
        msgs = [r['message'] for r in data['results']]
        self.assertEqual(msgs, ['Failed login for bob', 'Job x finished'])
        first = data['results'][1]
        self.assertEqual((first['level'], first['component'], first['username']),
                         ('info', 'jobs', 'alice'))
        self.assertEqual(first['metadata'], {'job': 'x'})
        self.assertIn('timestamp', first)
        r = self.client.get('/api/admin/logs/?level=WARNING').json()
        self.assertEqual([x['message'] for x in r['results']], ['Failed login for bob'])
        r = self.client.get('/api/admin/logs/?component=jobs').json()
        self.assertEqual(r['count'], 1)
        r = self.client.get('/api/admin/logs/?min_level=info&search=login').json()
        self.assertEqual(r['count'], 1)

    def test_unknown_level_filter_is_a_400_not_silently_empty(self):
        # C-06: a typo in ?level=/?min_level= must not look like "no such events".
        self.as_admin()
        r = self.client.get('/api/admin/logs/?level=bogus')
        self.assertEqual(r.status_code, 400)
        self.assertIn('level', r.json()['error']['fields'])
        r = self.client.get('/api/admin/logs/?min_level=bogus')
        self.assertEqual(r.status_code, 400)
        self.assertIn('min_level', r.json()['error']['fields'])

    def test_log_components_follow_the_spec(self):
        # C-04: SPEC §3.8 names cloudgene.auth/jobs/workflows/admin/api (+ worker); nothing
        # should still be filed under the old "accounts" component.
        logging.getLogger('cloudgene.auth').warning('Failed login for bob')
        logging.getLogger('cloudgene.jobs').info('Job abc submitted')
        self.as_admin()
        components = {r['component'] for r in
                      self.client.get('/api/admin/logs/?page_size=200').json()['results']}
        self.assertIn('auth', components)
        self.assertIn('jobs', components)
        self.assertNotIn('accounts', components)

    def test_cleanup_logs(self):
        old = SystemLog.objects.create(level='info', message='old')
        SystemLog.objects.filter(pk=old.pk).update(timestamp=timezone.now() - timedelta(days=40))
        SystemLog.objects.create(level='info', message='new')
        call_command('cleanup_logs', '--days', '30', stdout=StringIO())
        self.assertEqual(list(SystemLog.objects.values_list('message', flat=True)), ['new'])
