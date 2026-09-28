"""Jobs API: submission validation, permissions, actions, outputs, admin endpoints."""
import json
import os
import tempfile
import uuid
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core import config as cloudgene_config
from jobs import outputs, runner, workflow_bridge
from jobs.models import Job, JobMessage, JobOutput, JobState, JobStep
from jobs.submission import safe_filename
from jobs.worker import Worker
from workflows import registry

from .helpers import TempHomeMixin, install_fake_nextflow, make_app, make_user

ALL_INPUTS = """
id: all-inputs
name: All inputs
version: 2.0
workflow:
  steps:
    - name: Run
      script: main.nf
      params: {fake_mode: success, fake_tasks: 1}
  inputs:
    - {id: title, description: Title, type: text, value: hello}
    - {id: sep, description: Section, type: separator}
    - {id: count, description: Count, type: number, value: 3, min: 1, max: 10}
    - {id: ratio, description: Ratio, type: number, required: false}
    - {id: notes, description: Notes, type: textarea, writeFile: notes.txt, required: false}
    - {id: plain_notes, description: Plain notes, type: textarea, required: false}
    - {id: mode, description: Mode, type: list, value: fast, values: {fast: Fast, slow: Slow}}
    - {id: flavour, description: Flavour, type: radio, values: [a, b], required: false}
    - {id: flag, description: Flag, type: checkbox, value: true, values: {true: yes-please, false: no-thanks}}
    - {id: plain_flag, description: Plain flag, type: checkbox}
    - {id: data, description: Data, type: file, accept: '.csv,.txt'}
    - {id: many, description: Many, type: folder, required: false}
    - {id: hidden, description: Hidden, type: text, visible: false, value: secret}
    - {id: terms, description: I agree, type: terms_checkbox}
  outputs:
    - {id: outdir, description: Results, type: folder}
    - {id: private, description: Private, type: folder, download: false}
"""


def upload(name, content=b'a,b\n1,2\n'):
    return SimpleUploadedFile(name, content, content_type='text/csv')


