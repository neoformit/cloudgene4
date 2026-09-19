"""
Workflow registry (SPEC §3.2 "Workflow registry").

``settings.yaml`` ``apps[]`` is the source of truth for *which* workflows are installed and
for their access rules (``enabled``, ``public``, ``groups``) and per-app Nextflow
``profile``/``work_dir``. Each app is a directory containing ``cloudgene.yaml`` (plus its
scripts). The ``workflows.Workflow`` table is a cache of the parsed YAML + access rules,
rebuilt by :func:`sync_all`, which runs

* via ``manage.py sync_workflows`` (deploy / worker start-up),
* lazily from ``WorkflowSyncMiddleware`` on API requests whenever ``settings.yaml`` or an
  installed ``cloudgene.yaml`` changed on disk (:func:`sync_if_changed`),
* after every registry write (install / uninstall / access change / reload).

Public API::

    sync_all() -> list[AppStatus]          sync_if_changed() -> bool
    list_apps() -> list[AppStatus]         (syncs first; includes invalid entries)
    install(path, *, enabled=True, public=False, groups=(), copy=False) -> Workflow
    reload(app_id) -> AppStatus            uninstall(app_id) -> None
    update_access(app_id, *, enabled=None, public=None, groups=None) -> AppStatus
    get_nextflow_settings(app_id) -> dict  set_nextflow_settings(app_id, **fields) -> dict
    resolve_app_path(path) -> Path         (the cloudgene.yaml file)

Errors raise :class:`RegistryError` (``message``, ``errors`` list, ``status`` hint).
Workflow definitions are parsed/validated by ``workflows.definition.load_definition``
(owned by T03) through the one adapter :func:`load_definition`.
"""
from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from django.db import transaction
from django.utils import timezone

from core import config

logger = logging.getLogger('cloudgene.workflows')

YAML_NAMES = ('cloudgene.yaml', 'cloudgene.yml')


class RegistryError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None, status: int = 400,
                 code: str = 'invalid'):
        super().__init__(message)
        self.message = message
        self.errors = errors or []
        self.status = status
        self.code = code


# --------------------------------------------------------------------------------------
# Definition adapter (T03 owns workflows/definition.py)
# --------------------------------------------------------------------------------------


@dataclass
class Meta:
    """The subset of a workflow definition the registry needs."""

    id: str
    name: str
    version: str = ''
    description: str = ''
    category: str = ''
    website: str = ''
    warnings: list = field(default_factory=list)


# Minimal SPEC §4 checks used only while workflows/definition.py is unavailable.
_INPUT_TYPES = {
    'text', 'string', 'number', 'textarea', 'list', 'radio', 'checkbox', 'file', 'folder',
    'local-file', 'local-folder', 'separator', 'info', 'label', 'terms_checkbox',
    'agb_checkbox',
}
_OUTPUT_TYPES = {'file', 'folder', 'local-file', 'local-folder'}


def _fallback_validate(doc: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ['The workflow file must be a YAML mapping.']
    app_id = doc.get('id')
    if not isinstance(app_id, str) or not config.SLUG_RE.match(app_id):
        errors.append('id: required; lower-case letters, digits, "-" and "_" only.')
    if not isinstance(doc.get('name'), str) or not doc.get('name', '').strip():
        errors.append('name: required.')
    wf = doc.get('workflow')
    if not isinstance(wf, dict):
        return errors + ['workflow: required mapping with steps/inputs/outputs.']
    steps = wf.get('steps')
    if not isinstance(steps, list) or not steps:
        errors.append('workflow.steps: at least one step is required.')
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f'workflow.steps[{i}]: must be a mapping.')
            elif 'classname' in step:
                errors.append(f'workflow.steps[{i}]: "classname" steps are not supported.')
            elif not step.get('script'):
                errors.append(f'workflow.steps[{i}].script: required.')
    for kind, types in (('inputs', _INPUT_TYPES), ('outputs', _OUTPUT_TYPES)):
        items = wf.get(kind) or []
        if not isinstance(items, list):
            errors.append(f'workflow.{kind}: must be a list.')
            continue
        seen = set()
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f'workflow.{kind}[{i}]: must be a mapping.')
                continue
            if not item.get('id'):
                errors.append(f'workflow.{kind}[{i}].id: required.')
            elif item['id'] in seen:
                errors.append(f'workflow.{kind}[{i}].id: duplicate id "{item["id"]}".')
            seen.add(item.get('id'))
            if item.get('type') not in types:
                errors.append(f'workflow.{kind}[{i}].type: unknown type "{item.get("type")}".')
    return errors


