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
import shutil
import signal
import socket
import subprocess
import time
import types
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist, ObjectNotUpdated
from django.db import IntegrityError, OperationalError, close_old_connections, connection
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
#: Command steps: at most this much of a stream is shown as a job message / copied to the job log;
#: a step whose captured output grows beyond COMMAND_OUTPUT_LIMIT bytes per stream is stopped.
COMMAND_MESSAGE_BYTES = 64 * 1024
COMMAND_LOG_BYTES = 1024 * 1024
COMMAND_OUTPUT_LIMIT = 256 * 1024 * 1024
FAILURE_TAIL_BYTES = 4096
ORPHAN_MESSAGE = 'The worker was restarted while this job was running; the job was stopped.'
SHUTDOWN_MESSAGE = 'The worker was shut down while this job was running; the job was stopped.'


# ------------------------------------------------------------------------------------------
# A-03 (worker half): tick phases must not take each other down, and a transient SQLite write
# lock (the web process/another connection holding a write transaction) should be retried
# briefly rather than aborting a whole phase.
# ------------------------------------------------------------------------------------------

LOCK_RETRY_ATTEMPTS = 3
LOCK_RETRY_BACKOFF = 0.05   # seconds; doubles each attempt (0.05, 0.1, 0.2, ...)
_LOCK_MESSAGES = ('database is locked', 'database table is locked')


def is_locked_error(exc: BaseException) -> bool:
    """True for a SQLite ``OperationalError`` caused by write contention (not other
    OperationalErrors, e.g. a genuinely broken schema/query, which must not be retried)."""
    return isinstance(exc, OperationalError) and any(m in str(exc).lower() for m in _LOCK_MESSAGES)


def retry_on_locked(fn, *args, attempts: int = LOCK_RETRY_ATTEMPTS,
                    backoff: float = LOCK_RETRY_BACKOFF, **kwargs):
    """Call ``fn(*args, **kwargs)``, retrying up to ``attempts`` times (short backoff) if it
    raises a "database is locked"/"database table is locked" ``OperationalError``. Any other
    exception (including a non-lock ``OperationalError``) propagates immediately. Re-raises the
    last lock error once the attempts are exhausted."""
    delay = backoff
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except OperationalError as exc:
            if not is_locked_error(exc) or attempt == attempts:
                raise
            logger.warning('%s: database is locked (attempt %d/%d); retrying in %.2fs',
                           getattr(fn, '__name__', fn), attempt, attempts, delay)
            time.sleep(delay)
            delay *= 2


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


