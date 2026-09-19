"""
Accounts: validation rules, model invariants (K1), registration/activation, lockout,
password reset, profile/token/self-delete, admin users & groups, permission matrix.
"""
import json
import re
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from core import config

from . import validation
from .models import User, hash_token

PASSWORD = 'TestPass123'
CASES = json.loads((Path(__file__).parent / 'validation_cases.json').read_text())


def make_user(username='alice', email=None, password=PASSWORD, **extra):
    extra.setdefault('full_name', username.title())
    user = User.objects.create_user(username=username, email=email or f'{username}@example.org',
                                    password=password, **extra)
    if user.is_active and user.activated_at is None:
        user.activated_at = timezone.now()
        user.save(update_fields=['activated_at'])
    return user


def make_admin(username='boss'):
    user = make_user(username)
    user.make_admin()
    return user


@contextmanager
def setting(key, value):
    old = config.get(key)
    config.set_value(key, value)
    try:
        yield
    finally:
        config.set_value(key, old)


def register(client, **overrides):
    data = {'username': 'newuser', 'email': 'new@example.org', 'full_name': 'New User',
            'password': PASSWORD, 'password_confirm': PASSWORD}
    data.update(overrides)
    return client.post('/api/auth/register/', data, format='json')


def link_token(message, prefix):
    match = re.search(rf'{re.escape(prefix)}([A-Za-z0-9_\-]+)', message.body)
    assert match, message.body
    return match.group(1)


def fields(response):
    return response.json()['error']['fields']


# --- Validation rules (A4) ----------------------------------------------------------------------

class ValidationRulesTest(TestCase):
    """Same table as frontend/src/utils/validation.test.js (accounts/validation_cases.json)."""

    def test_username_cases(self):
        for value, expected in CASES['username']:
            with self.subTest(value=value):
                self.assertEqual(validation.validate_username(value), expected)

    def test_email_cases(self):
        for value, expected in CASES['email']:
            with self.subTest(value=value):
                self.assertEqual(validation.validate_email(value), expected)

    def test_password_cases(self):
        for value, confirm, expected in CASES['password']:
            with self.subTest(value=value, confirm=confirm):
                self.assertEqual(validation.validate_password(value, confirm), expected)

    def test_full_name_cases(self):
        for value, expected in CASES['full_name']:
            with self.subTest(value=value):
                self.assertEqual(validation.validate_full_name(value), expected)

    def test_group_name_cases(self):
        for value, expected in CASES['group_name']:
            with self.subTest(value=value):
                self.assertEqual(validation.validate_group_name(value), expected)

    def test_frontend_module_mirrors_messages(self):
        """Every backend message appears verbatim in the frontend mirror."""
        js = (Path(settings.BASE_DIR) / 'frontend/src/utils/validation.js').read_text()
        for key, message in validation.MESSAGES.items():
            with self.subTest(key=key):
                self.assertIn(json.dumps(message)[1:-1].replace('\\"', '"'), js)


# --- Model (K1) -----------------------------------------------------------------------------------

