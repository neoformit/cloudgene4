"""Accounts, profile & user admin (T04): scenarios A1–A7, D3 and the profile/admin parts of X1.

Tests create their own uniquely named users (`fresh_user`) so they can run in any order and
never lock out or modify the seeded alice/bob/admin (except read-only checks).
"""
import re
import time
import uuid
from urllib.parse import urlparse

import pytest
import requests
from playwright.sync_api import expect

from e2e.constants import USERS
from e2e.helpers import ApiClient, email_text, extract_link, latest_email
from e2e.pages import LoginPage, Navbar

PASSWORD = 'E2ePass123'


def uniq(prefix):
    return f'{prefix}{uuid.uuid4().hex[:8]}'


@pytest.fixture
def fresh_user(stack):
    """Factory: create an active user (optionally in groups) directly in the DB."""
    def _make(prefix='user', groups=(), password=PASSWORD):
        name = uniq(prefix)
        stack.django_shell(
            'from accounts.models import User\n'
            'from django.contrib.auth.models import Group\n'
            'from django.utils import timezone\n'
            f'u = User.objects.create_user(username={name!r}, email={name + "@e2e.test"!r}, '
            f'password={password!r}, full_name="E2E {name}")\n'
            'u.activated_at = timezone.now(); u.save()\n'
            f'u.groups.set(Group.objects.filter(name__in={list(groups)!r}))\n')
        return {'username': name, 'email': f'{name}@e2e.test', 'password': password}
    return _make


def ui_login(page, username, password):
    LoginPage(page).open().login(username, password)


def path_of(url):
    parsed = urlparse(url)
    return parsed.path + (('?' + parsed.query) if parsed.query else '')


# --- A1 ---------------------------------------------------------------------------------------

def test_a1_register_activate_login(page, stack, expect_api_error):
    """Register → activation mail → login blocked before activation → activate (twice: the second
    click is harmless) → login."""
    name = uniq('reg')
    email = f'{name}@e2e.test'
    page.goto('/register')
    page.get_by_test_id('register-username').fill(name)
    page.get_by_test_id('register-full-name').fill('Reg Istered')
    page.get_by_test_id('register-email').fill(email.upper())  # normalised server-side
    page.get_by_test_id('register-password').fill(PASSWORD)
    page.get_by_test_id('register-password-confirm').fill(PASSWORD)
    page.get_by_test_id('register-submit').click()
    expect(page.get_by_test_id('register-success')).to_contain_text('activation')

    link = extract_link(latest_email(stack.outbox_dir, to=email), '/activate/')

    expect_api_error(403, '/api/auth/login*')
    ui_login(page, name, PASSWORD)
    error = page.get_by_test_id('login-error')
    expect(error).to_contain_text('not active')
    expect(error).to_have_attribute('data-code', 'account_inactive')

    page.goto(path_of(link))
    expect(page.get_by_test_id('activate-success')).to_have_attribute('data-status', 'activated')
    page.goto(path_of(link))  # re-clicking the link must not tell the user to re-register (K1)
    expect(page.get_by_test_id('activate-success')).to_have_attribute('data-status', 'already_active')

    ui_login(page, name, PASSWORD)
    Navbar(page).expect_logged_in(name)


# --- A2 (K1) -----------------------------------------------------------------------------------

def test_a2_case_variant_duplicates_rejected(page, api, expect_api_error):
    expect_api_error(400, '/api/auth/register*')
    admin = api('admin')
    before = admin.get_json('/api/admin/users/?search=alice')['count']

    page.goto('/register')
    page.get_by_test_id('register-username').fill('ALICE')
    page.get_by_test_id('register-full-name').fill('Alice Again')
    page.get_by_test_id('register-email').fill(uniq('x') + '@e2e.test')
    page.get_by_test_id('register-password').fill(PASSWORD)
    page.get_by_test_id('register-password-confirm').fill(PASSWORD)
    page.get_by_test_id('register-submit').click()
    expect(page.get_by_test_id('register-username-error')).to_contain_text('already taken')

    page.get_by_test_id('register-username').fill(uniq('alice'))
    page.get_by_test_id('register-email').fill(' ' + USERS['alice']['email'].upper() + ' ')
    page.get_by_test_id('register-submit').click()
    expect(page.get_by_test_id('register-email-error')).to_contain_text('already registered')
    expect(page.get_by_test_id('register-success')).to_have_count(0)

    assert admin.get_json('/api/admin/users/?search=alice')['count'] == before == 1


