import contextlib
import io
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

import yaml

COMMITTED = Path(settings.BASE_DIR) / 'schema.yaml'
REGENERATE = 'python manage.py spectacular --file schema.yaml --validate'


class SchemaStalenessTest(SimpleTestCase):
    """The committed OpenAPI document must match the code (SPEC §3.5)."""

    def test_committed_schema_is_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'schema.yaml'
            with contextlib.redirect_stderr(io.StringIO()):
                call_command('spectacular', file=str(out), validate=True,
                             stdout=io.StringIO(), stderr=io.StringIO())
            generated = out.read_text()
        committed = COMMITTED.read_text()
        if generated != committed:
            self.fail(f'schema.yaml is stale. Regenerate with:\n    {REGENERATE}')

    def test_platform_endpoints_documented(self):
        schema = yaml.safe_load(COMMITTED.read_text())
        for path in ('/api/auth/me/', '/api/auth/login/', '/api/auth/logout/', '/api/health/'):
            self.assertIn(path, schema['paths'])
        self.assertIn('Error', schema['components']['schemas'])