class UserModelTest(TestCase):
    def test_email_normalised_and_username_stripped(self):
        user = User.objects.create_user(username='  Bob ', email='  Bob@Example.ORG ',
                                        password=PASSWORD, full_name='Bob')
        user.refresh_from_db()
        self.assertEqual(user.username, 'Bob')
        self.assertEqual(user.email, 'bob@example.org')

    def test_db_rejects_case_variant_username(self):
        make_user('Bob', email='bob1@example.org')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='bob', email='bob2@example.org', password=PASSWORD)

    def test_db_rejects_case_variant_email(self):
        make_user('alice', email='a@x.org')
        with self.assertRaises(IntegrityError), transaction.atomic():
            # bypass normalisation to prove the DB constraint itself is case-insensitive
            User.objects.bulk_create([User(username='other', email='A@X.ORG')])

    def test_natural_key_lookup_ignores_case(self):
        user = make_user('Bob')
        self.assertEqual(User.objects.get_by_natural_key('bOB'), user)

    def test_admin_helpers(self):
        user = make_user()
        self.assertFalse(user.is_admin_user())
        user.make_admin()
        self.assertTrue(user.is_admin_user())
        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_group('admin'))

    def test_clean_uses_shared_rules(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            User(username='ab', email='bad', full_name='').clean()
        self.assertEqual(set(ctx.exception.message_dict), {'username', 'email', 'full_name'})


class DuplicateDetectionTest(TestCase):
    """The K1 migration refuses to run when case-duplicates exist (lists them)."""

    def migration(self):
        import importlib
        return importlib.import_module('accounts.migrations.0003_case_insensitive_identity')

    def test_find_case_duplicates(self):
        m = self.migration()
        make_user('Bob', email='bob@x.org')
        make_user('carol', email='carol@x.org')
        fake = mock.Mock()
        fake.objects.order_by.return_value.values_list.side_effect = [
            [(1, 'Bob'), (2, 'bob '), (3, 'carol')],
            [(1, 'bob@x.org'), (2, 'BOB@x.org'), (3, 'carol@x.org')],
        ]
        dupes = m.find_case_duplicates(fake)
        self.assertEqual(dupes['username'], {'bob': [(1, 'Bob'), (2, 'bob ')]})
        self.assertEqual(dupes['email'], {'bob@x.org': [(1, 'bob@x.org'), (2, 'BOB@x.org')]})
        text = m.format_duplicates(dupes)
        self.assertIn("id=1 'Bob'", text)
        self.assertIn("id=2 'BOB@x.org'", text)
        self.assertEqual(m.find_case_duplicates(User), {})

    def test_check_raises_with_list(self):
        m = self.migration()
        fake_user = mock.Mock()
        fake_user.objects.order_by.return_value.values_list.side_effect = [
            [(1, 'Bob'), (2, 'bob')], [(1, 'a@x.org'), (2, 'b@x.org')]]
        apps = mock.Mock()
        apps.get_model.return_value = fake_user
        with self.assertRaises(m.DuplicateUsersError) as ctx:
            m.check_and_normalise(apps, None)
        self.assertIn("id=2 'bob'", str(ctx.exception))
        self.assertIn('Nothing was changed', str(ctx.exception))


# --- Registration & activation -----------------------------------------------------------------

class RegistrationTest(APITestCase):
    def test_register_sends_activation_mail_and_stores_hashed_key(self):
        r = register(self.client)
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertTrue(body['activation_required'])
        self.assertFalse(body['user']['is_active'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['new@example.org'])
        key = link_token(mail.outbox[0], '/activate/')
        user = User.objects.get(username='newuser')
        self.assertEqual(user.activation_key, hash_token(key))
        self.assertNotIn(key, user.activation_key)
        self.assertFalse(user.is_active)

    def test_link_uses_server_url(self):
        with setting('server.url', 'https://cg.example.org/'):
            register(self.client)
        self.assertIn('https://cg.example.org/activate/', mail.outbox[0].body)

    def test_email_normalised(self):
        r = register(self.client, email='  New@Example.ORG ')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['user']['email'], 'new@example.org')

    def test_all_field_errors_reported(self):
        r = register(self.client, username='ab', email='nope', full_name=' ', password='short',
                     password_confirm='short')
        self.assertEqual(r.status_code, 400)
        f = fields(r)
        self.assertEqual(f['username'], [validation.MESSAGES['username_short']])
        self.assertEqual(f['email'], [validation.MESSAGES['email_invalid']])
        self.assertEqual(f['full_name'], [validation.MESSAGES['full_name_required']])
        self.assertEqual(f['password'], [validation.MESSAGES['password_short']])

    def test_password_mismatch(self):
        r = register(self.client, password_confirm='Other1234')
        self.assertEqual(fields(r)['password'], [validation.MESSAGES['password_mismatch']])

    def test_case_variants_rejected(self):
        make_user('Bob', email='bob@x.org')
        r = register(self.client, username='bOB', email='Bob@X.org')
        self.assertEqual(r.status_code, 400)
        self.assertIn('username', fields(r))
        self.assertIn('email', fields(r))
        self.assertEqual(User.objects.count(), 1)

    def test_privilege_fields_ignored(self):
        r = register(self.client, is_staff=True, is_superuser=True, is_active=True,
                     groups=['admin'])
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_staff or user.is_superuser or user.is_active)
        self.assertFalse(user.groups.exists())

    def test_without_activation_account_is_active(self):
        with setting('security.require_activation', False):
            r = register(self.client)
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.json()['activation_required'])
        self.assertEqual(mail.outbox, [])
        user = User.objects.get(username='newuser')
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.activated_at)
        login = self.client.post('/api/auth/login/', {'username': 'newuser', 'password': PASSWORD},
                                 format='json')
        self.assertEqual(login.status_code, 200)

    def test_mail_failure_rolls_back(self):
        with mock.patch('accounts.views.send_mail', side_effect=OSError('smtp down')):
            r = register(self.client)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['error']['code'], 'mail_failed')
        self.assertFalse(User.objects.exists())