def test_a2_client_side_rules_match_server(page):
    """Invalid input is caught in the browser (no request) with the server's wording."""
    page.goto('/register')
    page.get_by_test_id('register-username').fill('ab_c')
    page.get_by_test_id('register-password').fill('lowercase1')
    page.get_by_test_id('register-password-confirm').fill('lowercase1')
    page.get_by_test_id('register-submit').click()
    expect(page.get_by_test_id('register-username-error')).to_contain_text('Only characters A-Z')
    expect(page.get_by_test_id('register-password-error')).to_contain_text('uppercase')


# --- A3 ----------------------------------------------------------------------------------------

@pytest.mark.serial
def test_a3_lockout(page, fresh_user, server_settings, expect_api_error):
    server_settings.update('security', max_login_attempts=3, lockout_duration=3)
    user = fresh_user('lock')
    expect_api_error((400, 429), '/api/auth/login*')
    error = page.get_by_test_id('login-error')

    login_page = LoginPage(page).open()
    for _ in range(2):
        login_page.login(user['username'], 'Wrong12345')
        expect(error).to_have_attribute('data-code', 'invalid_credentials')
    login_page.login(user['username'], 'Wrong12345')
    expect(error).to_have_attribute('data-code', 'account_locked')
    expect(error).to_contain_text('locked')
    # the right password is refused while locked
    login_page.login(user['username'], user['password'])
    expect(error).to_have_attribute('data-code', 'account_locked')

    time.sleep(3.5)  # the (shortened) lockout window passes
    login_page.login(user['username'], user['password'])
    Navbar(page).expect_logged_in(user['username'])


# --- A4 ----------------------------------------------------------------------------------------

def test_a4_password_reset(page, stack, fresh_user, expect_api_error):
    user = fresh_user('reset')

    # unknown address: same answer as a known one (A5 of the issue register: no enumeration)
    page.goto('/reset-password')
    page.get_by_test_id('reset-email').fill(uniq('nobody') + '@e2e.test')
    page.get_by_test_id('reset-submit').click()
    unknown_text = page.get_by_test_id('reset-success').inner_text()

    page.goto('/reset-password')
    page.get_by_test_id('reset-email').fill(user['email'].upper())
    page.get_by_test_id('reset-submit').click()
    expect(page.get_by_test_id('reset-success')).to_have_text(unknown_text)

    mail = latest_email(stack.outbox_dir, to=user['email'])
    link = extract_link(mail, '/recover/')
    assert '24 hours' in email_text(mail)

    page.goto(path_of(link))
    page.get_by_test_id('recover-password').fill('nouppercase1')
    page.get_by_test_id('recover-password-confirm').fill('nouppercase1')
    page.get_by_test_id('recover-submit').click()
    expect(page.get_by_test_id('recover-password-error')).to_contain_text('uppercase')

    page.get_by_test_id('recover-password').fill('Brand9New')
    page.get_by_test_id('recover-password-confirm').fill('Brand9New')
    page.get_by_test_id('recover-submit').click()
    expect(page.get_by_test_id('recover-success')).to_be_visible()

    # single use
    expect_api_error(400, '/api/auth/password-reset/*')
    page.goto(path_of(link))
    page.get_by_test_id('recover-password').fill('Other9Pass')
    page.get_by_test_id('recover-password-confirm').fill('Other9Pass')
    page.get_by_test_id('recover-submit').click()
    expect(page.get_by_test_id('recover-error')).to_contain_text('already been used')

    ui_login(page, user['username'], 'Brand9New')
    Navbar(page).expect_logged_in(user['username'])


# --- A5 ----------------------------------------------------------------------------------------

