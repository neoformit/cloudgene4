import multiprocessing
import os
import shutil
import tempfile
import time
from pathlib import Path

import yaml
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from core import config

REPO_HOME = Path(settings.BASE_DIR) / 'home'


class TempHomeMixin:
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / 'home'
        self._override = override_settings(CLOUDGENE_HOME=self.home)
        self._override.enable()
        config.clear_cache()

    def tearDown(self):
        self._override.disable()
        config.clear_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def write_yaml(self, data):
        config.settings_path().parent.mkdir(parents=True, exist_ok=True)
        config.settings_path().write_text(yaml.safe_dump(data))


class CommittedHomeTest(SimpleTestCase):
    def test_committed_settings_yaml_is_valid_and_complete(self):
        data = yaml.safe_load((REPO_HOME / 'config' / 'settings.yaml').read_text())
        cleaned = config.validate_settings(data)
        # every schema key is spelled out in the committed file (self-documenting)
        for section, spec in config.SCHEMA.items():
            self.assertIn(section, data)
            if isinstance(spec, dict):
                self.assertEqual(set(spec), set(data[section]) & set(spec),
                                 f'missing keys in {section}')
        self.assertEqual(cleaned['server']['max_running_jobs'], 2)

    def test_committed_layout(self):
        for rel in ('config/nextflow.config', 'config/nextflow.env', 'pages/home.html',
                    'pages/footer.html', 'pages/about.html', 'apps/.gitkeep'):
            self.assertTrue((REPO_HOME / rel).exists(), rel)


class ConfigLoadTest(TempHomeMixin, SimpleTestCase):
    def test_missing_file_yields_defaults(self):
        self.assertEqual(config.load_settings(), config.default_settings())
        self.assertEqual(config.get('server.max_queue_size'), 50)
        self.assertFalse(config.get('queue.paused'))
        self.assertEqual(config.get('nope.nothing', 'x'), 'x')

    def test_partial_file_filled_with_defaults_and_unknown_keys_kept(self):
        self.write_yaml({'server': {'name': 'X', 'extra': 1}, 'custom': {'a': 1}})
        s = config.load_settings()
        self.assertEqual(s['server']['name'], 'X')
        self.assertEqual(s['server']['extra'], 1)
        self.assertEqual(s['custom'], {'a': 1})
        self.assertEqual(s['server']['max_running_jobs'], 2)
        self.assertEqual(s['mail']['backend'], 'file')

    def test_validation_errors_are_keyed_by_path(self):
        self.write_yaml({'server': {'max_running_jobs': 0, 'maintenance': 'yes'},
                         'mail': {'backend': 'pigeon'},
                         'navbar': [{'title': 'x'}]})
        with self.assertRaises(config.ConfigError) as ctx:
            config.load_settings()
        errors = ctx.exception.errors
        self.assertIn('server.max_running_jobs', errors)
        self.assertIn('server.maintenance', errors)
        self.assertIn('mail.backend', errors)
        self.assertIn('navbar[0].url', errors)

    def test_numeric_strings_coerced(self):
        self.write_yaml({'server': {'max_queue_size': '7'}})
        self.assertEqual(config.get('server.max_queue_size'), 7)

    def test_invalid_yaml(self):
        config.settings_path().parent.mkdir(parents=True)
        config.settings_path().write_text('server: [unclosed')
        with self.assertRaises(config.ConfigError):
            config.load_settings()

    def test_broken_file_after_valid_load_keeps_last_valid(self):
        self.write_yaml({'server': {'name': 'Good'}})
        self.assertEqual(config.get('server.name'), 'Good')
        config.settings_path().write_text('server: {max_running_jobs: -5}\n# changed')
        with self.assertLogs('core.config', 'ERROR'):
            self.assertEqual(config.get('server.name'), 'Good')

    def test_returned_dict_is_a_copy(self):
        s = config.load_settings()
        s['server']['name'] = 'mutated'
        self.assertNotEqual(config.get('server.name'), 'mutated')

    def test_external_edit_picked_up_via_mtime(self):
        self.write_yaml({'server': {'name': 'A'}})
        self.assertEqual(config.get('server.name'), 'A')
        time.sleep(0.01)
        self.write_yaml({'server': {'name': 'Bee'}})  # different size too
        self.assertEqual(config.get('server.name'), 'Bee')

    def test_cache_hit_does_not_reparse(self):
        self.write_yaml({'server': {'name': 'A'}})
        config.load_settings()
        from unittest import mock
        with mock.patch.object(config, '_read_yaml', side_effect=AssertionError) as m:
            config.load_settings()
            m.assert_not_called()


