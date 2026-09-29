"""W1: workflow visibility per user (public / group / admin; disabled hidden).
D4: admin workflows — disable/enable, groups/public, per-app Nextflow settings, reload after a
YAML edit, install (valid + invalid path) and uninstall. settings.yaml is the source of truth.
"""
import copy
import shutil

import pytest
from playwright.sync_api import expect

from e2e.admin_helpers import wait_until
from e2e.constants import APPS

pytestmark = pytest.mark.serial

VISIBLE = {
    None: ['hello'],
    'bob': ['hello'],
    'alice': ['all-inputs', 'command-steps', 'hello'],
    'admin': sorted(APPS),
}


@pytest.fixture
def restore_apps(stack):
    """Put settings.yaml apps[] and the app files back after the test (and re-sync)."""
    original = copy.deepcopy(stack.read_settings())
    hello_yaml = (stack.home / 'apps' / 'hello' / 'cloudgene.yaml').read_text()
    yield
    stack.write_settings(original)
    (stack.home / 'apps' / 'hello' / 'cloudgene.yaml').write_text(hello_yaml)
    for extra in ('hello2', 'broken-app'):
        shutil.rmtree(stack.home / 'apps' / extra, ignore_errors=True)
    for name in ('nextflow.config', 'nextflow.env'):
        (stack.home / 'apps' / 'hello' / name).unlink(missing_ok=True)
    stack.manage('sync_workflows')


def card_ids(page):
    page.goto('/')
    expect(page.get_by_test_id('navbar')).to_be_visible()
    cards = page.get_by_test_id('workflow-card')
    page.wait_for_load_state('networkidle')
    return sorted(cards.evaluate_all('els => els.map(e => e.dataset.workflowId)'))


@pytest.mark.parametrize('user', [None, 'bob', 'alice', 'admin'], ids=['anonymous', 'bob', 'alice', 'admin'])
def test_w1_workflow_visibility_per_user(page, login, user):
    if user:
        login(page, user)
    assert card_ids(page) == VISIBLE[user]


def test_w1_d4_disable_hides_workflow_and_enable_restores(page, login, user_page, restore_apps, stack):
    login(page, 'admin')
    page.goto('/admin/workflows')
    row = page.locator('[data-testid="admin-workflow-row"][data-workflow-id="hello"]')
    expect(row).to_have_attribute('data-enabled', 'true')
    row.get_by_test_id('workflow-toggle').click()
    expect(row).to_have_attribute('data-enabled', 'false')
    expect(row.get_by_test_id('workflow-status')).to_have_text('disabled')
    assert stack.read_settings()['apps'][0]['enabled'] is False  # hello is apps[0]

    alice = user_page('alice')
    assert card_ids(alice) == ['all-inputs', 'command-steps']

    row.get_by_test_id('workflow-toggle').click()
    expect(row).to_have_attribute('data-enabled', 'true')
    assert card_ids(alice) == ['all-inputs', 'command-steps', 'hello']


def test_d4_groups_and_public_via_settings_page(page, login, user_page, restore_apps, stack):
    login(page, 'admin')
    page.goto('/admin/workflows/slow')
    expect(page.get_by_test_id('workflow-admin-title')).to_have_text('Slow')
    page.get_by_test_id('workflow-group-researchers').check()
    page.get_by_test_id('workflow-access-save').click()
    expect(page.get_by_test_id('workflow-settings-success')).to_be_visible()
    slow = next(a for a in stack.read_settings()['apps'] if a['path'] == 'slow')
    assert sorted(slow['groups']) == ['admin', 'researchers']

    alice = user_page('alice')
    assert 'slow' in card_ids(alice)
    bob = user_page('bob')
    assert 'slow' not in card_ids(bob)

    page.get_by_test_id('workflow-public').check()
    page.get_by_test_id('workflow-access-save').click()
    expect(page.get_by_test_id('workflow-settings-success')).to_be_visible()
    assert 'slow' in card_ids(bob)


