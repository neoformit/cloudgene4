"""X2: deep links and hard refresh on every SPA route, logged out and logged in.

Every visit also runs under the automatic guards, so a route whose page fires a failing API
call or logs a console error fails here even if the routing itself is right.
"""
import re
from urllib.parse import quote

import pytest
from playwright.sync_api import expect

from e2e.pages import Navbar

PUBLIC_ROUTES = ['/', '/login', '/register', '/reset-password', '/pages/about']
USER_ROUTES = ['/jobs', '/profile', '/run/hello']
ADMIN_ROUTES = [
    '/admin', '/admin/jobs', '/admin/users', '/admin/workflows', '/admin/workflows/hello',
    '/admin/settings/general', '/admin/settings/nextflow', '/admin/settings/mail',
    '/admin/settings/pages', '/admin/settings/logs',
]


def _path_re(path):
    return re.compile(re.escape(path) + r'/?$')


def _login_redirect_re(path):
    return re.compile(r'/login\?next=(%s|%s)$' % (re.escape(path), re.escape(quote(path, safe=''))))


@pytest.mark.parametrize('route', PUBLIC_ROUTES)
def test_public_route_logged_out(page, route):
    page.goto(route)
    expect(page).to_have_url(_path_re(route))
    Navbar(page).expect_logged_out()
    page.reload()
    expect(page).to_have_url(_path_re(route))


@pytest.mark.parametrize('route', USER_ROUTES + ADMIN_ROUTES)
def test_protected_route_logged_out_redirects_to_login_with_next(page, route):
    page.goto(route)
    expect(page).to_have_url(_login_redirect_re(route))


@pytest.mark.parametrize('route', PUBLIC_ROUTES[:1] + PUBLIC_ROUTES[4:] + USER_ROUTES)
def test_user_route_deep_link_and_refresh(page, login, route):
    login(page, 'alice')
    page.goto(route)
    expect(page).to_have_url(_path_re(route))
    Navbar(page).expect_logged_in('alice')
    page.reload()
    expect(page).to_have_url(_path_re(route))
    Navbar(page).expect_logged_in('alice')


@pytest.mark.parametrize('route', ADMIN_ROUTES)
def test_admin_route_forbidden_for_regular_user(page, login, base_url, route):
    login(page, 'alice')
    page.goto(route)
    expect(page).not_to_have_url(re.compile(r'/admin'))
    expect(page).not_to_have_url(re.compile(r'/login'))


@pytest.mark.parametrize('route', ADMIN_ROUTES)
def test_admin_route_deep_link_and_refresh(page, login, route, expect_api_error):
    if route == '/admin/jobs':
        # TODO(T03): remove once GET /api/admin/jobs exists (SPEC §3.6).
        expect_api_error(404, '/api/admin/jobs*')
    login(page, 'admin')
    page.goto(route)
    expect(page).to_have_url(_path_re(route))
    page.reload()
    expect(page).to_have_url(_path_re(route))


def test_unknown_route_redirects_home(page, base_url):
    page.goto('/no/such/route')
    expect(page).to_have_url(base_url + '/')
