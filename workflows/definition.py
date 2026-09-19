"""
Workflow definition (``cloudgene.yaml``) parsing and validation — plans/SPEC.md §4.

This module is pure (no DB access) and is the single parser used by:

* the workflow registry (T05) when installing / reloading an app into the ``Workflow`` cache row;
* the public workflow API (run form schema);
* job submission (server-side input validation) and the worker (params.json, outputs).

Public API::

    load_definition(source) -> WorkflowDefinition     # raises DefinitionError(errors)
    parse_definition(data: dict, app_dir=None) -> WorkflowDefinition

``source`` is a path to an app directory (containing ``cloudgene.yaml``/``cloudgene.yml``) or to the
YAML file itself (``str`` or ``Path``), a YAML document as ``str``/``bytes``, or an already parsed
``dict``. ``DefinitionError.errors`` is a list of human-readable messages, each prefixed with the
dotted location (``workflow.inputs[2].type: ...``).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    'DefinitionError', 'InputParam', 'OutputParam', 'Step', 'WorkflowDefinition',
    'load_definition', 'parse_definition', 'find_definition_file',
    'INPUT_TYPES', 'OUTPUT_TYPES', 'DISPLAY_TYPES', 'FILE_TYPES', 'RESERVED_FIELDS',
]

APP_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
PARAM_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')

#: Input types accepted in ``workflow.inputs[].type``.
INPUT_TYPES = (
    'text', 'string', 'number', 'textarea', 'list', 'radio', 'checkbox',
    'file', 'folder', 'local-file', 'local-folder',
    'separator', 'info', 'label', 'terms_checkbox', 'agb_checkbox',
)
#: Display-only inputs: rendered in the form, never submitted, never in params.json.
DISPLAY_TYPES = ('separator', 'info', 'label')
#: Upload inputs (``folder`` types accept several files).
FILE_TYPES = ('file', 'folder', 'local-file', 'local-folder')
FOLDER_TYPES = ('folder', 'local-folder')
TERMS_TYPES = ('terms_checkbox', 'agb_checkbox')
CHOICE_TYPES = ('list', 'radio')
OUTPUT_TYPES = ('folder', 'file', 'local-folder', 'local-file')
#: Multipart field names used by job submission; input/output ids must not use them.
RESERVED_FIELDS = ('workflow', 'job_name')
DEFINITION_FILENAMES = ('cloudgene.yaml', 'cloudgene.yml')


class DefinitionError(ValueError):
    """Invalid workflow definition. ``errors`` is a list of messages."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = list(errors)
        super().__init__('; '.join(self.errors) or 'Invalid workflow definition')


@dataclass
class InputParam:
    id: str
    type: str
    label: str = ''
    value: Any = None            # typed default: str | float/int | bool (checkbox/terms) | None
    values: list = field(default_factory=list)   # [{'key': str, 'label': str}] for list/radio
    checkbox_values: dict | None = None          # checkbox: {'true': mapped, 'false': mapped}
    required: bool = True
    visible: bool = True
    help: str = ''
    details: str = ''
    write_file: str = ''         # textarea: write content to input/<id>/<write_file>
    serialize: bool = True       # include in params.json
    accept: str = ''             # file types: ".csv,.vcf.gz"
    min: float | int | None = None
    max: float | int | None = None

    @property
    def is_display(self) -> bool:
        return self.type in DISPLAY_TYPES

    @property
    def is_file(self) -> bool:
        return self.type in FILE_TYPES

    @property
    def is_folder(self) -> bool:
        return self.type in FOLDER_TYPES

    @property
    def is_terms(self) -> bool:
        return self.type in TERMS_TYPES

    @property
    def value_keys(self) -> list[str]:
        return [v['key'] for v in self.values]

    @property
    def accept_extensions(self) -> list[str]:
        """Lower-case extensions from ``accept`` (MIME-type tokens are ignored)."""
        return [t.strip().lower() for t in (self.accept or '').split(',')
                if t.strip().startswith('.')]

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'type': self.type, 'label': self.label, 'value': self.value,
            'values': [dict(v) for v in self.values],
            'checkbox_values': dict(self.checkbox_values) if self.checkbox_values else None,
            'required': self.required, 'visible': self.visible, 'help': self.help,
            'details': self.details, 'write_file': self.write_file, 'serialize': self.serialize,
            'accept': self.accept, 'min': self.min, 'max': self.max,
        }


