# Workflow YAML Reference (`cloudgene.yaml`)

A Cloudgene "workflow" (also called an "app") is a directory containing a `cloudgene.yaml` (or
`cloudgene.yml`) file plus whatever Nextflow scripts it references. This document describes every
key the parser (`workflows/definition.py`) understands, and is the single source of truth for the
subset of the Cloudgene 3 format this port supports (SPEC §4).

A complete, validating example is committed at [`docs/examples/cloudgene.yaml`](examples/cloudgene.yaml)
and is loaded by a Django unit test
(`workflows/tests_yaml_reference_example.py::YamlReferenceExampleTest`) that asserts it parses with
no errors, so this document cannot silently drift from what the parser accepts.

## Loading and validation

Workflows are parsed by `workflows.definition.load_definition(source)`:

```python
from workflows.definition import load_definition, parse_definition, DefinitionError

d = load_definition(path_or_yaml)   # app directory | path to the yaml file | YAML str/bytes | dict
```

`source` may be an app directory (containing `cloudgene.yaml`/`cloudgene.yml`), a path to the YAML
file itself, a YAML document as `str`/`bytes`, or an already-parsed `dict`. An invalid definition
raises `DefinitionError`, whose `.errors` is a list of human-readable messages, each prefixed with
its dotted location, e.g.:

```
workflow.inputs[2].type: unknown type "dropdown" (supported: text, string, number, ...)
```

This is the **only** parser used anywhere in the app: the workflow registry (`workflows/registry.py`,
installing/reloading an app), the public workflow API (building the run form), job submission
(server-side input validation) and the worker (building `params.json` and locating outputs) all go
through it — there is no separate per-parameter database table; the raw YAML is cached on the
`Workflow` row and re-parsed on demand, and each submitted job snapshots the YAML it was submitted
with (`Job.workflow_yaml`).

Unknown top-level keys are ignored (forward-compatible); an unknown input/output `type` or a
`workflow.steps` entry with `classname:` (a Java step from Cloudgene 3) or another unsupported
`type:`/`cmd:` produces an **error at install/reload time** for the app itself, or is recorded as a
**definition warning** and turned into a step that fails any job that reaches it with a clear
message (never silently succeeds) — see *Steps* below for exactly which case applies.

## Top-level keys

```yaml
id: hello              # required; ^[a-z0-9][a-z0-9_-]{0,63}$ — also the app directory name
name: Hello            # required
version: 1.0.0         # optional, free text
description: <p>HTML is allowed here.</p>
website: https://example.org
author: Jane Doe
logo: logo.png
category: genomics
workflow:
  steps: [...]         # required, at least one step — see Steps
  inputs: [...]         # optional — see Inputs
  outputs: [...]         # optional — see Outputs
```

- `id` must match `^[a-z0-9][a-z0-9_-]{0,63}$` (lower-case letters, digits, `-`, `_`; max 64
  chars). It is also used as the app's directory name under `$CLOUDGENE_HOME/apps/` when a
  workflow is installed with `copy: true`, and as its permanent identifier in the database — two
  installed apps cannot share an `id`.
- `name` is required; everything else at the top level is optional free text, rendered as-is
  (`description` allows HTML) in the workflow list and detail pages.
- `workflow.steps` must be a non-empty list.

## Steps

```yaml
workflow:
  steps:
    - name: Say hello        # shown in the job page's step list
      type: nextflow          # optional; this is the default whenever `script` is present
      script: main.nf          # relative to the app directory, OR a remote pipeline (owner/repo)
      revision: 1.0             # optional Nextflow -r revision (tag, branch or commit)
      params:                   # arbitrary extra key/value pairs, merged into params.json as-is
        some_flag: true
      processes:                 # optional: hints for rendering per-process progress
        - process: SAY           # must match a Nextflow process name from the trace
          label: Saying hello    # shown in the UI instead of the raw process name
          view: list              # rendering hint (free text; the frontend interprets it)
          group: ''                # optional grouping key
```

Each step runs as one `nextflow run` invocation (SPEC §3.3), in order, in the job's workspace.
`script` is resolved against the app directory; if no such file exists there it is passed through
to Nextflow as-is, so it can name a remote pipeline (e.g. `nf-core/rnaseq`). `params` is a plain
mapping merged into that step's `params.json` alongside the submitted input values, letting a
workflow author pass fixed, step-specific configuration that isn't a user-facing input.

**Only Nextflow steps are executed.** A step is parsed as unsupported — and recorded as a
definition **warning**, not an install-time error — in any of these cases:
- it has a `classname:` key (a Java/Cloudgene-3-style step), or
- it has an explicit `type:` other than `nextflow`, or
- it has a `cmd:` key and no `script:` (a shell-command step).

A workflow with an unsupported step still installs successfully (so the rest of it — the run
form, other steps — is usable), but **a job that actually reaches that step fails** with the
parser's explanatory message (e.g. `Step "Legacy" uses classname "..." (Java step); only Nextflow
steps are supported.`) — it never silently "succeeds" as a no-op.

## Inputs

Each entry under `workflow.inputs` becomes one field in the run form and one key in the job's
typed parameters. All types share these common keys:

| Key | Applies to | Meaning |
|---|---|---|
| `id` | all | required; `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, unique across inputs **and** outputs, must not be `workflow` or `job_name` (reserved multipart field names) |
| `description` (alias `label`) | all | the field's label; defaults to `id` if omitted |
| `type` | all | required; see the table below |
| `value` | most types | the default value (meaning depends on type, below) |
| `required` | most types | default `true`; `false` allows an empty/unchecked value |
| `visible` | all | default `true`; `false` hides the field from the form but it is still submitted with its default/fixed value |
| `help` | all | short help text shown next to the field |
| `details` | all | longer help text, typically shown behind a "details" disclosure |
| `serialize` | all | default `true`; `false` excludes the value from `params.json` (still shown in the UI and stored on the job) |