class ConfigWriteTest(TempHomeMixin, SimpleTestCase):
    def test_set_value_persists_and_validates(self):
        config.set_value('queue.paused', True)
        self.assertTrue(config.get('queue.paused'))
        on_disk = yaml.safe_load(config.settings_path().read_text())
        self.assertTrue(on_disk['queue']['paused'])
        self.assertEqual(on_disk['server']['max_running_jobs'], 2)  # defaults materialised
        with self.assertRaises(config.ConfigError):
            config.set_value('server.max_running_jobs', 'many')
        self.assertEqual(config.get('server.max_running_jobs'), 2)

    def test_update_settings_deep_merge_and_callable(self):
        self.write_yaml({'server': {'name': 'A', 'max_queue_size': 3}})
        config.update_settings({'server': {'name': 'B'}, 'mail': {'port': 25}})
        self.assertEqual(config.get('server.name'), 'B')
        self.assertEqual(config.get('server.max_queue_size'), 3)
        self.assertEqual(config.get('mail.port'), 25)

        def add_app(doc):
            doc['apps'].append({'path': 'hello', 'groups': ['g']})
        config.update_settings(add_app)
        self.assertEqual(config.get('apps'),
                         [{'path': 'hello', 'groups': ['g'], 'enabled': True, 'public': False}])

    def test_save_is_atomic_no_temp_files_left(self):
        config.save_settings({'server': {'name': 'Z'}})
        leftovers = [p.name for p in config.config_dir().iterdir()
                     if p.name.endswith('.tmp')]
        self.assertEqual(leftovers, [])

    def test_failed_write_leaves_original_intact(self):
        config.save_settings({'server': {'name': 'Orig'}})
        from unittest import mock
        with mock.patch('core.config.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                config.save_settings({'server': {'name': 'New'}})
        config.clear_cache()
        self.assertEqual(config.get('server.name'), 'Orig')
        self.assertEqual([p for p in config.config_dir().iterdir() if p.suffix == '.tmp'], [])

    def test_concurrent_writers_from_processes_do_not_lose_updates(self):
        config.save_settings({})
        n = 8
        ctx = multiprocessing.get_context('fork')
        procs = [ctx.Process(target=_increment_worker, args=(str(self.home), 5))
                 for _ in range(n)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(30)
            self.assertEqual(p.exitcode, 0)
        config.clear_cache()
        self.assertEqual(config.get('server.max_queue_size'), 50 + n * 5)


def _increment_worker(home, times):
    # Runs in a forked process: simulate a second process (e.g. the worker) writing.
    os.environ['CLOUDGENE_HOME'] = home
    for _ in range(times):
        def inc(doc):
            doc['server']['max_queue_size'] += 1
        config.update_settings(inc)


class PathsAndPagesTest(TempHomeMixin, SimpleTestCase):
    def test_paths(self):
        self.assertEqual(config.cloudgene_home(), self.home)
        self.assertEqual(config.settings_path(), self.home / 'config' / 'settings.yaml')
        self.assertEqual(config.app_dir('hello'), self.home / 'apps' / 'hello')
        jid = '123e4567-e89b-12d3-a456-426614174000'
        self.assertEqual(config.job_dir(jid), self.home / 'jobs' / jid)
        config.ensure_home()
        for d in ('config', 'pages', 'apps', 'jobs'):
            self.assertTrue((self.home / d).is_dir())

    def test_traversal_rejected(self):
        for bad in ('../etc', 'a/b', '', '.hidden', 'UPPER', 'x' * 65, 'a b'):
            with self.assertRaises(ValueError):
                config.page_path(bad)
            with self.assertRaises(ValueError):
                config.app_dir(bad)
        with self.assertRaises(ValueError):
            config.job_dir('../../etc')

    def test_pages_roundtrip(self):
        self.assertIsNone(config.read_page('about'))
        config.write_page('about', '<p>Hi</p>')
        self.assertEqual(config.read_page('about'), '<p>Hi</p>')
        config.write_page('home', 'h')
        self.assertEqual(config.list_pages(), ['about', 'home'])
        self.assertTrue(config.delete_page('about'))
        self.assertFalse(config.delete_page('about'))

    def test_parse_env(self):
        env = config.parse_env('# c\nA=1\nexport B="two words"\n bad line\nC=\'x\'\n1X=no\n')
        self.assertEqual(env, {'A': '1', 'B': 'two words', 'C': 'x'})
