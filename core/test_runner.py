import logging
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


class CloudgeneTestRunner(DiscoverRunner):
    """Runs tests against a throw-away copy of CLOUDGENE_HOME and a fast password hasher.

    Tests therefore never modify the committed ``home/`` (settings.yaml, pages, jobs).
    Individual tests can still point elsewhere with ``override_settings(CLOUDGENE_HOME=...)``.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from core import config

        self._tmp_home = Path(tempfile.mkdtemp(prefix='cloudgene-test-home-'))
        source = Path(settings.CLOUDGENE_HOME)
        home = self._tmp_home / 'home'
        if source.is_dir():
            shutil.copytree(source, home, ignore=shutil.ignore_patterns('jobs', 'mail'))
        home.mkdir(exist_ok=True)
        self._override = override_settings(
            CLOUDGENE_HOME=home,
            PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
        )
        self._override.enable()
        config.clear_cache()
        # Expected 4xx/5xx responses are asserted by tests; don't flood the output.
        logging.getLogger('django.request').setLevel(logging.CRITICAL)

    def teardown_test_environment(self, **kwargs):
        from core import config

        self._override.disable()
        config.clear_cache()
        shutil.rmtree(self._tmp_home, ignore_errors=True)
        super().teardown_test_environment(**kwargs)
