# Job detail

## Purpose

The job page (`/jobs/:id`) shows one job to its owner or an admin: state, queue position,
elapsed time, live progress of steps and Nextflow processes, job messages, the submitted inputs,
the downloadable results and the job log. It polls the light status endpoint while the job is
active and stops when the job reaches a final state. It also offers cancel, delete and (admins
only) restart.

## Scope

Covered:

- `frontend/src/views/public/JobDetailView.vue`
- `frontend/src/components/jobs/JobProgress.vue`, `JobLogTab.vue`, `JobResultsTab.vue`
- `frontend/src/components/jobs/usePolling.js` (`createPoller`, `usePolling`), the poller used by
  this view and by [job-list.md](job-list.md)
- The detail-related functions of `frontend/src/api/jobs.js`: `getJob`, `getJobStatus`,
  `cancelJob`, `deleteJob`, `getJobLog`, `jobLogUrl`, `jobOutputUrl`, `adminRestartJob`

Out of scope:

- `JobStatusBadge` mapping: [job-list.md](job-list.md) (FE-JLIST-017).
- Admin jobs table and its restart button: [admin-dashboard-jobs.md](admin-dashboard-jobs.md).
- `ConfirmDialog`, `AlertMessage`, `LoadingSpinner`: [common-components.md](common-components.md).
- `formatBytes` (in `formModel.js`): [workflow-submit-form.md](workflow-submit-form.md).
- How the server produces steps, processes, messages, outputs and the log:
  [../backend/job-progress-outputs.md](../backend/job-progress-outputs.md).

## Dependencies

- [../backend/jobs-api.md](../backend/jobs-api.md): `jobs_retrieve` (BE-JAPI-008, 009),
  `jobs_status_retrieve` (BE-JAPI-010), `jobs_cancel_create` (BE-JAPI-011..013), `jobs_destroy`
  (BE-JAPI-014, 015), `jobs_log_retrieve` (BE-JAPI-016), `jobs_outputs_retrieve`
  (BE-JAPI-017..021), access rules (BE-JAPI-001..004).
- [../backend/job-progress-outputs.md](../backend/job-progress-outputs.md): message levels
  (BE-PROG-002), process counts (BE-PROG-012, 013), command steps without processes
  (BE-PROG-016), outputs (BE-PROG-017..020), log text (BE-PROG-021).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md): states, step states
  (BE-QUEUE-001..005), restart (`admin_jobs_restart_create`).
- [api-contract.md](api-contract.md); `schema.yaml` components `JobDetail`, `JobStatus`,
  `JobStep`, `ProcessProgress`, `JobMessage`, `JobMessageLevelEnum`, `JobOutput`, `JobInput`,
  `Error`.
- [api-client.md](api-client.md) (`apiErrorMessage`, 401 handler), [routing.md](routing.md)
  (`requiresAuth`), [state-stores.md](state-stores.md) (`auth.isAdmin`).

## Requirements

### Access, loading and errors

- **FE-JDET-001** The route `/jobs/:id` MUST require authentication (`meta.requiresAuth`); an
  anonymous visitor MUST be sent to login with `next` set to the job path.
- **FE-JDET-002** On mount the view MUST call `getJob(id)` (`jobs_retrieve`) and show the loading
  spinner until it settles.
- **FE-JDET-003** If `jobs_retrieve` answers `404` (job missing, deleted, or owned by someone
  else — the backend never answers `403`, BE-JAPI-002), the view MUST show
  `Job not found or you do not have permission to view it.` in `job-error` and render no job
  header, tabs or actions. Any other error MUST show `apiErrorMessage(e)`. A `401` is handled by
  the client's unauthorized handler ([api-client.md](api-client.md)).

### Header

- **FE-JDET-004** The header MUST show the state badge with label, the job name (`job-title`),
  `submitted_at` in the browser's locale, the elapsed time (`job-elapsed`), the owner's username
  (`job-user`, from `user.username`) and the workflow name and version (`job-workflow`). All MUST
  be text interpolation, never `v-html`.
