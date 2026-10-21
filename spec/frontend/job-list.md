# Job list

## Purpose

The job list (`/jobs`) is the signed-in user's dashboard of their own jobs. It shows each job's
state, queue position and duration, lets the user filter by state and page through results,
refreshes itself while any listed job is active, and offers cancel and delete with a confirmation
step. It also owns the job state badge, the one place where a backend job state is turned into a
label, icon and colour.

## Scope

Covered:

- `frontend/src/views/public/JobListView.vue`
- `frontend/src/components/jobs/JobStatusBadge.vue` (also used by [job-detail.md](job-detail.md))
- The list-related functions of `frontend/src/api/jobs.js`: `listJobs`, `cancelJob`, `deleteJob`,
  `JOB_STATES`, `ACTIVE_STATES`, `isActiveState`
- Use of `createPoller`/`usePolling` (`frontend/src/components/jobs/usePolling.js`) by this view.
  The poller's own algorithm is specified in [job-detail.md](job-detail.md#polling-algorithm).

Out of scope:

- `frontend/src/stores/jobs.js` (`useJobsStore`). The list view does **not** use it; the store
  is specified in [state-stores.md](state-stores.md).
- The admin jobs view (`/admin/jobs`, `adminListJobs`): [admin-dashboard-jobs.md](admin-dashboard-jobs.md).
- `ConfirmDialog`, `Pagination`, `AlertMessage`, `LoadingSpinner` internals:
  [common-components.md](common-components.md).
- Route guard mechanics and the 401 handler: [routing.md](routing.md), [api-client.md](api-client.md).

## Dependencies

- [../backend/jobs-api.md](../backend/jobs-api.md): `jobs_list` (BE-JAPI-005, 006),
  `jobs_cancel_create` (BE-JAPI-011..013), `jobs_destroy` (BE-JAPI-014, 015), summary fields
  (BE-JAPI-007).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md): job states and transitions
  (BE-QUEUE-001, 002), queue position (BE-QUEUE-005).
- [api-contract.md](api-contract.md) for the operation → function map; schema components
  `PaginatedJobListList`, `JobList`, `JobDetail`, `Error` in `schema.yaml`.
- [api-client.md](api-client.md): `apiErrorMessage`.
- [routing.md](routing.md): `meta.requiresAuth` guard.
- [common-components.md](common-components.md): `ConfirmDialog` (renders `message` with `v-html`),
  `Pagination` (hidden when there is one page).

## Requirements

### Access and loading

- **FE-JLIST-001** The route `/jobs` MUST require authentication (`meta.requiresAuth`). An
  anonymous visitor MUST be sent to the login page by the router guard
  ([routing.md](routing.md)) and no `jobs_list` call is made for them.