@dataclass
class OutputParam:
    id: str
    type: str
    label: str = ''
    download: bool = True
    serialize: bool = True

    @property
    def is_folder(self) -> bool:
        return self.type in FOLDER_TYPES

    def to_dict(self) -> dict:
        return {'id': self.id, 'type': self.type, 'label': self.label,
                'download': self.download, 'serialize': self.serialize}


@dataclass
class Step:
    name: str
    type: str = 'nextflow'       # 'nextflow' or 'unsupported'
    script: str = ''
    revision: str = ''
    params: dict = field(default_factory=dict)
    processes: list = field(default_factory=list)   # [{'process', 'label', 'view', 'group'}]
    error: str = ''              # why the step is unsupported (the job fails with this message)
    raw: dict = field(default_factory=dict)

    @property
    def supported(self) -> bool:
        return self.type == 'nextflow'

    def to_dict(self) -> dict:
        return {'name': self.name, 'type': self.type, 'script': self.script,
                'revision': self.revision, 'params': dict(self.params),
                'processes': [dict(p) for p in self.processes], 'error': self.error}


@dataclass
class WorkflowDefinition:
    id: str
    name: str
    version: str = ''
    description: str = ''
    website: str = ''
    author: str = ''
    logo: str = ''
    category: str = ''
    steps: list[Step] = field(default_factory=list)
    inputs: list[InputParam] = field(default_factory=list)
    outputs: list[OutputParam] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    app_dir: Path | None = None   # directory of cloudgene.yaml (None if parsed from text)
    source_path: Path | None = None
    raw: dict = field(default_factory=dict)
    yaml_text: str = ''           # the YAML source (for the Workflow cache row)

    def input(self, input_id: str) -> InputParam | None:
        return next((p for p in self.inputs if p.id == input_id), None)

    def output(self, output_id: str) -> OutputParam | None:
        return next((p for p in self.outputs if p.id == output_id), None)

    @property
    def value_inputs(self) -> list[InputParam]:
        """Inputs that carry a value (i.e. not separator/info/label)."""
        return [p for p in self.inputs if not p.is_display]

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'name': self.name, 'version': self.version,
            'description': self.description, 'website': self.website, 'author': self.author,
            'logo': self.logo, 'category': self.category,
            'steps': [s.to_dict() for s in self.steps],
            'inputs': [p.to_dict() for p in self.inputs],
            'outputs': [p.to_dict() for p in self.outputs],
            'warnings': list(self.warnings),
        }


# ------------------------------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------------------------------

def find_definition_file(path: str | os.PathLike) -> Path:
    """Resolve an app directory or YAML file path to the ``cloudgene.yaml`` file."""
    p = Path(path)
    if p.is_dir():
        for name in DEFINITION_FILENAMES:
            if (p / name).is_file():
                return p / name
        raise DefinitionError(f'No cloudgene.yaml found in {p}')
    if p.is_file():
        return p
    raise DefinitionError(f'Workflow definition not found: {p}')


