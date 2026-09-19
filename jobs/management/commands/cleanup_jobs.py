"""
Retention: ``python manage.py cleanup_jobs [--days N] [--dry-run]``.

Removes the workspaces of finished jobs older than ``server.job_retention_days`` (0 = keep
forever) and of deleted jobs; the Job rows stay (``purged_at`` set, outputs removed).
Schedule it daily (cron/systemd timer).
"""
import shutil
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core import config as cloudgene_config
from jobs.models import Job, JobOutput, JobState


class Command(BaseCommand):
    help = 'Remove job workspaces past the retention period'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None,
                            help='Override server.job_retention_days')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        days = opts['days']
        if days is None:
            days = int(cloudgene_config.get('server.job_retention_days', 7) or 0)
        now = timezone.now()
        cond = Q(deleted_at__isnull=False)
        if days > 0:
            cond |= Q(status__in=JobState.FINISHED, finished_at__lt=now - timedelta(days=days))
        jobs = Job.objects.filter(cond, status__in=JobState.FINISHED)
        count = 0
        for job in jobs:
            workspace = cloudgene_config.job_dir(job.id)
            if job.purged_at and not workspace.exists():
                continue
            count += 1
            if opts['dry_run']:
                self.stdout.write(f'would remove {workspace}')
                continue
            shutil.rmtree(workspace, ignore_errors=True)
            JobOutput.objects.filter(job=job).delete()
            Job.objects.filter(pk=job.pk).update(purged_at=job.purged_at or now)
        verb = 'Would remove' if opts['dry_run'] else 'Removed'
        self.stdout.write(f'{verb} {count} job workspace(s) (retention: '
                          f'{days if days > 0 else "keep"} days).')
