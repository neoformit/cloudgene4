"""
Job actions shared by the user and admin endpoints (web process side), plus a queue summary
helper for the admin dashboard (T05).
"""
from __future__ import annotations

import shutil

from django.db import transaction
from django.utils import timezone

from core import config as cloudgene_config

from . import workflow_bridge
from .models import Job, JobMessage, JobOutput, JobState, JobStep


class JobActionError(Exception):
    def __init__(self, message, code='invalid_state', status=409):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


def cancel_job(job: Job, by_admin=False) -> Job:
    """Waiting → cancelled immediately; running → ``cancel_requested`` (the worker kills the
    process group and sets ``cancelled``)."""
    if job.status in JobState.FINISHED:
        raise JobActionError(f'The job is already {job.status}.')
    now = timezone.now()
    who = ' by an administrator' if by_admin else ''
    if job.status == JobState.WAITING:
        updated = Job.objects.filter(pk=job.pk, status=JobState.WAITING).update(
            status=JobState.CANCELLED, cancel_requested=True, finished_at=now, updated_at=now)
        if updated:
            JobMessage.objects.create(job=job, level='warning', text=f'Job cancelled{who}.')
            job.refresh_from_db()
            return job
    # running (or claimed by the worker in the meantime)
    if not job.cancel_requested:
        Job.objects.filter(pk=job.pk, status__in=JobState.ACTIVE).update(
            cancel_requested=True, updated_at=now)
        JobMessage.objects.create(job=job, level='warning', text=f'Cancellation requested{who}.')
    job.refresh_from_db()
    return job


def delete_job(job: Job) -> None:
    """Soft-delete a finished job and remove its workspace."""
    if job.status not in JobState.FINISHED:
        raise JobActionError('Only finished jobs can be deleted. Cancel the job first.')
    now = timezone.now()
    Job.objects.filter(pk=job.pk).update(deleted_at=now, purged_at=job.purged_at or now, updated_at=now)
    JobOutput.objects.filter(job=job).delete()
    shutil.rmtree(cloudgene_config.job_dir(job.id), ignore_errors=True)


def restart_job(job: Job) -> Job:
    """Admin: re-queue a failed/cancelled job with the same inputs (outputs/logs are reset).
    The current definition of the workflow is used."""
    if job.status not in (JobState.FAILED, JobState.CANCELLED):
        raise JobActionError(f'Only failed or cancelled jobs can be restarted (job is {job.status}).')
    if job.purged_at or job.deleted_at:
        raise JobActionError('The job workspace has been removed; it cannot be restarted.',
                             code='workspace_removed')
    workflow = job.workflow
    if workflow is None or not workflow_bridge.is_enabled(workflow):
        raise JobActionError('The workflow of this job is no longer installed or is disabled.',
                             code='workflow_unavailable')
    workspace = cloudgene_config.job_dir(job.id)
    for sub in ('output', 'logs', 'work', '.nextflow'):
        shutil.rmtree(workspace / sub, ignore_errors=True)
    for f in list(workspace.glob('*params.json')) + [workspace / 'cloudgene.config']:
        f.unlink(missing_ok=True)
    (workspace / 'output').mkdir(parents=True, exist_ok=True)
    now = timezone.now()
    with transaction.atomic():
        JobStep.objects.filter(job=job).delete()
        JobMessage.objects.filter(job=job).delete()
        JobOutput.objects.filter(job=job).delete()
        Job.objects.filter(pk=job.pk).update(
            status=JobState.WAITING, cancel_requested=False, submitted_at=now, started_at=None,
            finished_at=None, pid=None, pgid=None, current_step=0, error_message='',
            workflow_yaml=workflow.yaml_config, app_dir=str(workflow_bridge.app_dir(workflow)),
            updated_at=now,
        )
        JobMessage.objects.create(job=job, level='info', text='Job restarted by an administrator.')
    job.refresh_from_db()
    return job


def queue_summary() -> dict:
    """``{paused, maintenance, running, waiting, max_running, max_queue}`` for dashboards."""
    return {
        'paused': bool(cloudgene_config.get('queue.paused', False)),
        'maintenance': bool(cloudgene_config.get('server.maintenance', False)),
        'running': Job.objects.filter(status=JobState.RUNNING).count(),
        'waiting': Job.objects.filter(status=JobState.WAITING).count(),
        'max_running': int(cloudgene_config.get('server.max_running_jobs', 2) or 0),
        'max_queue': int(cloudgene_config.get('server.max_queue_size', 50) or 0),
    }
