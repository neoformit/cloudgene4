"""
Database log handler for the admin "Logs" page (SPEC §3.8).

Configured in ``settings.LOGGING`` on the ``cloudgene`` logger at INFO, so every module
that logs through ``logging.getLogger('cloudgene.<area>')`` shows up in Admin → Logs::

    log = logging.getLogger('cloudgene.jobs')
    log.info('Job %s finished: %s', job.id, state, extra={'user': job.user, 'data': {...}})

``extra`` keys understood: ``user`` (a User instance or id), ``data`` (JSON-serialisable
dict stored in ``metadata``). Never raises: logging must not break the caller (e.g. when
the table does not exist yet during ``migrate``, or the DB is locked).
"""
import json
import logging
import threading
import traceback

_state = threading.local()


def component_of(logger_name: str) -> str:
    parts = logger_name.split('.')
    if parts[0] == 'cloudgene' and len(parts) > 1:
        return parts[1]
    return parts[0]


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


class DatabaseLogHandler(logging.Handler):
    def emit(self, record):
        if getattr(_state, 'busy', False):  # a DB error logged while writing a log record
            return
        _state.busy = True
        try:
            from django.apps import apps
            if not apps.ready:
                return
            from .models import SystemLog

            metadata = {}
            data = getattr(record, 'data', None)
            if isinstance(data, dict):
                metadata.update({str(k): _jsonable(v) for k, v in data.items()})
            if record.exc_info:
                metadata['traceback'] = ''.join(traceback.format_exception(*record.exc_info))
            user = getattr(record, 'user', None)
            user_id = getattr(user, 'pk', user) if user is not None else None
            if not isinstance(user_id, int):
                user_id = None
            if user_id is not None:
                from django.contrib.auth import get_user_model
                if not get_user_model().objects.filter(pk=user_id).exists():
                    user_id = None
            SystemLog.objects.create(
                level=record.levelname.lower()[:20],
                message=record.getMessage(),
                component=component_of(record.name)[:100],
                logger=record.name[:200],
                user_id=user_id,
                metadata=metadata,
            )
        except Exception:  # never propagate logging failures
            pass
        finally:
            _state.busy = False