class ActivationTest(APITestCase):
    def setUp(self):
        register(self.client)
        self.key = link_token(mail.outbox[0], '/activate/')

    def activate(self, key=None):
        return self.client.post(f'/api/auth/activate/{key or self.key}/')

    def login(self):
        return self.client.post('/api/auth/login/', {'username': 'newuser', 'password': PASSWORD},
                                format='json')

    def test_login_blocked_before_activation(self):
        r = self.login()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'account_inactive')

    def test_inactive_with_wrong_password_gets_generic_message(self):
        r = self.client.post('/api/auth/login/', {'username': 'newuser', 'password': 'Wrong1234'},
                             format='json')
        self.assertEqual(r.json()['error']['code'], 'invalid_credentials')

    def test_activate_is_idempotent(self):
        r = self.activate()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'activated')
        r = self.activate()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'already_active')
        self.assertEqual(self.login().status_code, 200)

    def test_invalid_key(self):
        r = self.activate('not-a-key')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], 'invalid_activation_key')

    def test_raw_hash_is_not_a_key(self):
        stored = User.objects.get(username='newuser').activation_key
        self.assertEqual(self.activate(stored).status_code, 400)

    def test_deactivated_user_cannot_reactivate_with_old_link(self):
        self.activate()
        User.objects.filter(username='newuser').update(is_active=False)
        r = self.activate()
        self.assertEqual(r.json()['status'], 'already_active')
        self.assertFalse(User.objects.get(username='newuser').is_active)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(f'/api/auth/activate/{self.key}/').status_code, 405)


class K1RegressionTest(APITestCase):
    """register(Bobby) → activate → admin adds group → register(bobby)/(BOB@x) rejected →
    exactly one user in the admin list."""

    def test_no_duplicate_users(self):
        admin = make_admin()
        Group.objects.create(name='researchers')
        anon = APIClient()
        r = register(anon, username='Bobby', email='bob@x.org')
        self.assertEqual(r.status_code, 201, r.content)
        key = link_token(mail.outbox[-1], '/activate/')
        self.assertEqual(anon.post(f'/api/auth/activate/{key}/').status_code, 200)

        staff = APIClient()
        staff.force_authenticate(admin)
        bob = User.objects.get(username='Bobby')
        r = staff.patch(f'/api/admin/users/{bob.pk}/', {'groups': ['researchers']}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['groups'], ['researchers'])
        self.assertTrue(bob.has_group('researchers'))

        r = register(anon, username='bobby', email='other@x.org')
        self.assertEqual(r.status_code, 400)
        self.assertIn('username', fields(r))
        r = register(anon, username='Robert', email='BOB@x.org')
        self.assertEqual(r.status_code, 400)
        self.assertIn('email', fields(r))
        r = register(anon, username='BOBBY', email=' Bob@X.ORG ')
        self.assertEqual(set(fields(r)), {'username', 'email'})

        r = staff.get('/api/admin/users/', {'search': 'bobby'})
        self.assertEqual(r.json()['count'], 1)
        row = r.json()['results'][0]
        self.assertEqual(row['username'], 'Bobby')
        self.assertEqual(row['groups'], ['researchers'])
        self.assertTrue(row['is_active'])