def load_definition(source) -> WorkflowDefinition:
    """Load and validate a workflow definition (see module docstring for ``source``)."""
    app_dir = source_path = None
    if isinstance(source, dict):
        return parse_definition(source)
    if isinstance(source, bytes):
        source = source.decode('utf-8')
    if isinstance(source, os.PathLike) or (isinstance(source, str) and _looks_like_path(source)):
        source_path = find_definition_file(source)
        app_dir = source_path.parent
        try:
            text = source_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            raise DefinitionError(f'Cannot read {source_path}: {exc}') from exc
    elif isinstance(source, str):
        text = source
    else:
        raise DefinitionError(f'Unsupported definition source: {type(source).__name__}')

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DefinitionError(f'Invalid YAML: {exc}') from exc
    if isinstance(data, str) and '\n' not in text.strip():
        raise DefinitionError(f'Workflow definition not found: {text.strip()}')
    definition = parse_definition(data, app_dir=app_dir)
    definition.source_path = source_path
    definition.yaml_text = text
    return definition


def _looks_like_path(value: str) -> bool:
    if '\n' in value or not value.strip():
        return False
    return os.path.exists(value) or value.endswith(('.yaml', '.yml')) or value.startswith(('/', './'))


# ------------------------------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------------------------------

def _str(value, default='') -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _bool(value, default, where, errors) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ('true', 'yes', '1'):
        return True
    if isinstance(value, str) and value.strip().lower() in ('false', 'no', '0'):
        return False
    errors.append(f'{where}: must be true or false')
    return default


def _number(value, where, errors):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        errors.append(f'{where}: must be a number')
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).strip()
        return int(text) if re.match(r'^[+-]?\d+$', text) else float(text)
    except ValueError:
        errors.append(f'{where}: must be a number')
        return None


def _parse_values(raw, where, errors) -> list[dict]:
    items = []
    if isinstance(raw, dict):
        items = [{'key': _str(k), 'label': _str(v, _str(k))} for k, v in raw.items()]
    elif isinstance(raw, list):
        for i, entry in enumerate(raw):
            if isinstance(entry, dict) and ('key' in entry or 'value' in entry):
                key = _str(entry.get('key', entry.get('value')))
                items.append({'key': key, 'label': _str(entry.get('label'), key)})
            elif isinstance(entry, (str, int, float, bool)):
                items.append({'key': _str(entry), 'label': _str(entry)})
            else:
                errors.append(f'{where}[{i}]: must be a value or {{key, label}}')
    elif raw is not None:
        errors.append(f'{where}: must be a mapping of key: label')
    keys = [v['key'] for v in items]
    if len(set(keys)) != len(keys):
        errors.append(f'{where}: duplicate keys')
    return items


