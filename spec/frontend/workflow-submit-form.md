# Workflow submit form

## Purpose

The run page (`/run/:workflowId`) loads one workflow, renders its inputs as a form generated
from the typed run-form schema, checks the values in the browser with the same rules the server
uses, and submits a multipart request that creates a job. On success the user lands on the job
page. The client checks exist to save a round trip; the server stays authoritative and its
field errors are shown on the same fields.

## Scope

Covered:

- `frontend/src/views/public/WorkflowSubmitView.vue` — load, page header, job name, submit,
  error mapping, redirect.
- `frontend/src/components/workflows/form/DynamicForm.vue` — per-input wrapper, display types,
  visibility.
- `frontend/src/components/workflows/form/ParamInput.vue` — one control per value input type.
- `frontend/src/components/workflows/form/formModel.js` — defaults, client validation,
  multipart payload, `formatBytes`.
- The calls `getWorkflow` (`frontend/src/api/workflows.js`) and `submitJob`
  (`frontend/src/api/jobs.js`) as used here.

Out of scope:

- Route guard mechanics and the login redirect → [routing.md](routing.md).
- `apiErrorMessage` / `apiFieldErrors`, CSRF header, 401 handling → [api-client.md](api-client.md).
- `AlertMessage`, `LoadingSpinner` → [common-components.md](common-components.md).
- Maintenance banner → [layout-navigation.md](layout-navigation.md).
- The job page reached after submission → [job-detail.md](job-detail.md).
- Workflow cards linking to this page → [home-static-pages.md](home-static-pages.md).
- Server-side parsing of inputs → [../backend/workflow-definition.md](../backend/workflow-definition.md);
  server-side validation and storage → [../backend/job-submission.md](../backend/job-submission.md).

## Dependencies

- [../backend/workflows-api.md](../backend/workflows-api.md) — `workflows_retrieve` visibility
  (BE-WAPI-001, -002), `definition_errors` (BE-WAPI-006), `max_upload_mb` (BE-WAPI-004).
- [../backend/workflow-definition.md](../backend/workflow-definition.md) — input types and
  attribute defaults (BE-WDEF-016 to -024), HTML in labels (BE-WDEF-031).
- [../backend/job-submission.md](../backend/job-submission.md) — field names, validation
  messages, error codes and check order (BE-JSUB-001 to -023).
- [api-contract.md](api-contract.md), [../backend/api-contract.md](../backend/api-contract.md) —
  `workflows_retrieve` (`Workflow`, `WorkflowInput`), `jobs_create`
  (`JobSubmitRequestRequest`, `JobDetail`), error envelope.
- [api-client.md](api-client.md) — `apiErrorMessage`, `apiFieldErrors`, FormData content type.
- [routing.md](routing.md) — `requiresAuth` guard.

## Requirements

Access and loading

- **FE-FORM-001** The route `/run/:workflowId` MUST require authentication (`meta.requiresAuth`).
  An anonymous visitor MUST be sent to login (see [routing.md](routing.md)) and no form is shown.
- **FE-FORM-002** On mount the view MUST call `getWorkflow(workflowId)` (`workflows_retrieve`)
  once and show a spinner until it settles.
- **FE-FORM-003** If the call fails with 404 the view MUST show `Workflow not found.` in the
  `run-error` alert and no form. Any other failure MUST show `apiErrorMessage(error)`. The same
  404 text MUST be shown for a workflow the user may not access (the API does not distinguish
  them, BE-WAPI-002).
- **FE-FORM-004** On success the header MUST show the workflow `name` (`workflow-title`) and
  `version` (`workflow-version`), and the `description` when non-empty.
- **FE-FORM-005** When `definition_errors` is non-empty the view MUST show
  `This workflow is misconfigured: <errors joined by '; '>` (`workflow-definition-error`).
- **FE-FORM-006** (planned) When `definition_errors` is non-empty the submit button SHOULD be
  disabled, since the server rejects the submission (409 `workflow_invalid`, BE-JSUB-006).

Rendering (one wrapper per input, in `inputs` order)

