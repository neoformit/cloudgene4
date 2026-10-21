# Jobs API

## Purpose

The jobs API is how a signed-in user submits jobs, lists and inspects their own jobs, polls a
running job, cancels or deletes it, reads its log and downloads its result files. It is served by
`JobViewSet` under `/api/jobs/`. This file defines, for each operation, who may call it, what it
returns, the status and error codes, and the security rules for file downloads.

## Scope

Covered: `jobs/views.py` (`JobViewSet`, `_output_response`, `_filter_state`),
`jobs/serializers.py` (response serializers for the user endpoints), `jobs/urls.py` (the `jobs`
router), and the job actions in `jobs/services.py` (`cancel_job`, `delete_job`) as seen through
the API.

Out of scope:

- Validation of the submission body, uploads, naming, queue/maintenance checks:
  [job-submission.md](job-submission.md). This file covers only the endpoint entry.
- `AdminJobViewSet` (`admin_jobs_list`, `admin_jobs_cancel_create`, `admin_jobs_restart_create`)
  and `services.restart_job`: [admin-api.md](admin-api.md).
- How steps, messages, outputs and the log text are produced, and output path resolution:
  [job-progress-outputs.md](job-progress-outputs.md).
- What happens after a cancel request (signals, final state): [job-queue-worker.md](job-queue-worker.md).
- Field-by-field shapes (`JobList`, `JobStatus`, `JobDetail`, `Error`, pagination envelope):
  [api-contract.md](api-contract.md) and `schema.yaml`.
- Session/token authentication and CSRF: [authentication.md](authentication.md).
- The admin role (`is_admin`): [access-control.md](access-control.md).

## Dependencies

- [api-contract.md](api-contract.md): error envelope, pagination, trailing-slash handling,
  operation catalogue.
- [authentication.md](authentication.md): 401 for anonymous callers, CSRF for session writes.
- [access-control.md](access-control.md): `is_admin`.
- [job-submission.md](job-submission.md): `submit_job` rules and error codes for `jobs_create`.
- [job-progress-outputs.md](job-progress-outputs.md): BE-PROG-013 (`processes`), BE-PROG-017..021
  (outputs, download resolution, log text).
- [job-queue-worker.md](job-queue-worker.md): job states, `cancel_requested` handling.
- [configuration.md](configuration.md): `server.job_retention_days`, `job_dir(id)`.
- Operations: `jobs_list`, `jobs_create`, `jobs_retrieve`, `jobs_status_retrieve`,
  `jobs_cancel_create`, `jobs_destroy`, `jobs_log_retrieve`, `jobs_outputs_retrieve`.

## Requirements

### Access

- **BE-JAPI-001** Every operation in this file MUST require an authenticated user (session or
  token). An anonymous caller MUST get `401` with error code `not_authenticated` and a
  `WWW-Authenticate: Token` header, and no job data.
- **BE-JAPI-002** `jobs_retrieve`, `jobs_status_retrieve`, `jobs_log_retrieve`,
  `jobs_outputs_retrieve`, `jobs_cancel_create` and `jobs_destroy` MUST be allowed for the job's
  owner and for admins. Any other authenticated user MUST get `404` `not_found` — never `403` —
  so job ids cannot be probed.
- **BE-JAPI-003** A job deleted by its owner (`deleted_at` set) MUST be `404` `not_found` on every
  operation for every caller, admins included, and MUST NOT appear in `jobs_list`.
- **BE-JAPI-004** A job id in the path MUST match `[0-9a-fA-F-]{32,36}`; a value that does not
  match, or matches but is not a valid UUID, MUST give `404` `not_found` (never `500`).

### List

- **BE-JAPI-005** `jobs_list` MUST return only the caller's own visible jobs (admins too; all
  users' jobs are listed by `admin_jobs_list`), ordered by `submitted_at` descending then `id`,
  paginated per [api-contract.md](api-contract.md) (`page`, `page_size`; default 20, max 200), each
  item a `JobList`.
- **BE-JAPI-006** `jobs_list` MUST accept `state` as one state or a comma-separated list of
  `waiting`, `running`, `success`, `failed`, `cancelled`, and return jobs in any of them. An
  unknown state MUST give `400` `invalid` with `fields.state` naming the bad value and the allowed
  values.

### Job summary fields (shared by list, status and detail)

- **BE-JAPI-007** Each job representation MUST carry: `state` (the job state); `queue_position`
  (1-based rank among **all** waiting jobs by `submitted_at`, `id`; `null` unless waiting);
  `duration_seconds` (from `started_at` to `finished_at` or now, rounded to 0.1 s; `null` if not
  started); `expires_at` (`finished_at` + `server.job_retention_days`; `null` if unfinished or the
  setting is ≤ 0); `can_cancel` (active and not `cancel_requested`); `can_delete` (finished);
  `can_restart` (failed or cancelled and not purged); and the workflow and owner both as nested
  objects (`workflow`, `user`) and flat aliases, taken from the submission-time snapshot.

