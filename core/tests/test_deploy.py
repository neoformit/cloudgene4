"""Unit tests for TASKS T09a: hashers, system checks, JSON logging, JSON body limit."""
import json
import logging
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.checks import Error, Tags, Warning, run_checks
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from core import checks as core_checks
from core.logging_formatters import JsonFormatter
from core.middleware import JsonBodySizeLimitMiddleware

User = get_user_model()

# The real production order (core.test_runner.CloudgeneTestRunner overrides PASSWORD_HASHERS to
# a fast MD5-only hasher for the whole unit suite, so these tests restore the real list
# explicitly rather than reading django.conf.settings, which reflects that override).
PROD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]


class PasswordHasherTest(TestCase):
    def test_argon2_is_the_default_hasher(self):
        import cloudgene_django.settings as raw_settings
        self.assertEqual(raw_settings.PASSWORD_HASHERS[0],
                         'django.contrib.auth.hashers.Argon2PasswordHasher')
        self.assertEqual(raw_settings.PASSWORD_HASHERS, PROD_HASHERS)

    def test_pbkdf2_hash_is_upgraded_to_argon2_on_login(self):
        # Create the user under the legacy hasher only (as if from before this change).
        with override_settings(
                PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher']):
            user = User.objects.create_user(username='olduser', email='old@example.org',
                                            password='Secret123', full_name='Old')
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))

        # Now authenticate with the real (Argon2-first) hasher list: check_password() upgrades
        # the stored hash in place when it verifies under a non-preferred hasher.
        with override_settings(PASSWORD_HASHERS=PROD_HASHERS):
            ok = check_password('Secret123', user.password, setter=user.set_password)
            self.assertTrue(ok)
            user.save(update_fields=['password'])
        user.refresh_from_db()
        self.assertTrue(user.password.startswith('argon2$'), user.password)


class InsecureHashingCheckTest(SimpleTestCase):
    def _run(self):
        return run_checks(tags=[Tags.security])

    def test_error_when_set_outside_debug_and_e2e(self):
        with mock.patch.dict(os.environ, {'INSECURE_FAST_PASSWORD_HASHING': '1'}, clear=False):
            os.environ.pop('CLOUDGENE_E2E', None)
            with override_settings(DEBUG=False):
                errors = core_checks.check_insecure_hashing_not_leaked(None)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], Error)
        self.assertEqual(errors[0].id, core_checks.E_INSECURE_HASHING)

    def test_clean_when_e2e_flag_set(self):
        with mock.patch.dict(os.environ, {'INSECURE_FAST_PASSWORD_HASHING': '1',
                                          'CLOUDGENE_E2E': '1'}, clear=False):
            with override_settings(DEBUG=False):
                errors = core_checks.check_insecure_hashing_not_leaked(None)
        self.assertEqual(errors, [])

    def test_clean_when_debug(self):
        with mock.patch.dict(os.environ, {'INSECURE_FAST_PASSWORD_HASHING': '1'}, clear=False):
            os.environ.pop('CLOUDGENE_E2E', None)
            with override_settings(DEBUG=True):
                errors = core_checks.check_insecure_hashing_not_leaked(None)
        self.assertEqual(errors, [])

    def test_clean_when_flag_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('INSECURE_FAST_PASSWORD_HASHING', None)
            with override_settings(DEBUG=False):
                errors = core_checks.check_insecure_hashing_not_leaked(None)
        self.assertEqual(errors, [])


