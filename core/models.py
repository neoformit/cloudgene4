from datetime import timedelta

from django.db import models
from django.utils import timezone


class WorkerHeartbeat(models.Model):
    """Liveness record of the job worker (``manage.py run_worker``, owned by T03).

    One row per worker name (normally just ``"default"``). The worker calls
    ``WorkerHeartbeat.beat()`` every tick; ``/api/health`` reports it via ``status()``.
    """

    STALE_AFTER = timedelta(seconds=30)

    name = models.CharField(max_length=64, primary_key=True, default='default')
    hostname = models.CharField(max_length=255, blank=True, default='')
    pid = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField()
    info = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'worker_heartbeat'

    def __str__(self):
        return f'{self.name} pid={self.pid} last_seen={self.last_seen:%Y-%m-%d %H:%M:%S}'

    @classmethod
    def beat(cls, name='default', *, hostname='', pid=None, started_at=None, info=None):
        """Upsert the heartbeat row with ``last_seen=now``."""
        defaults = {'last_seen': timezone.now(), 'hostname': hostname, 'pid': pid}
        if started_at is not None:
            defaults['started_at'] = started_at
        if info is not None:
            defaults['info'] = info
        obj, _ = cls.objects.update_or_create(name=name, defaults=defaults)
        return obj

    @property
    def is_alive(self):
        return timezone.now() - self.last_seen <= self.STALE_AFTER

    @classmethod
    def status(cls, name='default'):
        obj = cls.objects.filter(name=name).first()
        if obj is None:
            return {'ok': False, 'last_seen': None, 'age_seconds': None, 'pid': None}
        age = (timezone.now() - obj.last_seen).total_seconds()
        return {
            'ok': obj.is_alive,
            'last_seen': obj.last_seen,
            'age_seconds': round(age, 1),
            'pid': obj.pid,
        }
