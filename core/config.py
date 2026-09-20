"""
Configuration service — the single source of truth for application settings.

Reads ``$CLOUDGENE_HOME/config/settings.yaml`` (schema + defaults below), caches it
by file mtime/size, and writes atomically (temp file + ``os.replace``) under an
exclusive ``fcntl`` lock. Web and worker processes both go through this module, so a
change saved by an admin is picked up by the worker on its next read without a restart.

Public API (see plans/SPEC.md §3.2 for the key table)::

    load_settings(force=False) -> dict          # validated, defaults filled, deep copy
    get(key, default=None) -> Any               # dotted path, e.g. get('server.max_running_jobs')
    save_settings(data) -> dict                 # validate + atomic write of the whole document
    update_settings(patch_or_fn) -> dict        # locked read-modify-write (deep merge or callable)
    set_value(key, value) -> dict               # locked write of one dotted key
    validate_settings(data) -> dict             # raises ConfigError(errors={key: [msg]})
    default_settings() -> dict

    cloudgene_home(), config_dir(), settings_path(), pages_dir(), apps_dir(), jobs_dir()
    nextflow_config_path(), nextflow_env_path()
    app_dir(app_id), job_dir(job_id), page_path(slug)
    read_page(slug) -> str | None, write_page(slug, html), delete_page(slug), list_pages()
    read_text(path, default='') -> str, write_text_atomic(path, text)
    parse_env(text) -> dict                     # KEY=VALUE lines (nextflow.env)
    ensure_home()                               # create the directory layout

Unknown keys in settings.yaml are preserved (forward compatible) but not validated.
"""
from __future__ import annotations

import contextlib
import copy
import fcntl
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')

# --------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------


class Field:
    """A typed scalar setting."""

    def __init__(self, type_, default, *, min=None, max=None, choices=None, help=''):
        self.type = type_
        self.default = default
        self.min = min
        self.max = max
        self.choices = choices
        self.help = help

    def clean(self, value, path, errors):
        if value is None:
            return copy.deepcopy(self.default)
        t = self.type
        if t is bool:
            if not isinstance(value, bool):
                errors.setdefault(path, []).append('Must be true or false.')
                return self.default
        elif t is int:
            if isinstance(value, bool) or not isinstance(value, int):
                if isinstance(value, str) and value.strip().lstrip('-').isdigit():
                    value = int(value.strip())
                else:
                    errors.setdefault(path, []).append('Must be an integer.')
                    return self.default
        elif t is str:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            if not isinstance(value, str):
                errors.setdefault(path, []).append('Must be a string.')
                return self.default
        elif t is list:  # list of strings
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.setdefault(path, []).append('Must be a list of strings.')
                return copy.deepcopy(self.default)
        if self.min is not None and value < self.min:
            errors.setdefault(path, []).append(f'Must be at least {self.min}.')
        if self.max is not None and value > self.max:
            errors.setdefault(path, []).append(f'Must be at most {self.max}.')
        if self.choices is not None and value not in self.choices:
            errors.setdefault(path, []).append(
                f'Must be one of: {", ".join(map(str, self.choices))}.')
        return value


class ListOf:
    """A list of mappings, each validated against ``item`` (dict of Fields)."""

    def __init__(self, item: dict, default=None, required=()):
        self.item = item
        self.default = default or []
        self.required = required

    def clean(self, value, path, errors):
        if value is None:
            return copy.deepcopy(self.default)
        if not isinstance(value, list):
            errors.setdefault(path, []).append('Must be a list.')
            return copy.deepcopy(self.default)
        out = []
        for i, entry in enumerate(value):
            ipath = f'{path}[{i}]'
            if not isinstance(entry, dict):
                errors.setdefault(ipath, []).append('Must be a mapping.')
                continue
            for req in self.required:
                if entry.get(req) in (None, ''):
                    errors.setdefault(f'{ipath}.{req}', []).append('This field is required.')
            out.append(_clean_section(self.item, entry, ipath, errors))
        return out