class DeployChecksTest(SimpleTestCase):
    def test_sqlite_warning_only_when_debug_off(self):
        with override_settings(DEBUG=False, DATABASES={
                'default': {'ENGINE': 'django.db.backends.sqlite3'}}):
            warnings = core_checks.check_database_engine(None)
        self.assertEqual([w.id for w in warnings], [core_checks.W_SQLITE_IN_PROD])

        with override_settings(DEBUG=False, DATABASES={
                'default': {'ENGINE': 'django.db.backends.postgresql'}}):
            self.assertEqual(core_checks.check_database_engine(None), [])

        with override_settings(DEBUG=True, DATABASES={
                'default': {'ENGINE': 'django.db.backends.sqlite3'}}):
            self.assertEqual(core_checks.check_database_engine(None), [])

    def test_allowed_hosts_wildcard_warning(self):
        with override_settings(DEBUG=False, ALLOWED_HOSTS=['*']):
            warnings = core_checks.check_allowed_hosts(None)
        self.assertEqual([w.id for w in warnings], [core_checks.W_ALLOWED_HOSTS_WILDCARD])
        with override_settings(DEBUG=False, ALLOWED_HOSTS=['cloudgene.example.org']):
            self.assertEqual(core_checks.check_allowed_hosts(None), [])

    def test_secret_key_weak_warning(self):
        with override_settings(DEBUG=False, SECRET_KEY='changeme'):
            warnings = core_checks.check_secret_key_strength(None)
        self.assertEqual([w.id for w in warnings], [core_checks.W_SECRET_KEY_WEAK])
        with override_settings(DEBUG=False, SECRET_KEY='x' * 50):
            self.assertEqual(core_checks.check_secret_key_strength(None), [])

    def test_secure_transport_warnings(self):
        with override_settings(DEBUG=False, SESSION_COOKIE_SECURE=False,
                               CSRF_COOKIE_SECURE=False, SECURE_SSL_REDIRECT=False,
                               SECURE_HSTS_SECONDS=0):
            warnings = core_checks.check_secure_transport_settings(None)
        self.assertEqual({w.id for w in warnings}, {
            core_checks.W_SECURE_COOKIES_OFF, core_checks.W_SSL_REDIRECT_OFF,
            core_checks.W_HSTS_OFF,
        })
        with override_settings(DEBUG=False, SESSION_COOKIE_SECURE=True,
                               CSRF_COOKIE_SECURE=True, SECURE_SSL_REDIRECT=True,
                               SECURE_HSTS_SECONDS=31536000):
            self.assertEqual(core_checks.check_secure_transport_settings(None), [])


class JsonFormatterTest(SimpleTestCase):
    def test_produces_valid_json_with_expected_keys(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name='cloudgene.jobs', level=logging.INFO, pathname=__file__, lineno=1,
            msg='job %s submitted', args=('abc123',), exc_info=None)
        line = formatter.format(record)
        data = json.loads(line)
        self.assertEqual(data['level'], 'INFO')
        self.assertEqual(data['logger'], 'cloudgene.jobs')
        self.assertEqual(data['message'], 'job abc123 submitted')
        self.assertIn('timestamp', data)
        self.assertIn('pid', data)

    def test_extra_data_is_included(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name='cloudgene.jobs', level=logging.INFO, pathname=__file__, lineno=1,
            msg='submitted', args=(), exc_info=None)
        record.data = {'job_id': 'abc123'}
        line = formatter.format(record)
        data = json.loads(line)
        self.assertEqual(data['data'], {'job_id': 'abc123'})


class JsonBodySizeLimitMiddlewareTest(SimpleTestCase):
    def _get_response(self, request):
        self._reached = True
        return HttpResponse('ok')

    def setUp(self):
        self._reached = False
        self.factory = RequestFactory()
        self.middleware = JsonBodySizeLimitMiddleware(self._get_response)

    def test_rejects_oversized_json_body_by_content_length_alone(self):
        request = self.factory.post('/api/auth/register/', data='{}',
                                    content_type='application/json')
        request.META['CONTENT_LENGTH'] = str(50 * 1024 * 1024)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self._reached)
        body = json.loads(response.content)
        self.assertEqual(body['error']['code'], 'upload_too_large')

    def test_allows_small_json_body(self):
        request = self.factory.post('/api/auth/register/', data='{}',
                                    content_type='application/json')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._reached)

    def test_exempts_multipart_regardless_of_content_length(self):
        request = self.factory.post('/api/jobs/', data={'f': 'x'})
        self.assertIn('multipart/form-data', request.META['CONTENT_TYPE'])
        request.META['CONTENT_LENGTH'] = str(500 * 1024 * 1024)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._reached)

    def test_ignores_non_api_paths(self):
        request = self.factory.post('/some/other/path/', data='{}',
                                    content_type='application/json')
        request.META['CONTENT_LENGTH'] = str(50 * 1024 * 1024)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._reached)
