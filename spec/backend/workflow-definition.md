# Workflow definition (`cloudgene.yaml`)

## Purpose

A workflow ("app") is described by one `cloudgene.yaml` file. `workflows/definition.py` is the
single parser and validator for that file. It turns YAML into a typed `WorkflowDefinition`
(metadata, steps, inputs, outputs, warnings) or raises `DefinitionError` with a list of
located messages. The registry, the public workflow API (run-form schema), job submission and
the runner all read workflows only through this parser, so its contract is what a valid app
is.

## Scope

- `workflows/definition.py` — loading, validation, defaults, `to_dict()` shapes.
- Fixtures: `workflows/test_fixtures/apps/*`, `workflows/fixtures/taxodactyl-v1.5.0.yml`.

Out of scope:
- How the registry stores the parsed result → [workflow-registry.md](workflow-registry.md).
- How submitted values are checked against inputs → [job-submission.md](job-submission.md).
- How steps run (`script`, `cmd` substitution, `$name` quoting) →
  [job-runner.md](job-runner.md).
- How processes / outputs are tracked at run time →
  [job-progress-outputs.md](job-progress-outputs.md).
- The author-facing YAML reference in `docs/` (Article 1.3).

## Dependencies

- None at run time (pure module: PyYAML `safe_load`, no DB, no settings).
- Consumers: [workflow-registry.md](workflow-registry.md), [workflows-api.md](workflows-api.md)
  (`workflows_list`, `workflows_retrieve` expose `inputs`/`outputs` built from `to_dict()`).

## Requirements

Loading

- **BE-WDEF-001** `load_definition(source)` MUST accept: a path (`str` or `os.PathLike`) to an
  app directory or YAML file; a YAML document as `str` or `bytes` (UTF-8); or an
  already-parsed `dict`. Any other type MUST raise `DefinitionError`
  (`Unsupported definition source: <type>`).
- **BE-WDEF-002** A directory source MUST resolve to `cloudgene.yaml`, else `cloudgene.yml`, in
  that order. A directory with neither MUST raise `DefinitionError` (`No cloudgene.yaml found in
  <dir>`); a non-existent path MUST raise `Workflow definition not found: <path>`.
- **BE-WDEF-003** A `str` is treated as a path when it is a single non-blank line and the path
  exists, ends in `.yaml`/`.yml`, or starts with `/` or `./`. Otherwise it is YAML text. A
  single-line string that parses to a YAML scalar MUST raise `Workflow definition not found`.
- **BE-WDEF-004** YAML MUST be parsed with a safe loader. A parse failure MUST raise
  `DefinitionError` with one message starting `Invalid YAML:`. A non-mapping document MUST
  raise `The workflow definition must be a YAML mapping`.
- **BE-WDEF-005** When loaded from a path, the result MUST carry `app_dir` (directory of the
  YAML file), `source_path`, and `yaml_text` (the exact file text). When loaded from text,
  `app_dir` and `source_path` are `None` and `yaml_text` is the text. A `dict` source yields
  `yaml_text == ''`.

Errors and warnings

- **BE-WDEF-006** Validation MUST collect every error before failing, and raise one
  `DefinitionError` whose `errors` is a list of strings, each prefixed by the dotted location
  of the offending key (`id: …`, `workflow.inputs[2].type: …`,
  `workflow.steps[0].cmd: …`). `str(DefinitionError)` is the messages joined by `"; "`.
- **BE-WDEF-007** Non-fatal problems MUST be returned in `WorkflowDefinition.warnings` (located
  the same way) and MUST NOT prevent loading. The warnings are: an unsupported step (BE-WDEF-013)
  and a list/radio default that is not one of its values (BE-WDEF-020).

Top-level keys

- **BE-WDEF-008** `id` is required and MUST match `^[a-z0-9][a-z0-9_-]{0,63}$`. An `id` that
  YAML reads as a boolean (e.g. `yes`) MUST be an error telling the author to quote it.
- **BE-WDEF-009** `name` MUST be present (non-blank after trimming).
- **BE-WDEF-010** `version`, `description`, `website`, `author`, `logo`, `category` are optional
  strings, default `''`. Non-string scalars MUST be converted with `str()` (booleans to
  `'true'`/`'false'`). Their content is passed through unmodified (no HTML escaping, no URL
  validation); see BE-WDEF-031.
