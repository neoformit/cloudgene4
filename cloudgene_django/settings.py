"""
Django settings for the Cloudgene port.

Only *infrastructure* settings live here and they all come from the environment
(optionally via a ``.env`` file in the repo root). Application settings (server
name, queue limits, mail, Nextflow, navbar, installed workflows, ...) live in
``$CLOUDGENE_HOME/config/settings.yaml`` and are read through ``core.config``.

Environment variables:
  DEBUG                  "1"/"true" enables debug mode (default: off)
  DJANGO_SECRET_KEY      secret key; if unset, one is generated once and stored in
                         $CLOUDGENE_HOME/config/secret_key (shared by web + worker)
  ALLOWED_HOSTS          comma-separated (default: localhost,127.0.0.1,[::1])
  CSRF_TRUSTED_ORIGINS   comma-separated origins, e.g. https://cloudgene.example.org
  DATABASE_URL           e.g. postgres://user:pw@host/db (default: sqlite db.sqlite3)
  CLOUDGENE_HOME         data/config directory (default: <repo>/home)
  LOG_LEVEL              root log level (default: INFO)
  DJANGO_SECURE_COOKIES  "1" → Secure session/CSRF cookies (set behind HTTPS)
  DJANGO_SECURE_SSL_REDIRECT, DJANGO_HSTS_SECONDS, DJANGO_BEHIND_TLS_PROXY
"""

import os
import secrets
import warnings
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value == '':
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


DEBUG = env_bool('DEBUG', False)

# Cloudgene data/config directory (see core.config and plans/SPEC.md §3.2)
CLOUDGENE_HOME = Path(os.environ.get('CLOUDGENE_HOME') or BASE_DIR / 'home').resolve()


def _load_secret_key():
    key = os.environ.get('DJANGO_SECRET_KEY')
    if key:
        return key
    key_file = CLOUDGENE_HOME / 'config' / 'secret_key'
    try:
        existing = key_file.read_text().strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    key = secrets.token_urlsafe(50)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another process (web/worker) won the race
        return key_file.read_text().strip()
    with os.fdopen(fd, 'w') as fh:
        fh.write(key)
    return key


SECRET_KEY = _load_secret_key()

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1', '[::1]'])

CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    # Vite dev server proxies /api to Django; its Origin must be trusted.
    ['http://localhost:5173', 'http://127.0.0.1:5173'] if DEBUG else [],
)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'core',
    'accounts',
    'workflows',
    'jobs',
    'admin_panel',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.ApiTrailingSlashMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'workflows.middleware.WorkflowSyncMiddleware',  # T05: lazy registry sync on /api/
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cloudgene_django.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'cloudgene_django.wsgi.application'


# Database

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=int(os.environ.get('DB_CONN_MAX_AGE', '0')),
    )
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
    # Web and worker share the DB file; wait for locks instead of failing.
    DATABASES['default'].setdefault('OPTIONS', {}).setdefault('timeout', 20)


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files. The Vite build writes to static/frontend/ (base URL /static/frontend/).

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').is_dir() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'
SPA_INDEX_FILE = BASE_DIR / 'static' / 'frontend' / 'index.html'
# Serve straight from STATICFILES_DIRS so `npm run build` is enough (no collectstatic).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG
# STATIC_ROOT only exists after collectstatic (prod); finders serve files otherwise.
warnings.filterwarnings('ignore', message=r'No directory at: .*staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'


# Security

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False  # the SPA reads csrftoken and sends X-CSRFToken
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_FAILURE_VIEW = 'core.views.csrf_failure'
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', False)
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0'))
if env_bool('DJANGO_BEHIND_TLS_PROXY', False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
X_FRAME_OPTIONS = 'DENY'


# REST framework

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        # Token first so unauthenticated requests get 401 (WWW-Authenticate: Token)
        # rather than 403. The SPA uses the session; CSRF is enforced for it.
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'EXCEPTION_HANDLER': 'core.exceptions.api_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Cloudgene API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'core.serializers.add_error_envelope',
    ],
    'ENUM_NAME_OVERRIDES': {
        'JobStatusEnum': 'jobs.models.Job.STATUS_CHOICES',
        'WorkflowStatusEnum': 'workflows.models.Workflow.STATUS_CHOICES',
        'HealthStatusEnum': ['ok', 'degraded', 'error'],
    },
}


# Uploads: large files are streamed to temp files; the per-job upload limit is
# server.max_upload_mb in settings.yaml (enforced on submission).
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# E-mail: the effective mail settings come from settings.yaml (see core.mail).
# These are only the fallback used by code calling django.core.mail directly.
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.filebased.EmailBackend')
EMAIL_FILE_PATH = CLOUDGENE_HOME / 'mail'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@localhost')


# Logging

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s [%(process)d] %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': LOG_LEVEL,
        },
        # T05: cloudgene.* records at INFO+ → SystemLog (Admin → Logs), SPEC §3.8
        'db': {
            'class': 'admin_panel.logging.DatabaseLogHandler',
            'level': 'INFO',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
        'django.db.backends': {'level': 'INFO'},
        'cloudgene': {'handlers': ['console', 'db'], 'level': 'INFO', 'propagate': False},
    },
}

TEST_RUNNER = 'core.test_runner.CloudgeneTestRunner'
