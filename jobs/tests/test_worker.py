"""Worker state machine with a fake `nextflow` executable."""
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase

from core import config as cloudgene_config
from core.models import WorkerHeartbeat
from jobs import worker as worker_mod
from jobs.models import Job, JobMessage, JobOutput, JobState
from jobs.submission import submit_job
from jobs.worker import ORPHAN_MESSAGE, Worker

from .helpers import TempHomeMixin, install_fake_nextflow, make_app, make_user, pid_alive


class WorkerTestBase(TempHomeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fake = install_fake_nextflow(self._tmp.name)
        cloudgene_config.set_value('server.max_running_jobs', 2)
        cloudgene_config.set_value('queue.paused', False)
        self.user = make_user('alice')
        self.worker = Worker(tick_seconds=0.05, grace=1)
        self.addCleanup(self.worker.shutdown)

    def submit(self, app='hello', name='My job', **data):
        return submit_job(self.user, {'workflow': app, 'job_name': name, **data}, {})

    def run_until(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.worker.tick()
            if predicate():
                return
            time.sleep(0.05)
        self.fail('condition not reached in time')

    def state(self, job):
        job.refresh_from_db()
        return job.status


class WorkerSuccessTest(WorkerTestBase):
    def test_job_runs_to_success_with_progress_messages_and_outputs(self):
        make_app('hello')
        job = self.submit(name='  Täst job with spaces 🚀  ', title='hello world')
        self.assertEqual(job.name, 'Täst job with spaces 🚀')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.SUCCESS, job.error_message)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.finished_at)
        self.assertIsNone(job.pid)

        step = job.steps.get()
        self.assertEqual(step.status, 'success')
        self.assertEqual(step.processes, [{
            'name': 'SAY', 'label': 'Saying hello', 'submitted': 2, 'running': 0,
            'completed': 2, 'failed': 0, 'total': 2}])

        texts = list(job.messages.values_list('level', 'text'))
        self.assertIn(('info', 'hello from stdout'), texts)
        self.assertIn(('warning', 'careful now'), texts)
        self.assertIn(('error', 'grouped line 1\ngrouped line 2'), texts)
        self.assertIn(('info', 'task 1 says hi'), texts)
        self.assertIn(('info', 'task 2 says hi'), texts)
        self.assertEqual(texts[-1], ('success', 'Job completed successfully.'))

        outputs = sorted(JobOutput.objects.filter(job=job).values_list('output_id', 'path'))
        self.assertEqual(outputs, [('outdir', 'outdir/result.txt'), ('outdir', 'outdir/sub dir/nested ü.txt')])

        # Command line, params.json and environment (SPEC §3.3, W4)
        workspace = cloudgene_config.job_dir(job.id)
        inv = json.loads((workspace / 'work' / 'invocation.json').read_text())
        argv = inv['argv']
        self.assertEqual(argv[:2], ['-log', str(workspace / 'logs' / 'nextflow.log')])
        self.assertEqual(argv[2:4], ['run', str(cloudgene_config.apps_dir() / 'hello' / 'main.nf')])
        for flag, value in (('-params-file', str(workspace / 'params.json')),
                            ('-w', str(workspace / 'work')),
                            ('-with-trace', str(workspace / 'logs' / 'trace.txt')),
                            ('-with-report', str(workspace / 'logs' / 'report.html')),
                            ('-with-timeline', str(workspace / 'logs' / 'timeline.html'))):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertIn(str(cloudgene_config.nextflow_config_path()), argv)
        self.assertNotIn('-profile', argv)
        self.assertEqual(inv['params'], {
            'fake_mode': 'success', 'fake_tasks': 2, 'title': 'hello world',
            'outdir': str((workspace / 'output' / 'outdir').resolve())})
        env = inv['env']
        self.assertEqual(env['CLOUDGENE_JOB_ID'], str(job.id))
        self.assertEqual(env['CLOUDGENE_JOB_NAME'], 'Täst job with spaces 🚀')
        self.assertEqual(env['CLOUDGENE_USER_NAME'], 'alice')
        self.assertEqual(env['CLOUDGENE_USER_EMAIL'], 'alice@example.com')
        self.assertEqual(env['CLOUDGENE_USER_FULL_NAME'], 'Alice Tester')
        self.assertEqual(env['CLOUDGENE_APP_ID'], 'hello')
        self.assertEqual(env['CLOUDGENE_APP_VERSION'], '1.0.0')
        self.assertEqual(env['CLOUDGENE_APP_LOCATION'], str(cloudgene_config.apps_dir() / 'hello'))
        self.assertEqual(env['CLOUDGENE_SERVICE_NAME'], 'Cloudgene')
        self.assertEqual(inv['cwd'], str(workspace))
        # the job name is never part of a path or argument
        self.assertFalse(any('Täst' in a for a in argv))

    def test_env_files_profile_and_app_config(self):
        make_app('hello', files={'nextflow.config': '// app\n', 'nextflow.env': 'FAKE_APP=app-${FAKE_GLOBAL}\n'})
        cloudgene_config.write_text_atomic(cloudgene_config.nextflow_env_path(), 'export FAKE_GLOBAL="g 1"\n')
        cloudgene_config.set_value('nextflow.profile', 'test')
        job = self.submit()
        self.worker.drain(timeout=30, tick_seconds=0.05)
        inv = json.loads((cloudgene_config.job_dir(job.id) / 'work' / 'invocation.json').read_text())
        self.assertEqual(inv['env']['FAKE_GLOBAL'], 'g 1')
        self.assertEqual(inv['env']['FAKE_APP'], 'app-g 1')
        argv = inv['argv']
        self.assertEqual(argv[argv.index('-profile') + 1], 'test')
        self.assertIn(str(cloudgene_config.apps_dir() / 'hello' / 'nextflow.config'), argv)

    def test_multi_step_and_remote_script(self):
        make_app('multi', """
id: multi
name: Multi
workflow:
  steps:
    - name: First
      script: main.nf
    - name: Second
      script: nf-core/demo
      revision: '1.0'
""")
        job = self.submit('multi')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.SUCCESS, job.error_message)
        self.assertEqual(list(job.steps.values_list('name', 'status')),
                         [('First', 'success'), ('Second', 'success')])
        inv = json.loads((cloudgene_config.job_dir(job.id) / 'work' / 'invocation.json').read_text())
        self.assertEqual(inv['argv'][3:6], ['nf-core/demo', '-r', '1.0'])
        self.assertIn('step2-trace.txt', ' '.join(inv['argv']))