- **FE-JLIST-002** The view MUST show only the caller's own jobs, as returned by `jobs_list`; an
  admin also sees only their own jobs here (all users' jobs are in `/admin/jobs`).
- **FE-JLIST-003** On mount the view MUST call `listJobs({page: 1, page_size: 20})`
  (`jobs_list`) and show the loading spinner until the first response or error.
- **FE-JLIST-004** If loading fails, the view MUST show the envelope message from
  `apiErrorMessage` in the `jobs-error` alert, with the fallback `Could not load jobs.`.

### Table

- **FE-JLIST-005** Each job MUST be one `job-row` with `data-job-id` and `data-state`, showing:
  the state badge (FE-JLIST-017); the job name as a link to `/jobs/<id>`; `workflow_name` and
  `workflow_version`; `submitted_at` in the browser's locale; and `duration_seconds` formatted as
  `Ns`, `Nm Ns` or `Nh Nm` (truncated seconds), or `-` when null.
- **FE-JLIST-006** A `waiting` job with a non-null `queue_position` MUST show
  `Queue position <n>` (`job-row-queue`). A `running` job with `cancel_requested` true MUST show
  `Cancelling…`.
- **FE-JLIST-007** Job name, workflow name and version MUST be rendered with text interpolation,
  never `v-html`.

### Filter and pagination

- **FE-JLIST-008** The state filter (`job-filter-state`) MUST offer `All` (no `state` param),
  `Active` (`state=waiting,running`) and one option per state in `JOB_STATES`, labelled with the
  capitalised state name. Changing it MUST reload page 1 with the chosen `state`.
- **FE-JLIST-009** The view MUST request pages of 20 (`page_size=20`) and compute the page count
  as `ceil(count / 20)` (minimum 1). The `Pagination` control MUST be shown only when there is more
  than one page; choosing a page MUST call `jobs_list` with that `page` and the current filter.

### Empty state

- **FE-JLIST-010** When the loaded page has no jobs, the view MUST show `jobs-empty` instead of
  the table: with no filter, `No jobs yet. Run a workflow to get started.` where "Run a workflow"
  links to `/`; with a filter, `No jobs in this state.`.

### Refresh while active

- **FE-JLIST-011** While at least one job on the current page is `waiting` or `running`, the
  view MUST refetch the current page and filter, first after 3 s. A refetch whose
  `(id, state, queue_position)` list is unchanged, or that fails, MUST increase the delay by ×1.5
  up to 10 s; a changed refetch MUST reset it to 3 s.
- **FE-JLIST-012** Refreshing MUST stop when no job on the current page is active, and MUST stop
  when the view is unmounted. It MUST restart when a later fetch (filter, page, action) returns an
  active job.
- **FE-JLIST-013** (planned) Refreshing SHOULD pause while the document is hidden
  (`document.hidden`) and resume with an immediate fetch when it becomes visible.

### Cancel and delete

- **FE-JLIST-014** A row MUST show the Cancel button (`job-row-cancel`) only when the job's
  `can_cancel` is true, and the Delete button (`job-row-delete`) only when `can_delete` is true.
  The view MUST NOT derive these from `state` itself.
- **FE-JLIST-015** Each button MUST open a `ConfirmDialog` and send no request until the user
  confirms:

  | Action | Title | Message | Confirm button |
  |--------|-------|---------|----------------|
  | cancel | `Cancel Job` | `Are you sure you want to cancel <b>NAME</b>?` | `Cancel Job` (`btn-warning`) |
  | delete | `Delete Job` | `Delete <b>NAME</b> and all its results? This cannot be undone.` | `Delete Job` (`btn-danger`) |

  Dismissing the dialog MUST send nothing. NAME MUST be the job name HTML-escaped (`& < > " '`)
  before it is placed in the message, because `ConfirmDialog` renders `message` with `v-html`
  (Article 8.2).
- **FE-JLIST-016** On confirm the view MUST call `cancelJob(id)` (`jobs_cancel_create`) or
  `deleteJob(id)` (`jobs_destroy`), keep the confirm button disabled with `Please wait...` while
  the request runs, then refetch the current page and filter. On error (for example `409
  invalid_state`) it MUST show the envelope message in `jobs-error`. The dialog MUST close in both
  cases.
- **FE-JLIST-018** (planned) After an action, if the current page no longer exists (the server
  answers `404` for a page beyond the last), the view SHOULD load the last existing page instead
  of showing an error.

### State badge

- **FE-JLIST-017** `JobStatusBadge` MUST map every state of BE-QUEUE-001 as follows, set
  `data-state` to the state and `title` to the label, and show the label text only when
  `with-label` is set:

  | State | Label | Icon | Badge class | Active? |
  |-------|-------|------|-------------|---------|
  | `waiting` | Waiting | `fa-hourglass-half` | `bg-secondary` | yes |
  | `running` | Running | `fa-spinner fa-spin` | `bg-primary` | yes |
  | `success` | Success | `fa-check` | `bg-success` | no |
  | `failed` | Failed | `fa-times` | `bg-danger` | no |
  | `cancelled` | Cancelled | `fa-ban` | `bg-warning text-dark` | no |
  | any other / empty | the raw value (`unknown` when empty) | `fa-circle` | `bg-light text-dark` | no |

  "Active" is `isActiveState(state)` (`waiting`, `running`) and MUST match BE-QUEUE-001.
- **FE-JLIST-019** (planned) The icon-only badge used in the table SHOULD expose its label to
  assistive technology (visually hidden text or `aria-label`), not only through `title`.

### API use

- **FE-JLIST-020** The view MUST reach the API only through `src/api/jobs.js` functions
  (Article 5.1f).

## Interfaces

API calls (operation details in [../backend/jobs-api.md](../backend/jobs-api.md#interfaces)):

| Function (`src/api/jobs.js`) | operationId | Used for |
|------------------------------|-------------|----------|
| `listJobs(params)` | `jobs_list` | initial load, filter, page change, refresh, after actions |
| `cancelJob(id)` | `jobs_cancel_create` | Cancel (response body ignored; page is refetched) |
| `deleteJob(id)` | `jobs_destroy` | Delete (`204`) |

`listJobs` also accepts a bare page number (legacy form, `listJobs(3)` → `?page=3`).

Fields read from each `JobList` item: `id`, `name`, `state`, `queue_position`,
`cancel_requested`, `workflow_name`, `workflow_version`, `submitted_at`, `duration_seconds`,
`can_cancel`, `can_delete`. From the page: `count`, `results`. The view tolerates a bare array
response (`data.results ?? data`), which `schema.yaml` does not allow.

Exports used by other views: `JOB_STATES = ['waiting','running','success','failed','cancelled']`,
`ACTIVE_STATES = ['waiting','running']`, `isActiveState(state)`.

Test ids: `job-filter-state`, `jobs-error`, `jobs-empty`, `jobs-table`, `job-row`
(`data-job-id`, `data-state`), `job-row-state`, `job-row-link`, `job-row-queue`,
`job-row-cancel`, `job-row-delete`; dialog `confirm-ok` / `confirm-cancel`.

`JobStatusBadge` props: `state` (preferred), `status` (legacy alias), `withLabel` (bool),
`testid` (default `job-state`).

## Behaviour

```
mount ─► fetch page 1 ─► any active? ─yes─► poll (3 s … ×1.5 … 10 s) ─► no active ─► stop
                │                                  ▲
filter/page ────┘        cancel/delete confirmed ──┘ (refetch; restarts poll if active)
```

- `loading` is true only until the first fetch settles; filter and page changes do not show the
  spinner, the table is replaced when the response arrives.
- A refresh error is swallowed by the poller (it only lengthens the delay); the table keeps the
  last good data and no message is shown.
- Cancelling a `waiting` job makes it `cancelled` at once; cancelling a `running` job leaves it
  `running` with `cancel_requested` (row shows `Cancelling…`) until the worker stops it
  (BE-JAPI-011, 012). The refresh loop picks up the final state.
- The filter value `waiting,running` relies on the comma list accepted by BE-JAPI-006.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-JLIST-001 | `e2e/tests/test_deep_links.py::test_protected_route_logged_out_redirects_to_login_with_next[/jobs]`, `::test_user_route_deep_link_and_refresh[/jobs]` | e2e |
| FE-JLIST-002 | `e2e/tests/test_access_jobs.py::test_other_user_cannot_see_job_outputs_or_log` (API list); UI check `frontend/src/test/views/job-list.test.js` › "lists only returned jobs" (planned) | e2e, unit |
| FE-JLIST-003 | `frontend/src/test/contracts/jobs.test.js` › "jobs api endpoints" › "lists own jobs with params or a page number"; view call `frontend/src/test/views/job-list.test.js` › "loads page 1 of 20 on mount" (planned) | unit |
| FE-JLIST-004 | `frontend/src/test/views/job-list.test.js` › "shows the envelope message on load error" (planned) | unit |
| FE-JLIST-005 | `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` (row, `data-state`); duration/date formatting `frontend/src/test/views/job-list.test.js` › "formats duration" (planned) | e2e, unit |
| FE-JLIST-006 | `frontend/src/test/views/job-list.test.js` › "shows queue position and cancelling" (planned) | unit |
| FE-JLIST-007 | `e2e/tests/test_jobs_list.py::test_html_in_job_name_is_text` (planned) | e2e |
| FE-JLIST-008 | `e2e/tests/test_jobs_list.py::test_state_filter` (planned) | e2e |
| FE-JLIST-009 | `e2e/tests/test_jobs_list.py::test_pagination` (planned) | e2e |
| FE-JLIST-010 | `frontend/src/test/views/job-list.test.js` › "empty state with and without filter" (planned) | unit |
| FE-JLIST-011, 012 | `frontend/src/test/contracts/dynamic-form.test.js` › "helpers" › "poller backs off without changes and stops when inactive" (poller); `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` (row reaches `cancelled` without reload); view wiring `frontend/src/test/views/job-list.test.js` › "polls only while a job is active" (planned) | unit, e2e |
| FE-JLIST-014 | `frontend/src/test/views/job-list.test.js` › "buttons follow can_cancel/can_delete" (planned); `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` | unit, e2e |
| FE-JLIST-015 | `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` (confirm-ok path); dismiss sends nothing + escaping `frontend/src/test/views/job-list.test.js` › "confirm dialog escapes the job name" (planned) | e2e, unit |
| FE-JLIST-016 | `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` (cancel); delete from list and 409 message `e2e/tests/test_jobs_list.py::test_delete_from_list_and_conflict_message` (planned) | e2e |
| FE-JLIST-017 | `frontend/src/test/components/job-status-badge.test.js` › "maps every state" (planned); `frontend/src/test/contracts/jobs.test.js` › "jobs api endpoints" › "state helpers" (state list) | unit |
| FE-JLIST-020 | `frontend/src/test/architecture.test.js` › "views do not import the HTTP client" (planned) | unit |

FE-JLIST-013, 018, 019 are SHOULD (planned) and have no test yet.

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| FE-JLIST-008 | `Active` sends `state=waiting,running`, but `schema.yaml` declares `jobs_list.state` as a single-value enum. A schema-validating contract test of the request would reject it (backend side: BE-JAPI-006 gap). | `frontend/src/views/public/JobListView.vue:99` | minor |
| FE-JLIST-017 | `schema.yaml` gives `JobList.state` as a plain `string` (description only, no enum), so the badge mapping and `JOB_STATES` are hand-copied and cannot be checked against the contract. | `frontend/src/api/jobs.js:4`, `schema.yaml` (`JobList.state`) | minor |
| FE-JLIST-018 | After cancel/delete the view refetches `currentPage`; deleting the only job on the last page (> 1) gets `404` "Invalid page." and shows it as an error with the stale table. | `frontend/src/views/public/JobListView.vue:80` | minor |
| FE-JLIST-013 | Refreshing continues while the tab is hidden (no `visibilitychange` handling anywhere in `src/`). | `frontend/src/components/jobs/usePolling.js:8-49` | minor |
| FE-JLIST-019 | The table badge is icon-only; its label is only in `title`, which screen readers may not announce. | `frontend/src/components/jobs/JobStatusBadge.vue:38-46` | minor |
| FE-JLIST-011 | Refresh errors are silently swallowed; a user whose session expired mid-refresh is redirected by the 401 handler, but other failures (500, network) leave stale data with no notice. | `frontend/src/components/jobs/usePolling.js:17-21` | minor |
| — | The view tolerates a non-paginated array (`data.results ?? data`, `data.count ?? length`), a shape `schema.yaml` does not define. | `frontend/src/views/public/JobListView.vue:48-49` | minor |
| FE-JLIST-002..017 | No component tests exist for `JobListView` or `JobStatusBadge`; filter, pagination and empty state have no e2e test. | `frontend/src/test/` | minor |

## Open questions

- Should the list's refresh rate (3 s start) match the detail view's 2 s, or is a slower list
  rate intended?
- `useJobsStore` duplicates the list logic and is unused; remove it or make the view use it
  (decision for [state-stores.md](state-stores.md)).