def test_a5_profile_name_email_password_token(page, stack, fresh_user, expect_api_error):
    user = fresh_user('prof')
    ui_login(page, user['username'], user['password'])
    Navbar(page).expect_logged_in(user['username'])
    page.goto('/profile')

    # name
    page.get_by_test_id('profile-full-name').fill('Renamed Person')
    page.get_by_test_id('profile-save').click()
    expect(page.get_by_test_id('profile-success')).to_be_visible()

    # e-mail: needs the current password (field appears once the address changes)
    new_email = uniq('new') + '@e2e.test'
    page.get_by_test_id('profile-email').fill(new_email)
    expect(page.get_by_test_id('profile-email-current-password')).to_be_visible()
    page.get_by_test_id('profile-email-current-password').fill(user['password'])
    page.get_by_test_id('profile-save').click()
    expect(page.get_by_test_id('profile-success')).to_be_visible()
    expect(page.get_by_test_id('profile-email-current-password')).to_have_count(0)

    # password: wrong current password → server field error
    expect_api_error(400, '/api/me*')
    page.get_by_test_id('password-current').fill('Wrong12345')
    page.get_by_test_id('password-new').fill('Changed9Pw')
    page.get_by_test_id('password-confirm').fill('Changed9Pw')
    page.get_by_test_id('password-save').click()
    expect(page.get_by_test_id('password-current-error')).to_contain_text('not correct')
    page.get_by_test_id('password-current').fill(user['password'])
    page.get_by_test_id('password-save').click()
    # two PBKDF2 rounds (check + set) on a busy host can take a few seconds
    expect(page.get_by_test_id('password-success')).to_be_visible(timeout=15000)

    # still logged in after the change; the server state is what the page showed
    page.reload()
    expect(page.get_by_test_id('profile-full-name')).to_have_value('Renamed Person')
    expect(page.get_by_test_id('profile-email')).to_have_value(new_email)

    # API token: created, shown once, works like `curl -H "Authorization: Token ..."`
    expect(page.get_by_test_id('token-status')).to_have_attribute('data-state', 'none')
    page.get_by_test_id('token-create').click()
    token = page.get_by_test_id('token-value').input_value()
    assert re.fullmatch(r'[0-9a-f]{40}', token)
    expect(page.get_by_test_id('token-status')).to_have_attribute('data-state', 'active')
    r = requests.get(stack.base_url + '/api/me/', headers={'Authorization': 'Token ' + token}, timeout=10)
    assert r.status_code == 200 and r.json()['username'] == user['username']
    assert 'token' not in r.text.replace('"api_token"', '')  # key never echoed back

    page.reload()
    expect(page.get_by_test_id('token-value')).to_have_count(0)  # shown once only
    page.get_by_test_id('token-revoke').click()
    expect(page.get_by_test_id('token-status')).to_have_attribute('data-state', 'none')
    r = requests.get(stack.base_url + '/api/me/', headers={'Authorization': 'Token ' + token}, timeout=10)
    assert r.status_code == 401

    # the new password is the one that works
    client = ApiClient(stack.base_url)
    client.login(user['username'], 'Changed9Pw')


# --- A6 ----------------------------------------------------------------------------------------

def test_a6_delete_own_account(page, stack, fresh_user, expect_api_error, base_url):
    user = fresh_user('gone')
    ui_login(page, user['username'], user['password'])
    Navbar(page).expect_logged_in(user['username'])
    page.goto('/profile')
    page.get_by_test_id('delete-account').click()

    expect_api_error(400, '/api/me*')
    page.get_by_test_id('delete-password').fill('Wrong12345')
    page.get_by_test_id('delete-confirm').click()
    expect(page.get_by_test_id('delete-error')).to_contain_text('not correct')

    page.get_by_test_id('delete-password').fill(user['password'])
    page.get_by_test_id('delete-confirm').click()
    expect(page).to_have_url(base_url + '/')
    Navbar(page).expect_logged_out()

    expect_api_error(400, '/api/auth/login*')
    ui_login(page, user['username'], user['password'])
    expect(page.get_by_test_id('login-error')).to_have_attribute('data-code', 'invalid_credentials')


# --- A7 / X1 -----------------------------------------------------------------------------------

def test_a7_non_admin_blocked_from_admin_ui_and_api(page, login, api, stack, base_url):
    login(page, 'bob')
    page.goto('/admin/users')
    expect(page).to_have_url(base_url + '/')
    expect(page.get_by_test_id('admin-users-table')).to_have_count(0)

    alice_id = api('admin').get_json('/api/admin/users/?search=alice')['results'][0]['id']
    bob = api('bob')
    anon = ApiClient(stack.base_url)
    for method, path in (('get', '/api/admin/users/'), ('get', f'/api/admin/users/{alice_id}/'),
                         ('patch', f'/api/admin/users/{alice_id}/'), ('delete', f'/api/admin/users/{alice_id}/'),
                         ('get', '/api/admin/groups/'), ('post', '/api/admin/groups/')):
        r = getattr(bob, method)(path, json={'is_active': False, 'name': 'hax'})
        assert r.status_code == 403, (method, path, r.status_code)
        assert set(r.json()) == {'error'}, r.text  # no data leak
        assert getattr(anon, method)(path, json={}).status_code == 401, (method, path)

    # no mass-assignment through the profile endpoint
    r = bob.patch('/api/me/', json={'is_staff': True, 'is_superuser': True, 'groups': ['admin'],
                                    'username': 'root', 'full_name': USERS['bob']['full_name']})
    assert r.status_code == 200
    assert r.json()['username'] == 'bob' and r.json()['is_admin'] is False
    assert r.json()['groups'] == []
    # the old unscoped endpoints are gone
    assert bob.get('/api/users/').status_code == 404
    assert api('admin').get_json(f'/api/admin/users/{alice_id}/')['is_active'] is True