def _normalise_errors(errors: Any) -> list[str]:
    if errors is None:
        return []
    if isinstance(errors, str):
        return [errors]
    if isinstance(errors, dict):
        out = []
        for key, value in errors.items():
            for msg in (value if isinstance(value, (list, tuple)) else [value]):
                out.append(f'{key}: {msg}' if key else str(msg))
        return out
    if isinstance(errors, (list, tuple)):
        out = []
        for e in errors:
            out.extend(_normalise_errors(e))
        return out
    return [str(errors)]


def load_definition(yaml_path: Path):
    """Parse + validate one cloudgene.yaml. Returns (Meta, raw_text); raises RegistryError.

    The single seam to T03's ``workflows.definition.load_definition(path) ->
    WorkflowDefinition`` (raises ``DefinitionError(errors)``).
    """
    try:
        raw = Path(yaml_path).read_text(encoding='utf-8')
    except OSError as exc:
        raise RegistryError(f'Cannot read {yaml_path}: {exc.strerror or exc}')
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RegistryError('Invalid YAML.', [f'Invalid YAML: {exc}'])

    try:
        from workflows import definition as definition_module  # T03
    except ImportError:
        definition_module = None

    if definition_module is not None and hasattr(definition_module, 'load_definition'):
        error_cls = getattr(definition_module, 'DefinitionError', ValueError)
        try:
            defn = definition_module.load_definition(Path(yaml_path))
        except error_cls as exc:  # type: ignore[misc]
            errors = _normalise_errors(getattr(exc, 'errors', None) or str(exc))
            raise RegistryError(errors[0] if errors else 'Invalid workflow.', errors)
        get = (lambda k: getattr(defn, k, None) if not isinstance(defn, dict) else defn.get(k))
    else:
        errors = _fallback_validate(doc)
        if errors:
            raise RegistryError(errors[0], errors)
        get = doc.get

    def text(key):
        value = get(key)
        if value is None and isinstance(doc, dict):
            value = doc.get(key)
        return '' if value is None else str(value)

    meta = Meta(id=text('id'), name=text('name'), version=text('version'),
                description=text('description'), category=text('category'),
                website=text('website'),
                warnings=[str(w) for w in (get('warnings') or [])])
    if not config.SLUG_RE.match(meta.id):
        raise RegistryError(f'Invalid workflow id "{meta.id}".',
                            ['id: lower-case letters, digits, "-" and "_" only (max 64).'])
    return meta, raw


# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------


def resolve_app_path(path: str | Path) -> Path:
    """Locate the cloudgene.yaml for an ``apps[].path`` value or an install argument.

    Relative paths are tried against ``$CLOUDGENE_HOME/apps`` first, then
    ``$CLOUDGENE_HOME``. A directory resolves to its ``cloudgene.yaml``.
    """
    p = Path(str(path)).expanduser()
    candidates = [p] if p.is_absolute() else [config.apps_dir() / p, config.cloudgene_home() / p]
    for cand in candidates:
        if cand.is_dir():
            for name in YAML_NAMES:
                if (cand / name).is_file():
                    return cand / name
        elif cand.is_file():
            return cand
    raise RegistryError(f'No cloudgene.yaml found at "{path}".', [f'Not found: {path}'],
                        code='not_found')