- **FE-FORM-007** Every input that is rendered MUST have a wrapper with
  `data-testid="input-<id>"`; value inputs also carry `data-type="<type>"`.
- **FE-FORM-008** An input with `visible: false` MUST NOT be rendered and MUST NOT be sent; the
  server applies its default (BE-JSUB-012).
- **FE-FORM-009** Display types MUST render as: `separator` → `<hr>`; `info` → an
  `alert-info` box with `label` as content; `label` → a muted paragraph with `label` as content.
  They have no value and are never sent.
- **FE-FORM-010** Value controls per type MUST be:

  | Type | Control | Notes |
  |------|---------|-------|
  | `text`, `string` | `<input type=text>` | |
  | `number` | `<input type=number step=any>` | `min`/`max` attributes set when not null |
  | `textarea` | `<textarea rows=5>` | `write_file` is server-side only |
  | `list` | `<select>` with one `<option>` per `values[]` (`key` → value, `label` → text) | an empty `— select —` option is present when the input is optional or has no value |
  | `radio` | one radio per `values[]`, `name` shared | |
  | `checkbox` | one checkbox, label beside it | `checkbox_values` not used by the client |
  | `terms_checkbox`, `agb_checkbox` | one checkbox, label beside it | always starts unchecked |
  | `file`, `local-file` | `<input type=file>` without `multiple` | `accept` attribute = `accept` |
  | `folder`, `local-folder` | `<input type=file multiple>` | individual files, not a directory picker |

- **FE-FORM-011** Initial values MUST come from `value` (BE-WDEF-017 to -024): text, number,
  list, radio → `String(value)` or `''` when null; `checkbox` → `value === true`; terms → `false`;
  file types → no files.
- **FE-FORM-012** A required marker `*` MUST be shown after the label of a required value input
  other than `checkbox`; a terms input shows it unless `required` is `false`. A `checkbox` never
  shows it.
- **FE-FORM-013** `help` that starts with `http://` or `https://` MUST render as a help icon link
  (`a[title=Help]`, `target=_blank`, `rel=noopener`). Other `help` and every `details` MUST render
  as escaped text below the control. For upload inputs with `accept`, the text
  `Accepted: <accept>` MUST be shown.
- **FE-FORM-014** For upload inputs the chosen files MUST be listed (`files-<id>`) with name and
  size (`formatBytes`: B, KB, MB, GB, TB, one decimal above bytes), each with a remove button.
  Choosing files again MUST replace the list.

HTML rendering (Article 8.2)

- **FE-FORM-015** Only these admin-authored fields MAY be rendered as HTML (`v-html`): workflow
  `description`, and input `label` (value inputs, `info`, `label`). The trust basis is that only
  admins install workflows (BE-WDEF-031). `help`, `details`, `accept`, list/radio option labels,
  `definition_errors`, the workflow `name`/`version`, file names and every server error message
  MUST be rendered as escaped text.
- **FE-FORM-016** A `help` value MUST become a link `href` only when it matches
  `^https?://`; any other scheme (`javascript:`, `data:`) MUST be shown as text.
- **FE-FORM-017** (planned) HTML from `description` and `label` SHOULD be sanitised (allow-list of
  inline formatting and links) before insertion, so a compromised or careless workflow cannot run
  script in users' sessions.

Job name

- **FE-FORM-018** A `Job name (optional)` text field (`job-name`) MUST be shown above the inputs,
  empty by default, with placeholder `<workflow name> <date>` and `maxlength=255`.
- **FE-FORM-019** The job name MUST be sent verbatim as `job_name`, including leading, trailing
  and inner spaces and any Unicode; trimming and the default name are server-side (BE-JSUB-008,
  -009). An empty field sends `job_name=''`.
- **FE-FORM-020** A job name whose trimmed length exceeds 255 characters MUST block submission
  with `At most 255 characters.` under the field (`error-job_name`).

Client validation (mirrors BE-JSUB-014 to -020, BE-JSUB-023)