def _parse_input(raw, where, errors, warnings) -> InputParam | None:
    if not isinstance(raw, dict):
        errors.append(f'{where}: must be a mapping')
        return None
    pid = _str(raw.get('id')).strip()
    if not pid:
        errors.append(f'{where}.id: is required')
    elif not PARAM_ID_RE.match(pid):
        errors.append(f'{where}.id: "{pid}" must match {PARAM_ID_RE.pattern}')
    elif pid in RESERVED_FIELDS:
        errors.append(f'{where}.id: "{pid}" is reserved')
    ptype = _str(raw.get('type')).strip()
    if not ptype:
        errors.append(f'{where}.type: is required')
        return None
    if ptype not in INPUT_TYPES:
        errors.append(f'{where}.type: unknown type "{ptype}" (supported: {", ".join(INPUT_TYPES)})')
        return None

    label = _str(raw.get('description', raw.get('label')), pid)
    param = InputParam(
        id=pid, type=ptype, label=label,
        required=_bool(raw.get('required'), True, f'{where}.required', errors),
        visible=_bool(raw.get('visible'), True, f'{where}.visible', errors),
        help=_str(raw.get('help')), details=_str(raw.get('details')),
        write_file=_str(raw.get('writeFile', raw.get('write_file'))).strip(),
        serialize=_bool(raw.get('serialize'), True, f'{where}.serialize', errors),
        accept=_str(raw.get('accept')).strip(),
    )
    value = raw.get('value')

    if ptype in ('text', 'string', 'textarea'):
        param.value = _str(value)
        if param.write_file:
            if ptype != 'textarea':
                errors.append(f'{where}.writeFile: only supported for textarea inputs')
            elif not _safe_filename(param.write_file):
                errors.append(f'{where}.writeFile: must be a plain file name')
    elif ptype == 'number':
        param.min = _number(raw.get('min'), f'{where}.min', errors)
        param.max = _number(raw.get('max'), f'{where}.max', errors)
        param.value = _number(value, f'{where}.value', errors)
        if param.min is not None and param.max is not None and param.min > param.max:
            errors.append(f'{where}: min must be <= max')
    elif ptype in CHOICE_TYPES:
        param.values = _parse_values(raw.get('values'), f'{where}.values', errors)
        if not param.values:
            errors.append(f'{where}.values: {ptype} inputs need at least one value')
        param.value = _str(value) if value is not None else ''
        if param.value and param.values and param.value not in param.value_keys:
            warnings.append(f'{where}.value: default "{param.value}" is not one of the values; ignored')
            param.value = ''
    elif ptype == 'checkbox':
        mapping = raw.get('values')
        if mapping is not None:
            if not isinstance(mapping, dict):
                errors.append(f'{where}.values: must be a mapping {{true: ..., false: ...}}')
            else:
                norm = {_str(k).lower(): v for k, v in mapping.items()}
                if 'true' not in norm or 'false' not in norm:
                    errors.append(f'{where}.values: needs both true and false keys')
                else:
                    param.checkbox_values = {'true': norm['true'], 'false': norm['false']}
        param.value = _checkbox_default(value, param.checkbox_values)
        param.required = False   # an unchecked checkbox is a valid value
    elif ptype in TERMS_TYPES:
        param.value = False   # must be checked unless `required: false`
    elif ptype in FILE_TYPES:
        param.value = None
    else:  # display types
        param.value = _str(value)
        param.required = False
        param.serialize = False
    return param


def _checkbox_default(value, mapping) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = _str(value).strip().lower()
    if text in ('true', 'yes', '1', 'on'):
        return True
    if mapping and _str(mapping.get('true')).lower() == text:
        return True
    return False


def _safe_filename(name: str) -> bool:
    return bool(name) and '/' not in name and '\\' not in name and name not in ('.', '..') \
        and not name.startswith('.')


def _parse_output(raw, where, errors) -> OutputParam | None:
    if not isinstance(raw, dict):
        errors.append(f'{where}: must be a mapping')
        return None
    pid = _str(raw.get('id')).strip()
    if not pid:
        errors.append(f'{where}.id: is required')
    elif not PARAM_ID_RE.match(pid):
        errors.append(f'{where}.id: "{pid}" must match {PARAM_ID_RE.pattern}')
    elif pid in RESERVED_FIELDS:
        errors.append(f'{where}.id: "{pid}" is reserved')
    ptype = _str(raw.get('type'), 'folder').strip()
    if ptype not in OUTPUT_TYPES:
        errors.append(f'{where}.type: unknown type "{ptype}" (supported: {", ".join(OUTPUT_TYPES)})')
        return None
    return OutputParam(
        id=pid, type=ptype, label=_str(raw.get('description', raw.get('label')), pid),
        download=_bool(raw.get('download'), True, f'{where}.download', errors),
        serialize=_bool(raw.get('serialize'), True, f'{where}.serialize', errors),
    )