SCHEMA: dict[str, Any] = {
    'server': {
        'name': Field(str, 'Cloudgene', help='Service name shown in the navbar and e-mails'),
        'url': Field(str, '', help='Public base URL used in e-mail links (empty = request host)'),
        'max_running_jobs': Field(int, 2, min=1, help='Jobs executed concurrently'),
        'max_queue_size': Field(int, 50, min=0, help='Max waiting jobs; submissions beyond → rejected'),
        'maintenance': Field(bool, False, help='Block submissions by non-admins, show banner'),
        'maintenance_message': Field(
            str, 'The service is in maintenance mode. Job submission is temporarily disabled.'),
        'job_retention_days': Field(int, 7, min=0, help='Delete job workspaces after N days (0 = keep)'),
        'max_upload_mb': Field(int, 1024, min=1, help='Max total upload size per job submission'),
    },
    'queue': {
        'paused': Field(bool, False, help='Worker does not start new jobs while paused'),
    },
    'security': {
        'max_login_attempts': Field(int, 5, min=0, help='Failed logins before lockout (0 = off)'),
        'lockout_duration': Field(int, 300, min=0, help='Lockout duration in seconds'),
        'require_activation': Field(bool, True, help='New accounts must be activated by e-mail'),
    },
    'mail': {
        'backend': Field(str, 'file', choices=['smtp', 'file', 'console'],
                         help='smtp for real delivery; file/console for dev/test'),
        'file_path': Field(str, 'mail', help='Outbox dir for backend=file (relative to CLOUDGENE_HOME)'),
        'host': Field(str, 'localhost'),
        'port': Field(int, 587, min=1, max=65535),
        'user': Field(str, ''),
        'password': Field(str, '', help='Write-only in APIs'),
        'use_tls': Field(bool, True),
        'use_ssl': Field(bool, False),
        'from_email': Field(str, 'noreply@localhost'),
    },
    'nextflow': {
        'binary': Field(str, 'nextflow'),
        'profile': Field(str, '', help='Default -profile for all workflows'),
        'work_dir': Field(str, '', help='Nextflow work dir (empty = <job>/work)'),
    },
    'navbar': ListOf({
        'title': Field(str, ''),
        'url': Field(str, ''),
        'icon': Field(str, ''),
        'admin_only': Field(bool, False),
        'auth_only': Field(bool, False),
    }, required=('title', 'url')),
    'apps': ListOf({
        'path': Field(str, '', help='App dir or cloudgene.yaml; relative to CLOUDGENE_HOME/apps'),
        'enabled': Field(bool, True),
        'public': Field(bool, False),
        'groups': Field(list, []),
        'profile': Field(str, '', help='Per-app Nextflow -profile (overrides nextflow.profile)'),
        'work_dir': Field(str, '', help='Per-app Nextflow work dir (overrides nextflow.work_dir)'),
    }, required=('path',)),
}


def _clean_section(schema: dict, data: dict, path: str, errors: dict) -> dict:
    out = dict(data)  # preserve unknown keys
    for key, spec in schema.items():
        kpath = f'{path}.{key}' if path else key
        if isinstance(spec, dict):
            value = data.get(key)
            if value is None:
                value = {}
            if not isinstance(value, dict):
                errors.setdefault(kpath, []).append('Must be a mapping.')
                value = {}
            out[key] = _clean_section(spec, value, kpath, errors)
        else:
            out[key] = spec.clean(data.get(key), kpath, errors)
    return out


def _defaults(schema: dict) -> dict:
    out = {}
    for key, spec in schema.items():
        out[key] = _defaults(spec) if isinstance(spec, dict) else copy.deepcopy(spec.default)
    return out


class ConfigError(ValueError):
    """Invalid settings. ``errors`` maps dotted key paths to lists of messages."""

    def __init__(self, errors: dict[str, list[str]] | str):
        if isinstance(errors, str):
            errors = {'settings': [errors]}
        self.errors = errors
        first_key = next(iter(errors))
        super().__init__(f'{first_key}: {errors[first_key][0]}')


def default_settings() -> dict:
    return _defaults(SCHEMA)


def validate_settings(data: dict | None) -> dict:
    """Return a normalised copy of ``data`` with defaults filled in; raise ConfigError."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError('The settings document must be a mapping.')
    errors: dict[str, list[str]] = {}
    cleaned = _clean_section(SCHEMA, data, '', errors)
    if errors:
        raise ConfigError(errors)
    return cleaned


# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------


def cloudgene_home() -> Path:
    """The configured CLOUDGENE_HOME (Django setting, else env, else ./home)."""
    try:
        from django.conf import settings
        if settings.configured and getattr(settings, 'CLOUDGENE_HOME', None):
            return Path(settings.CLOUDGENE_HOME)
    except Exception:  # pragma: no cover - django not importable
        pass
    env = os.environ.get('CLOUDGENE_HOME')
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent / 'home'


def config_dir() -> Path:
    return cloudgene_home() / 'config'


def settings_path() -> Path:
    return config_dir() / 'settings.yaml'


def nextflow_config_path() -> Path:
    return config_dir() / 'nextflow.config'


def nextflow_env_path() -> Path:
    return config_dir() / 'nextflow.env'


def pages_dir() -> Path:
    return cloudgene_home() / 'pages'


def apps_dir() -> Path:
    return cloudgene_home() / 'apps'


def jobs_dir() -> Path:
    return cloudgene_home() / 'jobs'


def _check_slug(value: str, what: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.match(value):
        raise ValueError(f'Invalid {what}: {value!r} (allowed: a-z, 0-9, "-", "_")')
    return value


def app_dir(app_id: str) -> Path:
    return apps_dir() / _check_slug(app_id, 'app id')


def job_dir(job_id) -> Path:
    job_id = str(job_id)
    if not re.match(r'^[0-9a-fA-F-]{8,64}$', job_id):
        raise ValueError(f'Invalid job id: {job_id!r}')
    return jobs_dir() / job_id


def page_path(slug: str) -> Path:
    return pages_dir() / f'{_check_slug(slug, "page slug")}.html'


def ensure_home() -> Path:
    home = cloudgene_home()
    for d in (config_dir(), pages_dir(), apps_dir(), jobs_dir()):
        d.mkdir(parents=True, exist_ok=True)
    return home


# --------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------


def read_text(path: Path, default: str = '') -> str:
    try:
        return Path(path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return default


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file in the same dir + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def parse_env(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines (``#`` comments, optional ``export``, optional quotes)."""
    env = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].strip()
        key, sep, value = line.partition('=')
        key = key.strip()
        if not sep or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        env[key] = value
    return env