- **FE-FORM-021** On submit the view MUST validate all visible value inputs before any request.
  If any rule fails, no request MUST be sent, each failing input MUST show its message
  (`error-<id>`, control gets `is-invalid`), and `run-error` MUST show
  `Please correct the highlighted fields.` (or the upload-size message, FE-FORM-024).
- **FE-FORM-022** The client messages MUST be identical to the server's:

  | Rule | Message |
  |------|---------|
  | required text/number/textarea empty (whitespace only) | `This field is required.` |
  | required list/radio empty | `Please select a value.` |
  | list/radio value not among `values[].key` | `Select a valid choice.` |
  | number not matching `^[+-]?(\d+\.?\d*\|\.\d+)([eE][+-]?\d+)?$` | `Please enter a number.` |
  | number < `min` / > `max` | `Must be at least <min>.` / `Must be at most <max>.` |
  | terms with `required !== false` not ticked | `You must accept this to submit the job.` |
  | required file / folder with no files | `Please select a file.` / `Please select at least one file.` |
  | more than one file on a non-folder input | `Only one file can be uploaded here.` |
  | file name not ending in an `accept` extension (case-insensitive; MIME tokens ignored) | `"<name>" is not an accepted file type (<accept>).` |

- **FE-FORM-023** `checkbox` inputs MUST NOT be validated (unchecked is a valid value).
- **FE-FORM-024** When the summed size of all selected files exceeds `max_upload_mb` × 1 MiB,
  submission MUST be blocked and `run-error` MUST show
  `Uploads exceed the maximum total size of <max_upload_mb> MB.`

Payload (`jobs_create`)

- **FE-FORM-025** The view MUST call `submitJob(formData)` (`jobs_create`, `POST /api/jobs/`)
  with a `FormData` body; the client MUST NOT set `Content-Type` itself (see
  [api-client.md](api-client.md)).
- **FE-FORM-026** The body MUST contain: `workflow` = workflow `id` (never `workflow_id`),
  `job_name` (FE-FORM-019), and one field per visible value input named by the input `id`:
  - text, number, textarea, list, radio: the value as typed, omitted when empty;
  - `checkbox` and terms: always sent, `true` or `false`;
  - file types: one file part per selected file, with the original file name.
  Display inputs and hidden inputs MUST NOT be sent.

Submit, result and errors

- **FE-FORM-027** While the request is in flight the submit button (`job-submit`) MUST be disabled
  and read `Submitting…` with a spinner, and all generated controls MUST be disabled. Otherwise it
  reads `Submit Job`.
- **FE-FORM-028** On 201 the view MUST navigate to `/jobs/<id>` using the `id` of the returned
  `JobDetail`.
- **FE-FORM-029** On failure the view MUST show every `error.fields` entry whose key is an input
  id or `job_name` under that field (messages joined by a space) and MUST show
  `apiErrorMessage(error, 'Job submission failed.')` in `run-error`. The user stays on the page
  and keeps all entered values and selected files.
- **FE-FORM-030** The server's status codes MUST surface as follows (messages come from the
  envelope, BE-JSUB-001 to -023):

  | Status / code | What the user sees |
  |---------------|--------------------|
  | 400 `invalid` | field errors + `<first field>: <first message>` |
  | 401 | redirect to login ([api-client.md](api-client.md), [routing.md](routing.md)) |
  | 403 `csrf_failed` | envelope message |
  | 404 `not_found` | envelope message (workflow removed or access revoked since load) |
  | 409 `workflow_disabled` / `workflow_invalid` | envelope message |
  | 413 `upload_too_large` | envelope message + the message under every file input |
  | 429 `queue_full` | `The job queue is full (… jobs waiting). Please try again later.` |
  | 503 `maintenance` | the configured `server.maintenance_message` |
  | network failure | `Cannot reach the server. Check your connection.` |

- **FE-FORM-031** The view MUST NOT pre-check maintenance or queue state; the server decides
  (admins may submit during maintenance, BE-JSUB-004).

## Interfaces

Operations (by operationId, see [api-contract.md](api-contract.md)):

