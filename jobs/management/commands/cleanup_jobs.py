"""
Retention: ``python manage.py cleanup_jobs [--days N] [--dry-run]``.

Removes the workspaces of finished jobs older than ``server.job_retention_days`` (0 = keep
forever) and of deleted jobs; the Job rows stay (``purged_at`` set, outputs removed).
Also removes orphan workspace directories under ``jobs/`` that have no Job row (e.g. after a user
was deleted while the web process could not remove them).
Schedule it daily (cron/systemd timer).
"""
import re
import shutil
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core import config as cloudgene_config
from jobs.models import Job, JobOutput, JobState

ORPHAN_MIN_AGE_SECONDS = 3600
JOB_DIR_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


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
        orphans = 0
        jobs_root = cloudgene_config.jobs_dir()
        if jobs_root.is_dir():
            known = {str(i) for i in Job.objects.values_list('id', flat=True)}
            for entry in jobs_root.iterdir():
                if not entry.is_dir() or entry.name in known or not JOB_DIR_RE.match(entry.name):
                    continue
                # a submission in progress creates its workspace before the Job row commits
                if time.time() - entry.stat().st_mtime < ORPHAN_MIN_AGE_SECONDS:
                    continue
                orphans += 1
                if opts['dry_run']:
                    self.stdout.write(f'would remove orphan {entry}')
                else:
                    shutil.rmtree(entry, ignore_errors=True)
        verb = 'Would remove' if opts['dry_run'] else 'Removed'
        self.stdout.write(f'{verb} {count} job workspace(s) (retention: '
                          f'{days if days > 0 else "keep"} days) and {orphans} orphan workspace(s).')
