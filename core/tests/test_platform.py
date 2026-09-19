import subprocess
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from jobs.models import Job
from workflows.models import Workflow

User = get_user_model()


class NoCeleryChannelsTest(SimpleTestCase):
    def test_django_boots_without_celery_channels_redis(self):
        """Loading settings, apps and all URL modules must not import removed infra (P3)."""
        code = (
            'import sys, django; django.setup();'
            'from django.urls import get_resolver; get_resolver().url_patterns;'
            'import cloudgene_django.wsgi, cloudgene_django.asgi;'
            'bad = [m for m in ("celery", "channels", "redis", "corsheaders",'
            ' "django_celery_results") if m in sys.modules];'
            'print(",".join(bad))'
        )
        out = subprocess.run([sys.executable, '-c', code], cwd=settings.BASE_DIR,
                             capture_output=True, text=True, timeout=60,
                             env={'DJANGO_SETTINGS_MODULE': 'cloudgene_django.settings',
                                  'PATH': '/usr/bin:/bin',
                                  'CLOUDGENE_HOME': str(settings.CLOUDGENE_HOME)})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), '')


class SubmissionWithoutWorkerTest(TestCase):
    def test_submitted_job_waits_until_the_worker_claims_it(self):
        """Celery is gone; submission must not crash and must not fake a running job."""
        user = User.objects.create_user(username='alice', email='a@example.org',
                                        password='Secret123', full_name='A')
        Workflow.objects.create(
            id='hello', name='Hello', status='enabled', public=True,
            yaml_config='id: hello\nname: Hello\nworkflow:\n  steps: [{script: main.nf}]\n'
                        '  inputs:\n    - {id: name, description: Name, type: text}\n')
        client = APIClient()
        client.force_authenticate(user)
        r = client.post('/api/jobs/', {'workflow': 'hello', 'job_name': 'my job', 'name': 'x'},
                        format='json')
        self.assertEqual(r.status_code, 201, r.content)
        job = Job.objects.get(id=r.json()['id'])
        self.assertEqual(job.status, 'waiting')
        self.assertIsNone(job.started_at)