# --- Login & lockout (A6) ------------------------------------------------------------------------

class LoginTest(APITestCase):
    def setUp(self):
        self.user = make_user('alice')

    def login(self, password=PASSWORD, username='alice'):
        return self.client.post('/api/auth/login/', {'username': username, 'password': password},
                                format='json')

    def test_success_updates_last_login_and_session(self):
        self.assertIsNone(self.user.last_login)
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['user']['username'], 'alice')
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)
        self.assertTrue(self.client.get('/api/auth/me/').json()['authenticated'])

    def test_username_case_insensitive(self):
        self.assertEqual(self.login(username='ALICE').status_code, 200)

    def test_unknown_user_and_wrong_password_same_answer(self):
        a = self.login(username='nobody')
        b = self.login(password='Wrong1234')
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.json(), b.json())
        self.assertEqual(a.json()['error']['code'], 'invalid_credentials')

    def test_lockout_after_max_attempts(self):
        with setting('security.max_login_attempts', 3), setting('security.lockout_duration', 600):
            for _ in range(2):
                self.assertEqual(self.login(password='Wrong1234').status_code, 400)
            r = self.login(password='Wrong1234')
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.json()['error']['code'], 'account_locked')
            self.assertIn('10 minutes', r.json()['error']['message'])
            self.assertIn('Retry-After', r)
            # correct password is refused while locked
            self.assertEqual(self.login().status_code, 429)
            # lock expires
            User.objects.filter(pk=self.user.pk).update(
                locked_until=timezone.now() - timedelta(seconds=1))
            self.assertEqual(self.login().status_code, 200)
            self.user.refresh_from_db()
            self.assertEqual(self.user.login_attempts, 0)
            self.assertIsNone(self.user.locked_until)

    def test_success_resets_counter(self):
        with setting('security.max_login_attempts', 3):
            self.login(password='Wrong1234')
            self.login(password='Wrong1234')
            self.assertEqual(self.login().status_code, 200)
            self.user.refresh_from_db()
            self.assertEqual(self.user.login_attempts, 0)
            self.assertEqual(self.login(password='Wrong1234').status_code, 400)

    def test_lockout_disabled_with_zero(self):
        with setting('security.max_login_attempts', 0):
            for _ in range(8):
                self.login(password='Wrong1234')
            self.assertEqual(self.login().status_code, 200)

    def test_obtain_token_endpoint_removed(self):
        r = self.client.post('/api/auth/token/', {'username': 'alice', 'password': PASSWORD})
        self.assertEqual(r.status_code, 404)


# --- Password reset (A5) -------------------------------------------------------------------------

