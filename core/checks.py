"""
Django system checks for production readiness (SPEC §5, TASKS T09a).

Two kinds:
- Always-on (no ``deploy=True``): run before *every* ``manage.py`` command (including
  ``runserver``/``migrate``, which every deploy runs before starting gunicorn) so a dangerous
  misconfiguration blocks the command instead of only showing up if someone remembers to pass
  ``--deploy``.
- ``deploy=True``: only run by ``manage.py check --deploy``, mirroring Django's own
  ``django.security.W0xx`` checks (SECRET_KEY, ALLOWED_HOSTS, SECURE_* cookies/SSL/HSTS) but with
  messages that name this project's own env vars, plus checks Django has no opinion on (SQLite in
  production, the insecure hasher).
"""
import os

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

E_INSECURE_HASHING = 'core.E001'
W_SQLITE_IN_PROD = 'core.W001'
W_SECRET_KEY_WEAK = 'core.W002'
W_ALLOWED_HOSTS_WILDCARD = 'core.W003'
W_SECURE_COOKIES_OFF = 'core.W004'
W_SSL_REDIRECT_OFF = 'core.W005'
W_HSTS_OFF = 'core.W006'


def _env_true(name):
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


@register(Tags.security)
def check_insecure_hashing_not_leaked(app_configs, **kwargs):
    """INSECURE_FAST_PASSWORD_HASHING may only be active in DEBUG or a declared E2E stack.

    This is an Error (not gated behind --deploy) so it blocks *any* manage.py command,
    including the migrate/collectstatic a deploy runs before starting gunicorn.
    """
    if os.environ.get('INSECURE_FAST_PASSWORD_HASHING') != '1':
        return []
    if settings.DEBUG or _env_true('CLOUDGENE_E2E'):
        return []
    return [Error(
        'INSECURE_FAST_PASSWORD_HASHING=1 is set with DEBUG off and CLOUDGENE_E2E unset — this '
        'looks like a production process (settings.py has already neutralised the hasher choice '
        'back to the default Argon2/PBKDF2 hashers, but the env var itself must be removed).',
        hint='Unset INSECURE_FAST_PASSWORD_HASHING outside the E2E stack (which also sets '
             'CLOUDGENE_E2E=1). Never set either variable in a production environment file.',
        id=E_INSECURE_HASHING,
    )]


@register(Tags.security, deploy=True)
def check_secret_key_strength(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    key = settings.SECRET_KEY or ''
    weak = {'changeme', 'change-me', 'secret', 'insecure', 'dev', 'development', ''}
    # 50 matches Django's own security.W009 threshold (django.core.checks.security.base) so the
    # two checks agree instead of giving contradictory verdicts.
    if len(key) < 50 or key.lower() in weak:
        return [Warning(
            'SECRET_KEY looks weak or short for a production deployment.',
            hint='Set DJANGO_SECRET_KEY to a long random value, or leave it unset so '
                 '$CLOUDGENE_HOME/config/secret_key is generated once (50 url-safe chars).',
            id=W_SECRET_KEY_WEAK,
        )]
    return []


@register(Tags.security, deploy=True)
def check_allowed_hosts(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    if '*' in settings.ALLOWED_HOSTS:
        return [Warning(
            'ALLOWED_HOSTS contains "*" — any Host header is accepted.',
            hint='Set ALLOWED_HOSTS to the comma-separated hostname(s) this deployment is '
                 'reachable at (e.g. cloudgene.example.org).',
            id=W_ALLOWED_HOSTS_WILDCARD,
        )]
    return []


@register(Tags.security, deploy=True)
def check_secure_transport_settings(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    warnings = []
    if not (settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE):
        warnings.append(Warning(
            'Session/CSRF cookies are not marked Secure.',
            hint='Set DJANGO_SECURE_COOKIES=1 once this deployment is served over HTTPS.',
            id=W_SECURE_COOKIES_OFF,
        ))
    if not settings.SECURE_SSL_REDIRECT:
        warnings.append(Warning(
            'HTTP requests are not redirected to HTTPS.',
            hint='Set DJANGO_SECURE_SSL_REDIRECT=1 (and DJANGO_BEHIND_TLS_PROXY=1 if TLS is '
                 'terminated by nginx) once this deployment is served over HTTPS.',
            id=W_SSL_REDIRECT_OFF,
        ))
    if not settings.SECURE_HSTS_SECONDS:
        warnings.append(Warning(
            'HSTS is not enabled (SECURE_HSTS_SECONDS=0).',
            hint='Set DJANGO_HSTS_SECONDS (e.g. 31536000) once this deployment is served over '
                 'HTTPS and you are confident it will remain so.',
            id=W_HSTS_OFF,
        ))
    return warnings


@register(Tags.database, deploy=True)
def check_database_engine(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
    if engine == 'django.db.backends.sqlite3':
        return [Warning(
            'Using SQLite with DEBUG off — SPEC §3.1 designates Postgres as the production '
            'database (SQLite is fine for development and small single-user installs only).',
            hint='Set DATABASE_URL to a postgres:// URL.',
            id=W_SQLITE_IN_PROD,
        )]
    return []