def _parse_step(raw, where, errors, warnings) -> Step | None:
    if not isinstance(raw, dict):
        errors.append(f'{where}: must be a mapping')
        return None
    name = _str(raw.get('name')).strip() or 'Step'
    step = Step(name=name, raw=dict(raw))
    stype = _str(raw.get('type')).strip().lower()
    if raw.get('classname'):
        step.type = 'unsupported'
        step.error = (f'Step "{name}" uses classname "{raw.get("classname")}" (Java step); '
                      f'only Nextflow steps are supported.')
    elif stype and stype != 'nextflow':
        step.type = 'unsupported'
        step.error = f'Step "{name}" has unsupported type "{stype}"; only Nextflow steps are supported.'
    elif not stype and raw.get('cmd') and not raw.get('script'):
        step.type = 'unsupported'
        step.error = f'Step "{name}" is a command step; only Nextflow steps are supported.'
    if step.type != 'nextflow':
        warnings.append(f'{where}: {step.error}')
        return step
    step.script = _str(raw.get('script'), 'main.nf').strip() or 'main.nf'
    step.revision = _str(raw.get('revision')).strip()
    params = raw.get('params')
    if params is None:
        params = {}
    if not isinstance(params, dict):
        errors.append(f'{where}.params: must be a mapping')
        params = {}
    step.params = params
    processes = raw.get('processes') or []
    if not isinstance(processes, list):
        errors.append(f'{where}.processes: must be a list')
        processes = []
    for i, proc in enumerate(processes):
        if not isinstance(proc, dict) or not proc.get('process'):
            errors.append(f'{where}.processes[{i}]: needs a "process" name')
            continue
        step.processes.append({
            'process': _str(proc.get('process')), 'label': _str(proc.get('label')),
            'view': _str(proc.get('view'), 'list'), 'group': _str(proc.get('group')),
        })
    return step


def parse_definition(data, app_dir=None) -> WorkflowDefinition:
    """Validate a parsed ``cloudgene.yaml`` mapping. Raises ``DefinitionError``."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        raise DefinitionError('The workflow definition must be a YAML mapping')

    app_id = _str(data.get('id')).strip()
    if isinstance(data.get('id'), bool):
        errors.append(f'id: "{app_id}" was read as a boolean; quote it in the YAML')
    elif not app_id:
        errors.append('id: is required')
    elif not APP_ID_RE.match(app_id):
        errors.append(f'id: "{app_id}" must match {APP_ID_RE.pattern}')
    name = _str(data.get('name')).strip()
    if not name:
        errors.append('name: is required')

    wf = data.get('workflow')
    steps, inputs, outputs = [], [], []
    if not isinstance(wf, dict):
        errors.append('workflow: is required and must be a mapping')
    else:
        raw_steps = wf.get('steps')
        if not isinstance(raw_steps, list) or not raw_steps:
            errors.append('workflow.steps: at least one step is required')
        else:
            for i, raw in enumerate(raw_steps):
                step = _parse_step(raw, f'workflow.steps[{i}]', errors, warnings)
                if step:
                    steps.append(step)
        for key, parser, target in (('inputs', _parse_input, inputs), ('outputs', _parse_output, outputs)):
            raw_list = wf.get(key)
            if raw_list is None:
                continue
            if not isinstance(raw_list, list):
                errors.append(f'workflow.{key}: must be a list')
                continue
            for i, raw in enumerate(raw_list):
                where = f'workflow.{key}[{i}]'
                item = parser(raw, where, errors, warnings) if key == 'inputs' else parser(raw, where, errors)
                if item:
                    target.append(item)

    seen = {}
    for kind, items in (('inputs', inputs), ('outputs', outputs)):
        for item in items:
            if not item.id:
                continue
            if item.id in seen:
                errors.append(f'workflow.{kind}: duplicate id "{item.id}" (also in {seen[item.id]})')
            else:
                seen[item.id] = kind

    if errors:
        raise DefinitionError(errors)

    return WorkflowDefinition(
        id=app_id, name=name, version=_str(data.get('version')),
        description=_str(data.get('description')), website=_str(data.get('website')),
        author=_str(data.get('author')), logo=_str(data.get('logo')),
        category=_str(data.get('category')), steps=steps, inputs=inputs, outputs=outputs,
        warnings=warnings, app_dir=Path(app_dir) if app_dir else None, raw=data,
    )
