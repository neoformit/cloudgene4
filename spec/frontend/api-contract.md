# Frontend API contract

## Purpose

This file is the frontend index of the HTTP contract between the Vue SPA and the backend
(constitution Article 5). The contract is `schema.yaml` at the repository root; the backend side
and the operation catalogue are in [backend/api-contract.md](../backend/api-contract.md). This file
states how the SPA consumes the contract (API modules, fixtures, contract tests), maps every
`operationId` of the backend catalogue to the API-module function that calls it (or says why the
SPA does not call it), and records every place where the SPA's requests or the response fields it
reads differ from `schema.yaml`. Field shapes are not repeated here; they live in `schema.yaml`.

## Scope

Covered:

- `frontend/src/api/admin.js`, `auth.js`, `jobs.js`, `server.js`, `users.js`, `workflows.js`
  (one function per call) and the use of their functions by views, components and stores.
- `frontend/src/api/client.js` only as "the HTTP client" (Article 5.1f). Its internals (base URL,
  CSRF, interceptors, error helpers) are in [api-client.md](api-client.md).
- Contract tests and test data: `frontend/src/test/schemas.js`, `frontend/src/test/fixtures/jobs.js`,
  `frontend/src/test/contracts/*.test.js`, `frontend/src/test/admin-api.test.js`.
- The shared validation case file `accounts/validation_cases.json` as consumed by
  `frontend/src/utils/validation.js` and `frontend/src/utils/validation.test.js`.

Out of scope:

- What each operation does on the server: the owning backend file named in the
  [backend catalogue](../backend/api-contract.md#operation-catalogue).
- Error envelope reading, 401 handling, CSRF header: [api-client.md](api-client.md).
- View behaviour (loading/empty/error states, messages): the view's own spec file, e.g.
  [job-detail.md](job-detail.md), [admin-users-groups.md](admin-users-groups.md).
- The run-form payload rules per input type (`formModel.js`): [workflow-submit-form.md](workflow-submit-form.md).
  This file only checks the payload against `schema.yaml`.
- Test commands and the requirement-to-test traceability table: [tests.md](tests.md).

## Dependencies

- [backend/api-contract.md](../backend/api-contract.md) — authoritative operation catalogue,
  error codes, pagination and change procedure.
- `schema.yaml` — every component named below.
- [api-client.md](api-client.md) — the HTTP client and the error helpers `apiErrorMessage`,
  `apiFieldErrors`, `apiErrorCode`.
- [state-stores.md](state-stores.md) — `auth`, `server`, `jobs` stores (consumers of `auth_*`,
  `server_info`, `jobs_*`).
- [../backend/accounts.md](../backend/accounts.md) — owner of `accounts/validation_cases.json`.

## Requirements

### Mechanism

- **FE-API-001** Only modules in `frontend/src/api/*.js` MAY import `client.js`'s default export or
  `axios`, or issue HTTP requests to `/api/`. Views, components, stores and the router MUST call
  API-module functions and MUST NOT use `fetch`, `XMLHttpRequest`, `axios` or `client` directly.
  They MAY import the error helpers and `onUnauthorized` from `client.js`.
- **FE-API-002** Each `operationId` the SPA calls MUST have exactly one API-module function. The
  function MUST use the method and the path of `schema.yaml` (relative to the client base URL
  `/api`, ending in `/`).
- **FE-API-003** Path parameters MUST be encoded with `encodeURIComponent` before they are placed in
  a path.
- **FE-API-004** A request body MUST contain only properties declared in the operation's request
  component (`*Request`, `Patched*Request`), with the declared types. Exceptions: `jobs_create`
  carries one multipart part per workflow input id, and `me_destroy` carries `{"password"}`; both
  are undocumented in `schema.yaml` today (Known gaps). JSON bodies are sent as
  `application/json`; `jobs_create` is sent as `multipart/form-data` (`FormData`).
- **FE-API-005** Query parameters MUST be names that `schema.yaml` lists for the operation. Filter
  helpers SHOULD drop empty values (`''`, `null`, `undefined`) before sending.
- **FE-API-006** Consumers MUST read only response fields that exist in the success component of
  the operation they called, and MUST NOT carry fallbacks for shapes the contract does not allow
  (for example `data.results ?? data` on a paginated operation, `job.status`, `job.completed_at`).
- **FE-API-007** A consumer of a paginated operation (`Paginated*List`) MUST either offer paging
  (reading `count` and `results`, sending `page`/`page_size`) or fetch every page. It MUST NOT
  present the first page as the complete set. Consumers of the plain-array operations
  (`admin_groups_list`, `admin_pages_list`, `admin_workflows_list`, `admin_workflows_sync`) MUST
  read the array directly.
- **FE-API-008** Buttons for job actions MUST be shown from the permitted-action flags of the job
  response (`can_cancel`, `can_delete`, `can_restart`), not from a client-side list of states.
  Restart is additionally limited to admins.
- **FE-API-009** Links that the browser follows into `/api/` (output downloads, raw log) MUST use a
  URL from the response (`JobOutput.url`, `JobDetail.log_url`) or a URL builder in an API module.
  No other code MAY build an `/api/` URL.
- **FE-API-010** Views and stores MUST read error responses only through the helpers of
  [api-client.md](api-client.md); they MUST NOT read `err.response.data` directly.

### Contract artefacts and tests

- **FE-API-011** The [operation mapping](#operation-mapping) in this file MUST list every
  `operationId` of the backend catalogue, in the same order, and no other. Adding, renaming or
  removing an operation MUST update both files in the same change (Article 5.1a, 5.1b).
- **FE-API-012** Frontend contract tests MUST validate against components loaded from
  `../schema.yaml` at test time (Article 5.1e). The loader MUST parse the YAML, resolve
  `#/components/schemas/*` references, translate OpenAPI 3.0 keywords to JSON Schema (`nullable:
  true` → `type: [<t>, "null"]`; `readOnly` properties removed from request validation and
  `writeOnly` properties removed from response validation; `allOf` of one `$ref` kept), and
  validate with Ajv and `ajv-formats`. `frontend/src/test/schemas.js` MUST then be deleted.
  (planned)
- **FE-API-013** Every response fixture (`frontend/src/test/fixtures/*`) and every response body
  mocked in a contract test MUST validate against the `schema.yaml` component of the operation it
  stands for; a fixture the schema rejects MUST fail `vitest run`. (planned)
- **FE-API-014** Contract tests MUST validate the request body each API-module function sends
  (and the static parts of the `jobs_create` `FormData`: `workflow`, `job_name`) against the
  operation's request component, and MUST fail on an undeclared property. (planned)
- **FE-API-015** Every exported API-module function MUST have a test that asserts its method, URL,
  query parameters and body.
- **FE-API-016** API-module functions that no view, component or store calls SHOULD be removed;
  while they exist they MUST be listed in the [mapping](#operation-mapping) as unused.
- **FE-API-017** `src/utils/validation.js` MUST return, for every case in
  `accounts/validation_cases.json`, the expected message (or `null`), so that client-side account
  validation matches the server's `error.fields` messages. The case file is the shared contract
  for these rules until pending amendment P2 is decided.
- **FE-API-018** The e2e harness MUST fail a test when the SPA receives an `/api/` error response
  (4xx/5xx) that the test did not declare with `expect_api_error`, so that a request the backend
  rejects as off-contract cannot pass unnoticed (Article 7.3).

## Interfaces

### API modules

| Module | Functions | Operations (prefix) |
|--------|-----------|---------------------|
| `src/api/auth.js` | 7 | `auth_*` |
| `src/api/users.js` | 12 | `me_*`, `admin_users_*`, `admin_groups_*` |
| `src/api/workflows.js` | 3 | `workflows_*`, `categories_list` |
| `src/api/jobs.js` | 12 functions + 3 state helpers | `jobs_*`, duplicates of `admin_jobs_*` |
| `src/api/server.js` | 2 | `server_info`, `pages_retrieve` |
| `src/api/admin.js` | 31 | `admin_*` (dashboard, queue, maintenance, settings, pages, workflows, jobs, logs) |

All functions return the axios promise unchanged. Callers read `response.data`. Every path ends in `/`.

### Test artefacts (as they are today)

| Artefact | Content |
|----------|---------|
| `src/test/schemas.js` | Hand-written JSON Schemas: `userSchema`, `authResponseSchema`, `meResponseSchema`, `workflowInputSchema`, `workflowSchema`, `workflowListSchema`, `profileSchema`, `apiTokenSchema`, `adminUserListSchema`, `adminGroupListSchema`, `jobListItemSchema`, `jobStatusSchema`, `jobSchema`, `errorSchema`/`validationErrorSchema`. Not derived from `schema.yaml` (Known gap FE-API-012). |
| `src/test/fixtures/jobs.js` | `workflowFixture` (all input types), `jobListItemFixture`, `jobStatusFixture`, `jobDetailFixture`. |
| `src/test/setup.js` | Custom matchers `toMatchApiSchema` (Ajv via `global.ajv`), `toBeValidApiResponse`, `toHaveApiField`. |
| `src/test/contracts/*.test.js` | Mock `@/api/client` with `vi.fn()`; assert URL/params/body and validate mocked bodies with the hand-written schemas. |
| `src/test/admin-api.test.js` | Replaces the axios adapter; asserts method, URL and JSON body of every `admin.js` and `server.js` function. Response bodies are not validated. |
| `accounts/validation_cases.json` | Shared table of account-field examples; imported by `src/utils/validation.test.js` through `../../../accounts/validation_cases.json` (a path outside `frontend/`). |

### Target contract-test loader (FE-API-012, planned)

```js
// src/test/openapi.js (planned)
import { readFileSync } from 'node:fs'
import { parse } from 'yaml'                // devDependency to add
const doc = parse(readFileSync(new URL('../../../schema.yaml', import.meta.url), 'utf8'))
export function componentSchema(name, direction /* 'response' | 'request' */) { /* resolve $ref,
  nullable → type union, drop readOnly (request) / writeOnly (response) */ }
export function responseSchema(operationId, status) { /* via paths[*][method].responses */ }
export function requestSchema(operationId) { /* application/json requestBody */ }
```

### Operation mapping

Same order and set as the [backend catalogue](../backend/api-contract.md#operation-catalogue)
(65 operations). "Used by" names the consumer files under `frontend/src/`. Contract test names
use `file › describe › it`. `admin-api` = `src/test/admin-api.test.js › admin api › %#: request shape`
(one case per function). No contract test validates a response against `schema.yaml` today, so the
"Contract test" column means a request-shape test, with the response checked by a hand-written
schema where one is named.

| operationId | Function (file:line) | Request the function builds | Used by | Contract test |
|---|---|---|---|---|
| admin_dashboard | `getDashboard` (admin.js:6) | — | views/admin/AdminDashboardView.vue | admin-api |
| admin_groups_list | `listGroups` (users.js:40) | — | views/admin/AdminUsersView.vue, views/admin/AdminWorkflowSettingsView.vue, components/admin/GroupManagementModal.vue | users.test.js › admin groups › listGroups → plain array with member_count (`adminGroupListSchema`) |
| admin_groups_create | `createGroup` (users.js:43) | body `{name}` (caller-built) | components/admin/GroupManagementModal.vue | users.test.js › admin groups › createGroup / deleteGroup |
| admin_groups_destroy | `deleteGroup` (users.js:46) | path `id` | components/admin/GroupManagementModal.vue | users.test.js › admin groups › createGroup / deleteGroup |
| admin_jobs_list | `listAdminJobs` (admin.js:44); duplicate `adminListJobs` (jobs.js:34, unused) | query from `{state, user, workflow, page}` with empty values dropped; never sends `page_size`, `search` | views/admin/AdminJobsView.vue | admin-api.test.js › admin api › sends only non-empty admin job filters (C6); jobs.test.js › jobs api endpoints › admin endpoints |
| admin_jobs_cancel_create | `cancelAdminJob` (admin.js:51); duplicate `adminCancelJob` (jobs.js:35, unused) | path `id`, no body | views/admin/AdminJobsView.vue | admin-api; jobs.test.js › admin endpoints |
| admin_jobs_restart_create | `restartAdminJob` (admin.js:52) **and** `adminRestartJob` (jobs.js:36; alias `restartJob` jobs.js:38, unused) | path `id`, no body | AdminJobsView.vue (admin.js); views/public/JobDetailView.vue (jobs.js) | admin-api; jobs.test.js › admin endpoints |
| admin_logs_list | `listLogs` (admin.js:55) | query `{min_level, component, search, page, page_size: 50}`, empty dropped; never sends `level` | views/admin/settings/LogsView.vue | admin-api.test.js › admin api › sends log filters |
| admin_maintenance_enter | `enterMaintenance` (admin.js:9) | `{message}` or `{}` when empty | AdminDashboardView.vue | admin-api |
| admin_maintenance_exit | `exitMaintenance` (admin.js:11) | — | AdminDashboardView.vue | admin-api |
| admin_pages_list | `listPages` (admin.js:25) | — | views/admin/settings/PagesView.vue | admin-api |
| admin_pages_retrieve | `getPage` (admin.js:26) | path `slug` (encoded) | PagesView.vue | admin-api (incl. `../x` → `..%2Fx`) |
| admin_pages_update | `savePage` (admin.js:27) | path `slug` (encoded), body `{html}` | PagesView.vue | admin-api |
| admin_pages_destroy | `deletePage` (admin.js:29) | path `slug` (encoded) | PagesView.vue | admin-api |
| admin_queue_pause | `pauseQueue` (admin.js:7) | — | AdminDashboardView.vue | admin-api |
| admin_queue_resume | `resumeQueue` (admin.js:8) | — | AdminDashboardView.vue | admin-api |
| admin_settings_general_retrieve | `getGeneralSettings` (admin.js:14) | — | views/admin/settings/GeneralSettingsView.vue | admin-api |
| admin_settings_general_update | `updateGeneralSettings` (admin.js:15) | body = the whole `GeneralSettings` object as loaded and edited | GeneralSettingsView.vue | admin-api |
| admin_settings_mail_retrieve | `getMailSettings` (admin.js:16) | — | views/admin/settings/MailSettingsView.vue | admin-api |
| admin_settings_mail_update | `updateMailSettings` (admin.js:17) | body = `MailSettings` minus `password_set`, plus `password` when typed, `clear_password: true` when ticked | MailSettingsView.vue | admin-api |
| admin_settings_mail_test | `sendTestMail` (admin.js:18) | `{to}` or `{}` | MailSettingsView.vue | admin-api (both forms) |
| admin_settings_navbar_retrieve | `getNavbar` (admin.js:21) | — | GeneralSettingsView.vue | admin-api |
| admin_settings_navbar_update | `updateNavbar` (admin.js:22) | body `{navbar: [...]}` (array wrapped by the function) | GeneralSettingsView.vue | admin-api |
| admin_settings_nextflow_retrieve | `getNextflowSettings` (admin.js:19) | — | views/admin/settings/NextflowSettingsView.vue | admin-api |
| admin_settings_nextflow_update | `updateNextflowSettings` (admin.js:20) | body = `NextflowSettings` minus `variables` | NextflowSettingsView.vue | admin-api |
| admin_users_list | `listUsers` (users.js:26) | query: AdminUsersView `{page, page_size: 20, search?}`; GroupMembersModal `{group, page_size: 200}`; never `is_active` | views/admin/AdminUsersView.vue, components/admin/GroupMembersModal.vue | users.test.js › admin users › listUsers → GET /admin/users/ with params (paginated) (`adminUserListSchema`) |
| admin_users_retrieve | `getUser` (users.js:29) — **not called by SPA**: the users view works from `admin_users_list` rows and `admin_users_partial_update` responses | path `id` | — | users.test.js › admin users › updateUser / deleteUser / getUser |
| admin_users_partial_update | `updateUser` (users.js:33) | path `id`; body one of `{groups}`, `{is_active}`, `{is_admin}` | AdminUsersView.vue, GroupMembersModal.vue | users.test.js › admin users › updateUser / deleteUser / getUser |
| admin_users_destroy | `deleteUser` (users.js:36) | path `id` | AdminUsersView.vue | users.test.js › admin users › updateUser / deleteUser / getUser |
| admin_workflows_list | `listAdminWorkflows` (admin.js:32) | — | views/admin/AdminWorkflowsView.vue, AdminJobsView.vue (workflow filter) | admin-api |
| admin_workflows_retrieve | `getAdminWorkflow` (admin.js:33) | path `workflow_id` (not encoded) | views/admin/AdminWorkflowSettingsView.vue | admin-api |
| admin_workflows_update | `updateAdminWorkflow` (admin.js:34) | path `workflow_id`; body `{enabled}` (list) or `{enabled, public, groups}` (settings page) | AdminWorkflowsView.vue, AdminWorkflowSettingsView.vue | admin-api |
| admin_workflows_uninstall | `uninstallWorkflow` (admin.js:35) | path `workflow_id` | AdminWorkflowsView.vue | admin-api |
| admin_workflows_nextflow_retrieve | `getWorkflowNextflow` (admin.js:39) | path `workflow_id` | AdminWorkflowSettingsView.vue | admin-api |
| admin_workflows_nextflow_update | `updateWorkflowNextflow` (admin.js:40) | path `workflow_id`; body `{profile, work_dir, config, env}` | AdminWorkflowSettingsView.vue | admin-api |
| admin_workflows_reload | `reloadWorkflow` (admin.js:36) | path `workflow_id` | AdminWorkflowsView.vue, AdminWorkflowSettingsView.vue | admin-api |
| admin_workflows_install | `installWorkflow` (admin.js:37) | body `{path, public, groups, copy}` (never `enabled`) | AdminWorkflowsView.vue | admin-api |
| admin_workflows_sync | `syncWorkflows` (admin.js:38) | — | AdminWorkflowsView.vue | admin-api |
| auth_activate_create | `activate` (auth.js:20) | path `activation_key` (encoded), no body | views/public/ActivateView.vue | users.test.js › account flows (auth.js) › activate POSTs the (url-encoded) key |
| auth_login_create | `login` (auth.js:8) | body `{username, password}` | stores/auth.js (`login`) ← views/public/LoginView.vue | auth.test.js › Session › login() posts credentials and receives {user} (no token) (`authResponseSchema`) |
| auth_logout_create | `logout` (auth.js:11) | no body | stores/auth.js (`logout`) ← components/layout/AppNavbar.vue | auth.test.js › Session › logout() posts to /auth/logout/ |
| auth_me_retrieve | `me` (auth.js:5) | — | stores/auth.js (`boot`, `refresh`) ← router/index.js guards | auth.test.js › Session › me() calls GET /auth/me/ … (`meResponseSchema`) |
| auth_password_reset_create | `requestPasswordReset` (auth.js:24) | body `{email}` | views/public/PasswordResetView.vue | auth.test.js › Password reset › requestPasswordReset() posts the e-mail |
| auth_password_reset_confirm | `confirmPasswordReset` (auth.js:28) | path `token` (encoded); body `{password, password_confirm?}` | views/public/PasswordRecoveryView.vue | users.test.js › account flows (auth.js) › confirmPasswordReset posts password (+ confirm) … |
| auth_register_create | `register` (auth.js:16) | body `{username, full_name, email, password, password_confirm}` | views/public/RegisterView.vue | auth.test.js › Registration › register() posts the form and receives {user, message} |
| categories_list | `listCategories` (workflows.js:9) — **not called by SPA**: no view groups workflows by category | — | — | none |
| categories_retrieve | none — **not called by SPA**: no category view | — | — | — |
| health | none — **not called by SPA**: for load balancers and monitoring ([../backend/server-pages-mail.md](../backend/server-pages-mail.md)) | — | — | — |
| jobs_list | `listJobs` (jobs.js:9) | query `{page, page_size: 20, state?}` (a bare number is sent as `{page}`) | views/public/JobListView.vue; stores/jobs.js (store unused) | jobs.test.js › jobs api endpoints › lists own jobs with params or a page number |
| jobs_create | `submitJob` (jobs.js:18) | `FormData` from `formModel.buildFormData`: `workflow`, `job_name`, one part per editable input id (files as file parts, checkboxes `true`/`false`) | views/public/WorkflowSubmitView.vue | jobs.test.js › submits multipart FormData unchanged (`jobSchema`); dynamic-form.test.js › buildFormData › sends SPEC field names, typed text, explicit checkbox values and files |
| jobs_retrieve | `getJob` (jobs.js:12) | path `id` (not encoded) | JobDetailView.vue; stores/jobs.js (unused) | jobs.test.js › uses the SPEC paths for detail, status, cancel, delete, log |
| jobs_destroy | `deleteJob` (jobs.js:22) | path `id` | JobListView.vue, JobDetailView.vue | same |
| jobs_cancel_create | `cancelJob` (jobs.js:20) | path `id`, no body | JobListView.vue, JobDetailView.vue | same |
| jobs_log_retrieve | `getJobLog` (jobs.js:25) as text; URL builder `jobLogUrl` (jobs.js:29) for the raw-log link | path `id`; `responseType: 'text'` | components/jobs/JobLogTab.vue | same |
| jobs_outputs_retrieve | none via client — **not called through the client**: the browser follows `<a :href="o.url" download>` with `JobOutput.url` (components/jobs/JobResultsTab.vue). URL builder `jobOutputUrl` (jobs.js:30) is unused | — | JobResultsTab.vue (link only) | jobs.test.js (builder only) |
| jobs_status_retrieve | `getJobStatus` (jobs.js:15) | path `id` | JobDetailView.vue (polling, 2 s with back-off to 10 s) | jobs.test.js › uses the SPEC paths … (`jobStatusSchema` on fixture) |
| me_retrieve | `getProfile` (users.js:5) | — | views/public/ProfileView.vue | users.test.js › profile › getProfile → GET /me/ with token metadata only (`profileSchema`) |
| me_partial_update | `updateProfile` (users.js:10) | body `{full_name, email, current_password?}` or `{current_password, password, password_confirm}` | ProfileView.vue | users.test.js › profile › updateProfile → PATCH /me/ |
| me_destroy | `deleteAccount` (users.js:14) | DELETE with JSON body `{password}` | ProfileView.vue | users.test.js › profile › deleteAccount sends the password as the DELETE body |
| me_token_create | `createApiToken` (users.js:18) | no body | ProfileView.vue | users.test.js › profile › createApiToken / revokeApiToken (`apiTokenSchema`) |
| me_token_destroy | `revokeApiToken` (users.js:21) | — | ProfileView.vue | same |
| pages_retrieve | `getPage` (server.js:7) | path `slug` (encoded) | views/public/HomeView.vue (`home`), views/public/StaticPageView.vue | admin-api (server.getPage) |
| server_info | `getServerInfo` (server.js:4) | — | stores/server.js ← App.vue, AppNavbar, AppFooter, MaintenanceBanner, AdminDashboardView, PagesView | admin-api; server-store.test.js › server store › loads name, maintenance, navbar and footer |
| workflows_list | `listWorkflows` (workflows.js:3) | no query (first page only) | HomeView.vue | workflows.test.js › workflows api › lists and gets workflows (mocks a plain array; Known gap) |
| workflows_retrieve | `getWorkflow` (workflows.js:6) | path `id` (not encoded) | views/public/WorkflowSubmitView.vue | workflows.test.js › lists and gets workflows (`workflowSchema`) |

Totals: 65 operations; 60 called by the SPA through the client, 1 followed as a browser link
(`jobs_outputs_retrieve`), 4 not called (`admin_users_retrieve`, `categories_list`,
`categories_retrieve`, `health`).

### Response fields read by consumers

Checked against `schema.yaml`. Only fields outside the component, untyped in it, or
contract-relevant are listed; every other field read exists in the component.

| Operation | Consumer | Fields read | Status vs `schema.yaml` |
|-----------|----------|-------------|-------------------------|
| jobs_list | JobListView.vue:48-49, stores/jobs.js:17-18 | `results ?? data`, `count ?? length` | Fallback for a non-paginated shape (FE-API-006) |
| admin_jobs_list | AdminJobsView.vue:36-38, :45-46, :140 | `job.state ?? job.status`, `workflow?.name ?? workflow_name`, `user?.username ?? user_username`, `finished_at ?? completed_at`, `results ?? data` | `status`, `completed_at` not in `JobList` (FE-API-006) |
| admin_jobs_list | AdminJobsView.vue:14-15, :143, :151 | Cancel/Restart shown from local `ACTIVE`/`RESTARTABLE` state lists | Ignores `can_cancel`/`can_restart` (FE-API-008) |
| workflows_list | HomeView.vue:20-21 | `results ?? data`; first page only | Paginated `PaginatedWorkflowList` (FE-API-006, FE-API-007) |
| admin_groups_list | AdminWorkflowSettingsView.vue:60 | `data.results ?? data ?? []` | Plain array; dead fallback (FE-API-006) |
| admin_users_list | GroupMembersModal.vue:21-22 | `results` of one page of 200 | No paging (FE-API-007) |
| jobs_retrieve / jobs_status_retrieve | JobDetailView.vue:59-64 | `updated_at`, `state`; merges `JobStatus` into the `JobDetail` held | Present in both components |
| jobs_retrieve | JobLogTab.vue:38 via `jobLogUrl` | builds `/api/jobs/{id}/log/` | `JobDetail.log_url` ignored (FE-API-009) |
| jobs_retrieve | JobResultsTab.vue | `outputs[].output_id, label, path, size, download_count, url`, `purged_at`, `expires_at` | Present |
| jobs_retrieve | JobDetailView.vue:198 | `inputs[].value` (any JSON) | Untyped in `JobInput` (backend accepted list) |
| admin_settings_nextflow_retrieve | NextflowSettingsView.vue:81-82 | `variables[].name`, `variables[].description` | `NextflowSettings.variables` is `array` of free-form objects (Known gap) |
| me_retrieve / me_partial_update | ProfileView.vue:63 | `api_token?.created` | `Profile.api_token` nullable object with `created` (typed) |
| workflows_retrieve | formModel.js, ParamInput.vue | `inputs[].type, value, values, min, max, accept, required, visible, help, details, label` | `type` has no enum; `value` untyped (backend accepted list) |
| admin_logs_list | LogsView.vue:72-80 | `metadata` (any object) | Untyped `SystemLog.metadata` (backend accepted list) |
| server_info | stores/server.js:25-30 | `name, url, maintenance, maintenance_message, navbar || [], footer_html || ''` | Present |
| auth_register_create | RegisterView.vue:36 | `message` only (`activation_required` unused) | Present |

## Behaviour

### Change flow on the frontend side

Steps 4 and 6 of the backend [change procedure](../backend/api-contract.md#change-procedure), in
this order, in the same change set as the backend change:

1. Update or add the API-module function (path, method, params, body).
2. Update fixtures; run the contract tests, which (once FE-API-012 is done) load the new
   components from the regenerated `schema.yaml` and reject stale fixtures.
3. Update views/stores that read the changed fields; grep for the old field name.
4. Update the [operation mapping](#operation-mapping) row and the
   [fields-read table](#response-fields-read-by-consumers).

### Pagination use

| Operation | Consumer | Paging |
|-----------|----------|--------|
| jobs_list | JobListView | `page`, `page_size=20`, `Pagination` component, polling every 3 s while a job is active |
| admin_jobs_list | AdminJobsView | `page`; page size assumed 20 (server default) |
| admin_users_list | AdminUsersView | `page`, `page_size=20` |
| admin_users_list | GroupMembersModal | one request, `page_size=200` (server cap); no further pages |
| admin_logs_list | LogsView | `page`, `page_size=50` |
| workflows_list | HomeView | none — first page (20) only |
| categories_list | — | not called |

### Unused or duplicate functions

| Function | Status |
|----------|--------|
| `jobs.adminListJobs`, `jobs.adminCancelJob` | Duplicates of `admin.listAdminJobs`, `admin.cancelAdminJob`; unused |
| `jobs.adminRestartJob` / `admin.restartAdminJob` | Two functions for `admin_jobs_restart_create`; both used |
| `jobs.restartJob` | Deprecated alias; unused |
| `jobs.jobOutputUrl` | Unused; downloads use `JobOutput.url` |
| `users.getUser` | Unused |
| `workflows.listCategories` | Unused |
| `admin.getPage` vs `server.getPage` | Same name for `admin_pages_retrieve` and `pages_retrieve` |
| `stores/jobs.js` (`useJobsStore`) | Never imported; calls `listJobs`/`getJob` |

### Direct HTTP outside `src/api`

None. A grep of `frontend/src` (excluding `src/api` and `src/test`) finds no `axios`, `fetch(`,
`XMLHttpRequest` or `client.<method>` use. All `/api/` paths called by the SPA exist in
`schema.yaml`.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-API-001 | Lint/grep test: no `axios`/`fetch`/`client` import outside `src/api` (planned: `src/test/contracts/boundary.test.js::only api modules call the client`) | unit |
| FE-API-002 | `src/test/admin-api.test.js › admin api › %#: request shape`; `src/test/contracts/jobs.test.js › jobs api endpoints › uses the SPEC paths for detail, status, cancel, delete, log`; `src/test/contracts/users.test.js › users API › *`; `src/test/contracts/auth.test.js › Authentication API Contracts › *`; every path/method checked against `schema.yaml` (planned: `src/test/contracts/operations.test.js::every api function uses a schema.yaml path and method`) | contract |
| FE-API-003 | `src/test/admin-api.test.js › admin api › %#: request shape` (`getPage('../x')`); `users.test.js › account flows (auth.js) › activate POSTs the (url-encoded) key`; job/workflow/user ids (planned) | contract |
| FE-API-004 | `admin-api.test.js › admin api › %#: request shape` (bodies); `dynamic-form.test.js › buildFormData › sends SPEC field names, typed text, explicit checkbox values and files`; schema validation of bodies (planned, FE-API-014) | contract |
| FE-API-005 | `admin-api.test.js › admin api › sends only non-empty admin job filters (C6)`, `› sends log filters`; `jobs.test.js › lists own jobs with params or a page number` | contract |
| FE-API-006 | (planned) `src/test/contracts/fields-read.test.js::views read only schema fields` — mount each list view with a schema-valid fixture and assert rendering | unit |
| FE-API-007 | `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` (job list); home page with more than 20 workflows (planned: `e2e/tests/test_smoke.py::test_home_lists_all_workflows`) | e2e |
| FE-API-008 | `e2e/tests/test_admin_dashboard.py::test_d2_admin_jobs_filter_cancel_restart`; restart hidden for purged job (planned) | e2e |
| FE-API-009 | `e2e/tests/test_access_jobs.py::test_owner_and_admin_can_download`; `e2e/tests/test_jobs.py::test_all_inputs_uploads_folder_and_write_file` | e2e |
| FE-API-010 | `src/test/client.test.js › apiErrorMessage › *`; grep test (planned, with FE-API-001) | unit |
| FE-API-011 | (planned) `src/test/contracts/operations.test.js::mapping table lists every schema.yaml operationId` — parses this file and `schema.yaml` | unit |
| FE-API-012 | (planned) `src/test/contracts/openapi-loader.test.js::loads components from schema.yaml` | contract |
| FE-API-013 | (planned) `src/test/contracts/fixtures.test.js::every fixture validates against its schema.yaml component` | contract |
| FE-API-014 | (planned) `src/test/contracts/requests.test.js::request bodies validate against *Request components` | contract |
| FE-API-015 | `admin-api.test.js`, `contracts/*.test.js` (all functions except `listCategories`) | contract |
| FE-API-016 | Review; (planned) `operations.test.js::every exported function is used or listed unused` | unit |
| FE-API-017 | `src/utils/validation.test.js › validation mirrors accounts/validation.py › username/email/password/full name/group name …`; backend side `accounts/tests.py::ValidationRulesTest`; `e2e/tests/test_accounts.py::test_a2_client_side_rules_match_server` | unit, e2e |
| FE-API-018 | `e2e/tests/test_harness_selftest.py::test_api_500_fails`, `::test_declared_api_error_passes`, `::test_declared_wrong_status_still_fails` | e2e |

Cross-stack coverage (Article 7.3) of the operations the SPA calls is listed per view in the view
spec files and in [tests.md](tests.md).

## Known gaps

| Req | What the code does | Where | Severity |
|-----|--------------------|-------|----------|
| FE-API-012 | Contract tests use hand-written JSON Schemas, not components loaded from `schema.yaml` (Article 5.1e). No YAML loader or OpenAPI-to-JSON-Schema step exists; drift between `schema.yaml` and the SPA is not detected. | `frontend/src/test/schemas.js`, `frontend/src/test/setup.js:47`, `frontend/package.json` (no `yaml` dependency) | major |
| FE-API-013 | `workflowFixture.category_name` is `null`, but `Workflow.category_name` in `schema.yaml` is a non-nullable string. The fixture matches the server (`CharField(..., default=None)`), so the schema is wrong; the fixture will fail once FE-API-013 is in force. | `frontend/src/test/fixtures/jobs.js:11`, `workflows/serializers.py:50`, `schema.yaml` `Workflow` | minor |
| FE-API-013 | The `user` mocked in auth contract tests lacks `is_active`, `groups`, `date_joined`, `last_login`, which `User` requires; the hand-written `userSchema` does not require them. | `frontend/src/test/contracts/auth.test.js:22`, `frontend/src/test/schemas.js:5` | minor |
| FE-API-013 | `workflows_list` is mocked and validated as a plain array (`workflowListSchema`), but the operation returns `PaginatedWorkflowList`. The test encodes a shape the server never sends. | `frontend/src/test/contracts/workflows.test.js:27`, `frontend/src/test/schemas.js:149` | major |
| FE-API-013 | Hand-written schemas add enums that `schema.yaml` lacks: job `state` (`JOB_STATE`) and `WorkflowInput.type`. The "rejects legacy shapes" and "rejects unknown input types" tests lose their meaning when schemas come from `schema.yaml` unless the backend adds these enums (BE-API-004 gap). | `frontend/src/test/schemas.js:44`, `:154`; `frontend/src/test/contracts/workflows.test.js:42`; `jobs.test.js:88` | minor |
| FE-API-014 | No test validates request bodies against `*Request` components. | `frontend/src/test/admin-api.test.js`, `contracts/*.test.js` | major |
| FE-API-004 | `jobs_create`: the SPA sends one part per input id; `JobSubmitRequestRequest` documents only `workflow`, `job_name` (backend gap BE-API-004). The payload cannot be validated against the contract. | `frontend/src/components/workflows/form/formModel.js:116`, `schema.yaml` `JobSubmitRequestRequest` | major |
| FE-API-004 | `me_destroy`: the SPA sends `{password}` as a DELETE body; `schema.yaml` documents no request body (backend gap BE-API-004). | `frontend/src/api/users.js:14` | major |
| FE-API-007 | Home page calls `workflows_list` without paging and shows only the first page (20 by default). Workflows beyond 20 are not listed on the home page, and nothing tells the user. | `frontend/src/api/workflows.js:3`, `frontend/src/views/public/HomeView.vue:17` | major |
| FE-API-007 | Group members modal reads one page of 200 users; members beyond 200 are not shown. | `frontend/src/components/admin/GroupMembersModal.vue:21` | minor |
| FE-API-006 | Fallbacks for shapes outside the contract: `data.results ?? data` on paginated lists, `?? data` on a plain array, `job.status`, `job.completed_at`, `user_username`/`workflow_name` fallbacks. They hide contract drift instead of failing. | `frontend/src/views/public/JobListView.vue:48`, `HomeView.vue:21`, `views/admin/AdminJobsView.vue:36-38`, `:45`, `:140`, `views/admin/AdminWorkflowSettingsView.vue:60`, `stores/jobs.js:17` | minor |
| FE-API-008 | Admin jobs view shows Cancel for `waiting`/`running` and Restart for `failed`/`cancelled` from local lists. The server also requires `!cancel_requested` (cancel) and `purged_at == null` (restart), so the buttons can lead to `409 invalid_state`. | `frontend/src/views/admin/AdminJobsView.vue:14-15`, `:143`, `:151`; `jobs/models.py:132`, `:138` | minor |
| FE-API-009 | The raw-log link is built by `jobLogUrl` instead of using `JobDetail.log_url`; two sources for one URL. | `frontend/src/api/jobs.js:29`, `frontend/src/components/jobs/JobLogTab.vue:38` | minor |
| FE-API-003 | Job ids, user ids, group ids and workflow ids are put in paths without `encodeURIComponent`. Workflow ids come from `cloudgene.yaml`. | `frontend/src/api/jobs.js:12-36`, `admin.js:33-41`, `users.js:29-46`, `workflows.js:6` | minor |
| FE-API-002 | `admin_jobs_restart_create` has two functions (`admin.restartAdminJob`, `jobs.adminRestartJob`); `admin_jobs_list` and `admin_jobs_cancel_create` also have unused duplicates in `jobs.js`. | `frontend/src/api/jobs.js:34-38`, `frontend/src/api/admin.js:44-52` | minor |
| FE-API-016 | Unused functions and store: `listCategories`, `getUser`, `jobOutputUrl`, `adminListJobs`, `adminCancelJob`, `restartJob`, `useJobsStore`. | `frontend/src/api/workflows.js:9`, `users.js:29`, `jobs.js:30-38`, `frontend/src/stores/jobs.js` | minor |
| FE-API-015 | `listCategories` has no test. | `frontend/src/api/workflows.js:9` | minor |
| — | `NextflowSettings.variables` is an array of free-form objects in `schema.yaml`, but the SPA reads `name` and `description` from each item. It is not in the backend's list of accepted untyped fields (`AppNextflow.variables` is typed `TemplateVariable`). | `frontend/src/views/admin/settings/NextflowSettingsView.vue:81`, `schema.yaml` `NextflowSettings` | minor |
| FE-API-011 | Nothing checks automatically that this mapping and the backend catalogue list the same operations. | — | minor |
| FE-API-017 | The shared case file is imported from outside `frontend/` (`../../../accounts/validation_cases.json`), so the frontend cannot be tested on its own. The mechanism sits outside `schema.yaml` (pending amendment P2). | `frontend/src/utils/validation.test.js:18` | minor |

## Open questions

1. Should `jobs_create` move to a documented shape (for example `inputs` as a JSON part plus file
   parts) so that FE-API-004/014 can validate it, or should `schema.yaml` get a
   `additionalProperties` note for per-input parts?
2. Should the home page page through `workflows_list`, or should the backend offer an unpaginated
   list for the home page (the run form needs the full set of visible workflows)?
3. Should restart stay reachable from both the job detail page and the admin jobs view? If yes,
   one API function should serve both (FE-API-002).
4. Should the planned schema loader keep the stricter checks (job `state` enum, input `type` enum)
   as local overlays, or should those enums be added on the backend (preferred by Article 5.1)?
5. `Workflow.category_name`: should the backend make it nullable in `schema.yaml`, or send `""`
   when there is no category?