class ApiTestBase(TempHomeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        install_fake_nextflow(self._tmp.name)
        self.alice = make_user('alice', groups=['researchers'])
        self.bob = make_user('bob')
        self.admin = make_user('boss', admin=True)
        self.hello = make_app('hello', public=True)
        self.client = APIClient()

    def as_user(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def submit(self, user, data, app='hello', files=None):
        payload = {'workflow': app, **data, **(files or {})}
        return self.as_user(user).post('/api/jobs/', payload, format='multipart')

    def run_worker(self):
        Worker(tick_seconds=0.05, grace=1).drain(timeout=30, tick_seconds=0.05)


class SubmissionTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        make_app('all-inputs', ALL_INPUTS, public=False, groups=['researchers'])

    def valid(self, **overrides):
        data = {'title': 'x', 'count': '4', 'mode': 'slow', 'terms': 'true',
                'data': upload('my data (1).csv')}
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not None}

    def test_all_input_types_are_resolved_and_stored(self):
        files = [upload('ä b.txt', b'1'), upload('../../etc/passwd.txt', b'2'), upload('ä b.txt', b'3')]
        res = self.submit(self.alice, self.valid(
            job_name='  Run #1 — ünïcode 🚀 with  spaces ', notes='line1\r\nline2', plain_notes=' keep ',
            ratio='0.5', flavour='b', flag='false', plain_flag='on', many=files, hidden='hacked'),
            app='all-inputs')
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body['name'], 'Run #1 — ünïcode 🚀 with  spaces')
        self.assertEqual(body['state'], 'waiting')
        self.assertEqual(body['queue_position'], 1)
        job = Job.objects.get(pk=body['id'])
        p = job.parameters
        self.assertEqual(p['title'], 'x')
        self.assertEqual(p['count'], 4)
        self.assertEqual(p['ratio'], 0.5)
        self.assertEqual(p['notes'], 'input/notes/notes.txt')
        self.assertEqual(p['plain_notes'], ' keep ')
        self.assertEqual(p['mode'], 'slow')
        self.assertEqual(p['flavour'], 'b')
        self.assertEqual(p['flag'], 'no-thanks')
        self.assertIs(p['plain_flag'], True)
        self.assertEqual(p['data'], 'input/data/my_data_1_.csv')
        self.assertEqual(p['many'], 'input/many')
        self.assertEqual(p['hidden'], 'secret')
        self.assertIs(p['terms'], True)
        self.assertNotIn('sep', p)
        ws = cloudgene_config.job_dir(job.id)
        self.assertEqual((ws / 'input/notes/notes.txt').read_text(), 'line1\nline2')
        self.assertEqual(sorted(os.listdir(ws / 'input/many')), ['a_b.txt', 'a_b_1.txt', 'passwd.txt'])
        self.assertEqual([f['name'] for f in job.uploads['many']], ['ä b.txt', 'passwd.txt', 'ä b.txt'])
        inputs = {i['id']: i for i in body['inputs']}
        self.assertEqual(inputs['data']['value'], 'my data (1).csv')
        self.assertEqual(inputs['mode']['value'], 'Slow')
        self.assertNotIn('hidden', inputs)

        # params.json built by the worker
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.SUCCESS, job.error_message)
        params = json.loads((ws / 'params.json').read_text())
        self.assertEqual(params['count'], 4)
        self.assertEqual(params['data'], str((ws / 'input/data/my_data_1_.csv').resolve()))
        self.assertEqual(params['many'], str((ws / 'input/many').resolve()))
        self.assertEqual(params['notes'], str((ws / 'input/notes/notes.txt').resolve()))
        self.assertEqual(params['flag'], 'no-thanks')
        self.assertIn('private', params)   # serialize defaults to true even if download is false
        self.assertFalse(JobOutput.objects.filter(job=job, output_id='private').exists())

    def test_defaults_and_unchecked_checkbox(self):
        res = self.submit(self.alice, self.valid(), app='all-inputs')
        self.assertEqual(res.status_code, 201, res.content)
        p = Job.objects.get(pk=res.json()['id']).parameters
        self.assertEqual(p['flag'], 'no-thanks')    # not sent = unchecked
        self.assertIs(p['plain_flag'], False)
        self.assertNotIn('ratio', p)
        self.assertTrue(res.json()['name'].startswith('All inputs 20'))

    def test_field_errors(self):
        res = self.submit(self.alice, {'count': '11', 'mode': 'nope', 'flavour': 'z', 'ratio': 'abc',
                                       'title': '   '}, app='all-inputs')
        self.assertEqual(res.status_code, 400)
        fields = res.json()['error']['fields']
        self.assertEqual(fields['count'], ['Must be at most 10.'])
        self.assertEqual(fields['mode'], ['Select a valid choice.'])
        self.assertEqual(fields['flavour'], ['Select a valid choice.'])
        self.assertEqual(fields['ratio'], ['Please enter a number.'])
        self.assertEqual(fields['title'], ['This field is required.'])
        self.assertEqual(fields['terms'], ['You must accept this to submit the job.'])
        self.assertEqual(fields['data'], ['Please select a file.'])
        self.assertEqual(Job.objects.count(), 0)
        self.assertFalse(any(cloudgene_config.jobs_dir().glob('*')) if cloudgene_config.jobs_dir().exists() else False)

    def test_number_min_and_nan(self):
        for value, msg in (('0', 'Must be at least 1.'), ('nan', 'Please enter a number.'),
                           ('inf', 'Please enter a number.')):
            res = self.submit(self.alice, self.valid(count=value), app='all-inputs')
            self.assertEqual(res.json()['error']['fields']['count'], [msg])

    def test_number_rejects_what_the_run_form_rejects(self):
        # A-05: Python's own leniency (Unicode digits, "1_0" digit-group underscores) must not
        # let the API accept a value formModel.js's NUMBER_RE would reject.
        for value in ('1_0', '٥', '1__0', '1_', '_1'):
            res = self.submit(self.alice, self.valid(count=value), app='all-inputs')
            self.assertEqual(res.json()['error']['fields']['count'], ['Please enter a number.'],
                             'count=%r was accepted' % value)
        for value, expected in (('5', 5), ('+5', 5), (' 7 ', 7), ('4.5', 4.5)):
            res = self.submit(self.alice, self.valid(count=value), app='all-inputs')
            self.assertEqual(res.status_code, 201, res.content)
            self.assertEqual(Job.objects.get(pk=res.json()['id']).parameters['count'], expected)

    def test_file_accept_and_single_file(self):
        res = self.submit(self.alice, self.valid(data=upload('evil.exe')), app='all-inputs')
        self.assertIn('not an accepted file type', res.json()['error']['fields']['data'][0])
        res = self.submit(self.alice, self.valid(data=[upload('a.csv'), upload('b.csv')]), app='all-inputs')
        self.assertEqual(res.json()['error']['fields']['data'], ['Only one file can be uploaded here.'])

    def test_file_part_for_text_input_is_rejected(self):
        # A-01/B-05: a file part for a `text` input must not be silently accepted (and must
        # never become the value, overriding what the user typed).
        res = self.submit(self.alice, self.valid(title=upload('sneaky-name.txt')), app='all-inputs')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('title', res.json()['error']['fields'])
        self.assertEqual(Job.objects.count(), 0)

        # Even a typed value alongside a file for the same field must be rejected, not silently
        # overridden by the file.
        res = self.submit(self.alice, self.valid(title=['typed by the user', upload('m.txt')]),
                          app='all-inputs')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('title', res.json()['error']['fields'])
        self.assertEqual(Job.objects.count(), 0)

    def test_many_files_in_folder_input_is_a_client_error_not_500(self):
        # A-02: more files than DATA_UPLOAD_MAX_NUMBER_FILES must be a 4xx, never a bare 500.
        with self.settings(DATA_UPLOAD_MAX_NUMBER_FILES=5):
            res = self.submit(self.alice, self.valid(many=[upload('f%d.txt' % i) for i in range(10)]),
                              app='all-inputs')
        self.assertLess(res.status_code, 500, res.content)
        self.assertEqual(res.json()['error']['code'], 'upload_too_large')
        self.assertEqual(Job.objects.count(), 0)

    def test_upload_size_limit(self):
        cloudgene_config.set_value('server.max_upload_mb', 1)
        res = self.submit(self.alice, self.valid(data=upload('big.csv', b'x' * (1024 * 1024 + 1))),
                          app='all-inputs')
        self.assertEqual(res.status_code, 413)
        self.assertEqual(res.json()['error']['code'], 'upload_too_large')
        self.assertIn('data', res.json()['error']['fields'])

    def test_name_too_long_and_control_chars(self):
        res = self.submit(self.alice, {'job_name': 'x' * 256})
        self.assertEqual(res.status_code, 400)
        self.assertIn('job_name', res.json()['error']['fields'])
        res = self.submit(self.alice, {'job_name': 'a\x00b\tc'})
        self.assertEqual(res.json()['name'], 'a b c')

    def test_legacy_name_field_and_json_body(self):
        res = self.submit(self.alice, {'name': 'legacy name'})
        self.assertEqual(res.json()['name'], 'legacy name')
        res = self.as_user(self.alice).post('/api/jobs/', {'workflow': 'hello', 'job_name': 'json job',
                                                           'title': 'hi'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Job.objects.get(pk=res.json()['id']).parameters['title'], 'hi')

    def test_workflow_access_and_disabled(self):
        self.assertEqual(self.submit(self.bob, self.valid(), app='all-inputs').status_code, 404)
        self.assertEqual(self.submit(self.bob, {}, app='nope').status_code, 404)
        self.assertEqual(self.submit(self.bob, {'workflow': ''}).status_code, 400)
        make_app('offline', enabled=False)
        res = self.submit(self.alice, {}, app='offline')
        self.assertEqual((res.status_code, res.json()['error']['code']), (409, 'workflow_disabled'))
        self.assertEqual(APIClient().post('/api/jobs/', {'workflow': 'hello'}).status_code, 401)

    def test_maintenance_blocks_users_not_admins(self):
        cloudgene_config.update_settings({'server': {'maintenance': True,
                                                     'maintenance_message': 'Back soon'}})
        res = self.submit(self.alice, {})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['error'], {'message': 'Back soon', 'code': 'maintenance', 'fields': {}})
        self.assertEqual(self.submit(self.admin, {}).status_code, 201)

    def test_queue_full(self):
        cloudgene_config.set_value('server.max_queue_size', 2)
        self.assertEqual(self.submit(self.alice, {}).status_code, 201)
        self.assertEqual(self.submit(self.alice, {}).status_code, 201)
        res = self.submit(self.alice, {})
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()['error']['code'], 'queue_full')
        self.assertIn('queue is full', res.json()['error']['message'])


