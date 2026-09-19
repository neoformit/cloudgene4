"""D5: Settings General/Mail/Nextflow round-trips (UI → settings.yaml → reload shows it); mail
password never echoed; "send test mail" lands in the outbox.
D6: Pages — edit home & footer, create a page visible at /pages/<slug>, traversal slugs rejected,
delete; navbar editor.
"""
import copy

import pytest
import requests
from playwright.sync_api import expect

from e2e.helpers import latest_email

pytestmark = pytest.mark.serial


@pytest.fixture
def restore_home(stack):
    """Restore settings.yaml, the global Nextflow files and the pages after the test."""
    settings = copy.deepcopy(stack.read_settings())
    cfg = stack.home / 'config'
    files = {p: p.read_text() for p in (cfg / 'nextflow.config', cfg / 'nextflow.env')}
    pages = {p.name: p.read_text() for p in (stack.home / 'pages').glob('*.html')}
    yield
    stack.write_settings(settings)
    for p, text in files.items():
        p.write_text(text)
    for p in (stack.home / 'pages').glob('*.html'):
        if p.name not in pages:
            p.unlink()
    for name, text in pages.items():
        (stack.home / 'pages' / name).write_text(text)


def test_d5_general_settings_round_trip(page, login, restore_home, stack):
    login(page, 'admin')
    page.goto('/admin/settings/general')
    page.get_by_test_id('settings-name').fill('E2E Renamed Service')
    page.get_by_test_id('settings-max-queue').fill('7')
    page.get_by_test_id('settings-retention').fill('3')
    page.get_by_test_id('settings-save').click()
    expect(page.get_by_test_id('settings-success')).to_be_visible()

    server = stack.read_settings()['server']
    assert (server['name'], server['max_queue_size'], server['job_retention_days']) == \
        ('E2E Renamed Service', 7, 3)
    expect(page.get_by_test_id('nav-brand')).to_have_text('E2E Renamed Service')
    page.reload()
    expect(page.get_by_test_id('settings-max-queue')).to_have_value('7')


def test_d5_general_settings_validation_error(page, login, restore_home, stack, expect_api_error):
    login(page, 'admin')
    page.goto('/admin/settings/general')
    expect_api_error(400, '/api/admin/settings/general/')
    page.get_by_test_id('settings-url').fill('not-a-url')
    page.get_by_test_id('settings-save').click()
    expect(page.locator('#s-url.is-invalid')).to_be_visible()
    assert stack.read_settings()['server']['url'] != 'not-a-url'


def test_d5_mail_test_lands_in_outbox(page, login, restore_home, stack):
    login(page, 'admin')
    page.goto('/admin/settings/mail')
    expect(page.get_by_test_id('mail-backend')).to_have_value('file')
    page.get_by_test_id('mail-test-send').click()
    expect(page.get_by_test_id('mail-success')).to_contain_text('admin@e2e.test')
    msg = latest_email(stack.outbox_dir, to='admin@e2e.test')
    assert 'Test e-mail' in msg['Subject']


def test_d5_mail_password_write_only(page, login, restore_home, stack, api):
    login(page, 'admin')
    page.goto('/admin/settings/mail')
    page.get_by_test_id('mail-backend').select_option('smtp')
    page.get_by_test_id('mail-host').fill('smtp.e2e.test')
    page.get_by_test_id('mail-port').fill('2525')
    page.get_by_test_id('mail-user').fill('mailer')
    page.get_by_test_id('mail-password').fill('E2E-s3cret-pw')
    page.get_by_test_id('mail-save').click()
    expect(page.get_by_test_id('mail-success')).to_be_visible()

    mail = stack.read_settings()['mail']
    assert (mail['backend'], mail['host'], mail['port'], mail['password']) == \
        ('smtp', 'smtp.e2e.test', 2525, 'E2E-s3cret-pw')
    page.reload()
    expect(page.get_by_test_id('mail-host')).to_have_value('smtp.e2e.test')
    expect(page.get_by_test_id('mail-password')).to_have_value('')
    expect(page.get_by_test_id('mail-password')).to_have_attribute('placeholder', '•••••• (unchanged)')
    body = api('admin').get('/api/admin/settings/mail/').text
    assert 'E2E-s3cret-pw' not in body

    # saving again without typing a password keeps it
    page.get_by_test_id('mail-host').fill('smtp2.e2e.test')
    page.get_by_test_id('mail-save').click()
    expect(page.get_by_test_id('mail-success')).to_be_visible()
    assert stack.read_settings()['mail']['password'] == 'E2E-s3cret-pw'


def test_d5_nextflow_settings_round_trip(page, login, restore_home, stack):
    login(page, 'admin')
    page.goto('/admin/settings/nextflow')
    page.get_by_test_id('nextflow-profile').fill('e2e_profile')
    page.get_by_test_id('nextflow-config').fill('// E2E-D5 global\nprocess.executor = "local"\n')
    page.get_by_test_id('nextflow-env').fill('E2E_GLOBAL=1\n')
    page.get_by_test_id('nextflow-save').click()
    expect(page.get_by_test_id('nextflow-success')).to_be_visible()

    assert stack.read_settings()['nextflow']['profile'] == 'e2e_profile'
    assert 'E2E-D5 global' in (stack.home / 'config' / 'nextflow.config').read_text()
    assert (stack.home / 'config' / 'nextflow.env').read_text() == 'E2E_GLOBAL=1\n'
    page.reload()
    expect(page.get_by_test_id('nextflow-profile')).to_have_value('e2e_profile')


