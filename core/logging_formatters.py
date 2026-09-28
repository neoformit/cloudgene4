"""Opt-in JSON console log formatter (``LOG_FORMAT=json``, TASKS T09a bullet 5).

For journald / log shippers that parse structured lines. The default remains the
human-readable ``standard`` formatter in ``cloudgene_django.settings.LOGGING``.
"""
import json
import logging


class JsonFormatter(logging.Formatter):
    """Renders one JSON object per line: timestamp, level, logger, message, pid, plus any
    ``extra={'data': {...}}`` / ``extra={'user': ...}`` attached by callers (SPEC §3.8)."""

    #: standard LogRecord attributes, so anything else on the record is caller-supplied ``extra``.
    _RESERVED = frozenset(vars(logging.LogRecord('', 0, '', 0, '', (), None)).keys()) | {
        'message', 'asctime',
    }

    def format(self, record):
        payload = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'pid': record.process,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)
        if record.stack_info:
            payload['stack_info'] = self.formatStack(record.stack_info)
        for key, value in vars(record).items():
            if key in self._RESERVED or key.startswith('_'):
                continue
            if key == 'user':
                value = getattr(value, 'username', value) if value is not None else None
            try:
                json.dumps(value)
            except TypeError:
                value = str(value)
            payload[key] = value
        return json.dumps(payload, default=str)