def test_d4_per_app_nextflow_settings_persist(page, login, restore_apps, stack):
    login(page, 'admin')
    page.goto('/admin/workflows/hello')
    page.get_by_test_id('workflow-nf-profile').fill('e2eprofile')
    page.get_by_test_id('workflow-nf-config').fill('params.e2e_marker = "D4"\n')
    page.get_by_test_id('workflow-nf-env').fill('E2E_D4=yes\n')
    page.get_by_test_id('workflow-nf-save').click()
    expect(page.get_by_test_id('workflow-settings-success')).to_be_visible()

    hello = next(a for a in stack.read_settings()['apps'] if a['path'] == 'hello')
    assert hello['profile'] == 'e2eprofile'
    assert (stack.home / 'apps' / 'hello' / 'nextflow.config').read_text() == 'params.e2e_marker = "D4"\n'
    assert (stack.home / 'apps' / 'hello' / 'nextflow.env').read_text() == 'E2E_D4=yes\n'

    page.reload()
    expect(page.get_by_test_id('workflow-nf-profile')).to_have_value('e2eprofile')
    expect(page.get_by_test_id('workflow-nf-env')).to_have_value('E2E_D4=yes\n')


def test_d4_reload_after_yaml_edit(page, login, restore_apps, stack):
    yaml_file = stack.home / 'apps' / 'hello' / 'cloudgene.yaml'
    text = yaml_file.read_text()
    assert '  outputs:' in text
    yaml_file.write_text(text.replace(
        '  outputs:', '    - id: e2e_new_input\n      description: New input\n      type: text\n'
                      '      required: false\n  outputs:', 1))
    login(page, 'admin')
    page.goto('/admin/workflows/hello')
    page.get_by_test_id('workflow-reload').click()
    expect(page.get_by_test_id('workflow-yaml')).to_contain_text('e2e_new_input')
    # the cache row the run form / worker use has the new definition
    out = stack.django_shell("from workflows.models import Workflow; "
                             "print('e2e_new_input' in Workflow.objects.get(pk='hello').yaml_config)")
    assert out.strip().endswith('True')


def test_d4_install_invalid_then_valid_and_uninstall(page, login, restore_apps, stack, expect_api_error):
    broken = stack.home / 'apps' / 'broken-app'
    shutil.copytree(stack.home / 'apps' / 'hello', broken)
    (broken / 'cloudgene.yaml').write_text(
        (broken / 'cloudgene.yaml').read_text().replace('id: hello', 'id: broken-app')
        .replace('type: text', 'type: no-such-type'))
    good = stack.home / 'apps' / 'hello2'
    shutil.copytree(stack.home / 'apps' / 'hello', good)
    (good / 'cloudgene.yaml').write_text(
        (good / 'cloudgene.yaml').read_text().replace('id: hello', 'id: hello2')
        .replace('name: Hello', 'name: Hello Two'))

    login(page, 'admin')
    page.goto('/admin/workflows')
    page.get_by_test_id('workflow-install-open').click()

    expect_api_error(400, '/api/admin/workflows/install/')
    page.get_by_test_id('workflow-install-path').fill(str(broken))
    page.get_by_test_id('workflow-install-submit').click()
    expect(page.get_by_test_id('workflow-install-errors')).to_contain_text('no-such-type')

    page.get_by_test_id('workflow-install-path').fill('hello2')
    page.get_by_test_id('workflow-install-groups').fill('researchers')
    page.get_by_test_id('workflow-install-submit').click()
    expect(page.get_by_test_id('workflows-success')).to_contain_text('Hello Two')
    row = page.locator('[data-testid="admin-workflow-row"][data-workflow-id="hello2"]')
    expect(row.get_by_test_id('workflow-access')).to_contain_text('researchers')
    entry = next(a for a in stack.read_settings()['apps'] if a['path'] == 'hello2')
    assert entry['groups'] == ['researchers']

    row.get_by_test_id('workflow-uninstall').click()
    page.get_by_test_id('confirm-ok').click()
    expect(row).to_have_count(0)
    assert all(a['path'] != 'hello2' for a in stack.read_settings()['apps'])


def test_d4_invalid_entry_listed_with_errors(page, login, restore_apps, stack):
    broken = stack.home / 'apps' / 'broken-app'
    broken.mkdir()
    (broken / 'cloudgene.yaml').write_text('id: broken-app\nname: Broken\nworkflow:\n  steps: []\n')
    data = stack.read_settings()
    data['apps'].append({'path': 'broken-app'})
    stack.write_settings(data)  # hand edit; the next API request re-syncs

    login(page, 'admin')
    page.goto('/admin/workflows')
    row = page.locator('[data-testid="admin-workflow-row"][data-workflow-id="broken-app"]')
    expect(row).to_have_attribute('data-valid', 'false')
    expect(row.get_by_test_id('workflow-errors')).to_contain_text('steps')