# --- D3 ----------------------------------------------------------------------------------------

def test_d3_admin_users(page, login, api, fresh_user, expect_api_error):
    admin = api('admin')
    total_before = admin.get_json('/api/admin/users/')['count']
    user = fresh_user('dthree')
    login(page, 'admin')
    page.goto('/admin/users')

    # memberships are shown (T02 found the Groups column empty)
    page.get_by_test_id('admin-users-search').fill('alice')
    page.get_by_test_id('admin-users-search-submit').click()
    alice = page.locator('[data-testid="admin-user-row"][data-username="alice"]')
    expect(alice.locator('[data-testid="admin-user-group"][data-group="researchers"]')).to_be_visible()

    page.get_by_test_id('admin-users-search').fill(user['username'])
    page.get_by_test_id('admin-users-search-submit').click()
    row = page.locator(f'[data-testid="admin-user-row"][data-username="{user["username"]}"]')
    expect(row).to_have_count(1)
    expect(page.get_by_test_id('admin-user-row')).to_have_count(1)

    member = api()
    member.login(user['username'], user['password'])
    workflow_known = admin.get('/api/workflows/all-inputs/').status_code == 200
    if workflow_known:
        assert member.get('/api/workflows/all-inputs/').status_code == 404

    # add a group → immediate workflow access
    row.get_by_test_id('admin-user-group-add').select_option('researchers')
    chip = row.locator('[data-testid="admin-user-group"][data-group="researchers"]')
    expect(chip).to_be_visible()
    assert admin.get_json(f'/api/admin/users/?search={user["username"]}')['results'][0]['groups'] == ['researchers']
    if workflow_known:
        assert member.get('/api/workflows/all-inputs/').status_code == 200

    # remove it again → access gone
    chip.get_by_test_id('admin-user-group-remove').click()
    expect(chip).to_have_count(0)
    if workflow_known:
        assert member.get('/api/workflows/all-inputs/').status_code == 404

    # deactivate / activate
    row.get_by_test_id('admin-user-toggle-active').click()
    expect(row.get_by_test_id('admin-user-status')).to_have_attribute('data-state', 'inactive')
    probe = ApiClient(member.base_url)
    probe.get('/api/auth/me/')  # CSRF cookie
    r = probe.post('/api/auth/login/', json={'username': user['username'], 'password': user['password']})
    assert r.status_code == 403 and r.json()['error']['code'] == 'account_inactive', r.text
    row.get_by_test_id('admin-user-toggle-active').click()
    expect(row.get_by_test_id('admin-user-status')).to_have_attribute('data-state', 'active')

    # K1: group edits never create users
    assert admin.get_json('/api/admin/users/')['count'] == total_before + 1

    # groups modal: member counts, create and delete a group
    page.get_by_test_id('admin-users-manage-groups').click()
    modal = page.get_by_test_id('group-modal')
    researchers = modal.locator('[data-testid="group-row"][data-group="researchers"]')
    expect(researchers.get_by_test_id('group-member-count')).to_have_text(
        str(len(admin.get_json('/api/admin/users/?group=researchers&page_size=200')['results'])))
    expect(modal.locator('[data-testid="group-row"][data-group="admin"]').get_by_test_id('group-delete')).to_be_disabled()
    group = uniq('grp')
    modal.get_by_test_id('group-create-name').fill(group)
    modal.get_by_test_id('group-create-submit').click()
    new_row = modal.locator(f'[data-testid="group-row"][data-group="{group}"]')
    expect(new_row.get_by_test_id('group-member-count')).to_have_text('0')
    expect_api_error(400, '/api/admin/groups*')
    modal.get_by_test_id('group-create-name').fill(group.upper())
    modal.get_by_test_id('group-create-submit').click()
    expect(modal.get_by_test_id('group-create-error')).to_contain_text('already exists')
    new_row.get_by_test_id('group-delete').click()
    modal.get_by_test_id('group-delete-confirm').click()
    expect(new_row).to_have_count(0)
    modal.get_by_test_id('group-modal-close').click()

    # delete the user
    row.get_by_test_id('admin-user-delete').click()
    page.get_by_test_id('admin-user-delete-confirm').click()
    expect(row).to_have_count(0)
    assert admin.get_json(f'/api/admin/users/?search={user["username"]}')['count'] == 0
