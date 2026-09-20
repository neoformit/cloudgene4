from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from admin_panel.models import SystemLog

DEFAULT_DAYS = 30


class Command(BaseCommand):
    help = 'Delete SystemLog entries (Admin → Logs) older than N days.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                            help=f'Keep entries of the last N days (default {DEFAULT_DAYS})')

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=max(opts['days'], 0))
        deleted, _ = SystemLog.objects.filter(timestamp__lt=cutoff).delete()
        self.stdout.write(f'Deleted {deleted} log entries older than {opts["days"]} days.')