### Detail and status

- **BE-JAPI-008** `jobs_retrieve` MUST return `JobDetail`: the summary fields plus `updated_at`,
  `error_message`, `steps` (with `processes`), `messages`, `outputs_count`, `inputs`, `outputs`
  (each with `url` = the `jobs_outputs_retrieve` path) and `log_url` (the `jobs_log_retrieve`
  path).
- **BE-JAPI-009** `inputs` MUST list only visible value inputs present in the job's parameters, in
  YAML order, as `{id, label, type, value, files}`: file/folder inputs show the uploaded display
  names joined by `, ` and `files: [{name, size}]`; `list`/`radio` show the chosen option's label;
  a `textarea` with `writeFile` shows the file name, not the text. Server paths MUST NOT appear.
- **BE-JAPI-010** `jobs_status_retrieve` MUST return `JobStatus`: the same as `JobDetail` without
  `inputs`, `outputs` and `log_url`. It is the endpoint the SPA polls while a job is active.

### Cancel and delete

- **BE-JAPI-011** `jobs_cancel_create` on a `waiting` job MUST set it to `cancelled` at once
  (`cancel_requested=true`, `finished_at` set), add a `warning` message `Job cancelled.` (suffixed
  ` by an administrator` when the caller is not the owner) and return `200` `JobDetail`.
- **BE-JAPI-012** `jobs_cancel_create` on a `running` job MUST set `cancel_requested=true`, leave
  the state `running`, add one `warning` message `Cancellation requested.` (same suffix rule) and
  return `200` `JobDetail` with `can_cancel=false`. A repeat request MUST return `200` without a
  second message. The worker then stops the job ([job-queue-worker.md](job-queue-worker.md)).
- **BE-JAPI-013** `jobs_cancel_create` on a finished job MUST return `409` `invalid_state` with
  message `The job is already <state>.` and change nothing.
- **BE-JAPI-014** `jobs_destroy` on a finished job MUST return `204` with no body, set
  `deleted_at` (and `purged_at` if unset), delete the job's output rows and remove the job
  directory. The job row MUST be kept (for admin statistics) but is then hidden (BE-JAPI-003).
- **BE-JAPI-015** `jobs_destroy` on an active job MUST return `409` `invalid_state` with message
  `Only finished jobs can be deleted. Cancel the job first.` and change nothing.

### Log

- **BE-JAPI-016** `jobs_log_retrieve` MUST return `200` with `Content-Type: text/plain;
  charset=utf-8` and the text defined by BE-PROG-021, for active and finished jobs alike.

### Output downloads

- **BE-JAPI-017** `jobs_outputs_retrieve` MUST serve the file only when `file_id` is an output row
  of **that** job (an id belonging to another job, even one the caller owns, is not found) and the
  file resolves safely per BE-PROG-020. Otherwise it MUST return `404` `not_found` with message
  `File not found.`. A `file_id` that is not all digits MUST be `404`.
- **BE-JAPI-018** A successful download MUST stream the file with `Content-Disposition` filename
  equal to the file's base name, and increment that output's `download_count` by 1.
- **BE-JAPI-019** The response `Content-Type` MUST be the type guessed from the file name only when
  it is in the allowlist `text/plain`, `application/pdf`, `image/png`, `image/jpeg`, `image/gif`
  (`application/json` is served as `text/plain`); every other type, including HTML, SVG, XML,
  JavaScript and unknown, MUST be `application/octet-stream`.
- **BE-JAPI-020** The response MUST be `attachment` unless the query has `inline=1` or
  `inline=true` **and** the type is in the allowlist (BE-JAPI-019), in which case it MUST be
  `inline`.
- **BE-JAPI-021** Every download response MUST carry `X-Content-Type-Options: nosniff` and
  `Content-Security-Policy: sandbox`.

### Submission entry

- **BE-JAPI-022** `jobs_create` MUST accept `multipart/form-data` (and `application/json` without
  files) for an authenticated user, run the rules of [job-submission.md](job-submission.md), and
  return `201` with the new job's `JobDetail`. A rejected submission MUST return the error
  envelope with the code and status chosen there (for example `400` `invalid` with `fields`,
  `404` `not_found`, `413` `upload_too_large`); no job row or workspace is left behind.

### Errors and contract

- **BE-JAPI-023** Every non-2xx response of these operations MUST use the error envelope of
  [api-contract.md](api-contract.md); unexpected exceptions MUST give `500` `server_error` with a
  generic message.
- **BE-JAPI-024** Every 2xx JSON response MUST validate against the `schema.yaml` component named
  for its operation (contract test).