- **FE-JDET-005** Elapsed time MUST be `-` before `started_at`, otherwise the time from
  `started_at` to `finished_at` (or to the browser clock while unfinished), formatted `Ns`,
  `Nm Ns` or `Nh Nm`, and MUST update every second while the job runs.
- **FE-JDET-006** A `waiting` job MUST show the `job-queue-position` alert:
  `Waiting in the queue at position <n>. The job starts as soon as a slot is free.` (the
  "at position" part only when `queue_position` is non-null), or `Cancelling…` when
  `cancel_requested` is true. A `running` job with `cancel_requested` MUST show
  `Cancelling… the pipeline is being stopped.` (`job-cancelling`).

### Polling algorithm

- **FE-JDET-007** When the loaded job is active (`waiting` or `running`), the view MUST poll
  `getJobStatus(id)` (`jobs_status_retrieve`), first after 2 s, and merge the response fields into
  the job.
- **FE-JDET-008** The poller (`createPoller`) MUST wait `interval` after `start()`; after each
  tick it MUST multiply the delay by 1.5 (rounded, capped at `maxInterval`) when the tick reports
  no change or throws, and reset it to `interval` when the tick reports a change. A tick reports
  "no change" by returning `false`. Calling `start()` while running MUST be a no-op. The detail
  view uses `interval` 2000 ms and `maxInterval` 10000 ms.
- **FE-JDET-009** Polling MUST stop after the first tick that leaves the job in a final state,
  MUST stop on unmount (`usePolling` registers `onBeforeUnmount`), and MUST NOT start for a job
  that is already final when loaded.
- **FE-JDET-010** The detail view MUST treat a tick as "changed" when anything it displays
  changed (state, queue position, steps, processes, messages). Today it compares only
  `updated_at` (see Known gaps).
- **FE-JDET-011** When a status response moves the job from active to final, the view MUST
  refetch `jobs_retrieve` once so `inputs`, `outputs` and `log_url` reflect the final state.
- **FE-JDET-012** (planned) If a status poll answers `404` (job deleted elsewhere), the view
  SHOULD stop polling and show the FE-JDET-003 not-found message.
- **FE-JDET-013** (planned) Polling SHOULD pause while the document is hidden and resume with an
  immediate poll when it becomes visible.

### Tabs

- **FE-JDET-014** The page MUST have three tabs, `Details` (default), `Results` and `Logs`
  (`job-tab-details`, `job-tab-results`, `job-tab-logs`). The Results tab MUST show
  `outputs_count` as a badge when it is greater than 0.

### Details tab: failure, progress, messages, inputs

- **FE-JDET-015** A `failed` job with a non-empty `error_message` MUST show it in a
  `job-failure` danger alert, as text with line breaks preserved. A `waiting` job MUST show
  `We will start your job as soon as possible.`.
- **FE-JDET-016** `JobProgress` MUST list messages whose `step` is null first, then one card per
  step (`job-step`, `data-state`) in response order with the step name and a state icon
  (`waiting` empty circle, `running` spinner, `success` check, `failed` cross, `cancelled` ban),
  followed by that step's messages.
- **FE-JDET-017** For each process of a step (`job-process` with `data-process`,
  `data-completed`, `data-total`, `data-failed`, `data-running`), `JobProgress` MUST show
  `label` (or `name` when empty), `<completed> / <total> tasks`, `(<n> running)` when running > 0,
  `(<n> failed)` when failed > 0, and a bar at `round((completed + failed) / total × 100)` %
  (0 when total is 0). A `running` step with no processes (command step, BE-PROG-016) MUST show
  `Running…`.
- **FE-JDET-018** Each message (`job-message`, `data-level`) MUST show an icon and colour per
  level for all five levels of `JobMessageLevelEnum` (`debug`, `info`, `success`, `warning`,
  `error`), and its `text` as escaped text with line breaks preserved. Message text MUST NOT be
  rendered with `v-html` (it comes from workflow output, Article 8.2).
