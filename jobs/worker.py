"""
The job worker (``manage.py run_worker``) — scheduler + executor, plans/SPEC.md §3.3.

One tick (~1 s): heartbeat → read settings → reconcile orphans → poll running executions
(progress, cancellation, completion) → claim waiting jobs up to ``server.max_running_jobs``
unless ``queue.paused``. Every Nextflow run is a subprocess in its own process group so that
cancellation (SIGTERM → grace → SIGKILL) reaches the whole task tree and the worker never blocks.
"""
from __future__ import annotations

import logging
import os
import shlex
import signal
import socket
import subprocess
import time
from pathlib import Path

from django.db import close_old_connections, connection
from django.utils import timezone

from core import config as cloudgene_config
from core.models import WorkerHeartbeat
from workflows.definition import DefinitionError

from . import runner, workflow_bridge
from .models import Job, JobMessage, JobState, JobStep
from .outputs import collect_outputs
from .progress import (AnnotationParser, LineBuffer, MessageMerger, ProcessTracker, TraceReader,
                       parse_task_line, read_task_annotations)

logger = logging.getLogger('cloudgene.worker')

CANCEL_GRACE_SECONDS = 10
ORPHAN_MESSAGE = 'The worker was restarted while this job was running; the job was stopped.'
SHUTDOWN_MESSAGE = 'The worker was shut down while this job was running; the job was stopped.'


# ------------------------------------------------------------------------------------------
# Process-group helpers
# ------------------------------------------------------------------------------------------

