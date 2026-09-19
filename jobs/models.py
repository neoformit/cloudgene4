"""
Job runtime state (plans/SPEC.md §3.3).

States: ``waiting`` → ``running`` → ``success`` | ``failed`` | ``cancelled``. The worker
(``manage.py run_worker``) owns every transition out of ``waiting``/``running`` except the
immediate cancellation of a waiting job by the web process. Workspaces live in
``core.config.job_dir(job.id)`` and are never derived from user-provided text (K3).
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core import config as cloudgene_config


class JobState:
    WAITING = 'waiting'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

    CHOICES = [
        (WAITING, 'Waiting'),
        (RUNNING, 'Running'),
        (SUCCESS, 'Success'),
        (FAILED, 'Failed'),
        (CANCELLED, 'Cancelled'),
    ]
    ACTIVE = (WAITING, RUNNING)
    FINISHED = (SUCCESS, FAILED, CANCELLED)
    ALL = (WAITING, RUNNING, SUCCESS, FAILED, CANCELLED)


class JobQuerySet(models.QuerySet):
    def visible(self):
        """Jobs not deleted by their owner."""
        return self.filter(deleted_at__isnull=True)

    def waiting_in_order(self):
        return self.filter(status=JobState.WAITING).order_by('submitted_at', 'id')


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, blank=True, help_text='Free text; never used in paths (K3)')
    workflow = models.ForeignKey('workflows.Workflow', on_delete=models.SET_NULL, null=True,
                                 blank=True, related_name='jobs')
    # Snapshot of the workflow at submission (survives uninstall / reload).
    app_id = models.CharField(max_length=255, blank=True, default='')
    app_name = models.CharField(max_length=255, blank=True, default='')
    app_version = models.CharField(max_length=50, blank=True, default='')
    workflow_yaml = models.TextField(blank=True, default='')
    app_dir = models.CharField(max_length=1024, blank=True, default='')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jobs')

    status = models.CharField(max_length=20, choices=JobState.CHOICES, default=JobState.WAITING)
    cancel_requested = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Resolved input values (typed; file inputs as paths relative to the job dir).
    parameters = models.JSONField(default=dict, blank=True)
    # Uploaded files per input id: [{"name": display name, "path": relative path, "size": bytes}]
    uploads = models.JSONField(default=dict, blank=True)

    # Executor bookkeeping (worker only).
    pid = models.IntegerField(null=True, blank=True)
    pgid = models.IntegerField(null=True, blank=True)
    current_step = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')

    deleted_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True, help_text='Workspace removed')

    objects = JobQuerySet.as_manager()

    class Meta:
        db_table = 'jobs'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status', 'submitted_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f'{self.name or self.id} ({self.status})'

    @property
    def state(self):
        return self.status

    @property
    def is_active(self):
        return self.status in JobState.ACTIVE

    @property
    def is_finished(self):
        return self.status in JobState.FINISHED

    @property
    def workspace(self):
        return cloudgene_config.job_dir(self.id)

    def duration_seconds(self):
        if not self.started_at:
            return None
        end = self.finished_at or timezone.now()
        return max(0.0, round((end - self.started_at).total_seconds(), 1))

    def queue_position(self):
        """1-based position among waiting jobs (None unless waiting)."""
        if self.status != JobState.WAITING:
            return None
        earlier = Job.objects.filter(status=JobState.WAITING).filter(
            models.Q(submitted_at__lt=self.submitted_at)
            | models.Q(submitted_at=self.submitted_at, id__lt=self.id)
        ).count()
        return earlier + 1

    def expires_at(self):
        days = cloudgene_config.get('server.job_retention_days', 7) or 0
        if not self.finished_at or days <= 0:
            return None
        return self.finished_at + timedelta(days=days)

    def can_cancel(self):
        return self.status in JobState.ACTIVE and not self.cancel_requested

    def can_delete(self):
        return self.status in JobState.FINISHED

    def can_restart(self):
        return self.status in (JobState.FAILED, JobState.CANCELLED) and self.purged_at is None


class JobStep(models.Model):
    """One workflow step of a job; ``processes`` holds per-Nextflow-process task counts:
    ``[{"name", "label", "submitted", "running", "completed", "failed", "total"}]``."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='steps')
    order = models.IntegerField(default=0)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=JobState.CHOICES, default='waiting')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    processes = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'job_steps'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.job_id} #{self.order} {self.name}'


class JobMessage(models.Model):
    LEVELS = [('debug', 'Debug'), ('info', 'Info'), ('success', 'Success'),
              ('warning', 'Warning'), ('error', 'Error')]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='messages')
    step = models.ForeignKey(JobStep, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='messages')
    level = models.CharField(max_length=10, choices=LEVELS, default='info')
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'job_messages'
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.job_id} {self.level}: {self.text[:50]}'


class JobOutput(models.Model):
    """A downloadable file of a job output (``output_id`` from the YAML, ``path`` relative to
    ``<job>/output/``)."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='outputs')
    output_id = models.CharField(max_length=255)
    label = models.CharField(max_length=255, blank=True, default='')
    path = models.CharField(max_length=1024)
    size = models.BigIntegerField(default=0)
    download_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'job_outputs'
        ordering = ['output_id', 'path']

    @property
    def name(self):
        return self.path.rsplit('/', 1)[-1]

    def __str__(self):
        return f'{self.job_id} {self.path}'
