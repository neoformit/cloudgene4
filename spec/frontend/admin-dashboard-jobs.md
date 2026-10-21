# Admin dashboard and admin jobs

## Purpose

Gives administrators one page with the live state of the job queue (worker heartbeat, running
and waiting counts, pause and maintenance switches) plus headline counts and recent jobs, and a
second page listing every user's jobs with filters and the admin-only cancel and restart
actions. These views are thin clients of the admin API; all rules about what pausing,
maintenance, cancel and restart do live in the backend spec.

## Scope

Covered:

- `frontend/src/views/admin/AdminDashboardView.vue` (route `/admin`)
- `frontend/src/views/admin/AdminJobsView.vue` (route `/admin/jobs`)
- The dashboard, queue, maintenance and admin-jobs functions of `frontend/src/api/admin.js`
  (`getDashboard`, `pauseQueue`, `resumeQueue`, `enterMaintenance`, `exitMaintenance`,
  `listAdminJobs`, `cancelAdminJob`, `restartAdminJob`) and the use of `listAdminWorkflows`
  to fill the workflow filter.

Out of scope:

- Route guards themselves ([routing.md](routing.md)); the admin sidebar/`AdminLayout` and the
  maintenance banner ([layout-navigation.md](layout-navigation.md)).
- Shared `Pagination`, `ConfirmDialog`, `AlertMessage`, `LoadingSpinner`
  ([common-components.md](common-components.md)).
- The job detail page reached from the job links ([job-detail.md](job-detail.md)).
- Server behaviour of every operation ([../backend/admin-api.md](../backend/admin-api.md)).
- Charts: `chart.js` is a declared dependency (`frontend/package.json:19`) but no admin view
  draws a chart today. Nothing here specifies charts (see Open questions).

## Dependencies

- [../backend/admin-api.md](../backend/admin-api.md) — BE-ADM-010…014 (dashboard, queue,
  maintenance), BE-ADM-040…043 (admin jobs).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md) — cancel semantics, worker
  heartbeat.
- [api-client.md](api-client.md) — `apiErrorMessage`, 401 handling.
- [state-stores.md](state-stores.md) — `server.load(true)` refreshes the maintenance banner.
- Contract operations: `admin_dashboard`, `admin_queue_pause`, `admin_queue_resume`,
  `admin_maintenance_enter`, `admin_maintenance_exit`, `admin_jobs_list`,
  `admin_jobs_cancel_create`, `admin_jobs_restart_create`, `admin_workflows_list`
  (see [api-contract.md](api-contract.md)).

## Requirements

### Access

- **FE-ADASH-001** `/admin` and `/admin/jobs` MUST be reachable only by a signed-in admin
  (`meta.requiresAdmin`). A signed-in non-admin MUST be redirected to `/`; an anonymous visitor
  MUST be redirected to `/login?next=<path>`. No admin API call MUST be made before the guard
  passes.

### Dashboard

- **FE-ADASH-010** On mount the dashboard MUST call `getDashboard` (`admin_dashboard`) and show a
  spinner until the first response. It MUST then re-fetch every 10 s and on the Refresh button
  (`dashboard-refresh`), and MUST stop polling when the view is unmounted.
- **FE-ADASH-011** If a dashboard fetch fails, the view MUST show the error envelope message
  (fallback "Could not load the dashboard.") in an alert. Data from an earlier successful fetch
  MUST stay on screen; the next successful poll MUST clear the alert.
- **FE-ADASH-012** The queue card MUST show: worker status (`worker-status`, `data-worker`
  `ok`/`down`; "Worker alive (pid N)" or "Worker not running" with the last-seen time when
  known), running count with `max_running`, waiting count with `max_queue`, queue state
  Paused/Active (`queue-state`, `data-paused`) and maintenance On/Off (`maintenance-state`,
  `data-maintenance`), all taken from `queue` of the response.
- **FE-ADASH-013** The view MUST show exactly one of Pause queue (`queue-pause`, when not paused,
  calls `pauseQueue`) or Resume queue (`queue-resume`, when paused, calls `resumeQueue`).
- **FE-ADASH-014** When maintenance is off the view MUST offer a banner-message input
  (`maintenance-message`, pre-filled once from `queue.maintenance_message`) and an Enter
  maintenance mode button (`maintenance-enter`) that calls `enterMaintenance(message)`; an empty
  message MUST be sent as an empty body so the stored message is kept. When maintenance is on it
  MUST offer Leave maintenance mode (`maintenance-exit`, calls `exitMaintenance`).
- **FE-ADASH-015** While a queue or maintenance action runs, all four action buttons MUST be
  disabled. On success the queue card MUST update from the returned `QueueStatus` without a full
  reload, and the view MUST call `server.load(true)` so the site-wide maintenance banner changes
  at once. On failure the envelope message MUST be shown and the queue state left unchanged.
