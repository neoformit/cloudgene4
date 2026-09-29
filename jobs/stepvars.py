"""
Variable substitution for workflow steps (SPEC §3.3 / §4, docs/WORKFLOW_YAML_REFERENCE.md).

Cloudgene 3 evaluates the whole ``cloudgene.yaml`` as a Groovy template (``Planner.evaluateWDL``)
so ``$name`` / ``${name}`` in a step resolve to an input value, an output value or a
``CLOUDGENE_*`` variable. This module is the safe re-implementation for the two places where the
rebuild supports it: Nextflow ``params`` values and ``cmd`` of ``type: command`` steps.

Security (SPEC K3): user-supplied values are never interpreted by a shell.

* ``bash: false`` — ``split_command`` splits the *template* with ``shlex`` first; only then is each
  argv token substituted (verbatim), and the result is exec'd without a shell.
* ``bash: true`` — ``quote_into_shell`` substitutes each value quoted for the shell context it lands
  in (unquoted -> ``shlex.quote``; inside ``"..."`` -> escaped; inside ``'...'`` -> ``'\\''``), so a
  value is always one literal word. Only the admin-authored template text is shell syntax.

Unknown variables (not an input, output or ``CLOUDGENE_*`` name) are left untouched — Groovy would
abort the job; leaving them lets a ``bash: true`` command use ordinary shell variables (``$HOME``).
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)')


def build_variables(definition, parameters: dict, job_dir: Path, env: dict) -> dict:
    """``name -> str`` for every input, output and ``CLOUDGENE_*`` variable of a job.

    Inputs: typed value as a string (bool -> ``true``/``false``; file/folder/writeFile inputs ->
    the absolute local path); a declared input without a value is the empty string. Outputs: the
    absolute path of ``<job>/output/<id>``. ``CLOUDGENE_*``: the same values Nextflow gets."""
    variables: dict[str, str] = {}
    parameters = parameters or {}
    for p in definition.value_inputs:
        value = parameters.get(p.id)
        if value is None:
            variables[p.id] = ''
        elif p.is_file or (p.type == 'textarea' and p.write_file):
            variables[p.id] = str((job_dir / value).resolve())
        elif isinstance(value, bool):
            variables[p.id] = 'true' if value else 'false'
        else:
            variables[p.id] = str(value)
    for out in definition.outputs:
        variables[out.id] = str((job_dir / 'output' / out.id).resolve())
    for key, value in env.items():
        if key.startswith('CLOUDGENE_'):
            variables[key] = str(value)
    return variables


def substitute(text: str, variables: dict, quote=None) -> str:
    """Replace ``$name`` / ``${name}`` for known names in one pass (values are not re-scanned).
    ``quote`` optionally transforms each value."""
    def repl(m):
        name = m.group(1) or m.group(2)
        if name not in variables:
            return m.group(0)
        value = variables[name]
        return quote(value) if quote else value
    return VAR_RE.sub(repl, text)


def substitute_params(value, variables: dict):
    """Substitute inside the strings of a ``params`` value (recursively through dict/list)."""
    if isinstance(value, str):
        return substitute(value, variables)
    if isinstance(value, dict):
        return {k: substitute_params(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_params(v, variables) for v in value]
    return value


def split_command(template: str, variables: dict) -> list[str]:
    """``bash: false``: shlex-split the template, then substitute inside each token."""
    return [substitute(tok, variables) for tok in shlex.split(template)]


def _dq(value: str) -> str:
    return re.sub(r'([\\"$`])', r'\\\1', value)


def _sq(value: str) -> str:
    return value.replace("'", "'\\''")


def quote_into_shell(template: str, variables: dict) -> str:
    """``bash: true``: substitute values into a shell script so each is one literal word."""
    out = []
    state = None            # None (unquoted) | "'" | '"'
    i, n = 0, len(template)
    while i < n:
        ch = template[i]
        if ch == '$':
            m = VAR_RE.match(template, i)
            if m and (m.group(1) or m.group(2)) in variables:
                value = variables[m.group(1) or m.group(2)]
                out.append(shlex.quote(value) if state is None
                           else _dq(value) if state == '"' else _sq(value))
                i = m.end()
                continue
        if state == "'":
            if ch == "'":
                state = None
        elif ch == '\\' and i + 1 < n:
            out.append(ch + template[i + 1])
            i += 2
            continue
        elif ch in '\'"':
            if state is None:
                state = ch
            elif state == ch:
                state = None
        out.append(ch)
        i += 1
    return ''.join(out)
