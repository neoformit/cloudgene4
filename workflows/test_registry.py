"""Workflow registry (workflows/registry.py) against the fixture apps in test_fixtures/apps."""
import io
import shutil
import tempfile
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from core import config
from workflows import registry
from workflows.models import Workflow

FIXTURES = Path(__file__).resolve().parent / 'test_fixtures' / 'apps'
User = get_user_model()


class TempHomeMixin:
    """Each test gets an empty CLOUDGENE_HOME with the fixture apps copied into apps/."""

    copy_fixture_apps = True

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp(prefix='cg-registry-'))
        self.home = self._tmp / 'home'
        for sub in ('config', 'pages', 'apps', 'jobs'):
            (self.home / sub).mkdir(parents=True)
        if self.copy_fixture_apps:
            for app in FIXTURES.iterdir():
                shutil.copytree(app, self.home / 'apps' / app.name)
        (self.home / 'pages' / 'home.html').write_text('<h1>Home</h1>')
        (self.home / 'pages' / 'footer.html').write_text('<p>Footer</p>')
        self._override = override_settings(CLOUDGENE_HOME=self.home)
        self._override.enable()
        config.clear_cache()
        config.save_settings({})
        registry._last_signature = None

    def tearDown(self):
        self._override.disable()
        config.clear_cache()
        registry._last_signature = None
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def settings_on_disk(self):
        return yaml.safe_load(config.settings_path().read_text())

    def write_apps(self, apps):
        config.update_settings(lambda doc: {**doc, 'apps': apps})


class RegistryInstallTest(TempHomeMixin, TestCase):
    def test_install_app_dir_writes_settings_and_cache_row(self):
        wf = registry.install(str(self.home / 'apps' / 'hello'), public=True, groups=['lab'])
        self.assertEqual(wf.id, 'hello')
        self.assertEqual(wf.name, 'Hello')
        self.assertEqual(wf.version, '1.0.0')
        self.assertTrue(wf.enabled)
        self.assertTrue(wf.public)
        self.assertEqual(list(wf.allowed_groups.values_list('name', flat=True)), ['lab'])
        self.assertEqual(wf.category.name, 'testing')
        self.assertIn('Say hello', wf.yaml_config)
        # stored relative to apps/ in settings.yaml (source of truth)
        apps = self.settings_on_disk()['apps']
        self.assertEqual(apps, [{'path': 'hello', 'enabled': True, 'public': True,
                                 'groups': ['lab'], 'profile': '', 'work_dir': ''}])

    def test_install_yaml_file_outside_apps_is_referenced_absolute(self):
        outside = self._tmp / 'elsewhere' / 'other'
        shutil.copytree(FIXTURES / 'other', outside)
        wf = registry.install(str(outside / 'cloudgene.yaml'))
        self.assertEqual(wf.id, 'other')
        self.assertEqual(self.settings_on_disk()['apps'][0]['path'], str(outside.resolve()))
        self.assertEqual(wf.app_location, str(outside.resolve()))

    def test_install_with_copy(self):
        outside = self._tmp / 'src'
        shutil.copytree(FIXTURES / 'hello', outside)
        shutil.rmtree(self.home / 'apps' / 'hello')
        registry.install(str(outside), copy=True)
        self.assertTrue((self.home / 'apps' / 'hello' / 'cloudgene.yaml').is_file())
        self.assertEqual(self.settings_on_disk()['apps'][0]['path'], 'hello')

    def test_install_invalid_app_rejected_with_errors(self):
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.install(str(self.home / 'apps' / 'invalid'))
        self.assertTrue(any('no-such-type' in e for e in ctx.exception.errors))
        self.assertEqual(self.settings_on_disk().get('apps') or [], [])
        self.assertFalse(Workflow.objects.filter(pk='invalid').exists())

    def test_install_missing_path(self):
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.install('/no/such/dir')
        self.assertEqual(ctx.exception.code, 'not_found')

    def test_install_duplicate_id_conflict(self):
        registry.install('hello')
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.install('hello')
        self.assertEqual(ctx.exception.status, 409)

    def test_uninstall_removes_entry_and_row(self):
        registry.install('hello')
        registry.uninstall('hello')
        self.assertEqual(self.settings_on_disk()['apps'], [])
        self.assertFalse(Workflow.objects.filter(pk='hello').exists())
        self.assertTrue((self.home / 'apps' / 'hello' / 'cloudgene.yaml').exists())  # files kept

    def test_uninstall_unknown(self):
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.uninstall('nope')
        self.assertEqual(ctx.exception.status, 404)