class PasswordResetTest(APITestCase):
    def setUp(self):
        self.user = make_user('alice', email='alice@x.org')

    def request_reset(self, email):
        return self.client.post('/api/auth/password-reset/', {'email': email}, format='json')

    def confirm(self, token, password='NewPass456', **extra):
        return self.client.post(f'/api/auth/password-reset/{token}/',
                                {'password': password, **extra}, format='json')

    def test_same_answer_for_known_unknown_and_inactive(self):
        make_user('sleepy', email='sleepy@x.org', is_active=False)
        answers = [self.request_reset(e) for e in ('ALICE@x.org', 'nobody@x.org', 'sleepy@x.org',
                                                   'not-an-email')]
        for r in answers:
            self.assertEqual(r.status_code, 200)
        self.assertEqual(len({json.dumps(r.json()) for r in answers}), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alice@x.org'])

    def test_missing_email_is_field_error(self):
        r = self.client.post('/api/auth/password-reset/', {}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('email', fields(r))

    def test_token_hashed_single_use(self):
        self.request_reset('alice@x.org')
        token = link_token(mail.outbox[0], '/recover/')
        self.user.refresh_from_db()
        self.assertEqual(self.user.password_reset_token, hash_token(token))
        r = self.confirm(token, password_confirm='NewPass456')
        self.assertEqual(r.status_code, 200, r.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456'))
        r = self.confirm(token)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], 'invalid_token')

    def test_expired(self):
        self.request_reset('alice@x.org')
        token = link_token(mail.outbox[0], '/recover/')
        User.objects.filter(pk=self.user.pk).update(
            password_reset_expires=timezone.now() - timedelta(minutes=1))
        r = self.confirm(token)
        self.assertEqual(r.json()['error']['code'], 'expired_token')

    def test_expires_after_24h(self):
        self.request_reset('alice@x.org')
        self.user.refresh_from_db()
        delta = self.user.password_reset_expires - timezone.now()
        self.assertTrue(timedelta(hours=23, minutes=59) < delta <= timedelta(hours=24))

    def test_password_rules(self):
        self.request_reset('alice@x.org')
        token = link_token(mail.outbox[0], '/recover/')
        r = self.confirm(token, password='weakpass1')
        self.assertEqual(fields(r)['password'], [validation.MESSAGES['password_upper']])
        # token still usable after a validation error
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_reset_clears_lockout(self):
        User.objects.filter(pk=self.user.pk).update(
            login_attempts=9, locked_until=timezone.now() + timedelta(hours=1))
        self.request_reset('alice@x.org')
        self.confirm(link_token(mail.outbox[0], '/recover/'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_attempts, 0)
        self.assertIsNone(self.user.locked_until)


# --- Profile (A3, A7) -----------------------------------------------------------------------------

class ProfileTest(APITestCase):
    def setUp(self):
        self.user = make_user('alice', email='alice@x.org')
        self.client.login(username='alice', password=PASSWORD)

    def patch(self, **data):
        return self.client.patch('/api/me/', data, format='json')

    def test_get(self):
        body = self.client.get('/api/me/').json()
        self.assertEqual(body['username'], 'alice')
        self.assertIsNone(body['api_token'])
        self.assertEqual(body['groups'], [])

    def test_update_full_name(self):
        r = self.patch(full_name='  Alice A. ')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['full_name'], 'Alice A.')
        self.assertEqual(fields(self.patch(full_name=''))['full_name'],
                         [validation.MESSAGES['full_name_required']])

    def test_email_change_requires_current_password(self):
        r = self.patch(email='new@x.org')
        self.assertEqual(r.status_code, 400)
        self.assertIn('current_password', fields(r))
        r = self.patch(email='new@x.org', current_password='Wrong123')
        self.assertIn('current_password', fields(r))
        r = self.patch(email=' New@X.org', current_password=PASSWORD)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['email'], 'new@x.org')
        # unchanged e-mail needs no password
        self.assertEqual(self.patch(email='new@x.org', full_name='A').status_code, 200)

    def test_email_unique_ignoring_case(self):
        make_user('bob', email='bob@x.org')
        r = self.patch(email='BOB@x.org', current_password=PASSWORD)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(fields(r)['email'], ['This e-mail address is already registered.'])

    def test_password_change(self):
        r = self.patch(password='NewPass456')
        self.assertIn('current_password', fields(r))
        r = self.patch(password='weak', current_password=PASSWORD)
        self.assertEqual(fields(r)['password'], [validation.MESSAGES['password_short']])
        r = self.patch(password='NewPass456', password_confirm='NewPass457',
                       current_password=PASSWORD)
        self.assertEqual(fields(r)['password'], [validation.MESSAGES['password_mismatch']])
        r = self.patch(password='NewPass456', password_confirm='NewPass456',
                       current_password=PASSWORD)
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456'))
        # this session stays logged in
        self.assertTrue(self.client.get('/api/auth/me/').json()['authenticated'])

    def test_blank_password_means_unchanged(self):
        r = self.patch(password='', full_name='Alice')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_no_mass_assignment(self):
        Group.objects.create(name='researchers')
        r = self.patch(is_staff=True, is_superuser=True, is_active=False, groups=['researchers'],
                       username='mallory', is_admin=True, full_name='Alice')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'alice')
        self.assertFalse(self.user.is_staff or self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.groups.exists())
        self.assertFalse(r.json()['is_admin'])

    def test_put_not_allowed(self):
        self.assertEqual(self.client.put('/api/me/', {}, format='json').status_code, 405)


