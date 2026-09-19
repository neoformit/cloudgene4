"""A1 (login part): log in and out through the UI."""
import re

from playwright.sync_api import expect

from e2e.constants import USERS
from e2e.pages import LoginPage, Navbar


def test_login_and_logout_via_ui(page, login, base_url):
    login(page, 'alice', fresh=True)  # real UI login, not the cached storage state
    expect(page).to_have_url(base_url + '/')
    nav = Navbar(page)
    nav.expect_logged_in('alice')

    page.reload()
    nav.expect_logged_in('alice')

    nav.logout()
    nav.expect_logged_out()
    page.reload()
    nav.expect_logged_out()

    # The session is really gone: a protected route sends us to the login page.
    page.goto('/jobs')
    expect(page).to_have_url(re.compile(r'/login\?next=(/|%2F)jobs$'))


def test_login_wrong_password_shows_error(page, expect_api_error):
    expect_api_error((400, 401, 403), '/api/auth/login*')
    login_page = LoginPage(page).open()
    login_page.login('alice', 'not-the-password')
    expect(login_page.error).to_be_visible()
    expect(page).to_have_url(re.compile(r'/login'))
    Navbar(page).expect_logged_out()


def test_login_follows_next_parameter(page):
    LoginPage(page).open(next_path='/profile').login('bob', USERS['bob']['password'])
    expect(page).to_have_url(re.compile(r'/profile$'))
    Navbar(page).expect_logged_in('bob')


def test_admin_sees_admin_link_regular_user_does_not(page, login, user_page):
    login(page, 'admin')
    page.goto('/')
    Navbar(page).user_menu.click()
    expect(page.get_by_test_id('nav-admin')).to_be_visible()

    alice = user_page('alice')
    alice.goto('/')
    Navbar(alice).user_menu.click()
    expect(alice.get_by_test_id('nav-logout')).to_be_visible()
    expect(alice.get_by_test_id('nav-admin')).to_have_count(0)
