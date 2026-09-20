from django.conf import settings
from django.db import models


class SystemLog(models.Model):
    """One application log record, written by ``admin_panel.logging.DatabaseLogHandler``.

    Every record of a ``cloudgene.*`` logger at INFO or above lands here (see SPEC §3.8);
    ``component`` is the first segment after ``cloudgene.`` (``cloudgene.jobs.worker`` →
    ``jobs``). Shown in Admin → Logs; trimmed by ``manage.py cleanup_logs``.
    """

    LOG_LEVELS = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=20, choices=LOG_LEVELS)
    message = models.TextField()
    component = models.CharField(max_length=100, blank=True)
    logger = models.CharField(max_length=200, blank=True, default='')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'system_logs'
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['timestamp', 'level']),
            models.Index(fields=['component', 'level']),
        ]

    def __str__(self):
        return f'{self.timestamp} [{self.level.upper()}] {self.message[:50]}'
