# Job submission

## Purpose

Turns a `POST /api/jobs/` request into a `waiting` job. The web process checks access, service
state and queue capacity, validates every workflow input against the workflow definition, stores
uploads in a new workspace named by the job UUID, and records a snapshot of the workflow. This file
also owns the step-variable substitution (`$name` / `${name}`) and the `params.json` content that
the worker later hands to Nextflow, because both turn user input into data a process reads.

## Scope

Covered:

- `jobs/submission.py`: `submit_job`, `validate_inputs`, `clean_job_name`, `safe_filename`,
  `display_filename`, `parse_number`, `queue_is_full`, `resolve_workflow`.
- `jobs/stepvars.py`: variable table, substitution, argv splitting, shell quoting.
- `jobs/runner.py`: `build_params` only (the `params.json` content).
- `jobs/workflow_bridge.py`: `get_definition`, `definition_from_yaml`, `is_enabled`,
  `can_access`, `app_dir` as used at submission.
- The `create` action of `JobViewSet` in `jobs/views.py` (error mapping only).
- Upload limits in `cloudgene_django/settings.py` (`FILE_UPLOAD_MAX_MEMORY_SIZE`,
  `DATA_UPLOAD_MAX_MEMORY_SIZE`, `DATA_UPLOAD_MAX_NUMBER_FILES`) and their 413 mapping in
  `core/exceptions.py`.

Out of scope:

- Parsing of `cloudgene.yaml` and input types/attributes: [workflow-definition.md](workflow-definition.md).
- Workflow group access rules: [access-control.md](access-control.md).
- What happens after the job is `waiting`: [job-queue-worker.md](job-queue-worker.md).
- The Nextflow/command process itself: [job-runner.md](job-runner.md).
- Response body shape of `jobs_create` and the other job endpoints: [jobs-api.md](jobs-api.md),
  [api-contract.md](api-contract.md).
- Settings keys and defaults: [configuration.md](configuration.md).
- nginx `client_max_body_size`: deployment spec.

## Dependencies

- [api-contract.md](api-contract.md): error envelope, `jobs_create` operation.
- [workflow-definition.md](workflow-definition.md): `WorkflowDefinition`, `InputParam`
  (`id`, `type`, `required`, `visible`, `value`, `accept`, `writeFile`, `serialize`, min/max,
  list values, checkbox values), `Step.params`, `Output.serialize`.
- [access-control.md](access-control.md): `Workflow.can_access(user)`, `is_admin(user)`.
- [configuration.md](configuration.md): `server.maintenance`, `server.maintenance_message`,
  `server.max_queue_size`, `server.max_upload_mb`; `core.config.job_dir`.
- [data-model.md](data-model.md): `Job` fields.
- Operation: `jobs_create`.

## Requirements

### Who may submit, and service state

- **BE-JSUB-001** Only authenticated users may call `jobs_create`. An anonymous request MUST receive 401
  with the error envelope.
- **BE-JSUB-002** The request MUST name a workflow in `workflow` (alias `workflow_id`). A missing
  or empty value gives 400, code `invalid`, `fields.workflow`. A workflow that does not exist or
  that the user cannot access gives 404, code `not_found`, `fields.workflow` — the two cases are
  indistinguishable.
- **BE-JSUB-003** A disabled workflow MUST give 409, code `workflow_disabled`.
- **BE-JSUB-004** When `server.maintenance` is true, a non-admin submission MUST give 503, code
  `maintenance`, with `server.maintenance_message` as the message. Admins may still submit.
- **BE-JSUB-005** When `server.max_queue_size` > 0 and the number of `waiting` jobs is at least
  that value, any submission (admins included) MUST give 429, code `queue_full`, message
  `The job queue is full (<waiting> of <limit> jobs waiting). Please try again later.`
  `max_queue_size: 0` means no limit.
- **BE-JSUB-006** A workflow whose stored `cloudgene.yaml` does not parse MUST give 409, code
  `workflow_invalid`, message starting `The workflow definition is invalid:`.
- **BE-JSUB-007** Checks MUST run in this order, and the first failing check decides the
  response: workflow (400/404/409) → maintenance (503) → queue full (429) → definition (409) →
  job name (400) → inputs (400) → total upload size (413).

### Job name (K3)

- **BE-JSUB-008** The job name is optional and MUST be read from `job_name`; if `job_name` is absent and
  the workflow has no input with id `name`, the field `name` is used instead. ASCII control
  characters (`\x00`–`\x1f`, `\x7f`) are replaced by a space, then the value is trimmed. Inner
  spaces and any other Unicode characters are kept verbatim.