- **FE-ADASH-016** The counts row MUST show jobs (`total`, `success`, `failed`, `cancelled`),
  users (`total`, `active`, `admins`), workflows (`total`, `enabled`, `disabled`, `invalid`,
  invalid highlighted when non-zero) and active jobs (`running + waiting`), with the
  `count-*` test ids used by the e2e suite.
- **FE-ADASH-017** The Recent jobs table MUST list `recent_jobs` in response order with name
  (link to `/jobs/<id>`, id when name is empty), workflow name, username, submitted time and a
  state badge (`data-state`). An empty list MUST show "No jobs yet.". An "All jobs" link MUST go
  to `/admin/jobs`.
- **FE-ADASH-018** (planned) When `config.ok` is `false` the dashboard MUST show a warning alert
  listing every entry of `config.errors`, so the admin sees that `settings.yaml` has invalid
  values.
- **FE-ADASH-019** All server-supplied strings on the dashboard (job names, usernames, workflow
  names, maintenance message, config errors) MUST be rendered as text interpolation; the view
  MUST NOT use `v-html`.

### Admin jobs

- **FE-ADASH-030** On mount `/admin/jobs` MUST call `listAdminJobs({page: 1})`
  (`admin_jobs_list`) and `listAdminWorkflows` (`admin_workflows_list`) for the workflow filter.
  A failure of the workflow list MUST leave the filter with only "All workflows" and MUST NOT
  show an error.
- **FE-ADASH-031** The filter form MUST offer state (the five job states), workflow (installed
  workflow ids, labelled by name) and user (free text, username or id). Changing state or
  workflow MUST re-fetch page 1 immediately; the user field MUST apply on Filter/Enter. Reset
  (`jobs-filter-reset`) MUST clear all three and fetch page 1. Empty filters MUST NOT be sent as
  query parameters.