class RegistrySyncTest(TempHomeMixin, TestCase):
    def test_sync_from_hand_written_settings(self):
        self.write_apps([
            {'path': 'hello', 'public': True},
            {'path': 'apps/other/cloudgene.yaml', 'enabled': False, 'groups': ['x']},  # home-relative
            {'path': 'invalid'},
            {'path': 'broken-yaml'},
            {'path': 'missing-dir'},
        ])
        statuses = {s.id: s for s in registry.sync_all()}
        self.assertEqual(set(statuses), {'hello', 'other', 'invalid', 'broken-yaml', 'missing-dir'})
        self.assertTrue(statuses['hello'].valid)
        self.assertFalse(statuses['invalid'].valid)
        self.assertFalse(statuses['broken-yaml'].valid)
        self.assertIn('Invalid YAML', statuses['broken-yaml'].errors[0])
        self.assertFalse(statuses['missing-dir'].valid)
        self.assertEqual(Workflow.objects.get(pk='hello').status, 'enabled')
        self.assertEqual(Workflow.objects.get(pk='other').status, 'disabled')
        # unknown group names are ignored (not created) and reported as warnings
        self.assertFalse(Group.objects.filter(name='x').exists())
        self.assertIn('Group "x" does not exist (ignored).', statuses['other'].warnings)
        # invalid apps never get a cache row (not runnable)
        self.assertFalse(Workflow.objects.filter(pk='invalid').exists())

    def test_duplicate_ids_in_settings(self):
        self.write_apps([{'path': 'hello'}, {'path': 'apps/hello'}])
        statuses = registry.sync_all()
        self.assertTrue(statuses[0].valid)
        self.assertFalse(statuses[1].valid)
        self.assertIn('Duplicate', statuses[1].errors[0])

    def test_app_becoming_invalid_disables_row(self):
        registry.install('hello')
        yaml_file = self.home / 'apps' / 'hello' / 'cloudgene.yaml'
        yaml_file.write_text(yaml_file.read_text().replace('type: text', 'type: bogus'))
        st = registry.reload('hello')
        self.assertFalse(st.valid)
        row = Workflow.objects.get(pk='hello')
        self.assertEqual(row.status, 'disabled')
        self.assertTrue(row.errors)

    def test_reload_picks_up_new_input(self):
        registry.install('hello')
        yaml_file = self.home / 'apps' / 'hello' / 'cloudgene.yaml'
        yaml_file.write_text(yaml_file.read_text().replace(
            '  outputs:', '    - id: extra\n      description: Extra\n      type: text\n  outputs:'))
        registry.reload('hello')
        ids = [i['id'] for i in Workflow.objects.get(pk='hello').get_inputs()]
        self.assertEqual(ids, ['message', 'extra'])

    def test_sync_if_changed_detects_settings_edit(self):
        registry.sync_all()
        self.assertFalse(registry.sync_if_changed())
        self.write_apps([{'path': 'hello'}])  # e.g. edited by hand
        self.assertTrue(registry.sync_if_changed())
        self.assertTrue(Workflow.objects.filter(pk='hello').exists())
        self.assertFalse(registry.sync_if_changed())

    def test_manual_rows_untouched_by_sync(self):
        Workflow.objects.create(id='manual', name='Manual', yaml_config='id: manual')
        registry.sync_all()
        self.assertTrue(Workflow.objects.filter(pk='manual', status='enabled').exists())

    def test_removed_entry_with_jobs_is_kept_disabled(self):
        from jobs.models import Job
        registry.install('hello')
        user = User.objects.create_user(username='u1', email='u1@x.org', password='Secret123')
        Job.objects.create(workflow=Workflow.objects.get(pk='hello'), user=user)
        self.write_apps([])
        registry.sync_all()
        row = Workflow.objects.get(pk='hello')
        self.assertFalse(row.installed)
        self.assertEqual(row.status, 'disabled')

    def test_middleware_syncs_lazily_on_api_request(self):
        self.write_apps([{'path': 'hello', 'public': True}])
        self.assertFalse(Workflow.objects.filter(pk='hello').exists())
        self.client.get('/api/health/')
        self.assertTrue(Workflow.objects.filter(pk='hello').exists())