def _fallback_id(path: str) -> str:
    p = Path(str(path))
    base = p.parent.name if p.suffix in ('.yaml', '.yml') and p.stem.startswith('cloudgene') \
        else (p.stem if p.suffix in ('.yaml', '.yml') else p.name)
    slug = ''.join(c if c.isalnum() or c in '-_' else '-' for c in base.lower()).strip('-_')
    return slug[:64] or 'app'


def _stored_path(yaml_path: Path) -> str:
    """What to write into apps[].path: relative to apps/ when inside it, else absolute."""
    yaml_path = yaml_path.resolve()
    try:
        rel = yaml_path.parent.relative_to(config.apps_dir().resolve())
        return str(rel) if str(rel) != '.' else yaml_path.name
    except ValueError:
        return str(yaml_path.parent if yaml_path.name in YAML_NAMES else yaml_path)


# --------------------------------------------------------------------------------------
# Status objects
# --------------------------------------------------------------------------------------


@dataclass
class AppStatus:
    id: str
    index: int  # position in apps[]
    path: str  # as written in settings.yaml
    yaml_path: str  # resolved file ('' if not found)
    enabled: bool
    public: bool
    groups: list[str]
    profile: str = ''
    work_dir: str = ''
    meta: Meta | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def _scan(settings: dict) -> list[AppStatus]:
    statuses: list[AppStatus] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(settings.get('apps') or []):
        st = AppStatus(id=_fallback_id(entry['path']), index=index, path=entry['path'],
                       yaml_path='', enabled=bool(entry.get('enabled', True)),
                       public=bool(entry.get('public', False)),
                       groups=list(entry.get('groups') or []),
                       profile=entry.get('profile') or '', work_dir=entry.get('work_dir') or '')
        try:
            yaml_path = resolve_app_path(entry['path'])
            st.yaml_path = str(yaml_path)
            meta, _raw = load_definition(yaml_path)
            st.meta = meta
            st.id = meta.id
        except RegistryError as exc:
            st.errors = exc.errors or [exc.message]
            if st.yaml_path:
                # id readable even though the definition is invalid?
                try:
                    doc = yaml.safe_load(Path(st.yaml_path).read_text(encoding='utf-8'))
                    if isinstance(doc, dict) and isinstance(doc.get('id'), str) \
                            and config.SLUG_RE.match(doc['id']):
                        st.id = doc['id']
                except Exception:
                    pass
        if st.id in seen:
            st.errors = [f'Duplicate workflow id "{st.id}" (already installed by apps[{seen[st.id]}]).']
            st.meta = None
            st.id = f'{st.id}~{index}'
        else:
            seen[st.id] = index
        statuses.append(st)
    return statuses


# --------------------------------------------------------------------------------------
# Sync
# --------------------------------------------------------------------------------------

_sync_lock = threading.Lock()
_last_signature: Any = None


def _signature(settings_stamp, statuses_paths):
    stamps = []
    for p in statuses_paths:
        try:
            st = Path(p).stat()
            stamps.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            stamps.append((p, None, None))
    return (settings_stamp, tuple(stamps))


def _settings_stamp():
    try:
        st = config.settings_path().stat()
        return (st.st_mtime_ns, st.st_size, st.st_ino, str(config.settings_path()))
    except OSError:
        return (None, str(config.settings_path()))


def _upsert(st: AppStatus, raw: str | None):
    from django.contrib.auth.models import Group

    from .models import Workflow, WorkflowCategory

    now = timezone.now()
    row = Workflow.objects.filter(pk=st.id).first()
    if st.valid:
        meta = st.meta
        category = None
        if meta.category:
            category, _ = WorkflowCategory.objects.get_or_create(name=meta.category[:255])
        values = dict(name=meta.name[:255], version=(meta.version or '')[:50],
                      description=meta.description, website=meta.website[:200],
                      category=category, yaml_config=raw or '', app_path=st.yaml_path,
                      status='enabled' if st.enabled else 'disabled', public=st.public,
                      errors=[], installed=True, synced_at=now)
    else:
        if row is None:
            return None  # never-valid app: shown to admins from settings, no cache row
        values = dict(status='disabled', public=st.public, errors=st.errors, installed=True,
                      app_path=st.yaml_path or row.app_path, synced_at=now)
    if row is None:
        row = Workflow(pk=st.id, **values)
        row.save()
    else:
        for k, v in values.items():
            setattr(row, k, v)
        row.save()
    groups = [Group.objects.get_or_create(name=name)[0] for name in st.groups if name]
    row.allowed_groups.set(groups)
    return row