class SafeFilenameTest(TestCase):
    def test_names(self):
        self.assertEqual(safe_filename('my file ü.csv'), 'my_file_u.csv')
        self.assertEqual(safe_filename('../../etc/passwd'), 'passwd')
        self.assertEqual(safe_filename('C:\\Users\\x\\a b.vcf.gz'), 'a_b.vcf.gz')
        self.assertEqual(safe_filename('.hidden'), 'hidden')
        self.assertEqual(safe_filename('🚀🚀'), 'file')
        self.assertEqual(safe_filename('..'), 'file')
        self.assertTrue(safe_filename('a' * 300 + '.txt').endswith('.txt'))
        self.assertLessEqual(len(safe_filename('a' * 300 + '.txt')), 150)


class JobLifecycleApiTest(ApiTestBase):
    def finished_job(self, user=None, name='done'):
        res = self.submit(user or self.alice, {'job_name': name, 'title': 'T'})
        self.run_worker()
        return Job.objects.get(pk=res.json()['id'])

    def test_list_detail_status_log_and_download(self):
        job = self.finished_job(name='my job ✓')
        c = self.as_user(self.alice)
        listing = c.get('/api/jobs/').json()
        self.assertEqual(listing['count'], 1)
        item = listing['results'][0]
        self.assertEqual((item['name'], item['state'], item['workflow_id'], item['user']['username']),
                         ('my job ✓', 'success', 'hello', 'alice'))
        self.assertTrue(item['can_delete'])
        self.assertIsNotNone(item['expires_at'])
        self.assertEqual(c.get('/api/jobs/?state=running').json()['count'], 0)
        self.assertEqual(c.get('/api/jobs/?state=success,failed').json()['count'], 1)
        self.assertEqual(c.get('/api/jobs/?state=bogus').status_code, 400)

        detail = c.get(f'/api/jobs/{job.id}/').json()
        self.assertEqual(detail['steps'][0]['processes'][0]['completed'], 2)
        self.assertTrue(any(m['text'] == 'hello from stdout' for m in detail['messages']))
        self.assertEqual(detail['log_url'], f'/api/jobs/{job.id}/log/')
        out = {o['path']: o for o in detail['outputs']}
        self.assertEqual(set(out), {'outdir/result.txt', 'outdir/sub dir/nested ü.txt'})
        self.assertEqual(out['outdir/result.txt']['name'], 'result.txt')

        status = c.get(f'/api/jobs/{job.id}/status/').json()
        self.assertEqual(status['state'], 'success')
        self.assertEqual(status['outputs_count'], 2)
        self.assertNotIn('outputs', status)

        res = c.get(out['outdir/result.txt']['url'])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(b''.join(res.streaming_content), b'name=T\n')
        self.assertIn('attachment', res['Content-Disposition'])
        res = c.get(out['outdir/sub dir/nested ü.txt']['url'])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(JobOutput.objects.get(job=job, path='outdir/result.txt').download_count, 1)

        log = c.get(f'/api/jobs/{job.id}/log/')
        self.assertEqual(log.status_code, 200)
        self.assertTrue(log['Content-Type'].startswith('text/plain'))
        self.assertIn('hello from stdout', log.content.decode())
        self.assertIn('nextflow.log', log.content.decode())

    def test_other_users_get_404_admin_gets_access(self):
        job = self.finished_job()
        out = JobOutput.objects.filter(job=job).first()
        bob = self.as_user(self.bob)
        for url in (f'/api/jobs/{job.id}/', f'/api/jobs/{job.id}/status/', f'/api/jobs/{job.id}/log/',
                    f'/api/jobs/{job.id}/outputs/{out.id}/'):
            self.assertEqual(bob.get(url).status_code, 404, url)
        self.assertEqual(bob.post(f'/api/jobs/{job.id}/cancel/').status_code, 404)
        self.assertEqual(bob.delete(f'/api/jobs/{job.id}/').status_code, 404)
        self.assertEqual(bob.get('/api/jobs/').json()['count'], 0)
        admin = self.as_user(self.admin)
        self.assertEqual(admin.get(f'/api/jobs/{job.id}/').status_code, 200)
        self.assertEqual(admin.get(f'/api/jobs/{job.id}/outputs/{out.id}/').status_code, 200)
        self.assertEqual(admin.get('/api/jobs/').json()['count'], 0)   # own jobs only
        anon = APIClient()
        self.assertEqual(anon.get(f'/api/jobs/{job.id}/').status_code, 401)
        self.assertEqual(anon.get(f'/api/jobs/{job.id}/outputs/{out.id}/').status_code, 401)

    def test_output_traversal_and_foreign_ids(self):
        job = self.finished_job()
        other = self.finished_job(user=self.bob)
        c = self.as_user(self.alice)
        other_out = JobOutput.objects.filter(job=other).first()
        self.assertEqual(c.get(f'/api/jobs/{job.id}/outputs/{other_out.id}/').status_code, 404)
        ws = cloudgene_config.job_dir(job.id)
        secret = Path(self._tmp.name) / 'secret.txt'
        secret.write_text('secret')
        (ws / 'output' / 'outdir' / 'link.txt').symlink_to(secret)
        for bad in ('../../../etc/passwd', '/etc/passwd', 'outdir/../../params.json', 'outdir/link.txt',
                    'outdir/missing.txt', 'outdir/sub dir'):
            row = JobOutput.objects.create(job=job, output_id='outdir', path=bad)
            self.assertEqual(c.get(f'/api/jobs/{job.id}/outputs/{row.id}/').status_code, 404, bad)
        self.assertEqual(c.get(f'/api/jobs/{job.id}/outputs/..%2F..%2Fparams.json/').status_code, 404)
        # collector skips symlinks leaving the job's roots
        from jobs.outputs import collect_outputs
        from jobs import workflow_bridge
        collect_outputs(job, workflow_bridge.definition_from_yaml(job.workflow_yaml))
        self.assertFalse(JobOutput.objects.filter(job=job, path='outdir/link.txt').exists())

    def test_a04_per_app_work_dir_is_an_allowed_output_root(self):
        """`runner.work_dir_for` and `outputs._allowed_roots` must agree on which work dir a
        job actually uses, or a per-app `work_dir` override causes every symlinked
        (`publishDir` default) result to resolve outside every allowed root and be silently
        dropped (A-04)."""
        registry.set_nextflow_settings('hello', work_dir='custom-work')
        job = Job(id=uuid.uuid4(), workflow=self.hello, user=self.alice)
        configured = workflow_bridge.nextflow_work_dir(job.workflow)
        self.assertEqual(configured, 'custom-work')  # sanity: the override really applies
        work = runner.work_dir_for(job, configured).resolve()
        roots = outputs._allowed_roots(job)
        self.assertTrue(any(work == r or r in work.parents for r in roots),
                        'work dir %s not covered by allowed roots %s' % (work, roots))

    def test_a04_global_work_dir_still_allowed_without_an_app_override(self):
        job = Job(id=uuid.uuid4(), workflow=self.hello, user=self.alice)
        cloudgene_config.set_value('nextflow.work_dir', 'global-work')
        configured = workflow_bridge.nextflow_work_dir(job.workflow)
        work = runner.work_dir_for(job, configured).resolve()
        roots = outputs._allowed_roots(job)
        self.assertTrue(any(work == r or r in work.parents for r in roots))

    def test_cancel_waiting_and_delete_rules(self):
        c = self.as_user(self.alice)
        job_id = self.submit(self.alice, {}).json()['id']
        self.assertEqual(c.delete(f'/api/jobs/{job_id}/').status_code, 409)
        res = c.post(f'/api/jobs/{job_id}/cancel/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['state'], 'cancelled')
        res = c.post(f'/api/jobs/{job_id}/cancel/')
        self.assertEqual((res.status_code, res.json()['error']['code']), (409, 'invalid_state'))
        ws = cloudgene_config.job_dir(job_id)
        self.assertTrue(ws.exists())
        self.assertEqual(c.delete(f'/api/jobs/{job_id}/').status_code, 204)
        self.assertFalse(ws.exists())
        self.assertEqual(c.get(f'/api/jobs/{job_id}/').status_code, 404)
        self.assertEqual(c.get('/api/jobs/').json()['count'], 0)
        self.assertIsNotNone(Job.objects.get(pk=job_id).deleted_at)

    def test_cancel_running_sets_flag(self):
        job = Job.objects.get(pk=self.submit(self.alice, {}).json()['id'])
        Job.objects.filter(pk=job.pk).update(status=JobState.RUNNING)
        res = self.as_user(self.alice).post(f'/api/jobs/{job.id}/cancel/')
        self.assertEqual(res.json()['state'], 'running')
        self.assertTrue(res.json()['cancel_requested'])
        self.assertFalse(res.json()['can_cancel'])

    def test_queue_positions(self):
        c = self.as_user(self.alice)
        ids = [self.submit(self.alice, {}).json()['id'] for _ in range(3)]
        self.assertEqual([c.get(f'/api/jobs/{i}/status/').json()['queue_position'] for i in ids], [1, 2, 3])
        c.post(f'/api/jobs/{ids[0]}/cancel/')
        self.assertEqual(c.get(f'/api/jobs/{ids[2]}/status/').json()['queue_position'], 2)


class OutputDownloadContentTypeTest(ApiTestBase):
    """B-04: a job output must never be served as active content on the app origin. Only a
    small allowlist (text/plain, image/png|jpeg|gif, application/pdf) may be served with its
    real type and be inline (``?inline=1``); everything else — HTML/SVG/XML/JS/unknown — is
    always ``application/octet-stream`` and always an attachment."""

    PNG_MAGIC = b'\x89PNG\r\n\x1a\n' + b'0' * 8

    def seed_output(self, filename, content=b'data'):
        job = Job.objects.create(name='out', user=self.alice, app_id='hello', app_name='Hello',
                                 status=JobState.SUCCESS, finished_at=timezone.now())
        ws = cloudgene_config.job_dir(job.id) / 'output' / 'outdir'
        ws.mkdir(parents=True, exist_ok=True)
        (ws / filename).write_bytes(content)
        output = JobOutput.objects.create(job=job, output_id='outdir', path=f'outdir/{filename}',
                                          size=len(content))
        return job, output

    def get(self, job, output, inline=False):
        url = f'/api/jobs/{job.id}/outputs/{output.id}/'
        if inline:
            url += '?inline=1'
        return self.as_user(self.alice).get(url)

    def assert_common_headers(self, response):
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Content-Security-Policy'], 'sandbox')

    def test_html_never_served_as_html(self):
        job, output = self.seed_output('report.html', b'<script>alert(1)</script>')
        for inline in (False, True):
            r = self.get(job, output, inline=inline)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn('html', r['Content-Type'].lower())
            self.assertEqual(r['Content-Type'], 'application/octet-stream')
            self.assertIn('attachment', r['Content-Disposition'])
            self.assert_common_headers(r)

    def test_svg_never_served_inline(self):
        job, output = self.seed_output('image.svg', b'<svg onload="alert(1)"></svg>')
        for inline in (False, True):
            r = self.get(job, output, inline=inline)
            self.assertEqual(r['Content-Type'], 'application/octet-stream')
            self.assertIn('attachment', r['Content-Disposition'])
            self.assert_common_headers(r)

    def test_txt_is_safe_and_can_be_inline(self):
        job, output = self.seed_output('notes.txt', b'hello')
        r = self.get(job, output, inline=False)
        self.assertTrue(r['Content-Type'].startswith('text/plain'))
        self.assertIn('attachment', r['Content-Disposition'])
        self.assert_common_headers(r)
        r = self.get(job, output, inline=True)
        self.assertTrue(r['Content-Type'].startswith('text/plain'))
        self.assertIn('inline', r['Content-Disposition'])
        self.assert_common_headers(r)

    def test_png_is_safe_and_can_be_inline(self):
        job, output = self.seed_output('plot.png', self.PNG_MAGIC)
        r = self.get(job, output, inline=False)
        self.assertEqual(r['Content-Type'], 'image/png')
        self.assertIn('attachment', r['Content-Disposition'])
        r = self.get(job, output, inline=True)
        self.assertEqual(r['Content-Type'], 'image/png')
        self.assertIn('inline', r['Content-Disposition'])
        self.assert_common_headers(r)


class AdminJobsApiTest(ApiTestBase):
    def test_admin_list_filters_and_permissions(self):
        a = self.submit(self.alice, {'job_name': 'alpha'}).json()['id']
        b = self.submit(self.bob, {'job_name': 'beta'}).json()['id']
        admin = self.as_user(self.admin)
        self.assertEqual(admin.get('/api/admin/jobs/').json()['count'], 2)
        self.assertEqual([j['id'] for j in admin.get('/api/admin/jobs/?user=bob').json()['results']], [b])
        self.assertEqual(admin.get(f'/api/admin/jobs/?user={self.alice.id}').json()['results'][0]['id'], a)
        self.assertEqual(admin.get('/api/admin/jobs/?search=alp').json()['count'], 1)
        self.assertEqual(admin.get('/api/admin/jobs/?workflow=hello&state=waiting').json()['count'], 2)
        self.assertEqual(admin.get('/api/admin/jobs/?workflow=other').json()['count'], 0)
        self.assertEqual(self.as_user(self.alice).get('/api/admin/jobs/').status_code, 403)
        self.assertEqual(self.as_user(self.alice).post(f'/api/admin/jobs/{b}/cancel/').status_code, 403)
        self.assertEqual(APIClient().get('/api/admin/jobs/').status_code, 401)
        res = admin.post(f'/api/admin/jobs/{b}/cancel/')
        self.assertEqual(res.json()['state'], 'cancelled')
        self.assertTrue(JobMessage.objects.filter(job_id=b, text='Job cancelled by an administrator.').exists())

    def test_restart(self):
        admin = self.as_user(self.admin)
        make_app('bad', mode='fail')
        job_id = self.submit(self.alice, {}, app='bad').json()['id']
        self.assertEqual(admin.post(f'/api/admin/jobs/{job_id}/restart/').status_code, 409)  # waiting
        self.run_worker()
        self.assertEqual(Job.objects.get(pk=job_id).status, JobState.FAILED)
        # fix the workflow, then restart: uses the current definition
        make_app('bad', mode='success')
        res = admin.post(f'/api/admin/jobs/{job_id}/restart/')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['state'], 'waiting')
        self.assertEqual(JobStep.objects.filter(job_id=job_id).count(), 0)
        self.run_worker()
        self.assertEqual(Job.objects.get(pk=job_id).status, JobState.SUCCESS)
        self.assertEqual(admin.post(f'/api/admin/jobs/{job_id}/restart/').status_code, 409)  # success

    def test_restart_needs_enabled_workflow(self):
        job_id = self.submit(self.alice, {}).json()['id']
        Job.objects.filter(pk=job_id).update(status=JobState.FAILED)
        self.hello.status = 'disabled'
        self.hello.save()
        res = self.as_user(self.admin).post(f'/api/admin/jobs/{job_id}/restart/')
        self.assertEqual((res.status_code, res.json()['error']['code']), (409, 'workflow_unavailable'))