| operationId | API function | Used for |
|-------------|--------------|----------|
| `workflows_retrieve` | `getWorkflow(id)` → `GET /api/workflows/{id}/` | form schema |
| `jobs_create` | `submitJob(formData)` → `POST /api/jobs/` | submission |

Fields read from `Workflow`: `id`, `name`, `version`, `description`, `inputs`,
`definition_errors`, `max_upload_mb`. Fields read from `WorkflowInput`: `id`, `type`, `label`,
`value`, `values[].key/label`, `required`, `visible`, `help`, `details`, `accept`, `min`, `max`.
Not read: `checkbox_values`, `write_file`, `serialize`. Field read from `JobDetail`: `id`.

`formModel.js` exports (pure functions):

```
DISPLAY_TYPES, FILE_TYPES, FOLDER_TYPES, TERMS_TYPES, TEXT_TYPES, MAX_JOB_NAME = 255
isDisplay(p), isUpload(p), isFolder(p), isTerms(p)
editableParams(params)              -> visible, non-display inputs
initialValues(params)               -> {id: value}
fileAccepted(p, filename)           -> bool
validate(params, values, {maxUploadMb, jobName}) -> {id | 'job_name' | '_uploads': message}
buildFormData(workflowId, jobName, params, values) -> FormData
formatBytes(bytes)                  -> '2.0 KB'
```

Component contracts:

- `DynamicForm` props `params`, `modelValue` (`{id: value}`), `errors` (`{id: message}`),
  `disabled`; emits `update:modelValue` with a new object.
- `ParamInput` props `param`, `modelValue`, `error`, `disabled`; emits `update:modelValue`.
  Upload values are arrays of `File`.

Test ids: `workflow-title`, `workflow-version`, `workflow-definition-error`, `run-form`,
`job-name`, `error-job_name`, `dynamic-form`, `input-<id>`, `files-<id>`, `error-<id>`,
`run-error`, `job-submit`.

## Behaviour

Load:

1. Spinner → `getWorkflow`. Success: `workflow` stored, `values = initialValues(inputs)`.
   Failure: error alert only (no retry button).
2. A workflow with `definition_errors` has `inputs: []` (BE-WAPI-006); the page shows the
   misconfiguration alert, the job name field and an enabled submit button.

Submit:

1. Clear the top message; `errors = validate(...)`. Non-empty → show messages, stop.
2. `submitting = true`; build `FormData`; `submitJob`.
3. 201 → `router.push('/jobs/<id>')`.
4. Error → `errors` replaced by server `fields` (joined), top message from the envelope.
5. `submitting = false`.

Edge cases:

- A browser `type=number` control reports `''` for non-numeric text, so the user sees
  `This field is required.` (required) or the value is silently omitted (optional) instead of
  `Please enter a number.`. The regex rule is still enforced for values that reach `validate`.
- Field errors stay visible after the user edits the field, until the next submit.
- Server `fields` keys that match no rendered field (for example `workflow`, or a hidden input)
  appear only through the top message.
- Folder inputs take a multi-file selection; sub-directory structure is not sent (the server
  keeps basenames only anyway).
- `maxlength=255` counts UTF-16 code units; the server counts code points, so a name with many
  astral characters (emoji) is cut earlier in the browser than the server limit.
- An input `type` outside the list in FE-FORM-010 renders its label but no control; its default
  value is still sent if non-empty. The backend never emits such types (BE-WDEF-016).

## Acceptance tests