def sync_all() -> list[AppStatus]:
    """Rebuild the Workflow cache rows from settings.yaml apps[] (idempotent)."""
    global _last_signature
    from .models import Workflow

    with _sync_lock:
        settings_stamp = _settings_stamp()
        settings = config.load_settings()
        statuses = _scan(settings)
        with transaction.atomic():
            present = set()
            for st in statuses:
                raw = None
                if st.valid:
                    raw = Path(st.yaml_path).read_text(encoding='utf-8')
                if _upsert(st, raw) is not None:
                    present.add(st.id)
            # Registry-managed rows no longer listed in apps[] → uninstalled.
            stale = Workflow.objects.exclude(app_path='').exclude(pk__in=present) \
                .filter(installed=True)
            for row in stale:
                if _has_jobs(row):
                    row.installed = False
                    row.status = 'disabled'
                    row.synced_at = timezone.now()
                    row.save(update_fields=['installed', 'status', 'synced_at'])
                else:
                    row.delete()
        _last_signature = _signature(settings_stamp, [s.yaml_path for s in statuses if s.yaml_path])
        return statuses


def _has_jobs(row) -> bool:
    related = getattr(row, 'job_set', None)
    try:
        return bool(related is not None and related.exists())
    except Exception:
        return True


def sync_if_changed() -> bool:
    """Sync when settings.yaml or any installed cloudgene.yaml changed since the last sync
    in this process. Cheap (a few ``stat`` calls). Returns True if a sync ran."""
    last = _last_signature
    if last is not None:
        current = _signature(_settings_stamp(), [p for p, _m, _s in last[1]])
        if current == last:
            return False
    sync_all()
    return True


def list_apps() -> list[AppStatus]:
    return sync_all()


def get_status(app_id: str) -> AppStatus:
    for st in list_apps():
        if st.id == app_id:
            return st
    raise RegistryError(f'Workflow "{app_id}" is not installed.', status=404, code='not_found')


# --------------------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------------------


def _entry_index(settings: dict, app_id: str) -> int:
    for st in _scan(settings):
        if st.id == app_id:
            return st.index
    raise RegistryError(f'Workflow "{app_id}" is not installed.', status=404, code='not_found')


def install(path: str, *, enabled: bool = True, public: bool = False, groups=(),
            copy: bool = False, replace: bool = False):
    """Register the app at ``path`` (dir with cloudgene.yaml, or the yaml file).

    The app stays where it is and ``apps[].path`` references it (relative to
    ``$CLOUDGENE_HOME/apps`` when inside it, else absolute). With ``copy=True`` the app
    directory is first copied to ``$CLOUDGENE_HOME/apps/<id>/``. ``replace=True`` updates
    the path of an already installed app with the same id (keeping its access rules).
    """
    if not str(path or '').strip():
        raise RegistryError('A path is required.', ['This field is required.'])
    yaml_path = resolve_app_path(str(path).strip())
    meta, _raw = load_definition(yaml_path)
    groups = [g.strip() for g in groups if g and g.strip()]

    if copy:
        target = config.app_dir(meta.id)
        source = yaml_path.parent.resolve()
        if source != target.resolve():
            if target.exists():
                raise RegistryError(f'{target} already exists.', status=409, code='conflict')
            shutil.copytree(source, target)
        yaml_path = target / yaml_path.name

    stored = _stored_path(yaml_path)

    def apply(doc):
        apps = doc.setdefault('apps', [])
        for st in _scan(doc):
            if st.id == meta.id:
                if not replace:
                    raise RegistryError(f'A workflow with id "{meta.id}" is already installed '
                                        f'(apps[{st.index}]: {st.path}).', status=409,
                                        code='conflict')
                apps[st.index]['path'] = stored
                return
        apps.append({'path': stored, 'enabled': enabled, 'public': public, 'groups': groups})

    config.update_settings(apply)
    sync_all()
    logger.info('Workflow %s installed from %s', meta.id, stored)
    from .models import Workflow
    return Workflow.objects.get(pk=meta.id)