def test_d6_edit_home_and_footer(page, login, user_page, restore_home):
    login(page, 'admin')
    page.goto('/admin/settings/pages')
    page.locator('[data-testid="page-item"][data-slug="home"]').click()
    page.get_by_test_id('page-html').fill('<h1 data-e2e="x">E2E-D6-HOME edited</h1>')
    page.get_by_test_id('page-tab-preview').click()
    expect(page.get_by_test_id('page-preview')).to_contain_text('E2E-D6-HOME edited')
    page.get_by_test_id('page-save').click()
    expect(page.get_by_test_id('pages-success')).to_be_visible()
    expect(page.get_by_test_id('page-delete')).to_have_count(0)  # home can't be deleted

    page.locator('[data-testid="page-item"][data-slug="footer"]').click()
    page.get_by_test_id('page-html').fill('<span>E2E-D6-FOOTER edited</span>')
    page.get_by_test_id('page-save').click()
    expect(page.get_by_test_id('pages-success')).to_be_visible()

    anon = user_page()
    anon.goto('/')
    expect(anon.get_by_test_id('home-content')).to_contain_text('E2E-D6-HOME edited')
    expect(anon.get_by_test_id('footer')).to_contain_text('E2E-D6-FOOTER edited')


def test_d6_create_view_delete_page(page, login, user_page, restore_home, stack, expect_api_error):
    login(page, 'admin')
    page.goto('/admin/settings/pages')
    page.get_by_test_id('page-new-slug').fill('e2e-help')
    page.get_by_test_id('page-new').click()
    page.get_by_test_id('page-html').fill('<h2>E2E-D6-NEW page</h2>')
    page.get_by_test_id('page-save').click()
    expect(page.locator('[data-testid="page-item"][data-slug="e2e-help"]')).to_be_visible()
    assert (stack.home / 'pages' / 'e2e-help.html').read_text() == '<h2>E2E-D6-NEW page</h2>'

    anon = user_page()
    anon.goto('/pages/e2e-help')
    expect(anon.get_by_test_id('page-content')).to_contain_text('E2E-D6-NEW page')

    page.get_by_test_id('page-delete').click()
    page.get_by_test_id('confirm-ok').click()
    expect(page.locator('[data-testid="page-item"][data-slug="e2e-help"]')).to_have_count(0)
    assert not (stack.home / 'pages' / 'e2e-help.html').exists()

    expect_api_error(404, '/api/pages/*')
    anon.goto('/pages/e2e-help')
    expect(anon.get_by_test_id('page-not-found')).to_be_visible()


def test_d6_traversal_slugs_rejected(page, login, stack, api):
    login(page, 'admin')
    page.goto('/admin/settings/pages')
    page.get_by_test_id('page-new-slug').fill('../config/settings')
    page.get_by_test_id('page-new').click()
    expect(page.locator('[data-testid="page-new-form"] .invalid-feedback')).to_be_visible()
    expect(page.get_by_test_id('page-editor')).to_have_count(0)

    admin = api('admin')
    for path in ('/api/pages/..%2Fconfig%2Fsettings/', '/api/pages/..%2F..%2Fetc%2Fpasswd/',
                 '/api/pages/%2e%2e/', '/api/pages/Home/'):
        r = requests.get(stack.base_url + path, timeout=10)
        assert r.status_code == 404, (path, r.status_code)
        assert 'server' not in r.text or 'error' in r.text
    r = admin.put('/api/admin/pages/..%2Fescape/', json={'html': 'x'})
    assert r.status_code in (400, 404)
    assert not (stack.home / 'escape.html').exists()


def test_d6_navbar_editor(page, login, user_page, restore_home, stack):
    login(page, 'admin')
    page.goto('/admin/settings/general')
    page.get_by_test_id('navbar-add').click()
    row = page.get_by_test_id('navbar-row').last
    row.get_by_test_id('navbar-title').fill('E2E Docs')
    row.get_by_test_id('navbar-url').fill('/pages/about')
    row.get_by_test_id('navbar-auth-only').check()
    page.get_by_test_id('navbar-save').click()
    expect(page.get_by_test_id('settings-success')).to_contain_text('Navigation saved')
    assert stack.read_settings()['navbar'][-1]['title'] == 'E2E Docs'

    alice = user_page('alice')
    alice.goto('/')
    expect(alice.get_by_test_id('nav-item').last).to_have_text('E2E Docs')
    anon = user_page()
    anon.goto('/')
    expect(anon.get_by_test_id('navbar')).to_be_visible()
    expect(anon.get_by_test_id('nav-item').filter(has_text='E2E Docs')).to_have_count(0)