- **FE-ADASH-032** The table MUST show one row per result (`admin-job-row`, `data-job-id`,
  `data-state`) with state badge, name (link to `/jobs/<id>`), workflow name, username,
  submitted and finished time ("-" when null). An empty page MUST show "No jobs found."
  (`admin-jobs-empty`). A load failure MUST show the envelope message (fallback "Could not load
  jobs.").
- **FE-ADASH-033** Pagination MUST be derived from `count` and the page size actually requested;
  changing page MUST keep the current filters.
- **FE-ADASH-034** A Cancel button (`admin-job-cancel`) MUST be shown only for jobs the server
  marks cancellable (`can_cancel`), and a Restart button (`admin-job-restart`) only for jobs it
  marks restartable (`can_restart`).
- **FE-ADASH-035** Cancel and Restart MUST ask for confirmation (`ConfirmDialog`, "Cancel this
  job?" / "Restart this job?"). On confirm the view MUST call `cancelAdminJob` /
  `restartAdminJob`, show `Job "<name>" cancelled.` / `restarted.` (`jobs-success`) and re-fetch
  the current page. On failure (e.g. 409 `invalid_state`, `workspace_removed`,
  `workflow_unavailable`) it MUST show the envelope message and close the dialog.
- **FE-ADASH-036** Job names, usernames and workflow names MUST be rendered as text; the view
  MUST NOT use `v-html`.

## Interfaces

| View action | API function (`src/api/admin.js`) | operationId | Response used |
|-------------|-----------------------------------|-------------|---------------|
| Load / poll dashboard | `getDashboard()` | `admin_dashboard` | `Dashboard` |
| Pause / resume queue | `pauseQueue()` / `resumeQueue()` | `admin_queue_pause` / `admin_queue_resume` | `QueueStatus` |
| Enter / leave maintenance | `enterMaintenance(message)` / `exitMaintenance()` | `admin_maintenance_enter` / `admin_maintenance_exit` | `QueueStatus` |
| List jobs | `listAdminJobs({state, user, workflow, page})` | `admin_jobs_list` | `PaginatedJobListList` |
| Cancel / restart | `cancelAdminJob(id)` / `restartAdminJob(id)` | `admin_jobs_cancel_create` / `admin_jobs_restart_create` | `JobDetail` (ignored; list re-fetched) |
| Workflow filter options | `listAdminWorkflows()` | `admin_workflows_list` | `AdminWorkflow[]` |

`listAdminJobs` drops `''`, `null` and `undefined` params before the request
(`frontend/src/api/admin.js:44-50`). Field shapes: see [api-contract.md](api-contract.md).

## Behaviour

Dashboard poll loop: mount → `load()` → `setInterval(load, 10000)`; unmount → `clearInterval`.
`load()` replaces the whole `data` object; queue actions replace only `data.queue` with the
action response, so a poll arriving later overwrites it with the same server state.

Admin-jobs confirm flow: row button → `confirm = {job, action}` → dialog → `doConfirm()` →
API call → success message + re-fetch current page → dialog closed (also on error).

State badge colours (both views): waiting = warning, running = primary, success = success,
failed = danger, cancelled = secondary.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-ADASH-001 | `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` (users route); `frontend/src/test/router.test.js` admin guard for `/admin`, `/admin/jobs` (planned) | e2e, unit |
| FE-ADASH-010, 011 | `frontend/src/test/views/AdminDashboardView.test.js` › polls every 10 s, stops on unmount, keeps data on error (planned) | unit |
| FE-ADASH-012, 016, 017 | `e2e/tests/test_admin_dashboard.py::test_d1_dashboard_counts_match_db` | e2e |
| FE-ADASH-013, 015 | `e2e/tests/test_admin_dashboard.py::test_d1_pause_resume_queue`, `::test_d7_logs_show_admin_actions` | e2e |
| FE-ADASH-014, 015 | `e2e/tests/test_admin_dashboard.py::test_d1_maintenance_mode_banner`; `frontend/src/test/admin-api.test.js` › admin api request shape (`enterMaintenance`) | e2e, unit |
| FE-ADASH-018 | `frontend/src/test/views/AdminDashboardView.test.js` › shows config errors (planned) | unit |
| FE-ADASH-019, 036 | `frontend/src/test/views/admin-no-vhtml.test.js` › admin dashboard/jobs render `<script>` names as text (planned) | unit |
| FE-ADASH-030, 031, 032 | `e2e/tests/test_admin_dashboard.py::test_d2_admin_jobs_filter_cancel_restart`; `frontend/src/test/admin-api.test.js` › sends only non-empty admin job filters (C6) | e2e, unit |
| FE-ADASH-033 | `frontend/src/test/views/AdminJobsView.test.js` › page count from count/page_size, filters kept (planned) | unit |
| FE-ADASH-034, 035 | `e2e/tests/test_admin_dashboard.py::test_d2_admin_jobs_filter_cancel_restart`; restart of a purged job hides the button (planned, same file) | e2e |
| (contract) | `frontend/src/test/contracts/` fixture for `Dashboard` and `QueueStatus` validated against `schema.yaml` (planned) | contract |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| FE-ADASH-018 | The `config` block (`ConfigStatus {ok, errors}`) returned by `admin_dashboard` is ignored; an admin gets no UI signal that `settings.yaml` has invalid keys (QA C-02 follow-up). | `frontend/src/views/admin/AdminDashboardView.vue:63-231` | major |
| FE-ADASH-034 | Buttons are chosen from hard-coded state lists (`ACTIVE`, `RESTARTABLE`) instead of `can_cancel`/`can_restart`. Restart is offered for purged jobs (server answers 409 `workspace_removed`) and Cancel for jobs with `cancel_requested`. | `frontend/src/views/admin/AdminJobsView.vue:15-16`, `:142-158` | minor |
| FE-ADASH-033 | The view assumes the server page size is 20 (`pageSize = 20`) but does not send `page_size`; a change of the backend `PAGE_SIZE` breaks page counts. | `frontend/src/views/admin/AdminJobsView.vue:25`, `:45` | minor |
| — | Schema drift tolerance: the view reads legacy fields as fallbacks (`job.status`, `job.workflow_name`, `job.user_username`, `job.completed_at`, `data.results ?? data`) that are not how `JobList` / `PaginatedJobListList` define these values; this hides contract breaks instead of failing. | `frontend/src/views/admin/AdminJobsView.vue:36-38`, `:46-47`, `:140` | minor |
| — | Duplicate admin-job API functions: `src/api/jobs.js` also exports `adminListJobs`, `adminCancelJob`, `adminRestartJob` (used by `JobDetailView`), so two modules call the same operations. | `frontend/src/api/jobs.js:33-38` | minor |
| FE-ADASH-031 | The `search` filter that `admin_jobs_list` supports is not offered in the UI. | `frontend/src/views/admin/AdminJobsView.vue:93-116` | minor |
| FE-ADASH-010 | Overlapping polls are not guarded: a slow response can land after a newer one, and a poll can overwrite the queue state just set by an action until the next poll. | `frontend/src/views/admin/AdminDashboardView.vue:29-40`, `:56-59` | minor |
| — | No view-level vitest tests exist for either view; only API-module request shapes are unit tested. | `frontend/src/test/` | minor |

## Open questions

- Should the dashboard have charts (jobs per day/state)? `chart.js` is installed but unused;
  either spec charts as a feature or drop the dependency ([overview.md](overview.md)).
- Should the dashboard poll pause while the browser tab is hidden?