class RegistryAccessTest(TempHomeMixin, TestCase):
    def setUp(self):
        super().setUp()
        registry.install('hello')
        self.alice = User.objects.create_user(username='alice', email='a@x.org',
                                              password='Secret123')
        self.lab = Group.objects.create(name='lab')

    def test_groups_written_to_yaml_and_access_follows(self):
        wf = Workflow.objects.get(pk='hello')
        self.assertFalse(wf.can_access(self.alice))
        registry.update_access('hello', groups=['lab'])
        self.assertEqual(self.settings_on_disk()['apps'][0]['groups'], ['lab'])
        self.alice.groups.add(self.lab)
        self.assertTrue(Workflow.objects.get(pk='hello').can_access(self.alice))

    def test_deleted_group_is_pruned_from_settings(self):
        registry.update_access('hello', groups=['lab', 'other'])
        self.assertEqual(self.settings_on_disk()['apps'][0]['groups'], ['lab', 'other'])
        Group.objects.get(name='lab').delete()
        self.assertEqual(self.settings_on_disk()['apps'][0]['groups'], ['other'])
        wf = Workflow.objects.get(pk='hello')
        self.assertEqual(list(wf.allowed_groups.values_list('name', flat=True)), ['other'])
        # a sync never re-creates it
        registry.sync_all()
        self.assertFalse(Group.objects.filter(name='lab').exists())

    def test_enable_disable_public(self):
        registry.update_access('hello', enabled=False, public=True)
        entry = self.settings_on_disk()['apps'][0]
        self.assertEqual((entry['enabled'], entry['public']), (False, True))
        wf = Workflow.objects.get(pk='hello')
        self.assertEqual(wf.status, 'disabled')
        self.assertTrue(wf.public)

    def test_nextflow_settings_round_trip(self):
        registry.set_nextflow_settings('hello', profile='docker', work_dir='/scratch/w',
                                       config_text='process.cpus = 2\n', env_text='A=1\n')
        entry = self.settings_on_disk()['apps'][0]
        self.assertEqual((entry['profile'], entry['work_dir']), ('docker', '/scratch/w'))
        self.assertEqual((self.home / 'apps' / 'hello' / 'nextflow.config').read_text(),
                         'process.cpus = 2\n')
        self.assertEqual((self.home / 'apps' / 'hello' / 'nextflow.env').read_text(), 'A=1\n')
        wf = Workflow.objects.get(pk='hello')  # compatibility properties
        self.assertEqual(wf.nextflow_profile, 'docker')
        self.assertEqual(wf.working_directory, '/scratch/w')
        self.assertEqual(wf.nextflow_config, 'process.cpus = 2\n')
        self.assertEqual(wf.env_vars, 'A=1\n')


class CommandsTest(TempHomeMixin, TestCase):
    def test_install_workflow_command(self):
        out = io.StringIO()
        call_command('install_workflow', str(self.home / 'apps' / 'hello'), '--public',
                     '--groups', 'a,b', stdout=out)
        self.assertIn('Installed hello', out.getvalue())
        wf = Workflow.objects.get(pk='hello')
        self.assertTrue(wf.public)
        self.assertEqual(sorted(wf.allowed_groups.values_list('name', flat=True)), ['a', 'b'])

    def test_install_workflow_command_invalid(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('install_workflow', str(self.home / 'apps' / 'invalid'),
                         stdout=io.StringIO())
        self.assertIn('no-such-type', str(ctx.exception))

    def test_sync_workflows_command(self):
        self.write_apps([{'path': 'hello'}, {'path': 'invalid'}])
        out = io.StringIO()
        call_command('sync_workflows', stdout=out)
        self.assertIn('hello: enabled', out.getvalue())
        self.assertIn('invalid: INVALID', out.getvalue())