def _group_alive(pgid) -> bool:
    if not pgid:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _group_belongs_to_job(pgid, job_id) -> bool:
    """True if some process of group ``pgid`` mentions the job id (cmdline or environment)."""
    needle = str(job_id).encode()
    proc = Path('/proc')
    if not proc.is_dir():
        return True   # cannot verify on this platform; trust the stored pgid
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / 'stat').read_text()
            pgrp = int(stat.rsplit(')', 1)[1].split()[2])
            if pgrp != pgid:
                continue
            if needle in (entry / 'cmdline').read_bytes() or needle in (entry / 'environ').read_bytes():
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def _signal_group(pgid, sig) -> bool:
    try:
        os.killpg(pgid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def kill_orphan_group(job) -> bool:
    pgid = job.pgid or job.pid
    if pgid and _group_alive(pgid) and _group_belongs_to_job(pgid, job.id):
        _signal_group(pgid, signal.SIGKILL)
        return True
    return False


# ------------------------------------------------------------------------------------------
# Execution of one job
# ------------------------------------------------------------------------------------------

class JobSetupError(Exception):
    pass


class Execution:
    """Runs the steps of one claimed job, one subprocess at a time."""

    def __init__(self, job: Job, grace: float = CANCEL_GRACE_SECONDS):
        self.job = job
        self.grace = grace
        self.proc = None
        self.term_sent_at = None
        self.kill_sent = False
        self.finished = False
        try:
            self.definition = workflow_bridge.definition_from_yaml(job.workflow_yaml)
        except DefinitionError as exc:
            raise JobSetupError(f'The workflow definition is invalid: {exc}') from exc
        self.app_dir = Path(job.app_dir) if job.app_dir else cloudgene_config.apps_dir() / job.app_id
        self.job_dir = cloudgene_config.job_dir(job.id)
        JobStep.objects.filter(job=job).delete()
        self.step_rows = [JobStep.objects.create(job=job, order=i, name=s.name)
                          for i, s in enumerate(self.definition.steps)]
        self.index = -1

    # -- messages ---------------------------------------------------------------------------

    def _step_row(self):
        if 0 <= self.index < len(self.step_rows):
            return self.step_rows[self.index]
        return None

    def add_messages(self, messages):
        if not messages:
            return
        step = self._step_row()
        now = timezone.now()
        JobMessage.objects.bulk_create([
            JobMessage(job=self.job, step=step, level=level, text=text, created_at=now)
            for level, text in messages
        ])

    def _log(self, text):
        path = self.job_dir / 'logs' / 'stdout.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(f'[cloudgene] {text}\n')

    # -- lifecycle --------------------------------------------------------------------------

    def start(self):
        self.add_messages([('info', 'Job started.')])
        self._start_step(0)

    def _start_step(self, index):
        self.index = index
        step = self.definition.steps[index]
        row = self.step_rows[index]
        row.status = 'running'
        row.started_at = timezone.now()
        row.save(update_fields=['status', 'started_at'])
        Job.objects.filter(pk=self.job.pk).update(current_step=index)
        if not step.supported:
            self._finish(JobState.FAILED, step.error or f'Step "{step.name}" is not supported.')
            return

        wf = self.job.workflow
        binary = runner.resolve_binary(cloudgene_config.get('nextflow.binary', 'nextflow'))
        prepared = runner.prepare_step(
            self.job, self.definition, index, binary=binary,
            profile=workflow_bridge.nextflow_profile(wf),
            work_dir=workflow_bridge.nextflow_work_dir(wf), app_dir=self.app_dir,
        )
        total = len(self.definition.steps)
        self._log(f'Step {index + 1}/{total}: {step.name}')
        self._log('$ ' + shlex.join(prepared.command))
        self.stdout_path = prepared.stdout_path
        self.stdout_offset = self.stdout_path.stat().st_size if self.stdout_path.exists() else 0
        self.step_stdout_start = self.stdout_offset
        self.lines = LineBuffer()
        self.annotations = AnnotationParser()
        self.merger = MessageMerger()
        labels = {p['process']: p.get('label') for p in step.processes if p.get('label')}
        self.tracker = ProcessTracker(labels)
        self.trace = TraceReader(prepared.trace_path)
        self.term_sent_at = None
        self.kill_sent = False
        out = open(self.stdout_path, 'ab')
        try:
            self.proc = subprocess.Popen(
                prepared.command, cwd=prepared.cwd, env=prepared.env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
            )
        except OSError as exc:
            self._finish(JobState.FAILED, f'Could not start Nextflow ({prepared.command[0]}): {exc}')
            return
        finally:
            out.close()
        pgid = self.proc.pid
        try:
            pgid = os.getpgid(self.proc.pid)
        except OSError:
            pass
        Job.objects.filter(pk=self.job.pk).update(pid=self.proc.pid, pgid=pgid)
        self.job.pid, self.job.pgid = self.proc.pid, pgid

    def request_cancel(self):
        if self.proc is not None and self.term_sent_at is None and not self.finished:
            self._log('Cancel requested: sending SIGTERM to the process group')
            self.term_sent_at = time.monotonic()
            _signal_group(self.job.pgid or self.proc.pid, signal.SIGTERM)

    def poll(self, cancel_requested=False) -> bool:
        """Advance the execution; returns True when the job reached a final state."""
        if self.finished:
            return True
        if self.proc is None:
            return self.finished
        self._read_progress()
        if cancel_requested:
            self.request_cancel()
        if (self.term_sent_at is not None and not self.kill_sent
                and time.monotonic() - self.term_sent_at > self.grace):
            self._log('Grace period over: sending SIGKILL')
            _signal_group(self.job.pgid or self.proc.pid, signal.SIGKILL)
            self.kill_sent = True
        rc = self.proc.poll()
        if rc is None:
            return False
        # Nextflow is gone: make sure no task of its group survives.
        _signal_group(self.job.pgid or self.proc.pid, signal.SIGKILL)
        self._read_progress(final=True)
        row = self.step_rows[self.index]
        if self.term_sent_at is not None:
            self._finish(JobState.CANCELLED, 'Job cancelled.')
        elif rc == 0:
            self._save_processes()
            row.status, row.finished_at = 'success', timezone.now()
            row.save(update_fields=['status', 'finished_at'])
            if self.index + 1 < len(self.definition.steps):
                self._start_step(self.index + 1)
                return self.finished
            self._finish(JobState.SUCCESS, 'Job completed successfully.')
        else:
            self._finish(JobState.FAILED, self._failure_message(rc))
        return True

    def stop(self, message):
        """Worker shutdown: kill the group and fail the job."""
        if self.finished:
            return
        if self.proc is not None and self.proc.poll() is None:
            _signal_group(self.job.pgid or self.proc.pid, signal.SIGTERM)
            deadline = time.monotonic() + min(self.grace, 5)
            while self.proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            _signal_group(self.job.pgid or self.proc.pid, signal.SIGKILL)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self._finish(JobState.FAILED, message)

    # -- progress ---------------------------------------------------------------------------

    def _read_progress(self, final=False):
        messages = []
        try:
            size = self.stdout_path.stat().st_size
        except OSError:
            size = self.stdout_offset
        if size > self.stdout_offset:
            with open(self.stdout_path, 'rb') as fh:
                fh.seek(self.stdout_offset)
                chunk = fh.read(size - self.stdout_offset)
            self.stdout_offset = size
            lines = self.lines.feed(chunk.decode('utf-8', 'replace'))
            if final:
                lines += self.lines.flush()
            for line in lines:
                task = parse_task_line(line)
                if task:
                    self.tracker.submitted(*task)
                    continue
                messages += self.merger.add('stdout', self.annotations.feed_line(line))
        elif final:
            for line in self.lines.flush():
                messages += self.merger.add('stdout', self.annotations.feed_line(line))
        if final:
            messages += self.merger.add('stdout', self.annotations.close())
        for row in self.trace.read():
            self.tracker.trace_row(row)
            status = (row.get('status') or '').upper()
            if status in ('COMPLETED', 'FAILED'):
                messages += self.merger.add('tasks', read_task_annotations(row.get('workdir', '')))
        self.add_messages(messages)
        self._save_processes()

    def _save_processes(self):
        if self.tracker.changed:
            row = self.step_rows[self.index]
            row.processes = self.tracker.counts()
            row.save(update_fields=['processes'])
            self.tracker.changed = False

    def _failure_message(self, rc) -> str:
        text = ''
        try:
            with open(self.stdout_path, 'rb') as fh:
                fh.seek(self.step_stdout_start)
                text = fh.read(2 * 1024 * 1024).decode('utf-8', 'replace')
        except OSError:
            pass
        idx = text.find('ERROR ~')
        detail = ''
        if idx >= 0:
            block = [ln for ln in text[idx:].splitlines()[:15] if ln.strip()]
            detail = '\n'.join(block)
        step = self.definition.steps[self.index].name
        msg = f'Step "{step}" failed: Nextflow exited with code {rc}.'
        return f'{msg}\n{detail}' if detail else msg

    def _finish(self, state, message):
        if self.finished:
            return
        self.finished = True
        if hasattr(self, 'tracker'):
            if state != JobState.SUCCESS:
                self.tracker.kill_unfinished()
            if self.index >= 0:
                self._save_processes()
        now = timezone.now()
        step_state = {JobState.SUCCESS: 'success', JobState.CANCELLED: 'cancelled'}.get(state, 'failed')
        for i, row in enumerate(self.step_rows):
            if i == self.index and row.status == 'running':
                row.status, row.finished_at = step_state, now
                row.save(update_fields=['status', 'finished_at'])
            elif i > self.index and row.status == 'waiting' and state != JobState.SUCCESS:
                row.status = 'cancelled'
                row.save(update_fields=['status'])
        level = {JobState.SUCCESS: 'success', JobState.CANCELLED: 'warning'}.get(state, 'error')
        self.add_messages([(level, message)])
        self._log(f'Job {state}: {message.splitlines()[0]}')
        try:
            collect_outputs(self.job, self.definition)
        except Exception:  # pragma: no cover - never let output listing break finalisation
            logger.exception('Collecting outputs of job %s failed', self.job.id)
        Job.objects.filter(pk=self.job.pk).update(
            status=state, finished_at=now, pid=None, pgid=None,
            error_message='' if state == JobState.SUCCESS else message, updated_at=now,
        )
        logger.info('Job %s finished: %s', self.job.id, state)


# ------------------------------------------------------------------------------------------
# Worker
# ------------------------------------------------------------------------------------------

def fail_job(job_id, message):
    now = timezone.now()
    JobStep.objects.filter(job_id=job_id, status='running').update(status='failed', finished_at=now)
    JobStep.objects.filter(job_id=job_id, status='waiting').update(status='cancelled')
    JobMessage.objects.create(job_id=job_id, level='error', text=message)
    Job.objects.filter(pk=job_id).update(status=JobState.FAILED, finished_at=now, pid=None,
                                         pgid=None, error_message=message, updated_at=now)


class Worker:
    def __init__(self, tick_seconds: float = 1.0, grace: float = CANCEL_GRACE_SECONDS):
        self.tick_seconds = tick_seconds
        self.grace = grace
        self.executions: dict[str, Execution] = {}
        self.started_at = timezone.now()
        self.hostname = socket.gethostname()
        self.stopping = False
        self.paused = False

    # -- one tick ---------------------------------------------------------------------------

    def startup(self):
        self.reconcile_orphans()

    def reconcile_orphans(self):
        """Running jobs that this worker does not execute are orphans (worker restarted)."""
        orphans = Job.objects.filter(status=JobState.RUNNING).exclude(
            id__in=list(self.executions.keys()))
        for job in orphans:
            killed = kill_orphan_group(job)
            logger.warning('Orphaned job %s marked failed (process group killed: %s)', job.id, killed)
            fail_job(job.id, ORPHAN_MESSAGE)

    def tick(self):
        if not connection.in_atomic_block:   # (tests run the worker inside a transaction)
            close_old_connections()
        try:
            settings = cloudgene_config.load_settings()
        except Exception:  # invalid file and nothing cached: keep going with defaults
            logger.exception('Could not load settings.yaml')
            settings = cloudgene_config.default_settings()
        self.paused = bool(settings.get('queue', {}).get('paused', False))
        max_running = max(1, int(settings.get('server', {}).get('max_running_jobs', 2) or 1))
        WorkerHeartbeat.beat(pid=os.getpid(), hostname=self.hostname, started_at=self.started_at,
                             info={'running': len(self.executions), 'paused': self.paused,
                                   'max_running_jobs': max_running})
        self.reconcile_orphans()
        self.poll_executions()
        # A waiting job flagged for cancellation (race with the web process) is cancelled here.
        for job_id in Job.objects.filter(status=JobState.WAITING, cancel_requested=True).values_list('id', flat=True):
            now = timezone.now()
            if Job.objects.filter(pk=job_id, status=JobState.WAITING).update(
                    status=JobState.CANCELLED, finished_at=now, updated_at=now):
                JobMessage.objects.create(job_id=job_id, level='warning', text='Job cancelled.')
        if not self.paused and not self.stopping:
            self.claim(max_running - len(self.executions))

    def poll_executions(self):
        if not self.executions:
            return
        cancel_ids = {str(i) for i in Job.objects.filter(
            id__in=list(self.executions.keys()), cancel_requested=True).values_list('id', flat=True)}
        for job_id, execution in list(self.executions.items()):
            try:
                done = execution.poll(cancel_requested=job_id in cancel_ids)
            except Exception as exc:
                logger.exception('Polling job %s failed', job_id)
                execution.stop(f'Internal error while running the job: {exc}')
                done = True
            if done:
                del self.executions[job_id]

    def claim(self, slots):
        if slots <= 0:
            return
        candidates = list(Job.objects.waiting_in_order().filter(
            cancel_requested=False, deleted_at__isnull=True).values_list('id', flat=True)[:slots])
        for job_id in candidates:
            now = timezone.now()
            claimed = Job.objects.filter(pk=job_id, status=JobState.WAITING, cancel_requested=False) \
                .update(status=JobState.RUNNING, started_at=now, finished_at=None, updated_at=now)
            if not claimed:
                continue
            job = Job.objects.select_related('user', 'workflow').get(pk=job_id)
            self.launch(job)

    def launch(self, job):
        key = str(job.id)
        try:
            execution = Execution(job, grace=self.grace)
            self.executions[key] = execution
            execution.start()
        except JobSetupError as exc:
            self.executions.pop(key, None)
            fail_job(job.id, str(exc))
            return
        except Exception as exc:
            logger.exception('Starting job %s failed', job.id)
            self.executions.pop(key, None)
            fail_job(job.id, f'The job could not be started: {exc}')
            return
        if execution.finished:
            self.executions.pop(key, None)

    # -- loops ------------------------------------------------------------------------------

    def run_forever(self):
        self.startup()
        while not self.stopping:
            started = time.monotonic()
            try:
                self.tick()
            except Exception:
                logger.exception('Worker tick failed')
            time.sleep(max(0.05, self.tick_seconds - (time.monotonic() - started)))
        self.shutdown()

    def is_idle(self) -> bool:
        if self.executions:
            return False
        if self.paused:
            return True
        return not Job.objects.filter(status=JobState.WAITING, deleted_at__isnull=True).exists()

    def drain(self, timeout: float = 600, tick_seconds: float | None = None):
        """Run ticks until nothing is running and nothing is claimable (``--once``)."""
        self.startup()
        deadline = time.monotonic() + timeout
        interval = self.tick_seconds if tick_seconds is None else tick_seconds
        while True:
            self.tick()
            if self.is_idle() or time.monotonic() > deadline:
                break
            time.sleep(interval)
        if self.executions:
            self.shutdown()

    def shutdown(self):
        for job_id, execution in list(self.executions.items()):
            execution.stop(SHUTDOWN_MESSAGE)
            self.executions.pop(job_id, None)

    def request_stop(self, *_):
        self.stopping = True


def acquire_lock():
    """Single-instance lock (fcntl on ``$CLOUDGENE_HOME/config/worker.lock``). Returns the open
    file (keep it referenced) or None if another worker holds it."""
    import fcntl
    path = cloudgene_config.config_dir() / 'worker.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, 'a+')
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    return fh