def _tail_text(path, limit) -> str:
    """Last ``limit`` bytes of a text file (with an omission marker), '' if unreadable."""
    try:
        size = path.stat().st_size
        with open(path, 'rb') as fh:
            if size > limit:
                fh.seek(size - limit)
                data = fh.read().split(b'\n', 1)[-1]
                return f'[... {size - limit} bytes omitted ...]\n' + data.decode('utf-8', 'replace')
            return fh.read().decode('utf-8', 'replace')
    except OSError:
        return ''


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
        self.kind = 'nextflow'
        self.limit_exceeded = False
        self.cmd = None
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
        row.save(update_fields=['status', 'started_at'])  # raises ObjectNotUpdated if the row is gone
        if not Job.objects.filter(pk=self.job.pk).update(current_step=index):
            # C-03: the row vanished (e.g. the owning user was deleted) between being claimed
            # and this step starting. Nothing has been spawned yet; the caller (poll_executions
            # or launch()) turns this into a clean vanish().
            raise Job.DoesNotExist(f'Job {self.job.pk} vanished before step {index} could start')
        if not step.supported:
            self._finish(JobState.FAILED, step.error or f'Step "{step.name}" is not supported.')
            return

        self.kind = step.type
        self.limit_exceeded = False
        self.cmd = None
        if step.type == 'command':
            self._start_command(index, step)
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
        # C-03: `prepare_step` above can take a real amount of time for a real workflow
        # (uploads, folder inputs, per-app work dirs). A cheap existence check right before we
        # actually spawn Nextflow catches a row deleted during prep, so we never start a
        # process for a job nothing will track any more.
        if not Job.objects.filter(pk=self.job.pk).exists():
            raise Job.DoesNotExist(f'Job {self.job.pk} vanished before Nextflow could start')
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
        # Keep the in-memory pgid even if the DB write below fails to land, so a vanish() right
        # after this still knows what to kill.
        self.job.pid, self.job.pgid = self.proc.pid, pgid
        if not Job.objects.filter(pk=self.job.pk).update(pid=self.proc.pid, pgid=pgid):
            # C-03: the row vanished in the instant between the re-check above and Nextflow
            # actually starting. self.proc is already set, so the caller's vanish() kills it.
            raise Job.DoesNotExist(f'Job {self.job.pk} vanished right after Nextflow started')

    def _start_command(self, index, step):
        """``type: command``: one subprocess (own process group), no shell unless ``bash: true``.
        stdout/stderr go to per-step files; the flagged streams are surfaced (see _read_command)."""
        try:
            prepared = runner.prepare_command(self.job, self.definition, index, app_dir=self.app_dir)
        except ValueError as exc:
            self._finish(JobState.FAILED, f'Step "{step.name}" failed: {exc}')
            return
        total = len(self.definition.steps)
        self._log(f'Step {index + 1}/{total}: {step.name} (command)')
        self._log('$ ' + prepared.display)
        self.tracker = ProcessTracker({})
        self.cmd = types.SimpleNamespace(
            prepared=prepared, offsets={'stdout': 0, 'stderr': 0}, logged={'stdout': 0, 'stderr': 0},
            headers=set())
        for path in (prepared.stdout_path, prepared.stderr_path):
            path.write_bytes(b'')
        if not Job.objects.filter(pk=self.job.pk).exists():
            raise Job.DoesNotExist(f'Job {self.job.pk} vanished before the command could start')
        out, err = open(prepared.stdout_path, 'ab'), open(prepared.stderr_path, 'ab')
        try:
            self.proc = subprocess.Popen(
                prepared.argv, cwd=prepared.cwd, env=prepared.env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True,
            )
        except OSError as exc:
            self._finish(JobState.FAILED,
                         f'Step "{step.name}" failed: could not start command '
                         f'"{prepared.argv[0]}": {exc.strerror or exc}')
            return
        finally:
            out.close()
            err.close()
        pgid = self.proc.pid
        try:
            pgid = os.getpgid(self.proc.pid)
        except OSError:
            pass
        self.job.pid, self.job.pgid = self.proc.pid, pgid
        if not Job.objects.filter(pk=self.job.pk).update(pid=self.proc.pid, pgid=pgid):
            raise Job.DoesNotExist(f'Job {self.job.pk} vanished right after the command started')

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
        if self.limit_exceeded:
            self._finish(JobState.FAILED, self._failure_message(rc))
        elif self.term_sent_at is not None:
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

    def vanish(self):
        """C-03: the Job row (and its JobStep/JobMessage rows, ``on_delete=CASCADE``) was
        deleted while this execution was running — e.g. the owning user was deleted. There is
        no row left to update, so this is a designed shutdown path, not an error: kill the
        process group and remove whatever the dying execution has written since, then stop."""
        if self.finished:
            return
        self.finished = True
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
        shutil.rmtree(self.job_dir, ignore_errors=True)
        logger.info('Job %s: row was deleted while running; execution stopped and workspace removed.',
                   self.job.id)

    # -- progress ---------------------------------------------------------------------------

    def _read_progress(self, final=False):
        if self.cmd is not None:
            self._read_command(final)
            return
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

    # -- command steps ----------------------------------------------------------------------

    def _stream_path(self, name):
        return getattr(self.cmd.prepared, f'{name}_path')

    def _read_command(self, final=False):
        """Copy new output of the flagged streams into the job log (capped) and, when the step
        is over, add the captured text as job messages. Unflagged streams stay in their step
        file only. A stream growing beyond COMMAND_OUTPUT_LIMIT stops the step."""
        step = self.definition.steps[self.index]
        for name in ('stdout', 'stderr'):
            path = self._stream_path(name)
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > COMMAND_OUTPUT_LIMIT and not self.limit_exceeded and self.term_sent_at is None:
                self.limit_exceeded = True
                self._log(f'The {name} of the command exceeded {COMMAND_OUTPUT_LIMIT} bytes; stopping it')
                self.request_cancel()
            offset = self.cmd.offsets[name]
            if getattr(step, name) and size > offset:
                room = COMMAND_LOG_BYTES - self.cmd.logged[name]
                if room > 0:
                    with open(path, 'rb') as fh:
                        fh.seek(offset)
                        chunk = fh.read(min(size - offset, room))
                    self._append_job_log(name, step, chunk)
                    self.cmd.logged[name] += len(chunk)
                    if self.cmd.logged[name] >= COMMAND_LOG_BYTES:
                        self._log(f'[{name} of step "{step.name}" truncated in this log after '
                                  f'{COMMAND_LOG_BYTES} bytes; the full text is in {path.name}]')
            self.cmd.offsets[name] = size
        if final:
            messages = []
            for name, level in (('stdout', 'info'), ('stderr', 'warning')):
                if getattr(step, name):
                    text = _tail_text(self._stream_path(name), COMMAND_MESSAGE_BYTES).strip()
                    if text:
                        messages.append((level, text))
            self.add_messages(messages)

    def _append_job_log(self, name, step, chunk):
        path = self.job_dir / 'logs' / 'stdout.txt'
        with open(path, 'ab') as fh:
            if name not in self.cmd.headers:
                self.cmd.headers.add(name)
                fh.write(f'[cloudgene] --- {name} of step "{step.name}" ---\n'.encode())
            fh.write(chunk)
            if not chunk.endswith(b'\n'):
                fh.write(b'\n')

    def _command_failure_message(self, rc) -> str:
        step = self.definition.steps[self.index]
        if self.limit_exceeded:
            return (f'Step "{step.name}" failed: its output exceeded '
                    f'{COMMAND_OUTPUT_LIMIT // (1024 * 1024)} MiB and the command was stopped.')
        if rc < 0:
            try:
                what = f'killed by signal {signal.Signals(-rc).name}'
            except ValueError:
                what = f'killed by signal {-rc}'
        else:
            what = f'exit code {rc}'
        msg = f'Step "{step.name}" failed ({what}).'
        # Only streams the workflow author opted into (`stdout:`/`stderr:` true) are ever shown;
        # the others stay in the step's log file on disk.
        for name in ('stdout', 'stderr'):
            if getattr(step, name):
                detail = _tail_text(self._stream_path(name), FAILURE_TAIL_BYTES).strip()
                if detail:
                    msg += f'\n{name} (last lines):\n{detail}'
        return msg

    def _failure_message(self, rc) -> str:
        if self.cmd is not None:
            return self._command_failure_message(rc)
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
        if detail:
            msg = f'{msg}\n{detail}'
        # Cloudgene 3: `stdout: true` adds the raw output to the failure message.
        cfg = self.definition.steps[self.index]
        if (cfg.stdout or cfg.stderr) and text.strip():
            tail = text.strip()
            if len(tail) > FAILURE_TAIL_BYTES:
                tail = '[...]\n' + tail[-FAILURE_TAIL_BYTES:]
            msg = f'{msg}\nOutput (last lines):\n{tail}'
        return msg

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
            retry_on_locked(fail_job, job.id, ORPHAN_MESSAGE)

    def _beat(self, max_running):
        retry_on_locked(WorkerHeartbeat.beat, pid=os.getpid(), hostname=self.hostname,
                        started_at=self.started_at,
                        info={'running': len(self.executions), 'paused': self.paused,
                              'max_running_jobs': max_running})

    def _cancel_waiting_jobs(self):
        """A waiting job flagged for cancellation (race with the web process) is cancelled here."""
        for job_id in Job.objects.filter(status=JobState.WAITING, cancel_requested=True).values_list('id', flat=True):
            now = timezone.now()
            if retry_on_locked(Job.objects.filter(pk=job_id, status=JobState.WAITING).update,
                               status=JobState.CANCELLED, finished_at=now, updated_at=now):
                retry_on_locked(JobMessage.objects.create, job_id=job_id, level='warning',
                               text='Job cancelled.')

    # -- A-03 (worker half): each phase below runs independently of the others, so a locked
    # database (or any other unexpected error) in one phase never abandons the rest of the
    # tick — a lock storm on the heartbeat must not also stop poll/claim from running.

    def _run_phase(self, name, fn):
        try:
            fn()
        except OperationalError as exc:
            if is_locked_error(exc):
                # Expected under SQLite write contention and already retried at the call site;
                # a single WARNING (no traceback) is enough — the next tick tries again.
                logger.warning('Worker tick: phase "%s" failed (database is locked): %s', name, exc)
            else:
                logger.exception('Worker tick: phase "%s" failed', name)
        except Exception:
            logger.exception('Worker tick: phase "%s" failed', name)

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

        self._run_phase('heartbeat', lambda: self._beat(max_running))
        self._run_phase('reconcile', self.reconcile_orphans)
        self._run_phase('poll', self.poll_executions)
        self._run_phase('cancel_waiting', self._cancel_waiting_jobs)
        if not self.paused and not self.stopping:
            self._run_phase('claim', lambda: self.claim(max_running - len(self.executions)))

    def poll_executions(self):
        if not self.executions:
            return
        # C-03: a claimed job's row can vanish (e.g. the owning user was deleted) without any
        # of poll()'s own writes ever running — a quiet execution (no new trace activity) may
        # go a whole tick without writing anything at all. So check for existence up front,
        # once per tick, rather than relying only on an incidental write raising; the
        # exception handler below stays as a safety net for the row vanishing mid-tick.
        existing = {str(i) for i in Job.objects.filter(
            id__in=list(self.executions.keys())).values_list('id', flat=True)}
        cancel_ids = {str(i) for i in Job.objects.filter(
            id__in=list(existing), cancel_requested=True).values_list('id', flat=True)}
        for job_id, execution in list(self.executions.items()):
            if job_id not in existing:
                logger.info('Job %s vanished while running (its row was deleted); stopping.', job_id)
                execution.vanish()
                del self.executions[job_id]
                continue
            try:
                done = execution.poll(cancel_requested=job_id in cancel_ids)
            except (ObjectDoesNotExist, ObjectNotUpdated):
                # The Job row (or one of its steps) vanished mid-tick — most likely the owning
                # user was deleted while the job was running. Designed path, not a bug: no
                # traceback, just an informational log line.
                logger.info('Job %s vanished while running (its row was deleted); stopping.', job_id)
                execution.vanish()
                done = True
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
            claimed = retry_on_locked(
                Job.objects.filter(pk=job_id, status=JobState.WAITING, cancel_requested=False).update,
                status=JobState.RUNNING, started_at=now, finished_at=None, updated_at=now)
            if not claimed:
                continue
            try:
                job = Job.objects.select_related('user', 'workflow').get(pk=job_id)
            except Job.DoesNotExist:
                # C-03: the row vanished in the instant between the claim update above and
                # fetching it here. Nothing was ever launched for it; just clean up.
                logger.info('Job %s vanished right after being claimed; removing its workspace.',
                           job_id)
                shutil.rmtree(cloudgene_config.job_dir(job_id), ignore_errors=True)
                continue
            self.launch(job)

    def launch(self, job):
        key = str(job.id)
        execution = None
        try:
            execution = Execution(job, grace=self.grace)
            self.executions[key] = execution
            execution.start()
        except JobSetupError as exc:
            self.executions.pop(key, None)
            fail_job(job.id, str(exc))
            return
        except (ObjectDoesNotExist, ObjectNotUpdated, IntegrityError):
            # C-03: the row (or one of its cascaded JobStep rows) vanished while we were
            # setting up or starting the execution — most likely the owning user was deleted
            # in the same instant. Designed path, not a bug: stop/kill whatever was started
            # (if anything) and remove the workspace ourselves, since nothing else will.
            self.executions.pop(key, None)
            if execution is not None:
                execution.vanish()
            else:
                logger.info('Job %s vanished before it could be launched; removing its '
                           'workspace.', job.id)
                shutil.rmtree(cloudgene_config.job_dir(job.id), ignore_errors=True)
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