- **BE-WDEF-011** `workflow` is required and MUST be a mapping. `workflow.steps` MUST be a
  non-empty list. `workflow.inputs` and `workflow.outputs` are optional lists; when present and
  not a list, the error is `workflow.<key>: must be a list`.

Steps

- **BE-WDEF-012** Each step MUST be a mapping. `name` defaults to `Step`. `stdout` and `stderr`
  are booleans (default `false`) on every step type.
- **BE-WDEF-013** Step type resolution, in order:
  1. `classname` present → `type: unsupported` (Java step);
  2. `type: command`, or no `type`, no `script`, and `cmd` or `exec` present → command step;
  3. `type` present and not `nextflow` → `type: unsupported`;
  4. otherwise → Nextflow step.
  An unsupported step MUST load (not an error), set `step.error` to a message naming the step,
  and add that message to `warnings`. `Step.supported` is true only for `nextflow` and
  `command`.
- **BE-WDEF-014** Nextflow step: `script` defaults to `main.nf`; `revision` defaults to `''`;
  `params` MUST be a mapping (default `{}`) and is kept verbatim; `processes` MUST be a list of
  mappings each with a non-empty `process`. Each process is normalised to
  `{process, label, view, group}` with `view` defaulting to `list` and the others to `''`.
- **BE-WDEF-015** Command step: `cmd` (alias `exec`, which wins when both are set) is required,
  MUST be a non-blank string, and is stored verbatim. `bash` is a boolean (default `false`).
  When `bash` is false, `cmd` MUST split with POSIX shell rules (`shlex`) into at least one
  argument; unbalanced quotes are an error that suggests `bash: true`.

Inputs

- **BE-WDEF-016** Each input MUST be a mapping with `id` and `type`. `id` MUST match
  `^[A-Za-z_][A-Za-z0-9_]{0,63}$` and MUST NOT be `workflow` or `job_name` (reserved multipart
  field names). `type` MUST be one of: `text`, `string`, `number`, `textarea`, `list`, `radio`,
  `checkbox`, `file`, `folder`, `local-file`, `local-folder`, `separator`, `info`, `label`,
  `terms_checkbox`, `agb_checkbox`. Unknown types are errors that list the supported types.
- **BE-WDEF-017** Every input MUST get these common attributes and defaults: `label` from `description`,
  else `label`, else the id; `required` true; `visible` true; `serialize` true; `help`,
  `details`, `accept` `''`. Boolean attributes accept YAML booleans or the strings
  `true/yes/1/false/no/0` (case-insensitive); anything else is the error `must be true or false`.