| Req | Test | Layer |
|-----|------|-------|
| 001 | `e2e/tests/test_deep_links.py::test_protected_route_logged_out_redirects_to_login_with_next[/run/hello]` | e2e |
| 002, 004 | `e2e/tests/test_run_form.py::test_all_input_types_render_with_defaults` (title); `frontend/src/test/contracts/workflows.test.js` › workflows api › lists and gets workflows (call shape) | e2e, contract |
| 003 | (planned) `frontend/src/test/views/workflow-submit.test.js` › shows "Workflow not found." on 404; (planned) `e2e/tests/test_run_form.py::test_private_workflow_shows_not_found` | unit, e2e |
| 005 | (planned) `frontend/src/test/views/workflow-submit.test.js` › shows definition errors | unit |
| 007, 008, 009, 010, 011, 012 | `frontend/src/test/contracts/dynamic-form.test.js` › DynamicForm component › renders a wrapper per input with defaults and required markers (W2); › initialValues › uses YAML defaults for every type (F4), editableParams skips display-only and hidden inputs; `e2e/tests/test_run_form.py::test_all_input_types_render_with_defaults` | unit, e2e |
| 013 | `e2e/tests/test_command_steps.py::test_run_form_shows_details_help_and_accept`; dynamic-form.test.js (help text) | e2e, unit |
| 014 | `frontend/src/test/contracts/dynamic-form.test.js` › helpers › formatBytes; (planned) dynamic-form.test.js › lists selected files with size and removes one | unit |
| 015 | `e2e/tests/test_run_form.py::test_all_input_types_render_with_defaults` (`<b>` in info renders); (planned) dynamic-form.test.js › renders help, details and option labels as text | e2e, unit |
| 016 | (planned) dynamic-form.test.js › non-http help is not a link | unit |
| 018, 019 | `frontend/src/test/contracts/dynamic-form.test.js` › buildFormData › sends SPEC field names…; `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name`; `e2e/tests/test_run_form.py::test_all_input_types_render_with_defaults` (empty default) | unit, e2e |
| 020 | dynamic-form.test.js › validate › optional agb checkbox may stay unchecked; job name length | unit |
| 021, 022, 023 | dynamic-form.test.js › validate › reports required, range, choice, terms and file errors like the server; › checks accept, single file and total upload size; `e2e/tests/test_run_form.py::test_client_validation_blocks_submit` | unit, e2e |
| 022 (parity with server) | `e2e/tests/test_run_form.py::test_server_validation_field_errors`; `e2e/tests/test_findings_jobs.py::test_a05_number_input_rejects_values_the_form_rejects` | e2e |
| 024 | dynamic-form.test.js › validate › checks accept, single file and total upload size | unit |
| 025 | `frontend/src/test/contracts/jobs.test.js` › submits multipart FormData unchanged; `frontend/src/test/client.test.js` › never forces a JSON content type on FormData | contract, unit |
| 026 | dynamic-form.test.js › buildFormData › sends SPEC field names, typed text, explicit checkbox values and files; `e2e/tests/test_jobs.py::test_all_inputs_uploads_folder_and_write_file` | unit, e2e |
| 027 | (planned) `frontend/src/test/views/workflow-submit.test.js` › disables submit while submitting | unit |
| 028 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name`, `::test_all_inputs_uploads_folder_and_write_file` (`RunPage.submit` waits for `/jobs/<id>`) | e2e |
| 029 | `e2e/tests/test_run_form.py::test_server_field_errors_are_shown_in_the_form`; dynamic-form.test.js › DynamicForm component › shows field errors | e2e, unit |
| 030 (429, 503) | `e2e/tests/test_queue.py::test_queue_full_rejects_submission`, `::test_maintenance_blocks_users_not_admins` | e2e |
| 030 (413, 404, 409) | (planned) `frontend/src/test/views/workflow-submit.test.js` › maps 413/404/409 envelopes | unit |
| 031 | `e2e/tests/test_queue.py::test_maintenance_blocks_users_not_admins` (form loads and submits during maintenance; server answers 503) | e2e |

There is no view-level unit test for `WorkflowSubmitView.vue` today; FE-FORM-003, -005, -027 and
parts of -030 rely on planned tests.

## Known gaps

| Req | What the code does | Where | Severity |
|-----|--------------------|-------|----------|
| FE-FORM-017 | `description` and every input `label` go to `v-html` unsanitised. Anyone who can install or edit a workflow YAML can run script in every user's session on the run page. Trusted only by convention (admin-installed apps). | `frontend/src/views/public/WorkflowSubmitView.vue:72`, `frontend/src/components/workflows/form/DynamicForm.vue:150`, `:156`, `frontend/src/components/workflows/form/ParamInput.vue:48`, `:60` | major |
| — | Contract tests validate the workflow fixture against the hand-written `workflowSchema` in `frontend/src/test/schemas.js`, not `schema.yaml` (Article 5.1e). The fixture has `category_name: null`, which `schema.yaml` (`type: string`, not nullable) rejects; the hand-written schema enforces an input-type enum that `schema.yaml` (`WorkflowInput.type: string`) lacks. | `frontend/src/test/contracts/workflows.test.js:8`, `frontend/src/test/schemas.js:125`, `frontend/src/test/fixtures/jobs.js:11` | major |
| — | `WorkflowInput.type` is a free string in `schema.yaml`; the form's type switch has no typed contract. An unknown type renders a label with no control. | `schema.yaml` `WorkflowInput`, `frontend/src/components/workflows/form/ParamInput.vue:67-157` | minor |
| FE-FORM-006 | Submit stays enabled when `definition_errors` is non-empty; the user only learns on submit (409). | `frontend/src/views/public/WorkflowSubmitView.vue:83-111` | minor |
| FE-FORM-027 | The job name input is not disabled while submitting; only the generated controls are. | `frontend/src/views/public/WorkflowSubmitView.vue:89-98` | minor |
| FE-FORM-030 | A 413 from nginx (`client_max_body_size`) has no JSON envelope, so the user sees the generic `Job submission failed.` with no size hint. | `frontend/src/views/public/WorkflowSubmitView.vue:56`, `frontend/src/api/client.js:84-85` | minor |
| FE-FORM-029 | The 400 top message shows the raw input id (`number_in: Must be at most 10.`) rather than its label. | `frontend/src/views/public/WorkflowSubmitView.vue:56` | minor |
| FE-FORM-022 | `type=number` controls turn non-numeric text into `''`, so the user sees `This field is required.` or the value is silently dropped instead of `Please enter a number.`. | `frontend/src/components/workflows/form/ParamInput.vue:79-92` | minor |
| FE-FORM-014 | Removing a file from the list does not clear the native file input, which still shows the old count, and re-choosing the same file fires no `change` event. | `frontend/src/components/workflows/form/ParamInput.vue:27-31`, `:138-147` | minor |
| FE-FORM-013 | For `checkbox` and terms inputs, a `help` that is not a URL is never shown. | `frontend/src/components/workflows/form/ParamInput.vue:51-54` | minor |
| — | The radio group's `<label for>` points at a `div`, so the group has no accessible name; an optional radio cannot be cleared once chosen. | `frontend/src/components/workflows/form/ParamInput.vue:59`, `:120` | minor |
| — | The view reads `workflowId` only in `onMounted` and `RouterView` has no `key`, so a param-only navigation (`/run/a` → `/run/b`) would keep the old form. No in-app link does this today. | `frontend/src/views/public/WorkflowSubmitView.vue:26-36`, `frontend/src/App.vue:26` | minor |
| — | `getWorkflow` interpolates the id into the URL without `encodeURIComponent`; a crafted route param such as `..%2F…` changes the requested path (same-origin GET only). | `frontend/src/api/workflows.js:6-7` | minor |
| FE-FORM-003, -005, -027 | No unit test mounts `WorkflowSubmitView`; load errors, definition errors and button states are untested. | `frontend/src/test/` | minor |

## Open questions

- Who owns HTML sanitisation of workflow `description`/`label` (backend at parse time or the SPA
  at render time)? Same question as in
  [../backend/workflow-definition.md](../backend/workflow-definition.md#open-questions).
- Should the form show the total selected upload size and the `max_upload_mb` limit before
  submit, rather than only on failure?
- Should `separator` show its `label` as a section heading? Today the label is dropped and only
  `<hr>` is drawn.
- Should folder inputs use a directory picker (`webkitdirectory`) and send relative paths (see
  the backend open question on folder structure)?
- Should the form warn up front when the server is in maintenance (the banner already does) or
  the queue is full, instead of failing on submit?