### Type reference

| `type` | Value semantics | Extra keys | Submitted to the pipeline as |
|---|---|---|---|
| `text`, `string` | free text; `value` is the default | — | the string, verbatim |
| `textarea` | multi-line text | `writeFile: name.txt` (plain file name, no path separators) writes the textarea's content to `input/<id>/<name.txt>` | the file's path (if `writeFile` set), else the string |
| `number` | numeric; `value`/`min`/`max` are parsed as numbers (`min <= max` enforced) | `min`, `max` | a JSON number (int or float, whichever it parses as) |
| `list` | single choice from a mapping | `values: {key: label}` (or a list of scalars / `{key, label}` mappings); a `value` not among the keys is dropped with a warning | the selected key |
| `radio` | same as `list`, rendered as radio buttons | same as `list` | the selected key |
| `checkbox` | boolean, or one of two mapped values | `values: {true: ..., false: ...}` (optional; if given, both keys are required) | `true`/`false` (or the corresponding mapped value if `values` is set); never treated as `required` — an unchecked box is a valid value |
| `terms_checkbox`, `agb_checkbox` | must be checked to submit, unless `required: false` | — | not normally consumed by the pipeline; recorded as a boolean |
| `file` | one uploaded file | `accept: .csv,.vcf.gz` (comma-separated extensions; MIME-type tokens are ignored) | the uploaded file's path under `input/<id>/` |
| `folder` | one or more uploaded files (a folder upload) | `accept` as above | the folder's path under `input/<id>/` |
| `local-file` | a server-side file path (not a browser upload) | same behaviour as `file` otherwise | the given path |
| `local-folder` | a server-side folder path | same behaviour as `folder` otherwise | the given path |
| `separator` | a visual divider | — | never submitted, never in params.json |
| `info` | display-only informational text (`description` may contain HTML) | — | never submitted, never in params.json |
| `label` | display-only label text | — | never submitted, never in params.json |

`separator`/`info`/`label` are collectively the "display" types: they are always `required: false`
and `serialize: false` regardless of what is written in the YAML.

Unknown `type` values are rejected at install/reload time with an error naming every supported
type; this is a hard error (the workflow does not install), unlike the step-level "unsupported
step" case above.

## Outputs

```yaml
workflow:
  outputs:
    - id: outdir              # required, same id rules as inputs, unique across inputs+outputs
      description: Output folder
      type: folder             # folder (default) | file | local-folder | local-file
      download: true            # default true — listed as a downloadable JobOutput after the run
      serialize: true            # default true — included as a path in params.json before the run
```

After a run, every output with `download: true` is scanned and each file found under it becomes a
`JobOutput` row (path relative to the job's `output/` directory, plus size), downloadable via `GET
/api/jobs/{id}/outputs/{file_id}/`. Symlinks are only followed when they resolve inside the job's
own workspace or its Nextflow work directory. `serialize: true` (the default) also makes the
output's expected path available to the pipeline itself via `params.json`, so a Nextflow script can
publish directly to `<job>/output/<output id>`.

## The complete example

[`docs/examples/cloudgene.yaml`](examples/cloudgene.yaml) exercises every key and type documented
above: every input type including all three display-only types, both file-upload and
local-path variants, a checkbox with a custom `values` mapping, a `textarea` with `writeFile`, a
`number` with `min`/`max`, a hidden (`visible: false`) input, a non-serialized input, multi-step
`workflow.steps` with `params`/`revision`/`processes`, and both `file`/`folder` outputs. It does
**not** ship a working `main.nf` (it is a documentation fixture, not a runnable pipeline) — it is
validated for structure only:

```python
# workflows/tests_yaml_reference_example.py
from workflows.definition import load_definition

class YamlReferenceExampleTest(TestCase):
    def test_example_is_valid(self):
        definition = load_definition('docs/examples/cloudgene.yaml')
        self.assertEqual(definition.id, 'reference-example')
        self.assertEqual(definition.warnings, [])
```

Run it with:

```
PYTHON=/home/user/cloudgene4/venv/bin/python scripts/test.sh unit
```

For a *runnable* minimal example (with a real `main.nf`), see the E2E fixture apps under
`e2e/fixtures/apps/` — in particular `hello/` (one text input, one output) and `all-inputs/` (one
input of every type used against a real Nextflow pipeline).

## Python API (for code that consumes definitions)

```python
from workflows.definition import load_definition, parse_definition, DefinitionError

d = load_definition(path_or_yaml)
# -> WorkflowDefinition(
#      id, name, version, description, website, author, logo, category,
#      steps: [Step(name, type, script, revision, params, processes, error)],
#      inputs: [InputParam(id, type, label, value, values, checkbox_values, required,
#                           visible, help, details, write_file, serialize, accept, min, max)],
#      outputs: [OutputParam(id, type, label, download, serialize)],
#      warnings: [str], app_dir: Path | None, source_path, raw: dict, yaml_text: str)

d.input('sample_name')     # -> InputParam | None
d.output('results')        # -> OutputParam | None
d.value_inputs             # inputs excluding separator/info/label
d.to_dict()                 # JSON-serialisable form used by the public workflow API
```