class ApiTokenTest(APITestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.client.login(username='alice', password=PASSWORD)

    def test_create_use_regenerate_revoke(self):
        r = self.client.post('/api/me/token/')
        self.assertEqual(r.status_code, 201)
        key = r.json()['token']
        self.assertTrue(r.json()['created'])
        me = self.client.get('/api/me/').json()
        self.assertIsNotNone(me['api_token']['created'])
        self.assertNotIn(key, json.dumps(me))

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {key}')
        self.assertEqual(api.get('/api/me/').json()['username'], 'alice')

        key2 = self.client.post('/api/me/token/').json()['token']
        self.assertNotEqual(key, key2)
        self.assertEqual(api.get('/api/me/').status_code, 401)
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

        self.assertEqual(self.client.delete('/api/me/token/').status_code, 200)
        api.credentials(HTTP_AUTHORIZATION=f'Token {key2}')
        self.assertEqual(api.get('/api/me/').status_code, 401)
        self.assertIsNone(self.client.get('/api/me/').json()['api_token'])

    def test_token_client_needs_no_csrf(self):
        key = self.client.post('/api/me/token/').json()['token']
        api = APIClient(enforce_csrf_checks=True)
        api.credentials(HTTP_AUTHORIZATION=f'Token {key}')
        r = api.patch('/api/me/', {'full_name': 'Via Token'}, format='json')
        self.assertEqual(r.status_code, 200)


class SelfDeleteTest(APITestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.client.login(username='alice', password=PASSWORD)

    def test_requires_password(self):
        r = self.client.delete('/api/me/', {'password': 'Wrong123'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', fields(r))
        r = self.client.delete('/api/me/', format='json')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_logs_out(self):
        r = self.client.delete('/api/me/', {'password': PASSWORD}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='alice').exists())
        self.assertFalse(self.client.get('/api/auth/me/').json()['authenticated'])
        r = self.client.post('/api/auth/login/', {'username': 'alice', 'password': PASSWORD},
                             format='json')
        self.assertEqual(r.status_code, 400)

    def test_last_admin_cannot_delete_self(self):
        self.user.make_admin()
        r = self.client.delete('/api/me/', {'password': PASSWORD}, format='json')
        self.assertEqual(r.json()['error']['code'], 'last_admin')
        make_admin('boss2')
        r = self.client.delete('/api/me/', {'password': PASSWORD}, format='json')
        self.assertEqual(r.status_code, 200)


# --- Admin users & groups (A1, A8) ----------------------------------------------------------------

class AdminUsersTest(APITestCase):
    def setUp(self):
        self.admin = make_admin('boss')
        self.alice = make_user('alice', full_name='Alice Liddell')
        self.bob = make_user('bob', email='robert@x.org')
        self.researchers = Group.objects.create(name='researchers')
        self.alice.groups.add(self.researchers)
        self.client.force_authenticate(self.admin)

    def url(self, user=None):
        return f'/api/admin/users/{user.pk}/' if user else '/api/admin/users/'

    def test_list_shape_and_search(self):
        r = self.client.get(self.url())
        self.assertEqual(r.json()['count'], 3)
        row = next(u for u in r.json()['results'] if u['username'] == 'alice')
        for key in ('id', 'username', 'email', 'full_name', 'is_active', 'is_admin', 'groups',
                    'date_joined', 'last_login', 'is_superuser', 'activated_at'):
            self.assertIn(key, row)
        self.assertEqual(row['groups'], ['researchers'])
        boss = next(u for u in r.json()['results'] if u['username'] == 'boss')
        self.assertTrue(boss['is_admin'])
        self.assertEqual(boss['groups'], ['admin'])
        for term, expected in (('LIDDELL', ['alice']), ('robert', ['bob']), ('bo', ['bob', 'boss'])):
            names = [u['username'] for u in self.client.get(self.url(), {'search': term}).json()['results']]
            self.assertEqual(names, expected, term)
        names = [u['username'] for u in self.client.get(self.url(), {'group': 'researchers'}).json()['results']]
        self.assertEqual(names, ['alice'])
        r = self.client.get(self.url(), {'page_size': 2, 'page': 2})
        self.assertEqual(len(r.json()['results']), 1)

    def test_set_groups_by_name(self):
        lab = Group.objects.create(name='lab')
        r = self.client.patch(self.url(self.bob), {'groups': ['lab', 'researchers']}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['groups'], ['lab', 'researchers'])
        r = self.client.patch(self.url(self.bob), {'groups': ['lab']}, format='json')
        self.assertEqual(r.json()['groups'], ['lab'])
        self.assertEqual(list(self.bob.groups.all()), [lab])

    def test_unknown_group(self):
        r = self.client.patch(self.url(self.bob), {'groups': ['nope']}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('groups', fields(r))

    def test_admin_group_only_via_is_admin(self):
        r = self.client.patch(self.url(self.bob), {'groups': ['admin']}, format='json')
        self.assertEqual(r.json()['groups'], [])
        self.assertFalse(r.json()['is_admin'])
        r = self.client.patch(self.url(self.bob), {'is_admin': True}, format='json')
        self.assertTrue(r.json()['is_admin'])
        self.assertEqual(r.json()['groups'], ['admin'])
        # a groups edit keeps admin membership
        r = self.client.patch(self.url(self.bob), {'groups': ['researchers']}, format='json')
        self.assertEqual(r.json()['groups'], ['admin', 'researchers'])
        r = self.client.patch(self.url(self.bob), {'is_admin': False}, format='json')
        self.assertFalse(r.json()['is_admin'])
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_staff)

    def test_activate_deactivate(self):
        r = self.client.patch(self.url(self.bob), {'is_active': False}, format='json')
        self.assertFalse(r.json()['is_active'])
        anon = APIClient()
        r = anon.post('/api/auth/login/', {'username': 'bob', 'password': PASSWORD}, format='json')
        self.assertEqual(r.status_code, 403)
        self.client.patch(self.url(self.bob), {'is_active': True}, format='json')
        r = anon.post('/api/auth/login/', {'username': 'bob', 'password': PASSWORD}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_self_protection(self):
        r = self.client.patch(self.url(self.admin), {'is_active': False}, format='json')
        self.assertIn('is_active', fields(r))
        r = self.client.patch(self.url(self.admin), {'is_admin': False}, format='json')
        self.assertIn('is_admin', fields(r))
        r = self.client.delete(self.url(self.admin))
        self.assertEqual(r.json()['error']['code'], 'cannot_delete_self')

    def test_superuser_stays_admin(self):
        root = User.objects.create_superuser('root', 'root@x.org', PASSWORD, full_name='Root')
        r = self.client.patch(self.url(root), {'is_admin': False}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_privilege_fields_not_writable(self):
        r = self.client.patch(self.url(self.bob), {'is_superuser': True, 'username': 'x',
                                                   'email': 'x@x.org'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.bob.refresh_from_db()
        self.assertEqual((self.bob.username, self.bob.is_superuser), ('bob', False))

    def test_delete(self):
        r = self.client.delete(self.url(self.bob))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.bob.pk).exists())
        self.assertEqual(self.client.delete(self.url(self.bob)).status_code, 404)

    def test_put_and_post_not_allowed(self):
        self.assertEqual(self.client.put(self.url(self.bob), {}, format='json').status_code, 405)
        self.assertEqual(self.client.post(self.url(), {}, format='json').status_code, 405)


class AdminGroupsTest(APITestCase):
    def setUp(self):
        self.admin = make_admin('boss')
        self.client.force_authenticate(self.admin)
        self.researchers = Group.objects.create(name='researchers')
        make_user('alice').groups.add(self.researchers)
        make_user('bob').groups.add(self.researchers)

    def test_list_with_member_count(self):
        r = self.client.get('/api/admin/groups/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [
            {'id': Group.objects.get(name='admin').pk, 'name': 'admin', 'member_count': 1},
            {'id': self.researchers.pk, 'name': 'researchers', 'member_count': 2},
        ])

    def test_create(self):
        r = self.client.post('/api/admin/groups/', {'name': ' lab-1 '}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['name'], 'lab-1')
        self.assertEqual(r.json()['member_count'], 0)

    def test_create_duplicate_ignoring_case(self):
        r = self.client.post('/api/admin/groups/', {'name': 'Researchers'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('name', fields(r))

    def test_create_invalid(self):
        for name in ('', 'with space', None):
            r = self.client.post('/api/admin/groups/', {'name': name} if name is not None else {},
                                 format='json')
            self.assertEqual(r.status_code, 400)
            self.assertIn('name', fields(r))

    def test_delete(self):
        r = self.client.delete(f'/api/admin/groups/{self.researchers.pk}/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Group.objects.filter(name='researchers').exists())
        self.assertTrue(User.objects.filter(username='alice').exists())

    def test_admin_group_protected(self):
        admin_group = Group.objects.get(name='admin')
        r = self.client.delete(f'/api/admin/groups/{admin_group.pk}/')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], 'protected_group')


# --- Permission matrix (A7, A8) -------------------------------------------------------------------

class PermissionMatrixTest(APITestCase):
    """Every account endpoint × {anonymous, user, admin} (401 = not logged in, 403 = not admin)."""

    def setUp(self):
        self.user = make_user('alice')
        self.admin = make_admin('boss')
        self.victim = make_user('victim')
        self.group = Group.objects.create(name='lab')

    def status(self, who, method, url, data=None):
        client = APIClient()
        if who == 'user':
            client.force_authenticate(self.user)
        elif who == 'admin':
            client.force_authenticate(self.admin)
        return getattr(client, method)(url, data or {}, format='json').status_code

    def test_matrix(self):
        u, g = self.victim.pk, self.group.pk
        rows = [
            # method, url, data, anon, user, admin
            ('get', '/api/auth/me/', None, 200, 200, 200),
            ('post', '/api/auth/logout/', None, 200, 200, 200),
            ('get', '/api/me/', None, 401, 200, 200),
            ('patch', '/api/me/', {'full_name': 'X'}, 401, 200, 200),
            ('post', '/api/me/token/', None, 401, 201, 201),
            ('delete', '/api/me/token/', None, 401, 200, 200),
            ('delete', '/api/me/', {'password': 'wrong'}, 401, 400, 400),
            ('get', '/api/admin/users/', None, 401, 403, 200),
            ('get', f'/api/admin/users/{u}/', None, 401, 403, 200),
            ('patch', f'/api/admin/users/{u}/', {'is_active': True}, 401, 403, 200),
            ('get', '/api/admin/groups/', None, 401, 403, 200),
            ('post', '/api/admin/groups/', {'name': 'newgroup'}, 401, 403, 201),
            ('delete', f'/api/admin/groups/{g}/', None, 401, 403, 204),
            ('delete', f'/api/admin/users/{u}/', None, 401, 403, 204),
            ('get', '/api/users/', None, 404, 404, 404),
            ('get', '/api/groups/', None, 404, 404, 404),
        ]
        for method, url, data, *expected in rows:
            for who, want in zip(('anon', 'user', 'admin'), expected):
                with self.subTest(method=method, url=url, who=who):
                    self.assertEqual(self.status(who, method, url, data), want)

    def test_non_admin_gets_no_data(self):
        client = APIClient()
        client.force_authenticate(self.user)
        r = client.get('/api/admin/users/')
        self.assertEqual(set(r.json()), {'error'})
        self.assertEqual(r.json()['error']['code'], 'permission_denied')

    def test_admin_via_group_only(self):
        """Admin = admin group member without is_staff also passes (core.permissions.is_admin)."""
        member = make_user('groupie')
        member.groups.add(Group.objects.get(name='admin'))
        self.assertEqual(self.status_for(member, 'get', '/api/admin/users/'), 200)

    def status_for(self, user, method, url):
        client = APIClient()
        client.force_authenticate(user)
        return getattr(client, method)(url).status_code