def read_page(slug: str) -> str | None:
    path = page_path(slug)
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None


def write_page(slug: str, html: str) -> None:
    write_text_atomic(page_path(slug), html)


def delete_page(slug: str) -> bool:
    try:
        page_path(slug).unlink()
        return True
    except FileNotFoundError:
        return False


def list_pages() -> list[str]:
    d = pages_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob('*.html') if SLUG_RE.match(p.stem))


# --------------------------------------------------------------------------------------
# settings.yaml load / cache / write
# --------------------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {'path': None, 'stamp': None, 'data': None}


def _stamp(path: Path):
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _read_yaml(path: Path) -> dict:
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f'{path} is not valid YAML: {exc}') from exc
    return data or {}


def load_settings(force: bool = False) -> dict:
    """Return the validated settings (a deep copy; mutate freely).

    A missing file yields the defaults. Invalid content raises ConfigError, except when
    a previously valid version is cached, in which case that is returned and an error
    is logged (keeps a running worker alive if someone saves a broken file by hand).
    """
    path = settings_path()
    stamp = _stamp(path)
    with _cache_lock:
        if (not force and _cache['data'] is not None and _cache['path'] == str(path)
                and _cache['stamp'] == stamp):
            return copy.deepcopy(_cache['data'])
        try:
            data = validate_settings(_read_yaml(path))
        except ConfigError:
            if _cache['data'] is not None and _cache['path'] == str(path):
                logger.exception('Invalid %s; keeping last valid settings', path)
                return copy.deepcopy(_cache['data'])
            raise
        _cache.update(path=str(path), stamp=stamp, data=data)
        return copy.deepcopy(data)


def clear_cache() -> None:
    with _cache_lock:
        _cache.update(path=None, stamp=None, data=None)



def get(key: str, default: Any = None) -> Any:
    """Dotted-path lookup, e.g. ``get('server.max_running_jobs')``."""
    node: Any = load_settings()
    for part in key.split('.'):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


@contextlib.contextmanager
def _file_lock():
    lock_path = config_dir() / '.settings.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, 'a') as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _dump(data: dict) -> str:
    header = ('# Cloudgene settings — edited by the admin panel; see plans/SPEC.md §3.2.\n'
              '# Changes are picked up by web and worker without a restart.\n')
    return header + yaml.safe_dump(data, sort_keys=False, default_flow_style=False,
                                   allow_unicode=True)


def _write(data: dict) -> dict:
    cleaned = validate_settings(data)
    path = settings_path()
    write_text_atomic(path, _dump(cleaned))
    with _cache_lock:
        _cache.update(path=str(path), stamp=_stamp(path), data=cleaned)
    return copy.deepcopy(cleaned)


def save_settings(data: dict) -> dict:
    """Validate and atomically replace the whole settings document."""
    with _file_lock():
        return _write(data)


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def update_settings(patch: dict | Callable[[dict], dict | None]) -> dict:
    """Locked read-modify-write.

    ``patch`` is either a dict deep-merged into the current settings (lists are
    replaced, not merged) or a callable receiving the current settings (a copy) and
    returning the new document (or mutating it in place and returning None).
    """
    with _file_lock():
        current = validate_settings(_read_yaml(settings_path()))
        if callable(patch):
            result = patch(current)
            new = current if result is None else result
        else:
            new = _deep_merge(current, patch)
        return _write(new)


def set_value(key: str, value: Any) -> dict:
    """Set one dotted key, e.g. ``set_value('queue.paused', True)``."""
    parts = key.split('.')

    def apply(doc):
        node = doc
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    return update_settings(apply)