class WorkerFailureTest(WorkerTestBase):
    def test_failed_pipeline(self):
        make_app('bad', mode='fail')
        job = self.submit('bad')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('exited with code 1', job.error_message)
        self.assertIn('ERROR ~ Error executing process', job.error_message)
        self.assertTrue(job.messages.filter(level='error', text='it failed badly').exists())
        self.assertEqual(job.steps.get().status, 'failed')

    def test_unsupported_step_fails_with_clear_message(self):
        make_app('java', 'id: java\nname: Java\nworkflow:\n  steps:\n    - name: Old\n      classname: cloudgene.Foo\n')
        job = self.submit('java')
        self.worker.drain(timeout=10, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('classname', job.error_message)

    def test_missing_binary(self):
        make_app('hello')
        cloudgene_config.set_value('nextflow.binary', '/nonexistent/nextflow')
        job = self.submit()
        self.worker.drain(timeout=10, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('Could not start Nextflow', job.error_message)

    def test_invalid_snapshot(self):
        make_app('hello')
        job = self.submit()
        Job.objects.filter(pk=job.pk).update(workflow_yaml='id: [broken')
        self.worker.drain(timeout=10, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('definition is invalid', job.error_message)


class WorkerQueueTest(WorkerTestBase):
    def test_max_running_and_queue_advances_without_requests(self):
        """K2: finished jobs free a slot and the next waiting job starts on the next tick."""
        make_app('slow', mode='sleep')
        cloudgene_config.set_value('server.max_running_jobs', 1)
        a, b = self.submit('slow', 'a'), self.submit('slow', 'b')
        self.worker.tick()
        self.assertEqual((self.state(a), self.state(b)), (JobState.RUNNING, JobState.WAITING))
        self.assertEqual(b.queue_position(), 1)
        Job.objects.filter(pk=a.pk).update(cancel_requested=True)
        self.run_until(lambda: self.state(b) == JobState.RUNNING)
        self.assertEqual(self.state(a), JobState.CANCELLED)

    def test_paused_queue_claims_nothing(self):
        make_app('hello')
        cloudgene_config.set_value('queue.paused', True)
        job = self.submit()
        for _ in range(3):
            self.worker.tick()
        self.assertEqual(self.state(job), JobState.WAITING)
        cloudgene_config.set_value('queue.paused', False)
        self.run_until(lambda: self.state(job) == JobState.SUCCESS)

    def test_heartbeat(self):
        self.worker.tick()
        hb = WorkerHeartbeat.objects.get(name='default')
        self.assertEqual(hb.pid, os.getpid())
        self.assertTrue(hb.is_alive)
        self.assertEqual(hb.info['paused'], False)


class TickPhaseIsolationTest(WorkerTestBase):
    """A-03 (worker half): a "database is locked" error in one tick phase must not abandon the
    others (SQLite write contention between the web process and the worker), and the failure is
    logged once, without a traceback for the expected/known case."""

    def test_heartbeat_lock_error_does_not_stop_poll_and_claim(self):
        make_app('hello')
        job = self.submit()
        with mock.patch('jobs.worker.WorkerHeartbeat.beat',
                        side_effect=OperationalError('database is locked')):
            with self.assertLogs('cloudgene.worker', 'WARNING') as logs:
                self.worker.tick()
        # the heartbeat phase failed and logged a WARNING (no traceback)...
        self.assertTrue(any('heartbeat' in m and 'database is locked' in m for m in logs.output),
                        logs.output)
        self.assertFalse(any(r.levelno >= 40 for r in logs.records), logs.output)  # no ERROR
        self.assertFalse(any(r.exc_info for r in logs.records), logs.output)       # no traceback
        # ...but claim() still ran in the same tick: the job was picked up regardless.
        self.assertEqual(self.state(job), JobState.RUNNING)

    def test_unexpected_error_in_one_phase_is_logged_with_traceback_and_others_still_run(self):
        make_app('hello')
        job = self.submit()
        with mock.patch.object(Worker, 'reconcile_orphans', side_effect=RuntimeError('boom')):
            with self.assertLogs('cloudgene.worker', 'ERROR') as logs:
                self.worker.tick()
        self.assertTrue(any('reconcile' in m for m in logs.output), logs.output)
        self.assertTrue(any(r.exc_info for r in logs.records), logs.output)  # traceback kept
        self.assertEqual(self.state(job), JobState.RUNNING)   # claim() still ran


class RetryOnLockedTest(TestCase):
    def test_succeeds_after_transient_lock_errors(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise OperationalError('database is locked')
            return 'ok'

        with mock.patch('jobs.worker.time.sleep') as sleep:
            self.assertEqual(worker_mod.retry_on_locked(flaky), 'ok')
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_reraises_after_the_attempt_limit(self):
        def always_locked():
            raise OperationalError('database is locked')

        with mock.patch('jobs.worker.time.sleep'):
            with self.assertRaises(OperationalError):
                worker_mod.retry_on_locked(always_locked, attempts=3)

    def test_non_lock_error_is_not_retried(self):
        calls = []

        def broken():
            calls.append(1)
            raise OperationalError('no such table: jobs')

        with mock.patch('jobs.worker.time.sleep') as sleep:
            with self.assertRaises(OperationalError):
                worker_mod.retry_on_locked(broken)
        self.assertEqual(len(calls), 1)          # not retried
        sleep.assert_not_called()

    def test_other_exception_types_are_not_retried(self):
        with mock.patch('jobs.worker.time.sleep') as sleep:
            with self.assertRaises(ValueError):
                worker_mod.retry_on_locked(lambda: (_ for _ in ()).throw(ValueError('nope')))
        sleep.assert_not_called()


class WorkerCancelTest(WorkerTestBase):
    def test_cancel_running_kills_process_tree(self):
        make_app('slow', mode='sleep')
        job = self.submit('slow')
        child_file = cloudgene_config.job_dir(job.id) / 'work' / 'child.pid'
        self.run_until(child_file.exists)
        child = int(child_file.read_text())
        job.refresh_from_db()
        nf_pid = job.pid
        self.assertTrue(pid_alive(child))
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
        self.run_until(lambda: self.state(job) == JobState.CANCELLED, timeout=15)
        time.sleep(0.2)
        self.assertFalse(pid_alive(nf_pid))
        self.assertFalse(pid_alive(child))
        self.assertEqual(job.steps.get().status, 'cancelled')
        self.assertTrue(JobMessage.objects.filter(job=job, text='Job cancelled.').exists())

    def test_sigkill_after_grace(self):
        make_app('stubborn', mode='sleep', files={})
        # a fake that ignores SIGTERM
        stubborn = Path(self._tmp.name) / 'stubborn'
        stubborn.write_text(f'#!/bin/sh\ntrap "" TERM\nexec {self.fake} "$@"\n')
        stubborn.chmod(0o755)
        cloudgene_config.set_value('nextflow.binary', str(stubborn))
        job = self.submit('stubborn')
        child_file = cloudgene_config.job_dir(job.id) / 'work' / 'child.pid'
        self.run_until(child_file.exists)
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
        self.run_until(lambda: self.state(job) == JobState.CANCELLED, timeout=15)

    def test_waiting_cancel_race_handled_by_worker(self):
        make_app('hello')
        cloudgene_config.set_value('queue.paused', True)
        job = self.submit()
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
        self.worker.tick()
        self.assertEqual(self.state(job), JobState.CANCELLED)


class OrphanTest(WorkerTestBase):
    def test_orphan_running_job_is_failed_and_its_group_killed(self):
        make_app('hello')
        job = self.submit()
        workspace = cloudgene_config.job_dir(job.id)
        proc = subprocess.Popen(['sh', '-c', 'sleep 300', str(job.id)], start_new_session=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        Job.objects.filter(pk=job.pk).update(status=JobState.RUNNING, pid=proc.pid, pgid=proc.pid)
        self.worker.startup()
        self.assertEqual(self.state(job), JobState.FAILED)
        self.assertEqual(job.error_message, ORPHAN_MESSAGE)
        proc.wait(timeout=5)
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.assertTrue(workspace.exists())

    def test_foreign_process_group_is_not_killed(self):
        make_app('hello')
        job = self.submit()
        proc = subprocess.Popen(['sleep', '300'], start_new_session=True)
        self.addCleanup(proc.kill)
        Job.objects.filter(pk=job.pk).update(status=JobState.RUNNING, pid=proc.pid, pgid=proc.pid)
        self.worker.startup()
        self.assertEqual(self.state(job), JobState.FAILED)
        self.assertIsNone(proc.poll())


class ShutdownTest(WorkerTestBase):
    def test_shutdown_stops_running_jobs(self):
        make_app('slow', mode='sleep')
        job = self.submit('slow')
        child_file = cloudgene_config.job_dir(job.id) / 'work' / 'child.pid'
        self.run_until(child_file.exists)
        child = int(child_file.read_text())
        self.worker.request_stop(signal.SIGTERM, None)
        self.worker.shutdown()
        self.assertEqual(self.state(job), JobState.FAILED)
        self.assertIn('shut down', job.error_message)
        time.sleep(0.2)
        self.assertFalse(pid_alive(child))


class DeletedWhileRunningTest(WorkerTestBase):
    """C-03: the worker owns the workspace of any *claimed* job. Deleting a Job row (e.g.
    cascading from a user deletion) must not leave the workspace back on disk once the worker
    catches up, must never leave Nextflow running untracked, and the worker must not log a
    traceback for any of this — it is a designed shutdown path, not a bug."""

    def test_deleting_a_waiting_job_removes_the_workspace_immediately(self):
        # Never claimed: nothing is running for it, so the web process (the post_delete
        # signal) removes the workspace itself, without involving the worker at all.
        make_app('hello')
        cloudgene_config.set_value('queue.paused', True)
        job = self.submit()
        workspace = cloudgene_config.job_dir(job.id)
        self.assertTrue(workspace.is_dir())
        self.assertEqual(self.state(job), JobState.WAITING)

        with self.captureOnCommitCallbacks(execute=True):
            job.delete()
        self.assertFalse(workspace.exists())

    def test_deleting_a_running_job_leaves_the_workspace_to_the_worker(self):
        # The signal must not kill anything or touch the workspace for a running job — only
        # the worker (which alone knows whether Nextflow is still writing to it) may do that.
        make_app('slow', mode='sleep')
        job = self.submit('slow')
        child_file = cloudgene_config.job_dir(job.id) / 'work' / 'child.pid'
        self.run_until(child_file.exists)
        job.refresh_from_db()
        nf_pid = job.pid
        child = int(child_file.read_text())
        workspace = cloudgene_config.job_dir(job.id)
        self.assertTrue(pid_alive(nf_pid))

        with mock.patch('jobs.worker.kill_orphan_group') as killer:
            with self.assertLogs('cloudgene.jobs', 'INFO') as jlogs:
                with self.captureOnCommitCallbacks(execute=True):
                    job.delete()
        killer.assert_not_called()
        self.assertTrue(any('leaving the workspace for the worker' in m for m in jlogs.output),
                        jlogs.output)

        # nothing was killed and nothing was removed by the web process
        self.assertTrue(pid_alive(nf_pid))
        self.assertTrue(pid_alive(child))
        self.assertTrue(workspace.exists())

        # the worker still holds the Execution for this job; its next poll notices the row is
        # gone, kills the process group, waits for it to exit, and only then removes the
        # workspace — no traceback.
        with self.assertLogs('cloudgene.worker', 'INFO') as logs:
            self.worker.poll_executions()
        self.assertNotIn(str(job.id), self.worker.executions)
        self.assertFalse(any(r.levelno >= 40 for r in logs.records), logs.output)  # no ERROR/exception
        self.assertTrue(any('vanished' in m and 'row was deleted' in m for m in logs.output), logs.output)
        self.assertFalse(pid_alive(nf_pid))
        self.assertFalse(pid_alive(child))
        self.assertFalse(workspace.exists())

    def test_deleting_a_finished_job_does_not_try_to_kill_anything(self):
        make_app('hello')
        job = self.submit()
        self.run_until(lambda: self.state(job) == JobState.SUCCESS)
        workspace = cloudgene_config.job_dir(job.id)
        with mock.patch('jobs.worker.kill_orphan_group') as killer:
            with self.captureOnCommitCallbacks(execute=True):
                job.delete()
        killer.assert_not_called()
        self.assertFalse(workspace.exists())

    def test_row_deleted_right_after_nextflow_starts_is_not_left_running(self):
        """The original C-03 race: `claim()` sets status=running before pid/pgid are persisted.
        If the row is deleted in that exact window (simulated here by deleting it right after
        Popen returns, before the pid/pgid update lands), the process must still be killed and
        the workspace still removed — nothing must be left writing into a directory nobody is
        watching any more."""
        make_app('slow', mode='sleep')
        job = self.submit('slow')
        workspace = cloudgene_config.job_dir(job.id)
        real_popen = subprocess.Popen
        procs = []

        def popen_then_delete_row(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            procs.append(proc)
            Job.objects.filter(pk=job.pk).delete()
            return proc

        with mock.patch('jobs.worker.subprocess.Popen', side_effect=popen_then_delete_row):
            with self.assertLogs('cloudgene.worker', 'INFO') as logs:
                self.worker.tick()
        self.assertFalse(any(r.levelno >= 40 for r in logs.records), logs.output)  # no ERROR/exception
        self.assertTrue(any('row was deleted' in m for m in logs.output), logs.output)
        self.assertNotIn(str(job.id), self.worker.executions)

        self.assertEqual(len(procs), 1)
        procs[0].wait(timeout=5)
        self.assertFalse(pid_alive(procs[0].pid))
        self.assertFalse(workspace.exists())


class RunWorkerCommandTest(WorkerTestBase):
    def test_once_and_single_instance_lock(self):
        make_app('hello')
        job = self.submit()
        lock = worker_mod.acquire_lock()
        try:
            with self.assertRaises(CommandError):
                call_command('run_worker', '--once')
        finally:
            lock.close()
        call_command('run_worker', '--once', '--interval', '0.05')
        self.assertEqual(self.state(job), JobState.SUCCESS)