def uninstall(app_id: str) -> None:
    """Remove the app from apps[] (files are left on disk)."""

    def apply(doc):
        index = _entry_index(doc, app_id)
        doc['apps'].pop(index)

    config.update_settings(apply)
    sync_all()
    logger.info('Workflow %s uninstalled', app_id)


def update_access(app_id: str, *, enabled=None, public=None, groups=None) -> AppStatus:
    def apply(doc):
        entry = doc['apps'][_entry_index(doc, app_id)]
        if enabled is not None:
            entry['enabled'] = bool(enabled)
        if public is not None:
            entry['public'] = bool(public)
        if groups is not None:
            entry['groups'] = sorted({str(g).strip() for g in groups if str(g).strip()})

    config.update_settings(apply)
    sync_all()
    logger.info('Workflow %s access updated (enabled=%s public=%s groups=%s)',
                app_id, enabled, public, groups)
    return get_status(app_id)


def reload(app_id: str) -> AppStatus:
    """Re-read the app's cloudgene.yaml (sync) and return its status (incl. errors)."""
    st = get_status(app_id)
    logger.info('Workflow %s reloaded (%s)', app_id,
                'ok' if st.valid else '; '.join(st.errors))
    return st


# --------------------------------------------------------------------------------------
# Per-app Nextflow settings
# --------------------------------------------------------------------------------------


def app_config_dir(app_id: str) -> Path:
    """``$CLOUDGENE_HOME/apps/<id>/`` — holds the admin-editable nextflow.config/.env."""
    return config.app_dir(app_id)


def get_nextflow_settings(app_id: str) -> dict:
    """``{profile, work_dir, config, env, config_path, env_path}`` for one app.

    ``profile``/``work_dir`` come from the apps[] entry ('' = use the global
    ``nextflow.*``); the files live in :func:`app_config_dir`.
    """
    profile = work_dir = ''
    for entry_status in _scan(config.load_settings()):
        if entry_status.id == app_id:
            profile, work_dir = entry_status.profile, entry_status.work_dir
            break
    base = app_config_dir(app_id)
    return {
        'profile': profile,
        'work_dir': work_dir,
        'config': config.read_text(base / 'nextflow.config'),
        'env': config.read_text(base / 'nextflow.env'),
        'config_path': str(base / 'nextflow.config'),
        'env_path': str(base / 'nextflow.env'),
    }


def set_nextflow_settings(app_id: str, *, profile=None, work_dir=None, config_text=None,
                          env_text=None) -> dict:
    if profile is not None or work_dir is not None:
        def apply(doc):
            entry = doc['apps'][_entry_index(doc, app_id)]
            if profile is not None:
                entry['profile'] = profile.strip()
            if work_dir is not None:
                entry['work_dir'] = work_dir.strip()
        config.update_settings(apply)
    else:
        _entry_index(config.load_settings(), app_id)  # 404 for unknown apps
    base = app_config_dir(app_id)
    if config_text is not None:
        config.write_text_atomic(base / 'nextflow.config', config_text)
    if env_text is not None:
        config.write_text_atomic(base / 'nextflow.env', env_text)
    logger.info('Nextflow settings of workflow %s updated', app_id)
    return get_nextflow_settings(app_id)