- **BE-JAPI-025** Submit, cancel and delete SHOULD each write one `INFO` record to the
  `cloudgene.jobs` logger with the job id and the acting user.

## Interfaces

All paths are canonical with a trailing slash; the slash-less form is also routed
([api-contract.md](api-contract.md)).

| operationId | Method and path | Who | Success | Errors (status `code`) |
|-------------|-----------------|-----|---------|------------------------|
| `jobs_list` | `GET /api/jobs/?state=&page=&page_size=` | authenticated (own jobs only) | `200` `PaginatedJobListList` | `400 invalid` (bad `state`), `404 not_found` (page out of range), `401` |
| `jobs_create` | `POST /api/jobs/` | authenticated | `201` `JobDetail` | see [job-submission.md](job-submission.md); `401`, `403 csrf_failed` (session without CSRF) |
| `jobs_retrieve` | `GET /api/jobs/{id}/` | owner, admin | `200` `JobDetail` | `404 not_found`, `401` |
| `jobs_status_retrieve` | `GET /api/jobs/{id}/status/` | owner, admin | `200` `JobStatus` | `404 not_found`, `401` |
| `jobs_cancel_create` | `POST /api/jobs/{id}/cancel/` | owner, admin | `200` `JobDetail` | `409 invalid_state`, `404 not_found`, `401` |
| `jobs_destroy` | `DELETE /api/jobs/{id}/` | owner, admin | `204` | `409 invalid_state`, `404 not_found`, `401` |
| `jobs_log_retrieve` | `GET /api/jobs/{id}/log/` | owner, admin | `200` `text/plain` | `404 not_found`, `401` |
| `jobs_outputs_retrieve` | `GET /api/jobs/{id}/outputs/{file_id}/[?inline=1]` | owner, admin | `200` file stream | `404 not_found`, `401` |

Download response headers (BE-JAPI-018..021):

```
Content-Type: <allowlisted type> | application/octet-stream
Content-Disposition: attachment; filename="<basename>"   (inline; … only per BE-JAPI-020)
X-Content-Type-Options: nosniff
Content-Security-Policy: sandbox
```

Service functions used by the views (`jobs/services.py`): `cancel_job(job, by_admin)`,
`delete_job(job)`; both raise `JobActionError(message, code='invalid_state', status=409)`.

## Behaviour

Object lookup: `get_queryset` starts from visible jobs; for `list`, and for every action when the
caller is not an admin, it filters to `user = caller`. A lookup miss therefore yields DRF's `404`
for both "does not exist" and "not yours". Detail and status prefetch steps, messages and outputs.

Cancel race: a waiting job is cancelled with a conditional update (`status = waiting`). If the
worker claimed it in between, the update matches nothing and the running path is taken instead
(flag set, state stays `running`).

Delete is a soft delete with a hard workspace removal: the directory is removed synchronously with
errors ignored; outputs and log are gone afterwards, while the row survives with `deleted_at`.

Downloads re-check the file on every request (BE-PROG-020), so a file removed by retention cleanup
or replaced by an escaping symlink after listing is `404`.