- **FE-JDET-019** The inputs table (`job-inputs`, one row per input with `data-input-id`) MUST
  show `label` and `value`; an object value MUST be shown as JSON, any other value as text. A null
  value SHOULD show as empty (see Known gaps).

### Results tab

- **FE-JDET-020** `JobResultsTab` MUST show, in this order of precedence: `Results will be
  available when the job has finished.` while active; `The results of this job have been
  deleted.` (`job-results-expired`) when `purged_at` is set; `No downloadable results.`
  (`job-results-empty`) when there are no outputs.
- **FE-JDET-021** Outputs MUST be grouped by `output_id` in first-seen order (`job-output-group`,
  heading `label` or `output_id`). Each file MUST be a link (`job-output-link`, `data-filename` =
  `path`) whose `href` is the server-provided `url` (`jobs_outputs_retrieve`), showing `path`
  without the leading `<output_id>/`, the size via `formatBytes`, and the download count when > 0.
- **FE-JDET-022** Output links MUST download as attachments: they carry the `download` attribute
  and MUST NOT add `inline=1`. Authorization relies on the same-origin session cookie; the SPA
  MUST NOT build output URLs itself.
- **FE-JDET-023** When `expires_at` is set and there are outputs, the tab MUST show
  `Results are kept until <expires_at in the browser's locale>.` (`job-expires`).

### Logs tab

- **FE-JDET-024** `JobLogTab` MUST load the log with `getJobLog(id)` (`jobs_log_retrieve`) as
  plain text when the tab opens and again whenever the job state changes, show `Loading…` before
  the first text, and render it in `job-log` as escaped preformatted text (never `v-html`).
- **FE-JDET-025** A load error MUST be shown with `apiErrorMessage`, fallback
  `Could not load the log.`. A `Refresh` button (`job-log-refresh`) MUST reload it, and `Raw log`
  (`job-log-raw`) MUST open the log URL in a new tab.

### Actions

- **FE-JDET-026** The Cancel button (`job-cancel`) MUST be shown only when `can_cancel`, and
  Delete (`job-delete`) only when `can_delete`. Restart (`job-restart`) MUST be shown only when
  `can_restart` is true **and** the current user is an admin.
- **FE-JDET-027** Each action MUST ask for confirmation first and send nothing if dismissed:

  | Action | Title | Message | Confirm button |
  |--------|-------|---------|----------------|
  | cancel | `Cancel Job` | `Are you sure you want to cancel <b>NAME</b>?` | `Cancel Job` (`btn-warning`) |
  | delete | `Delete Job` | `Delete <b>NAME</b> and all its results? This cannot be undone.` | `Delete Job` (`btn-danger`) |
  | restart | `Restart Job` | `Restart <b>NAME</b> with the same inputs?` | `Restart Job` (`btn-primary`) |

  NAME MUST be HTML-escaped before it reaches `ConfirmDialog`'s `v-html` (Article 8.2).
- **FE-JDET-028** Confirmed cancel MUST call `cancelJob(id)` (`jobs_cancel_create`), replace the
  job with the returned `JobDetail`, and make sure polling runs while it is still active.
  Confirmed restart MUST call `adminRestartJob(id)` (`admin_jobs_restart_create`), replace the
  job with the returned `JobDetail` and start polling. Confirmed delete MUST call `deleteJob(id)`
  (`jobs_destroy`) and then navigate to `/jobs`.
- **FE-JDET-029** A failed action (for example `409 invalid_state`) MUST show the envelope
  message in `job-action-error` and leave the job shown. The dialog MUST close after success or
  failure, and its confirm button MUST be disabled while the request runs.

### Navigation and API use

- **FE-JDET-030** (planned) Navigating from one job page to another (only `:id` changes, the
  component is reused) SHOULD stop the old poller and load the new job.