- **BE-WDEF-018** Text types (`text`, `string`, `textarea`): `value` is a string (default `''`).
  `writeFile` (alias `write_file`) is allowed only on `textarea` and MUST be a plain file name:
  non-empty, no `/` or `\`, not `.`/`..`, not starting with `.`.
- **BE-WDEF-019** `number`: `value`, `min`, `max` are numbers or absent (`None`); integer-looking
  values stay `int`, others `float`. Booleans and non-numeric strings are errors. `min > max`
  MUST be an error.
- **BE-WDEF-020** `list` / `radio`: `values` is required with at least one entry and no duplicate
  keys. Accepted forms: a mapping `key: label`; a list of scalars (key = label); a list of
  `{key|value, label}` mappings. Values normalise to `[{key, label}]` (strings). `value` is a
  string default (`''` when absent); a default that is not one of the keys MUST be replaced by
  `''` with a warning.
- **BE-WDEF-021** `checkbox`: optional `values` MUST be a mapping with both `true` and `false`
  keys and becomes `checkbox_values = {true: …, false: …}`. `value` is a boolean: true for
  `true/yes/1/on` or when equal to the mapped `true` value, else false. `required` is always
  forced to `false`.
- **BE-WDEF-022** `terms_checkbox` / `agb_checkbox`: `value` MUST always be `false` (any YAML `value`
  is ignored); `required` keeps its configured value (default true = must be ticked).
- **BE-WDEF-023** File types (`file`, `folder`, `local-file`, `local-folder`): `value` MUST be `None`.
  `folder` and `local-folder` accept several files. `accept` is kept verbatim; its
  extension list (`accept_extensions`) is the comma-separated tokens starting with `.`,
  lower-cased; other tokens (MIME types) are ignored.
- **BE-WDEF-024** Display types (`separator`, `info`, `label`): `value` MUST be the string `value`;
  `required` and `serialize` are forced to `false`. They are excluded from `value_inputs`.

Outputs

- **BE-WDEF-025** Each output MUST be a mapping with an `id` following the input id rules
  (BE-WDEF-016). `type` defaults to `folder` and MUST be one of `folder`, `file`,
  `local-folder`, `local-file`. `label` follows the input rule; `download` and `serialize`
  default to true.
- **BE-WDEF-026** Ids MUST be unique across inputs and outputs together; a clash is reported as
  `workflow.<kind>: duplicate id "<id>" (also in <kind>)`.

Result shape

- **BE-WDEF-027** `WorkflowDefinition.to_dict()` MUST return exactly the keys `id, name, version,
  description, website, author, logo, category, steps, inputs, outputs, warnings`;
  `InputParam.to_dict()` exactly `id, type, label, value, values, checkbox_values, required,
  visible, help, details, write_file, serialize, accept, min, max`; `OutputParam.to_dict()`
  exactly `id, type, label, download, serialize`; `Step.to_dict()` exactly `name, type, script,
  revision, params, processes, error, cmd, bash, stdout, stderr`. Inputs and outputs keep YAML
  order.
- **BE-WDEF-028** The parser MUST be pure: no database, settings or network access, and no
  writes. Parsing the same text twice MUST give equal results.

Content trust

- **BE-WDEF-031** `description`, input `label`/`help`/`details` and `logo` are author (admin)
  content and MAY contain HTML. The parser MUST NOT alter them; any consumer that renders them
  as HTML is responsible for the trust decision (see Open questions).

Planned

- **BE-WDEF-029** (planned) A `number` default outside `[min, max]` SHOULD be an error.
- **BE-WDEF-030** (planned) Unknown keys at the top level, on a step, input or output SHOULD
  produce a warning naming the key (today they are silently ignored).

## Interfaces

```
load_definition(source) -> WorkflowDefinition        # raises DefinitionError
parse_definition(data: dict, app_dir=None) -> WorkflowDefinition
find_definition_file(path) -> Path                   # dir/file -> cloudgene.yaml
DefinitionError(errors).errors: list[str]

WorkflowDefinition: id, name, version, description, website, author, logo, category,
    steps[Step], inputs[InputParam], outputs[OutputParam], warnings[str],
    app_dir, source_path, raw (the parsed dict), yaml_text
    .input(id) / .output(id) -> item | None
    .value_inputs -> inputs that are not display types
InputParam: .is_display .is_file .is_folder .is_terms .value_keys .accept_extensions
OutputParam: .is_folder
Step: .supported

