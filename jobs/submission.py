"""
Job submission (web process) — plans/SPEC.md §3.3 "Submit".

``submit_job(user, data, files)`` validates everything against the workflow definition, writes
uploads into a fresh workspace keyed by the job UUID and creates the ``waiting`` Job row. Errors
are raised as ``SubmissionError`` (message, code, HTTP status, field errors).
"""
from __future__ import annotations

import math
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from core import config as cloudgene_config
from core.permissions import is_admin
from workflows.definition import DefinitionError, InputParam, WorkflowDefinition
from workflows.models import Workflow

from . import workflow_bridge
from .models import Job, JobState

MAX_NAME_LENGTH = 255
MAX_TEXT_LENGTH = 100_000
TRUE_STRINGS = ('true', 'on', '1', 'yes', 'checked')
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


class SubmissionError(Exception):
    def __init__(self, message, code='invalid', status=400, fields=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.fields = fields or {}


# ------------------------------------------------------------------------------------------
# Helpers (also used by tests)
# ------------------------------------------------------------------------------------------

def clean_job_name(raw, workflow_name: str) -> str:
    """K3: free text, trimmed, <= 255, control characters removed; default
    ``<workflow name> <YYYY-MM-DD HH:MM>``. Never used in a path or command line."""
    name = _CONTROL.sub(' ', str(raw or '')).strip()
    if len(name) > MAX_NAME_LENGTH:
        raise SubmissionError(f'job_name: at most {MAX_NAME_LENGTH} characters.',
                              fields={'job_name': [f'Ensure this field has no more than {MAX_NAME_LENGTH} characters.']})
    if not name:
        name = f'{workflow_name} {timezone.localtime():%Y-%m-%d %H:%M}'[:MAX_NAME_LENGTH]
    return name


def _basename(name) -> str:
    base = str(name or '').replace('\\', '/').split('/')[-1]
    return _CONTROL.sub('', base).strip()


def display_filename(name: str) -> str:
    """Original file name for display: basename only, control characters removed."""
    return _basename(name)[:255] or 'file'


def safe_filename(name: str) -> str:
    """File name used on disk: ASCII letters, digits, ``.``, ``_``, ``-`` only (spaces and other
    characters become ``_``); never hidden, never empty, at most 150 characters."""
    base = _basename(name)
    ascii_name = unicodedata.normalize('NFKD', base).encode('ascii', 'ignore').decode('ascii')
    ascii_name = re.sub(r'[^A-Za-z0-9._-]+', '_', ascii_name)
    ascii_name = re.sub(r'_{2,}', '_', ascii_name).strip('._-')
    if not ascii_name or set(ascii_name) <= {'.'}:
        ascii_name = 'file'
    if len(ascii_name) > 150:
        stem, dot, ext = ascii_name.rpartition('.')
        if dot and len(ext) <= 20:
            ascii_name = stem[:150 - len(ext) - 1] + '.' + ext
        else:
            ascii_name = ascii_name[:150]
    return ascii_name


def _unique(name: str, used: set) -> str:
    candidate, n = name, 1
    while candidate.lower() in used:
        stem, dot, ext = name.rpartition('.')
        candidate = f'{stem}_{n}.{ext}' if dot and stem else f'{name}_{n}'
        n += 1
    used.add(candidate.lower())
    return candidate


def _is_true(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUE_STRINGS


def _get(data, key):
    if data is None:
        return None
    value = data.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    return value


def _get_files(files, key):
    if files is None:
        return []
    if hasattr(files, 'getlist'):
        return [f for f in files.getlist(key) if f is not None]
    value = files.get(key)
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _accept_ok(param: InputParam, filename: str) -> bool:
    exts = param.accept_extensions
    if not exts:
        return True
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in exts)


def parse_number(text):
    """Returns int/float or raises ValueError."""
    if isinstance(text, bool):
        raise ValueError
    if isinstance(text, (int, float)):
        value = text
    else:
        s = str(text).strip()
        value = int(s) if re.match(r'^[+-]?\d+$', s) else float(s)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError
    return value


# ------------------------------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------------------------------

def validate_inputs(definition: WorkflowDefinition, data, files):
    """Returns ``(parameters, file_plan, text_files, errors)``.

    ``parameters``: input id -> typed value (files: path relative to the job dir).
    ``file_plan``: input id -> [(upload, display name, relative path)].
    ``text_files``: input id -> (relative path, content) for textarea ``writeFile``.
    """
    params, plan, text_files, errors = {}, {}, {}, {}

    def err(pid, msg):
        errors.setdefault(pid, []).append(msg)

    for p in definition.value_inputs:
        pid = p.id
        if not p.visible:
            # Hidden inputs always use the YAML default (clients can't override them).
            if p.type == 'checkbox':
                params[pid] = _checkbox_param(p, bool(p.value))
            elif p.is_terms:
                params[pid] = True
            elif not p.is_file and p.value not in (None, ''):
                params[pid] = p.value
            continue

        if p.is_file:
            uploads = _get_files(files, pid)
            if not uploads:
                if p.required:
                    err(pid, 'Please select a file.' if not p.is_folder else 'Please select at least one file.')
                continue
            if not p.is_folder and len(uploads) > 1:
                err(pid, 'Only one file can be uploaded here.')
                continue
            used, entries = set(), []
            for upload in uploads:
                shown = display_filename(getattr(upload, 'name', 'file'))
                if not _accept_ok(p, shown):
                    err(pid, f'"{shown}" is not an accepted file type ({p.accept}).')
                    continue
                disk = _unique(safe_filename(shown), used)
                entries.append((upload, shown, f'input/{pid}/{disk}'))
            if pid in errors:
                continue
            plan[pid] = entries
            params[pid] = f'input/{pid}' if p.is_folder else entries[0][2]
            continue

        raw = _get(data, pid)
        if p.type == 'checkbox':
            checked = raw is not None and (_is_true(raw) or (
                p.checkbox_values is not None and str(raw) == str(p.checkbox_values['true'])))
            params[pid] = _checkbox_param(p, checked)
            continue
        if p.is_terms:
            if raw is None or not _is_true(raw):
                err(pid, 'You must accept this to submit the job.')
            else:
                params[pid] = True
            continue

        text = '' if raw is None else str(raw)
        if p.type in ('text', 'string', 'textarea'):
            if p.type != 'textarea':
                text = text.strip()
            if not text.strip():
                if p.required:
                    err(pid, 'This field is required.')
                continue
            if len(text) > MAX_TEXT_LENGTH:
                err(pid, f'At most {MAX_TEXT_LENGTH} characters.')
                continue
            if p.type == 'textarea' and p.write_file:
                rel = f'input/{pid}/{p.write_file}'
                text_files[pid] = (rel, text)
                params[pid] = rel
            else:
                params[pid] = text
        elif p.type == 'number':
            if not text.strip():
                if p.required:
                    err(pid, 'This field is required.')
                continue
            try:
                value = parse_number(text)
            except (ValueError, TypeError):
                err(pid, 'Please enter a number.')
                continue
            if p.min is not None and value < p.min:
                err(pid, f'Must be at least {p.min}.')
            elif p.max is not None and value > p.max:
                err(pid, f'Must be at most {p.max}.')
            else:
                params[pid] = value
        elif p.type in ('list', 'radio'):
            if not text:
                if p.required:
                    err(pid, 'Please select a value.')
                continue
            if text not in p.value_keys:
                err(pid, 'Select a valid choice.')
            else:
                params[pid] = text
    return params, plan, text_files, errors


def _checkbox_param(p: InputParam, checked: bool):
    if p.checkbox_values:
        return p.checkbox_values['true' if checked else 'false']
    return checked


# ------------------------------------------------------------------------------------------
# Submission
# ------------------------------------------------------------------------------------------

def queue_is_full() -> tuple[bool, int, int]:
    limit = int(cloudgene_config.get('server.max_queue_size', 50) or 0)
    waiting = Job.objects.filter(status=JobState.WAITING).count()
    return (limit > 0 and waiting >= limit), waiting, limit


def resolve_workflow(user, workflow_id) -> Workflow:
    if not workflow_id:
        raise SubmissionError('workflow: This field is required.',
                              fields={'workflow': ['This field is required.']})
    workflow = Workflow.objects.filter(pk=str(workflow_id)).first()
    if workflow is None or not workflow_bridge.can_access(workflow, user):
        raise SubmissionError('workflow: Workflow not found.', code='not_found', status=404,
                              fields={'workflow': ['Workflow not found.']})
    if not workflow_bridge.is_enabled(workflow):
        raise SubmissionError('This workflow is currently disabled.', code='workflow_disabled',
                              status=409, fields={'workflow': ['This workflow is disabled.']})
    return workflow


def submit_job(user, data, files=None) -> Job:
    workflow = resolve_workflow(user, _get(data, 'workflow') or _get(data, 'workflow_id'))

    admin = is_admin(user)
    if cloudgene_config.get('server.maintenance', False) and not admin:
        raise SubmissionError(
            cloudgene_config.get('server.maintenance_message') or 'The service is in maintenance mode.',
            code='maintenance', status=503)
    full, waiting, limit = queue_is_full()
    if full:
        raise SubmissionError(
            f'The job queue is full ({waiting} of {limit} jobs waiting). Please try again later.',
            code='queue_full', status=429)

    try:
        definition = workflow_bridge.get_definition(workflow)
    except DefinitionError as exc:
        raise SubmissionError(f'The workflow definition is invalid: {exc}', code='workflow_invalid',
                              status=409) from exc

    raw_name = _get(data, 'job_name')
    if raw_name is None:
        raw_name = _get(data, 'name')  # legacy alias
    name = clean_job_name(raw_name, definition.name or workflow.name)

    params, plan, text_files, errors = validate_inputs(definition, data, files)
    if errors:
        field, messages = next(iter(errors.items()))
        raise SubmissionError(f'{field}: {messages[0]}', code='invalid', status=400, fields=errors)

    max_mb = int(cloudgene_config.get('server.max_upload_mb', 1024) or 1024)
    total = sum(getattr(up, 'size', 0) or 0 for entries in plan.values() for up, _, _ in entries)
    if total > max_mb * 1024 * 1024:
        msg = f'Uploads exceed the maximum total size of {max_mb} MB.'
        raise SubmissionError(msg, code='upload_too_large', status=413,
                              fields={pid: [msg] for pid in plan})

    job_id = uuid.uuid4()
    workspace = cloudgene_config.job_dir(job_id)
    uploads_meta = {}
    try:
        for sub in ('input', 'output', 'logs'):
            (workspace / sub).mkdir(parents=True, exist_ok=True)
        for pid, entries in plan.items():
            (workspace / 'input' / pid).mkdir(parents=True, exist_ok=True)
            uploads_meta[pid] = []
            for upload, shown, rel in entries:
                size = _save_upload(upload, workspace / rel)
                uploads_meta[pid].append({'name': shown, 'path': rel, 'size': size})
        for pid, (rel, text) in text_files.items():
            target = workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        with transaction.atomic():
            job = Job.objects.create(
                id=job_id, name=name, workflow=workflow, user=user,
                app_id=workflow.id, app_name=definition.name or workflow.name,
                app_version=definition.version or getattr(workflow, 'version', '') or '',
                workflow_yaml=workflow.yaml_config,
                app_dir=str(workflow_bridge.app_dir(workflow)),
                status=JobState.WAITING, parameters=params, uploads=uploads_meta,
            )
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    return job


def _save_upload(upload, target: Path) -> int:
    size = 0
    with open(target, 'wb') as fh:
        if hasattr(upload, 'chunks'):
            for chunk in upload.chunks():
                fh.write(chunk)
                size += len(chunk)
        else:
            data = upload.read()
            fh.write(data)
            size = len(data)
    return size