- **FE-JDET-031** The view and its components MUST reach the API only through
  `src/api/jobs.js` functions (Article 5.1f).

## Interfaces

API calls (server behaviour in [../backend/jobs-api.md](../backend/jobs-api.md#interfaces)):

| Function (`src/api/jobs.js`) | operationId | Called by | When |
|------------------------------|-------------|-----------|------|
| `getJob(id)` | `jobs_retrieve` | view | mount; after active → final |
| `getJobStatus(id)` | `jobs_status_retrieve` | view (poller) | every tick while active |
| `cancelJob(id)` | `jobs_cancel_create` | view | confirmed cancel |
| `deleteJob(id)` | `jobs_destroy` | view | confirmed delete |
| `adminRestartJob(id)` | `admin_jobs_restart_create` | view | confirmed restart (admin) |
| `getJobLog(id)` | `jobs_log_retrieve` | `JobLogTab` | tab open, state change, Refresh |
| `jobLogUrl(id)` → `/api/jobs/<id>/log/` | `jobs_log_retrieve` | `JobLogTab` | `Raw log` link `href` |
| `outputs[].url` (server value) | `jobs_outputs_retrieve` | `JobResultsTab` | link `href` |

`jobOutputUrl(jobId, fileId)` exists but no view uses it.

Fields read: header/summary `id`, `name`, `state`, `submitted_at`, `started_at`, `finished_at`,
`user.username`, `workflow_name`, `workflow_version`, `queue_position`, `cancel_requested`,
`can_cancel`, `can_delete`, `can_restart`, `updated_at`, `error_message`, `outputs_count`,
`purged_at`, `expires_at`; `steps[].{id,name,state,processes[].{name,label,completed,total,failed,running}}`;
`messages[].{id,level,text,step}`; `inputs[].{id,label,value}`;
`outputs[].{id,output_id,label,path,size,download_count,url}`. Not read: `duration_seconds`,
`log_url`, `inputs[].files`, `ProcessProgress.submitted`.

Poller (`frontend/src/components/jobs/usePolling.js`):

```js
createPoller(fn, { interval = 2000, maxInterval = 10000, shouldContinue = () => true })
  → { start(), stop(), running /* getter */, delay /* getter */ }
usePolling(fn, options)   // createPoller + stop() on onBeforeUnmount
// fn returns false = "no change"; any other value = changed; a throw counts as no change.
```

## Behaviour

```
mount ─► jobs_retrieve ─┬─ 404 ───────► "Job not found or …"
                        ├─ other err ─► apiErrorMessage
                        └─ ok ─► active? ─no─► static page
                                    │yes
                                    ▼
             ┌──── tick: jobs_status_retrieve, merge ◄──────────┐
             │       changed? delay=2 s : delay=min(delay×1.5,10 s)
             │       final now? ─yes─► jobs_retrieve once ─► stop
             └───────────────────── still active ───────────────┘
```

- Delay sequence with no change: 2 s → 3 s → 4.5 s → 6.75 s → 10 s (cap).
- A poll error (network, 5xx, 404) only lengthens the delay; polling continues while the last
  known state is active.
- Cancelling a `running` job returns `state=running`, `cancel_requested=true`, `can_cancel=false`;
  the page shows `Cancelling…` until a poll sees `cancelled` (BE-JAPI-012).
- The Logs tab does not poll; it reloads on each state change and on Refresh.
- Tab choice is local state; it is not in the URL and resets to Details on reload.
- Output downloads are plain links handled by the browser; the server sends
  `Content-Disposition: attachment` unless `inline=1` (BE-JAPI-020), which the SPA never adds.
- The 1 s clock for elapsed time runs for the life of the view (also for finished jobs, where it
  has no visible effect) and is cleared on unmount.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-JDET-001 | `e2e/tests/test_deep_links.py::test_protected_route_logged_out_redirects_to_login_with_next` (`/jobs/:id` case planned: `::test_job_page_deep_link` (planned)) | e2e |
| FE-JDET-002 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name`; `frontend/src/test/contracts/jobs.test.js` › "jobs api endpoints" › "uses the SPEC paths for detail, status, cancel, delete, log" | e2e, unit |
| FE-JDET-003 | `e2e/tests/test_access_jobs.py::test_other_user_cannot_see_job_outputs_or_log` (UI part); other-error path `frontend/src/test/views/job-detail.test.js` › "shows envelope message on non-404 error" (planned) | e2e, unit |
| FE-JDET-004 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` (title text); HTML-in-name `e2e/tests/test_job_detail.py::test_html_in_job_name_is_text` (planned) | e2e |
| FE-JDET-005 | `frontend/src/test/views/job-detail.test.js` › "elapsed time" (planned) | unit |
| FE-JDET-006 | `e2e/tests/test_queue.py::test_queue_limits_and_advances_after_cancel`, `::test_pause_and_resume_queue`; running-cancelling text `frontend/src/test/views/job-detail.test.js` › "shows cancelling" (planned) | e2e, unit |
| FE-JDET-007, 009 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` (reaches `success` without reload), `::test_live_progress_multi_process`; `e2e/tests/test_queue.py::test_pause_and_resume_queue`; stop-on-final/unmount `frontend/src/test/views/job-detail.test.js` › "stops polling on final state and unmount" (planned) | e2e, unit |
| FE-JDET-008 | `frontend/src/test/contracts/dynamic-form.test.js` › "helpers" › "poller backs off without changes and stops when inactive" | unit |
| FE-JDET-010 | `frontend/src/test/views/job-detail.test.js` › "progress change resets the poll delay" (planned) | unit |
| FE-JDET-011 | `e2e/tests/test_jobs.py::test_live_progress_multi_process` (outputs present after success without reload) | e2e |
| FE-JDET-014 | `e2e/tests/test_jobs.py::test_failing_workflow` (tabs); badge count `frontend/src/test/views/job-detail.test.js` › "results badge" (planned) | e2e, unit |
| FE-JDET-015 | `e2e/tests/test_jobs.py::test_failing_workflow` | e2e |
| FE-JDET-016 | `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` (5 steps, step messages) | e2e |
| FE-JDET-017 | `e2e/tests/test_jobs.py::test_live_progress_multi_process` | e2e |
| FE-JDET-018 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` (unicode/quotes as text), `::test_failing_workflow`; `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output`, `::test_failing_command_step_fails_the_job`; `<script>` in message `e2e/tests/test_job_detail.py::test_message_html_is_text` (planned) | e2e |
| FE-JDET-019 | `frontend/src/test/views/job-detail.test.js` › "inputs table" (planned) | unit |
| FE-JDET-020 | `frontend/src/test/components/job-results-tab.test.js` › "states: active, purged, empty" (planned) | unit |
| FE-JDET-021, 022 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` (download), `::test_all_inputs_uploads_folder_and_write_file`, `::test_live_progress_multi_process`; `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` | e2e |
| FE-JDET-023 | `frontend/src/test/components/job-results-tab.test.js` › "expiry line" (planned) | unit |
| FE-JDET-024 | `e2e/tests/test_jobs.py::test_failing_workflow`; `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` | e2e |
| FE-JDET-025 | `frontend/src/test/components/job-log-tab.test.js` › "error and refresh" (planned) | unit |
| FE-JDET-026 | `e2e/tests/test_jobs.py::test_cancel_running_job_from_job_page`; restart visibility `frontend/src/test/views/job-detail.test.js` › "restart only for admins" (planned) | e2e, unit |
| FE-JDET-027 | `e2e/tests/test_jobs.py::test_cancel_running_job_from_job_page`, `::test_cancel_waiting_and_delete_finished`; escaping `frontend/src/test/views/job-detail.test.js` › "confirm dialog escapes the job name" (planned) | e2e, unit |
| FE-JDET-028 | `e2e/tests/test_jobs.py::test_cancel_running_job_from_job_page`, `::test_cancel_waiting_and_delete_finished` (delete → `/jobs`); `e2e/tests/test_command_steps.py::test_cancel_during_long_command_step`; restart from job page `e2e/tests/test_job_detail.py::test_admin_restart_from_job_page` (planned) | e2e |
| FE-JDET-029 | `e2e/tests/test_job_detail.py::test_cancel_conflict_shows_message` (planned) | e2e |
| FE-JDET-031 | `frontend/src/test/architecture.test.js` › "views do not import the HTTP client" (planned) | unit |

FE-JDET-012, 013, 030 are SHOULD (planned) and have no test yet.

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| FE-JDET-010 | Change detection compares only `updated_at`. The worker updates step `processes`, `current_step` and messages without touching `Job.updated_at` (`row.save(update_fields=['processes'])`, `QuerySet.update(current_step=…)`), so during a run every tick counts as "no change" and the delay climbs to 10 s; live progress lags up to 10 s instead of 2 s. | `frontend/src/views/public/JobDetailView.vue:58-65`; `jobs/worker.py:219-220`, `jobs/worker.py:449-453` | major |
| — | `schema.yaml` declares `expires_at` (`JobList`/`JobStatus`/`JobDetail`) as a required non-nullable `string`, but the server returns `null` for unfinished jobs or when retention ≤ 0 (BE-JAPI-007; `get_expires_at` has no type hint). Real responses for every active job violate the contract; the frontend fixtures miss it because they validate against hand-written schemas (`src/test/schemas.js`), not `schema.yaml` (Article 5.1e). | `jobs/serializers.py:119-120`, `frontend/src/test/schemas.js` | major |
| FE-JDET-012 | A `404` on a status poll is swallowed; the view keeps polling every 10 s forever and keeps showing the deleted job. | `frontend/src/components/jobs/usePolling.js:17-25`, `frontend/src/views/public/JobDetailView.vue:67-71` | minor |
| FE-JDET-013 | Polling continues while the tab is hidden (no `visibilitychange` handling). | `frontend/src/components/jobs/usePolling.js:8-49` | minor |
| FE-JDET-030 | No watcher on `route.params.id`; moving between two job pages reuses the component and keeps the first job and its poller. | `frontend/src/views/public/JobDetailView.vue:73-85` | minor |
| FE-JDET-019 | A null input value is shown as the text `null` (`String(i.value)`). | `frontend/src/views/public/JobDetailView.vue:198` | minor |
| FE-JDET-005 | Elapsed time uses the browser clock against server timestamps, so clock skew shows wrong (even zero, clamped) times while running; the server's `duration_seconds` is ignored. | `frontend/src/views/public/JobDetailView.vue:41-50` | minor |
| FE-JDET-025 | `Raw log` uses the hard-coded `jobLogUrl(id)` instead of the `log_url` the server returns. | `frontend/src/components/jobs/JobLogTab.vue:38` | minor |
| — | The cancel dialog gets `data-testid="confirm-cancel"` as a fall-through attribute, overriding `ConfirmDialog`'s root `confirm-dialog` id and duplicating the id of the dialog's own Cancel button (`confirm-cancel`); `confirm-delete` / `confirm-restart` likewise replace `confirm-dialog`. | `frontend/src/views/public/JobDetailView.vue:220`, `:231`, `:242` | minor |
| FE-JDET-003..029 | No component tests exist for `JobDetailView`, `JobProgress`, `JobLogTab` or `JobResultsTab`; only the poller and API paths are unit-tested. | `frontend/src/test/` | minor |

## Open questions

- Should the Logs tab poll while the job runs (it reloads only on state change today)?
- Should the results tab offer an inline view (`inline=1`) for allowlisted types (text, PNG,
  PDF), which the server supports (BE-JAPI-020)?
- Should the elapsed time use the server's `duration_seconds` (refreshed by polling) instead of
  the browser clock?