Constants: INPUT_TYPES, OUTPUT_TYPES, DISPLAY_TYPES, FILE_TYPES, RESERVED_FIELDS
```

Error message examples (exact text is not normative, the `<location>: ` prefix is):

```
id: is required
id: "Bad Id" must match ^[a-z0-9][a-z0-9_-]{0,63}$
workflow.steps: at least one step is required
workflow.inputs[0].type: unknown type "app_list" (supported: text, string, …)
workflow.inputs[1].id: "workflow" is reserved
workflow.inputs[3].values: needs both true and false keys
workflow.steps[0].cmd: cannot be split into arguments (No closing quotation); fix the quoting or set bash: true
workflow.outputs: duplicate id "x" (also in inputs)
```

## Behaviour

1. `load_definition` resolves the source (BE-WDEF-001..003), reads the text as UTF-8 (read or
   decode failure → `Cannot read <path>: …`), safe-loads it, then calls `parse_definition`.
2. `parse_definition` validates top-level keys, then steps, then inputs, then outputs, then
   cross-list id uniqueness, appending to one error list. Items whose `type` is missing or
   unknown are dropped from further checks (so they never cause a duplicate-id error).
3. If any error was recorded, `DefinitionError(errors)` is raised; otherwise the definition
   is returned with its warnings.
4. Values are coerced, not rejected, where Cloudgene 2/3 YAML relied on it: scalar strings
   via `str()`, YAML booleans in keys/values to `'true'`/`'false'`.

Edge cases:
- A step with both `script` and `cmd` and no `type` is a Nextflow step (`cmd` ignored).
- `type: NextFlow` is accepted (type is lower-cased for steps only; input types are
  case-sensitive).
- A hidden (`visible: false`) required input with no default is valid; submission decides
  what happens.
- YAML number coercion happens before the parser: `version: 1.10` arrives as float `1.1`.

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| 001, 002, 005 | `workflows/test_definition.py::LoadDefinitionTest::test_load_from_dir_and_file` | unit |
| 002, 003 | `workflows/test_definition.py::LoadDefinitionTest::test_missing_path_string` | unit |
| 004 | `workflows/test_definition.py::LoadDefinitionTest::test_invalid_yaml` | unit |
| 006, 008, 009, 011 | `workflows/test_definition.py::LoadDefinitionTest::test_required_fields` | unit |
| 006, 016, 026 | `workflows/test_definition.py::LoadDefinitionTest::test_invalid_ids_and_duplicates`, `::test_unknown_input_type` | unit |
| 007, 013 | `workflows/test_definition.py::LoadDefinitionTest::test_unsupported_steps_load_with_error` | unit |
| 008 (boolean id) | (planned) `LoadDefinitionTest::test_boolean_id_must_be_quoted` | unit |
| 010, 014, 017–025, 027 | `workflows/test_definition.py::LoadDefinitionTest::test_all_input_types` | unit |
| 014 | `workflows/test_definition.py::LoadDefinitionTest::test_default_script_is_main_nf` | unit |
| 018, 019, 020, 021 | `workflows/test_definition.py::LoadDefinitionTest::test_list_needs_values_and_number_bounds` | unit |
| 020 | `workflows/test_definition.py::LoadDefinitionTest::test_bad_default_for_list_is_ignored_with_warning` | unit |
| 021 | `workflows/test_definition.py::LoadDefinitionTest::test_checkbox_default_by_mapped_value` | unit |
| 012, 015 | `workflows/test_definition.py::CommandStepParsingTest::*` (all six) | unit |
| 013–016, 023 | `workflows/test_definition.py::CommandStepParsingTest::test_taxodactyl_definition` | unit |
| 016, 024 | `workflows/tests_yaml_reference_example.py::YamlReferenceExampleTest::*` | unit |
| 018 (unsafe writeFile name) | (planned) `LoadDefinitionTest::test_write_file_must_be_plain_name` | unit |
| 022 | (planned) `LoadDefinitionTest::test_terms_value_ignored` | unit |
| 028 | (planned) `LoadDefinitionTest::test_parse_is_deterministic` | unit |
| 031 | `workflows/test_definition.py::LoadDefinitionTest::test_all_input_types` (`description: <b>demo</b>` loads; value not asserted — (planned) assert it is unchanged) | unit |
| 016–024 (form rendering end to end) | `e2e/tests/test_run_form.py::test_all_input_types_render_with_defaults` | e2e |

## Known gaps

| Requirement | What the code does | Where | Severity |
|---|---|---|---|
| BE-WDEF-029 | A `number` `value` outside `min`/`max` loads without error or warning; the run form then shows an out-of-range default. | `workflows/definition.py:363-368` | minor |
| BE-WDEF-030 | Unknown keys (typos such as `requried`, `defualt`) are silently ignored at every level. | `workflows/definition.py:325-398`, `:514-577` | minor |
| BE-WDEF-010 | Non-string `version` values are stringified after YAML coercion, so `1.10` becomes `'1.1'` with no warning. | `workflows/definition.py:572` | minor |
| BE-WDEF-008 | No test covers the boolean-id error branch. | `workflows/definition.py:522-523` | minor |

## Open questions

- `description`, input labels and `logo` are rendered as raw HTML by the SPA (`v-html`). The
  current trust model is "only admins install apps, so app YAML is trusted". Should the
  backend sanitise these fields, or should the frontend spec own sanitisation? (Article 8.2.)
- Nextflow `script` may be absolute or contain `..`; it is not constrained to the app
  directory. Acceptable under the admin-trusted model, or should the parser reject it?
- Should unsupported steps (Java `classname`, other `type`s) stay loadable with a warning, or
  become errors so the app is never offered to users?
