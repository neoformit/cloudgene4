"""S1: anonymous and logged-in visitors see the home page, navbar and footer configured in
CLOUDGENE_HOME (settings.yaml navbar + pages/*.html)."""
import pytest
from playwright.sync_api import expect

from e2e.constants import NAVBAR, PAGE_MARKERS
from e2e.pages import Navbar

PUBLIC_NAV = [i['title'] for i in NAVBAR if not i.get('admin_only')]
ALL_NAV = [i['title'] for i in NAVBAR]



def test_home_loads_cleanly_anonymous(page, base_url):
    page.goto('/')
    expect(page.get_by_test_id('navbar')).to_be_visible()
    expect(page.get_by_test_id('footer')).to_be_visible()
    Navbar(page).expect_logged_out()
    expect(page).to_have_url(base_url + '/')  # no redirect to /login for anonymous visitors


def test_home_loads_cleanly_logged_in(page, login):
    login(page, 'alice')
    page.goto('/')
    Navbar(page).expect_logged_in('alice')
    expect(page.get_by_test_id('footer')).to_be_visible()


def test_home_renders_home_template(page):
    page.goto('/')
    expect(page.get_by_test_id('home-content')).to_contain_text(PAGE_MARKERS['home'])


def test_footer_renders_footer_template(page):
    page.goto('/')
    expect(page.get_by_test_id('footer')).to_contain_text(PAGE_MARKERS['footer'])


def test_about_page_renders_pages_file(page):
    page.goto('/pages/about')
    expect(page.get_by_test_id('page-content')).to_contain_text(PAGE_MARKERS['about'])


def test_unknown_page_shows_not_found(page, expect_api_error):
    expect_api_error(404, '/api/pages/*')
    page.goto('/pages/no-such-page')
    expect(page.get_by_test_id('page-not-found')).to_be_visible()


@pytest.mark.parametrize('user, expected', [(None, PUBLIC_NAV), ('alice', PUBLIC_NAV), ('admin', ALL_NAV)],
                         ids=['anonymous', 'alice', 'admin'])
def test_navbar_items_from_yaml_in_order(page, login, user, expected):
    if user:
        login(page, user)
    page.goto('/')
    expect(page.get_by_test_id('nav-item')).to_have_count(len(expected))
    assert Navbar(page).item_titles() == expected