- **BE-JSUB-009** A name longer than 255 characters (after cleaning) MUST give 400, code `invalid`,
  `fields.job_name`. An empty name becomes `<workflow name> <YYYY-MM-DD HH:MM>` in server local
  time.
- **BE-JSUB-010** The job name MUST NOT be used in any file-system path, command line, shell text
  or Nextflow parameter. It reaches processes only as the environment variable
  `CLOUDGENE_JOB_NAME` (and, through it, as a substitution variable quoted per BE-JSUB-030).
  The workspace is named by the server-generated job UUID only.

### Input validation

- **BE-JSUB-011** All inputs MUST be validated before anything is written. If any input fails, the
  response is 400, code `invalid`, message `<first field>: <first message>`, and `fields` maps
  every failing input id to its messages. No job row and no workspace remain.
- **BE-JSUB-012** Inputs with `visible: false` MUST ignore client values: checkbox → its default
  state, terms → `true`, other non-file inputs → the YAML `value` (omitted when empty); hidden
  file inputs are omitted.
- **BE-JSUB-013** A multipart file part sent for a non-file input MUST give a field error
  `A file was uploaded for this field, which expects a text value, not a file.`
- **BE-JSUB-014** `text`/`string` values MUST be trimmed. `textarea`: `\r\n` and `\r` become `\n`, not
  trimmed. Empty (whitespace only) → `This field is required.` when required, otherwise omitted.
  More than 100 000 characters → `At most 100000 characters.`
- **BE-JSUB-015** A `textarea` with `writeFile` MUST store its content UTF-8 encoded at
  `input/<input id>/<writeFile>` and its parameter is that relative path.
- **BE-JSUB-016** `number`: the value MUST match `^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$` with
  ASCII digits only (the run form's rule); integers are stored as int, others as float; NaN and
  infinities are rejected (`Please enter a number.`); `min`/`max` give `Must be at least <min>.` /
  `Must be at most <max>.`
- **BE-JSUB-017** `list`/`radio`: the value MUST be one of the declared keys (`Select a valid
  choice.`); empty → `Please select a value.` when required.
- **BE-JSUB-018** A `checkbox` MUST be treated as checked when the value is one of `true`, `on`, `1`, `yes`, `checked`
  (case-insensitive) or equals the declared "true" value. The stored value is the declared
  true/false value, or a boolean when none is declared. A missing field means unchecked.
- **BE-JSUB-019** Terms inputs: a required terms input that is not truthy MUST give `You must accept
  this to submit the job.`
- **BE-JSUB-020** File inputs: a required input with no upload MUST give `Please select a file.`
  (folder: `Please select at least one file.`); a non-folder input with more than one upload gives
  `Only one file can be uploaded here.`; each file whose name does not end with one of the
  `accept` extensions (case-insensitive) gives `"<name>" is not an accepted file type (<accept>).`

### Uploads and workspace

- **BE-JSUB-021** On disk, an upload's file name MUST be: the basename only (both `/` and `\`
  separators), control characters removed, NFKD-folded to ASCII, every run of characters outside
  `[A-Za-z0-9._-]` replaced by `_`, leading/trailing `._-` removed, at most 150 characters
  (extension kept when ≤ 20 characters), `file` when nothing is left. Names are unique per input
  (case-insensitive) by adding `_1`, `_2`, … before the extension. User input therefore cannot
  escape `input/<input id>/` (Article 8.2).
- **BE-JSUB-022** The original display name (basename, control characters removed, ≤ 255
  characters), the relative path and the byte size of each upload MUST be stored in `Job.uploads`
  per input id.
- **BE-JSUB-023** When the total size of all uploads exceeds `server.max_upload_mb` × 1 MiB, the
  response MUST be 413, code `upload_too_large`, with the message in `fields` for every file input.
  A request with more files than `DATA_UPLOAD_MAX_NUMBER_FILES` (default 10 000, env
  `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES`) or a non-file body over `DATA_UPLOAD_MAX_MEMORY_SIZE`
  gives 413, code `upload_too_large` — never 500.
- **BE-JSUB-024** The workspace MUST be `CLOUDGENE_HOME/jobs/<job uuid>/` (see
  [configuration.md](configuration.md) for `job_dir`). Submission creates `input/`, `output/`,
  `logs/`; uploads go to `input/<input id>/<disk name>`. A file input's parameter is
  `input/<id>/<disk name>`; a folder input's parameter is `input/<id>`.
- **BE-JSUB-025** If writing files or creating the row fails, the workspace MUST be removed and no
  job row created.
- **BE-JSUB-026** A successful submission MUST create one `Job` with `status=waiting`, the typed
  parameters, the uploads metadata, and a snapshot of the workflow (`app_id`, `app_name`,
  `app_version`, `workflow_yaml`, `app_dir`), and return 201 with the `JobDetail` body.