class CleanupCommandTest(ApiTestBase):
    def test_retention(self):
        old = Job.objects.get(pk=self.submit(self.alice, {}).json()['id'])
        new = Job.objects.get(pk=self.submit(self.alice, {}).json()['id'])
        running = Job.objects.get(pk=self.submit(self.alice, {}).json()['id'])
        now = timezone.now()
        Job.objects.filter(pk=old.pk).update(status=JobState.SUCCESS, finished_at=now - timezone.timedelta(days=8))
        Job.objects.filter(pk=new.pk).update(status=JobState.SUCCESS, finished_at=now)
        Job.objects.filter(pk=running.pk).update(status=JobState.RUNNING, started_at=now - timezone.timedelta(days=30))
        call_command('cleanup_jobs', stdout=open(os.devnull, 'w'))
        self.assertFalse(cloudgene_config.job_dir(old.id).exists())
        self.assertTrue(cloudgene_config.job_dir(new.id).exists())
        self.assertTrue(cloudgene_config.job_dir(running.id).exists())
        old.refresh_from_db()
        self.assertIsNotNone(old.purged_at)
        self.assertFalse(old.can_restart())
        cloudgene_config.set_value('server.job_retention_days', 0)
        orphan = cloudgene_config.jobs_dir() / '0f0f0f0f-0000-4000-8000-000000000000'
        (orphan / 'input').mkdir(parents=True)
        os.utime(orphan, (0, 0))
        other = cloudgene_config.jobs_dir() / 'not-a-job'
        other.mkdir()
        call_command('cleanup_jobs', stdout=open(os.devnull, 'w'))
        self.assertTrue(cloudgene_config.job_dir(new.id).exists())
        self.assertFalse(orphan.exists())
        self.assertTrue(other.exists())

    def test_deleting_a_user_removes_job_workspaces(self):
        job = Job.objects.get(pk=self.submit(self.bob, {}).json()['id'])
        ws = cloudgene_config.job_dir(job.id)
        self.assertTrue(ws.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.bob.delete()
        self.assertFalse(Job.objects.filter(pk=job.pk).exists())
        self.assertFalse(ws.exists())
