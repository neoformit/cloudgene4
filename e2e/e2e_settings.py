"""Django settings used by the E2E stack.

Imports the project settings and forces the infra settings the harness controls from the
environment (SPEC §3.2). Once `cloudgene_django/settings.py` reads these env vars itself (T01) this
module is a no-op pass-through, but keeping it means the harness never touches the developer's
`db.sqlite3`, `emails/` or `jobs/` even if a setting regresses.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from cloudgene_django.settings import *  # noqa: F401,F403
from cloudgene_django import settings as _base

_home = os.environ.get('CLOUDGENE_HOME')
_db_url = os.environ.get('DATABASE_URL', '')
_outbox = os.environ.get('E2E_OUTBOX_DIR')

if not (_home and _db_url and _outbox):
    raise RuntimeError('e2e_settings requires CLOUDGENE_HOME, DATABASE_URL and E2E_OUTBOX_DIR')

if _db_url.startswith('sqlite:'):
    # sqlite:////abs/path.sqlite3  (dj-database-url style; 4 slashes = absolute path)
    _path = unquote(_db_url[len('sqlite:///'):]) if _db_url.startswith('sqlite:///') else \
        unquote(urlparse(_db_url).path)
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': _path,
                             'OPTIONS': {'timeout': 20}}}
else:  # e.g. Postgres: trust the project settings to parse DATABASE_URL (T01).
    DATABASES = _base.DATABASES

CLOUDGENE_HOME = Path(_home)

# Mail: file backend into the harness outbox (read by the `latest_email` helper).
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = _outbox

# Legacy (pre-T01) path settings — point them into the temp home so nothing leaks into the repo.
if hasattr(_base, 'CLOUDGENE_CONFIG_FILE'):
    CLOUDGENE_CONFIG_FILE = CLOUDGENE_HOME / 'config' / 'settings.yaml'
if hasattr(_base, 'JOBS_DIR'):
    JOBS_DIR = CLOUDGENE_HOME / 'jobs'
if hasattr(_base, 'WORKFLOWS_DIR'):
    WORKFLOWS_DIR = CLOUDGENE_HOME / 'apps'
if hasattr(_base, 'CELERY_BROKER_URL'):
    CELERY_BROKER_URL = 'sqla+sqlite:///' + str(CLOUDGENE_HOME / 'celery.db')
if hasattr(_base, 'CHANNEL_LAYERS'):
    # No Redis on test hosts; channels is being removed by T01 anyway.
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

if not hasattr(_base, 'LOGGING'):
    # Django's default config only prints request errors when DEBUG=True; the harness runs with
    # DEBUG=False (production-like) and needs 5xx tracebacks in server.log.
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {'console': {'class': 'logging.StreamHandler'}},
        'loggers': {'django.request': {'handlers': ['console'], 'level': 'WARNING',
                                       'propagate': False}},
        'root': {'handlers': ['console'], 'level': 'INFO'},
    }