- **BE-JSUB-027** (SHOULD) The queue-full check SHOULD be race-free, so concurrent submissions
  cannot push the number of waiting jobs above `server.max_queue_size`.

### Step variables and params.json

- **BE-JSUB-028** The variable table of a job MUST contain: every value input (string form;
  booleans `true`/`false`; file, folder and `writeFile` inputs as absolute paths inside the
  workspace; a declared input with no value as the empty string), every output id as the absolute
  path `<workspace>/output/<id>`, and every `CLOUDGENE_*` variable of the job environment.
- **BE-JSUB-029** Substitution MUST replace `$name` and `${name}` for known names in one pass;
  substituted values are never re-scanned; unknown names and `$` not followed by an identifier are
  left unchanged.
- **BE-JSUB-030** User values MUST NOT be interpreted by a shell. In argv mode (`bash: false`) the
  template is split with POSIX shell-word rules first and each token is substituted afterwards, so
  a value is always part of exactly one argument. In bash mode (`bash: true`) each value is quoted
  for the quoting context it lands in (unquoted: single-quoted word; inside `"…"`: `\`, `"`, `$`,
  `` ` `` escaped; inside `'…'`: `'` closed/escaped/reopened), so it is one literal word.
- **BE-JSUB-031** `params.json` for step N MUST be `<workspace>/params.json` (N = 1) or
  `<workspace>/step<N>-params.json` (N ≥ 2), UTF-8 JSON. It contains the step's `params`
  (strings substituted recursively through lists and maps), then every input with `serialize`
  true and a non-null value (file/folder/`writeFile` inputs as absolute paths), then every output
  with `serialize` true as its absolute output path. Later entries win on equal keys.

## Interfaces

Endpoint: `jobs_create` (`POST /api/jobs/`, multipart or JSON). The request body is
`JobSubmitRequestRequest` in `schema.yaml` (`workflow`, `job_name`) plus one field per workflow
input id (file parts for file inputs). Response: `JobDetail`. See [jobs-api.md](jobs-api.md).

Errors raised by `jobs.submission.SubmissionError(message, code, status, fields)` and rendered
with the error envelope:

| Status | code | Cause |
|--------|------|-------|
| 400 | `invalid` | missing workflow, bad job name, input errors |
| 401 | (DRF) | anonymous |
| 404 | `not_found` | unknown or inaccessible workflow |
| 409 | `workflow_disabled` | workflow disabled |
| 409 | `workflow_invalid` | stored YAML does not parse |
| 413 | `upload_too_large` | total size, too many files, body too big |
| 429 | `queue_full` | waiting jobs ≥ `server.max_queue_size` |
| 503 | `maintenance` | maintenance mode, non-admin |

Python helpers used elsewhere: `jobs.submission.safe_filename`, `display_filename`,
`parse_number`; `jobs.stepvars.build_variables`, `substitute`, `substitute_params`,
`split_command`, `quote_into_shell`; `jobs.runner.build_params`.

Workspace after submission:

```
CLOUDGENE_HOME/jobs/<uuid>/
  input/<input id>/<disk name>       uploads (file / folder inputs)
  input/<input id>/<writeFile>       textarea content
  output/
  logs/
```

## Behaviour

1. `resolve_workflow` → maintenance → `queue_is_full` → parse definition → `clean_job_name` →
   `validate_inputs` (collects all errors) → total-size check.
2. A UUID4 is generated; the workspace and its sub-directories are created; uploads are streamed
   to disk chunk by chunk; `writeFile` texts are written; the row is created in a transaction.
   Any exception removes the workspace and re-raises.
3. The job then waits for the worker ([job-queue-worker.md](job-queue-worker.md)); the worker
   builds `params.json` and the variable table at step start from `Job.parameters`.

Edge cases:

- DRF merges file parts into `request.data`; BE-JSUB-013 stops a file part from masquerading as a
  text value.
- Folder uploads are flattened: only each file's basename is kept, collisions get `_N`.
- A crash between creating the workspace and committing the row leaves a directory without a row;
  `cleanup_jobs` removes it after one hour ([job-queue-worker.md](job-queue-worker.md#behaviour)).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| 001, 002, 003 | `jobs/tests/test_api.py::SubmissionTest::test_workflow_access_and_disabled` | unit |
| 004 | `jobs/tests/test_api.py::SubmissionTest::test_maintenance_blocks_users_not_admins`; `e2e/tests/test_queue.py::test_maintenance_blocks_users_not_admins` | unit, e2e |
| 005 | `jobs/tests/test_api.py::SubmissionTest::test_queue_full`; `e2e/tests/test_queue.py::test_queue_full_rejects_submission` | unit, e2e |
| 006 | `jobs/tests/test_api.py::SubmissionTest::test_invalid_definition_gives_409` (planned) | unit |
| 007 | `jobs/tests/test_api.py::SubmissionTest::test_check_order` (planned) | unit |
| 008, 009 | `jobs/tests/test_api.py::SubmissionTest::test_name_too_long_and_control_chars`, `::test_legacy_name_field_and_json_body`, `::test_all_input_types_are_resolved_and_stored`; `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` | unit, e2e |
| 009 (default name) | `jobs/tests/test_api.py::SubmissionTest::test_defaults_and_unchecked_checkbox` | unit |
| 010 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_injection_is_literal_in_both_modes` (inputs only); `jobs/tests/test_worker.py::test_job_name_never_in_argv_or_paths` (planned) | e2e, unit |
| 011 | `jobs/tests/test_api.py::SubmissionTest::test_field_errors` (also asserts no row and no workspace); `e2e/tests/test_run_form.py::test_server_validation_field_errors` | unit, e2e |
| 012, 014, 015, 017, 018 | `jobs/tests/test_api.py::SubmissionTest::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox` | unit |
| 013 | `jobs/tests/test_api.py::SubmissionTest::test_file_part_for_text_input_is_rejected`; `e2e/tests/test_findings_jobs.py::test_a01_file_part_for_text_input_is_rejected` | unit, e2e |
| 016 | `jobs/tests/test_api.py::SubmissionTest::test_number_min_and_nan`, `::test_number_rejects_what_the_run_form_rejects`; `e2e/tests/test_findings_jobs.py::test_a05_number_input_rejects_values_the_form_rejects` | unit, e2e |
| 019 | `jobs/tests/test_api.py::SubmissionTest::test_field_errors` | unit |
| 020 | `jobs/tests/test_api.py::SubmissionTest::test_file_accept_and_single_file`, `::test_field_errors` | unit |
| 021, 022, 024 | `jobs/tests/test_api.py::SafeFilenameTest::test_names`, `SubmissionTest::test_all_input_types_are_resolved_and_stored`; `e2e/tests/test_jobs.py::test_all_inputs_uploads_folder_and_write_file` | unit, e2e |
| 023 | `jobs/tests/test_api.py::SubmissionTest::test_upload_size_limit`, `::test_many_files_in_folder_input_is_a_client_error_not_500`; `e2e/tests/test_findings_jobs.py::test_a02_many_files_in_folder_input_is_a_client_error` | unit, e2e |
| 025 | `jobs/tests/test_api.py::SubmissionTest::test_failed_write_removes_workspace` (planned) | unit |
| 026 | `jobs/tests/test_api.py::SubmissionTest::test_all_input_types_are_resolved_and_stored` | unit |
| 028–030 | `jobs/tests/test_command_steps.py::SubstitutionTest` (all tests), `CommandStepWorkerTest::test_injection_is_literal_in_both_modes` | unit |
| 031 | `jobs/tests/test_api.py::SubmissionTest::test_all_input_types_are_resolved_and_stored`; `jobs/tests/test_command_steps.py::SubstitutionTest::test_params_substitution_is_recursive_and_only_touches_strings` | unit |

## Known gaps

| Req | What the code does | Where | Severity |
|-----|--------------------|-------|----------|
| BE-JSUB-027 | Counts waiting jobs and then inserts without a lock, so concurrent submissions can exceed `max_queue_size`. | `jobs/submission.py:286-289`, `:314-318` | minor |
| BE-JSUB-023 | `max_upload_mb` is checked only after Django has received and spooled the whole body to temp files; the only earlier guard is nginx `client_max_body_size`. | `jobs/submission.py:336-341`, `cloudgene_django/settings.py:295-296` | minor |
| BE-JSUB-008 | Only ASCII control characters are removed; C1 controls (`\x80`–`\x9f`) and Unicode format characters (e.g. U+202E) are kept in job names and display file names. | `jobs/submission.py:32` | minor |
| BE-JSUB-002 | The alias `workflow_id` and the `name` alias of `job_name` are accepted but not declared in `JobSubmitRequestRequest` in `schema.yaml` (Article 5.1a). | `jobs/submission.py:307`, `:326-328`; `jobs/serializers.py:185-189` | minor |
| BE-JSUB-006, 007, 025 | No test for invalid stored YAML at submission, for check order, or for workspace removal on a failed write. | `jobs/tests/test_api.py` | minor |

## Open questions

- Folder uploads lose their sub-directory structure (basename only). Should relative paths
  (`webkitRelativePath`) be preserved, safely, under `input/<id>/`?
- Should 429 `queue_full` and 503 `maintenance` carry a `Retry-After` header?
- Should the queue limit apply to admins, as it does today?
