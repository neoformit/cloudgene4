from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import exceptions, serializers
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.exceptions import api_exception_handler
from core.models import WorkerHeartbeat
from core.permissions import is_admin

User = get_user_model()
PASSWORD = 'Secret123'


def make_user(username='alice', **extra):
    return User.objects.create_user(username=username, email=f'{username}@example.org',
                                    password=PASSWORD, full_name=username.title(), **extra)


def assert_envelope(test, response, status, code=None):
    test.assertEqual(response.status_code, status, response.content)
    body = response.json()
    test.assertEqual(set(body), {'error'})
    test.assertEqual(set(body['error']), {'message', 'code', 'fields'})
    test.assertIsInstance(body['error']['message'], str)
    test.assertTrue(body['error']['message'])
    if code:
        test.assertEqual(body['error']['code'], code)
    return body['error']


class IsAdminTest(TestCase):
    def test_admin_definition(self):
        self.assertFalse(is_admin(None))
        self.assertFalse(is_admin(AnonymousUser()))
        self.assertFalse(is_admin(make_user('plain')))
        self.assertTrue(is_admin(make_user('staff', is_staff=True)))
        self.assertTrue(is_admin(make_user('root', is_superuser=True)))
        member = make_user('member')
        member.groups.add(Group.objects.create(name='admin'))
        self.assertTrue(is_admin(member))
        self.assertTrue(member.is_admin_user())  # model helper delegates


class ErrorEnvelopeHandlerTest(TestCase):
    def handle(self, exc):
        return api_exception_handler(exc, {'view': None})

    def test_validation_error_fields(self):
        r = self.handle(serializers.ValidationError({'username': ['Required.'],
                                                     'nested': {'a': ['Bad.']}}))
        self.assertEqual(r.status_code, 400)
        err = r.data['error']
        self.assertEqual(err['code'], 'invalid')
        self.assertEqual(err['fields'], {'username': ['Required.'], 'nested.a': ['Bad.']})
        self.assertEqual(err['message'], 'username: Required.')

    def test_non_field_validation_error(self):
        r = self.handle(serializers.ValidationError({'non_field_errors': ['Nope.']}))
        self.assertEqual(r.data['error']['message'], 'Nope.')
        self.assertEqual(r.data['error']['fields'], {})
        r = self.handle(serializers.ValidationError('Plain.'))
        self.assertEqual(r.data['error']['message'], 'Plain.')

    def test_other_api_exceptions(self):
        r = self.handle(exceptions.NotFound())
        self.assertEqual((r.status_code, r.data['error']['code']), (404, 'not_found'))
        r = self.handle(exceptions.PermissionDenied('CSRF Failed: missing'))
        self.assertEqual(r.data['error']['code'], 'csrf_failed')
        r = self.handle(exceptions.Throttled(wait=3))
        self.assertEqual(r.status_code, 429)

    def test_unhandled_exception_becomes_500_envelope(self):
        with self.assertLogs('cloudgene.api', 'ERROR'):
            r = self.handle(RuntimeError('secret internals'))
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.data['error']['code'], 'server_error')
        self.assertNotIn('secret', r.data['error']['message'])


class AuthSessionTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self):
        response = self.client.get('/login')  # any SPA route sets the cookie
        self.assertIn('csrftoken', response.cookies)
        return response.cookies['csrftoken'].value

    def test_me_anonymous(self):
        r = self.client.get('/api/auth/me/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'authenticated': False, 'user': None})

    def test_login_requires_csrf(self):
        r = self.client.post('/api/auth/login/', {'username': 'alice', 'password': PASSWORD},
                             format='json')
        assert_envelope(self, r, 403, 'csrf_failed')

    def test_login_me_logout_flow_without_trailing_slash(self):
        token = self.csrf()
        r = self.client.post('/api/auth/login', {'username': 'alice', 'password': PASSWORD},
                             format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(set(body), {'user'})  # no token in the response any more
        self.assertEqual(body['user']['username'], 'alice')
        self.assertFalse(body['user']['is_admin'])
        self.assertIn('sessionid', r.cookies)

        r = self.client.get('/api/auth/me')
        self.assertEqual(r.json()['authenticated'], True)
        self.assertEqual(r.json()['user']['username'], 'alice')

        # login rotates the CSRF token (cookie updated by the login response)
        new_token = self.client.cookies['csrftoken'].value
        self.assertNotEqual(new_token, token)
        r = self.client.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=new_token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me/').json()['authenticated'], False)

    def test_session_write_without_csrf_rejected(self):
        self.client.force_login(self.user)
        r = self.client.post('/api/auth/logout/')
        assert_envelope(self, r, 403, 'csrf_failed')

    def test_login_errors_use_envelope(self):
        token = self.csrf()
        r = self.client.post('/api/auth/login/', {'username': 'alice', 'password': 'bad'},
                             format='json', HTTP_X_CSRFTOKEN=token)
        err = assert_envelope(self, r, 400, 'invalid')
        self.assertEqual(err['message'], 'Invalid username or password.')
        r = self.client.post('/api/auth/login/', {'password': 'x'}, format='json',
                             HTTP_X_CSRFTOKEN=token)
        err = assert_envelope(self, r, 400)
        self.assertIn('username', err['fields'])

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        token = self.csrf()
        r = self.client.post('/api/auth/login/', {'username': 'alice', 'password': PASSWORD},
                             format='json', HTTP_X_CSRFTOKEN=token)
        assert_envelope(self, r, 400)


class TokenAuthTest(TestCase):
    def test_token_auth_without_csrf(self):
        user = make_user()
        token = Token.objects.create(user=user)
        client = APIClient(enforce_csrf_checks=True)
        r = client.get('/api/auth/me/', HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertTrue(r.json()['authenticated'])

    def test_unauthenticated_protected_endpoint_is_401_envelope(self):
        r = APIClient().get('/api/jobs/')
        err = assert_envelope(self, r, 401, 'not_authenticated')
        self.assertEqual(err['fields'], {})
        self.assertIn('Token', r['WWW-Authenticate'])

    def test_bad_token_is_401_envelope(self):
        r = APIClient().get('/api/auth/me/', HTTP_AUTHORIZATION='Token nope')
        assert_envelope(self, r, 401, 'authentication_failed')


class AdminPermissionTest(TestCase):
    def test_admin_endpoints_use_is_admin(self):
        client = APIClient()
        client.force_authenticate(make_user('plain'))
        assert_envelope(self, client.get('/api/admin/dashboard/'), 403, 'permission_denied')
        staff = make_user('staffer', is_staff=True)  # is_staff alone is admin now
        client.force_authenticate(staff)
        self.assertEqual(client.get('/api/admin/dashboard/').status_code, 200)


class MiscRoutingTest(TestCase):
    def test_unknown_api_path_is_json_404(self):
        assert_envelope(self, self.client.get('/api/does-not-exist/'), 404, 'not_found')
        assert_envelope(self, self.client.get('/api'), 404, 'not_found')

    def test_spa_catch_all_sets_csrf_cookie(self):
        r = self.client.get('/jobs/123')
        self.assertIn(r.status_code, (200, 503))  # 503 = frontend not built
        self.assertIn('csrftoken', r.cookies)
        self.assertIn(b'<', r.content)

    @override_settings(SPA_INDEX_FILE=__import__('pathlib').Path('/nonexistent/index.html'))
    def test_spa_missing_build_message(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 503)
        self.assertIn(b'npm run build', r.content)

    def test_pagination_page_size(self):
        client = APIClient()
        admin = make_user('boss', is_staff=True)
        for i in range(5):
            make_user(f'user{i}')
        client.force_authenticate(admin)
        r = client.get('/api/users/?page_size=2')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['results']), 2)
        self.assertEqual(r.json()['count'], 6)


class HealthTest(TestCase):
    def test_health_without_worker(self):
        r = self.client.get('/api/health')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['status'], 'degraded')
        self.assertTrue(body['db']['ok'])
        self.assertFalse(body['worker']['ok'])
        self.assertIsNone(body['worker']['last_seen'])

    def test_health_with_fresh_and_stale_heartbeat(self):
        WorkerHeartbeat.beat(pid=42, hostname='h')
        body = self.client.get('/api/health/').json()
        self.assertEqual(body['status'], 'ok')
        self.assertTrue(body['worker']['ok'])
        self.assertEqual(body['worker']['pid'], 42)
        WorkerHeartbeat.objects.update(last_seen=timezone.now() - timedelta(minutes=5))
        body = self.client.get('/api/health/').json()
        self.assertEqual(body['status'], 'degraded')
        self.assertFalse(body['worker']['ok'])

    def test_health_db_down(self):
        with mock.patch('core.views.connection.cursor', side_effect=Exception('down')), \
                self.assertLogs('core.views', 'ERROR'):
            r = self.client.get('/api/health/')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['status'], 'error')


class CreateAdminCommandTest(TestCase):
    def test_create_and_update_idempotent(self):
        call_command('create_admin', username='boss', email='Boss@Example.org',
                     password='Admin1234', stdout=mock.MagicMock())
        user = User.objects.get(username='boss')
        self.assertTrue(is_admin(user))
        self.assertTrue(user.groups.filter(name='admin').exists())
        self.assertEqual(user.email, 'boss@example.org')
        self.assertTrue(user.check_password('Admin1234'))
        call_command('create_admin', username='boss', stdout=mock.MagicMock())
        self.assertEqual(User.objects.filter(username='boss').count(), 1)
        self.assertTrue(User.objects.get(username='boss').check_password('Admin1234'))