`jobs_status_retrieve` and `jobs_retrieve` include **all** steps and messages each time; the SPA
polls `jobs_status_retrieve` every 2 s while the job is active (see the frontend spec).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| BE-JAPI-001 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`; `e2e/tests/test_findings_security.py::test_permission_matrix_object_access`, `::test_permission_matrix_requires_authentication`; `e2e/tests/test_access_jobs.py::test_anonymous_cannot_download` | unit, e2e |
| BE-JAPI-002 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`; `e2e/tests/test_access_jobs.py::test_other_user_cannot_see_job_outputs_or_log`, `::test_owner_and_admin_can_download`; `e2e/tests/test_findings_security.py::test_permission_matrix_object_access` | unit, e2e |
| BE-JAPI-003 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` (owner); admin case `::test_deleted_job_is_404_for_admin` (planned) | unit |
| BE-JAPI-004 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_malformed_job_id_is_404` (planned) | unit |
| BE-JAPI-005 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`, `::test_other_users_get_404_admin_gets_access` (admin sees own only); ordering/pagination `::test_list_order_and_pagination` (planned); `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` | unit, e2e |
| BE-JAPI-006 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download` | unit |
| BE-JAPI-007 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`, `::test_queue_positions`, `::test_cancel_running_sets_flag` | unit |
| BE-JAPI-008 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` | unit, e2e |
| BE-JAPI-009 | `jobs/tests/test_api.py::SubmissionTest::test_all_input_types_are_resolved_and_stored` (stored values); detail rendering `JobLifecycleApiTest::test_detail_inputs_hide_paths` (planned); `e2e/tests/test_jobs.py::test_all_inputs_uploads_folder_and_write_file` | unit, e2e |
| BE-JAPI-010 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e/tests/test_jobs.py::test_live_progress_multi_process` | unit, e2e |
| BE-JAPI-011 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` | unit, e2e |
| BE-JAPI-012 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_running_sets_flag`; `e2e/tests/test_jobs.py::test_cancel_running_job_from_job_page`; repeat-without-message (planned) | unit, e2e |
| BE-JAPI-013 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` | unit |
| BE-JAPI-014 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` | unit, e2e |
| BE-JAPI-015 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` | unit |
| BE-JAPI-016 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e/tests/test_jobs.py::test_failing_workflow` | unit, e2e |
| BE-JAPI-017 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_output_traversal_and_foreign_ids`; `e2e/tests/test_findings_security.py::test_foreign_output_id_under_own_job` | unit, e2e |
| BE-JAPI-018 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` | unit, e2e |
| BE-JAPI-019, 020, 021 | `jobs/tests/test_api.py::OutputDownloadContentTypeTest::test_html_never_served_as_html`, `::test_svg_never_served_inline`, `::test_txt_is_safe_and_can_be_inline`, `::test_png_is_safe_and_can_be_inline`; `e2e/tests/test_findings_security.py::test_b04_html_output_not_served_as_active_content`; JSON→text/plain case (planned) | unit, e2e |
| BE-JAPI-022 | `jobs/tests/test_api.py::SubmissionTest` (all tests); `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name`; `e2e/tests/test_queue.py::test_queue_full_rejects_submission` | unit, e2e |
| BE-JAPI-023 | `core/tests/test_api.py::ErrorEnvelopeHandlerTest`; `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` (409 envelope) | unit |
| BE-JAPI-024 | `jobs/tests/test_contract.py::JobsContractTest` (planned) | contract |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| BE-JAPI-024 | No backend contract test validates job responses (or error envelopes) against `schema.yaml` components; only schema staleness is tested (`core/tests/test_schema.py`). Constitution 5.1d is unmet for this area. | `jobs/tests/` | major |
| BE-JAPI-007, BE-API-008 | `expires_at` is a `SerializerMethodField` typed only as `OpenApiTypes.DATETIME`, so `schema.yaml` declares it (`JobList`, `JobStatus`, `JobDetail`) as a required non-nullable `string`; `Job.expires_at()` returns `None` for every unfinished job and when `server.job_retention_days` ≤ 0. Real responses for active jobs violate the contract. The SPA depends on it ([../frontend/job-detail.md](../frontend/job-detail.md) FE-JDET-023). | `jobs/serializers.py:118-120`, `jobs/models.py:126-130`, `schema.yaml` `JobList.expires_at` | major |
| BE-JAPI-020 | The `inline` query parameter is not declared in `schema.yaml` for `jobs_outputs_retrieve` (no `OpenApiParameter`), so the contract does not describe a supported input (Article 5.3). | `jobs/views.py:157-169` | minor |
| BE-JAPI-019 | `schema.yaml` declares the `200` body only as `application/octet-stream` and the `404` without the `Error` content, while the view returns allowlisted types and an envelope body. | `jobs/views.py:157-158` | minor |
| BE-JAPI-006 | `schema.yaml` declares `state` as a single-value enum, but comma-separated lists are accepted and used (`success,failed`); a schema-validating client would reject valid requests. | `jobs/views.py:43-44` | minor |
| BE-JAPI-009 | If the stored `workflow_yaml` cannot be parsed, `inputs` falls back to every raw parameter, including hidden inputs and workspace-relative file paths, all typed `text`. | `jobs/serializers.py:161-167` | minor |
| BE-JAPI-010 | The polling endpoint is not light: it returns every message and step each call, and `queue_position` runs a count query per job; `jobs_list` repeats that count and a config read (`expires_at`) per row (N+1). | `jobs/serializers.py:112-119`, `jobs/models.py:116-130` | minor |
| BE-JAPI-014 | The workspace is removed with errors ignored after the row is marked deleted/purged; a failed removal leaves files on disk with no log record. | `jobs/services.py:52-54` | minor |
| BE-JAPI-018 | `download_count` is incremented before streaming, and also on `HEAD` (DRF maps `HEAD` to the `GET` action), so it counts attempts, not completed downloads. | `jobs/views.py:167` | minor |
| BE-JAPI-003, 004, 005, 012 | Parts of these requirements have no test (see planned rows). | — | minor |

## Open questions

1. Should admins see other users' jobs in `jobs_list` with a filter, or is `admin_jobs_list` the
   only list of all jobs (current behaviour)?
2. `queue_position` is global (counts other users' waiting jobs). Is exposing the overall queue
   depth to every user intended?
3. Should `jobs_destroy` be allowed for admins on another user's job through this endpoint
   (current behaviour), or only through an admin operation that is logged as an admin action?
4. Should `jobs_status_retrieve` support incremental messages (e.g. `?after=<message id>`) so that
   polling stays cheap for chatty workflows?
