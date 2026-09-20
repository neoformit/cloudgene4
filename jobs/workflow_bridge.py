"""
The only place where jobs/ reads the ``workflows.Workflow`` cache row (owned by T05).

Kept deliberately tolerant so the registry can evolve the model: it prefers explicit
accessors (``get_app_dir()``, ``enabled``) when present and falls back to the current fields.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from core import config as cloudgene_config
from workflows.definition import DefinitionError, WorkflowDefinition, load_definition


@lru_cache(maxsize=256)
def _parse(yaml_text: str, _digest: str) -> WorkflowDefinition:
    return load_definition(yaml_text)


def definition_from_yaml(yaml_text: str) -> WorkflowDefinition:
    """Parse (memoised by content) — raises ``DefinitionError``."""
    if not (yaml_text or '').strip():
        raise DefinitionError('The workflow has no definition (cloudgene.yaml)')
    return _parse(yaml_text, hashlib.sha1(yaml_text.encode('utf-8')).hexdigest())


def get_definition(workflow) -> WorkflowDefinition:
    return definition_from_yaml(workflow.yaml_config)


def is_enabled(workflow) -> bool:
    enabled = getattr(workflow, 'enabled', None)
    if isinstance(enabled, bool):
        return enabled
    return getattr(workflow, 'status', 'enabled') == 'enabled'


def can_access(workflow, user) -> bool:
    return bool(user and user.is_authenticated and workflow.can_access(user))


def app_dir(workflow) -> Path:
    """Directory containing the workflow's cloudgene.yaml / main.nf."""
    getter = getattr(workflow, 'get_app_dir', None)
    if callable(getter):
        value = getter()
        if value:
            return Path(value)
    for attr in ('app_location', 'app_dir', 'app_path'):
        value = getattr(workflow, attr, None)
        if isinstance(value, (str, Path)) and str(value):
            p = Path(value)
            if not p.is_absolute():
                p = cloudgene_config.apps_dir() / p
            return p.parent if p.suffix in ('.yaml', '.yml', '.nf') else p
    return cloudgene_config.apps_dir() / workflow.id


def _app_setting(workflow, key) -> str:
    """Per-app Nextflow setting from the registry (settings.yaml ``apps[].profile|work_dir``)."""
    if workflow is None:
        return ''
    try:
        return (workflow.nextflow_settings()[key] or '').strip()
    except Exception:
        return (getattr(workflow, {'profile': 'nextflow_profile',
                                   'work_dir': 'working_directory'}[key], '') or '').strip()


def nextflow_profile(workflow) -> str:
    return _app_setting(workflow, 'profile') or (cloudgene_config.get('nextflow.profile', '') or '').strip()


def nextflow_work_dir(workflow) -> str:
    return _app_setting(workflow, 'work_dir') or (cloudgene_config.get('nextflow.work_dir', '') or '').strip()
