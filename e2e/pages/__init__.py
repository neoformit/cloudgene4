"""Page objects. Locate elements by `data-testid` only (see e2e/README.md for the list)."""
import re

from playwright.sync_api import Page, expect


class Navbar:
    def __init__(self, page: Page):
        self.page = page
        self.root = page.get_by_test_id('navbar')
        self.user_menu = page.get_by_test_id('nav-user-menu')
        self.login_link = page.get_by_test_id('nav-login')
        self.admin_link = page.get_by_test_id('nav-admin')

    def item_titles(self):
        """Titles of the configurable (YAML) navbar items, in display order."""
        return [t.strip() for t in self.page.get_by_test_id('nav-item').all_inner_texts()]

    def expect_logged_in(self, username):
        expect(self.user_menu).to_contain_text(username)
        expect(self.login_link).to_have_count(0)

    def expect_logged_out(self):
        expect(self.login_link).to_be_visible()
        expect(self.user_menu).to_have_count(0)

    def logout(self):
        self.user_menu.click()
        self.page.get_by_test_id('nav-logout').click()


class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.username = page.get_by_test_id('login-username')
        self.password = page.get_by_test_id('login-password')
        self.submit = page.get_by_test_id('login-submit')
        self.error = page.get_by_test_id('login-error')

    def open(self, next_path=None):
        self.page.goto('/login' + ('?next=' + next_path if next_path else ''))
        expect(self.username).to_be_visible()
        return self

    def login(self, username, password):
        self.username.fill(username)
        self.password.fill(password)
        self.submit.click()


class RunPage:
    def __init__(self, page: Page):
        self.page = page
        self.form = page.get_by_test_id('run-form')
        self.job_name = page.get_by_test_id('job-name')
        self.submit_button = page.get_by_test_id('job-submit')
        self.error = page.get_by_test_id('run-error')

    def open(self, workflow_id):
        self.page.goto('/run/%s' % workflow_id)
        expect(self.form).to_be_visible()
        return self

    def field(self, input_id):
        """The native control inside the `input-<id>` wrapper."""
        return self.page.get_by_test_id('input-%s' % input_id).locator('input, textarea, select').first

    def fill(self, input_id, value):
        self.field(input_id).fill(str(value))

    def set_files(self, input_id, paths):
        """Choose file(s) for a file/folder input."""
        self.page.get_by_test_id('input-%s' % input_id).locator('input[type=file]').set_input_files(
            [str(p) for p in paths])

    def set_checked(self, input_id, checked=True):
        self.page.get_by_test_id('input-%s' % input_id).locator('input[type=checkbox]').set_checked(checked)

    def field_error(self, input_id):
        return self.page.get_by_test_id('error-%s' % input_id)

    def submit(self):
        """Submit and wait for the job page; returns the job id from the URL."""
        self.submit_button.click()
        self.page.wait_for_url(re.compile(r'/jobs/[^/?#]+$'))
        return self.page.url.rstrip('/').rsplit('/', 1)[-1]


class JobPage:
    def __init__(self, page: Page):
        self.page = page
        self.state = page.get_by_test_id('job-state')
        self.title = page.get_by_test_id('job-title')
        self.cancel_button = page.get_by_test_id('job-cancel')
        self.queue_position = page.get_by_test_id('job-queue-position')
        self.output_links = page.get_by_test_id('job-output-link')

    def open(self, job_id):
        self.page.goto('/jobs/%s' % job_id)
        expect(self.title).to_be_visible()
        return self

    def expect_state(self, *states, timeout=60_000):
        """Web-first wait for the state badge (`data-state`) — relies on the page's own polling."""
        pattern = re.compile('^(%s)$' % '|'.join(map(re.escape, states)))
        expect(self.state).to_have_attribute('data-state', pattern, timeout=timeout)

    def open_results(self):
        self.page.get_by_test_id('job-tab-results').click()

    def open_logs(self):
        self.page.get_by_test_id('job-tab-logs').click()
        return self.page.get_by_test_id('job-log')

    def messages(self, level=None):
        sel = '[data-testid="job-message"]' + ('[data-level="%s"]' % level if level else '')
        return self.page.locator(sel)

    def process(self, name):
        return self.page.locator('[data-testid="job-process"][data-process="%s"]' % name)

    def cancel(self):
        self.cancel_button.click()
        self.page.get_by_test_id('confirm-ok').click()

    def delete(self):
        self.page.get_by_test_id('job-delete').click()
        self.page.get_by_test_id('confirm-ok').click()
