# Admin API

## Purpose

The admin API lets administrators run a Cloudgene server from the SPA: see a dashboard of jobs,
users, workflows, worker and configuration health; pause the queue and enter maintenance mode;
manage users and groups; list, cancel and restart any user's job; edit server, mail and Nextflow
settings, the navbar and HTML pages; and read the application log. Settings are stored in
`$CLOUDGENE_HOME/config/settings.yaml` and files under `$CLOUDGENE_HOME`, read and written only
through `core.config`, so the worker picks changes up without a restart.

## Scope

Covered:

| Source | What |
|--------|------|
| `admin_panel/views.py`, `admin_panel/serializers.py`, `admin_panel/urls.py` | Dashboard, queue pause/resume, maintenance enter/exit, settings (general, mail, mail test, Nextflow, navbar), pages, logs |
| `accounts/views.py` (`AdminUserViewSet`, `AdminGroupViewSet`), `accounts/serializers.py` (`AdminUserSerializer`, `AdminUserUpdateSerializer`, `AdminGroupSerializer`) | Admin users and groups |
| `jobs/views.py` (`AdminJobViewSet`) | Admin job list, cancel, restart |

Out of scope (linked instead):

- Admin workflow endpoints (`admin_workflows_*`, `workflows/admin_views.py`): [workflows-api.md](workflows-api.md).
- The `settings.yaml` schema, defaults, locking and atomic writes: [configuration.md](configuration.md).
- The definition of "admin" and the permission classes: [access-control.md](access-control.md).
- What maintenance mode does to the rest of the system, the public server info and page endpoints, and mail delivery: [server-pages-mail.md](server-pages-mail.md).
- Job state machine and what cancel does to a running process: [job-queue-worker.md](job-queue-worker.md).
- How log records reach `SystemLog` (handler, components): [logging.md](logging.md).
- The `cleanup_logs` command: [management-commands.md](management-commands.md).
- The SPA admin views: `spec/frontend/`.

## Dependencies

- [api-contract.md](api-contract.md): error envelope, pagination, trailing-slash rule, auth schemes. All field shapes below are the `schema.yaml` components named there.
- [access-control.md](access-control.md): `IsAdmin`, `is_admin()`, the `admin` group.
- [authentication.md](authentication.md): session + CSRF and token authentication.
- [configuration.md](configuration.md): `load_settings`, `update_settings`, `ConfigError`, `config_status`, `page_path`/`read_page`/`write_page`/`delete_page`/`list_pages`, `write_text_atomic`.
- [server-pages-mail.md](server-pages-mail.md): `core.mail.send_mail`, maintenance effects, page slug rules on the public side.
- [job-queue-worker.md](job-queue-worker.md): `services.cancel_job`, `services.restart_job`, `WorkerHeartbeat`.
- [workflow-registry.md](workflow-registry.md): `registry.list_apps()` (dashboard workflow counts), `template_utils.VARIABLES`.
- [logging.md](logging.md): `SystemLog` model and `cloudgene.admin` logger.

## Requirements

### Access

- **BE-ADM-001** Every operation in this file MUST require an admin (`is_admin`). Anonymous requests MUST get 401 `not_authenticated`; authenticated non-admins MUST get 403 `permission_denied`, and the request MUST NOT change any setting, page, user, group or job.
- **BE-ADM-002** Unsafe methods (POST/PUT/PATCH/DELETE) authenticated by session MUST require a valid CSRF token (403 `csrf_failed` otherwise). Token-authenticated requests do not need CSRF.
- **BE-ADM-003** Every successful state-changing admin action (settings, navbar, pages, queue, maintenance, users, groups, job cancel/restart) MUST write one INFO record to the application log naming the action, visible in `admin_logs_list`.

### Dashboard and queue

- **BE-ADM-010** `admin_dashboard` MUST return, in one response: queue status (paused, maintenance, maintenance message, running and waiting counts, `max_running`, `max_queue`, worker heartbeat `{ok, last_seen, age_seconds, pid}`), job counts per state (`waiting`, `running`, `success`, `failed`, `cancelled`, `total`), user counts (`total`, `active`, `admins`), workflow counts (`total`, `enabled`, `disabled`, `invalid`), the 10 most recently submitted jobs, and the `settings.yaml` validation status `{ok, errors[]}` (the same data as the `config` block of `/api/health`).
- **BE-ADM-011** Dashboard job counts and recent jobs SHOULD exclude jobs soft-deleted by their owner, matching `admin_jobs_list`.
- **BE-ADM-012** `admin_queue_pause` / `admin_queue_resume` MUST set `queue.paused` to `true` / `false` in `settings.yaml` and return the queue status block. Pausing MUST NOT stop running jobs; the worker stops claiming new jobs on its next tick ([job-queue-worker.md](job-queue-worker.md)).
- **BE-ADM-013** `admin_maintenance_enter` MUST set `server.maintenance: true`; if the body has a non-empty `message` (max 2000 chars) it MUST also replace `server.maintenance_message`. `admin_maintenance_exit` MUST set `server.maintenance: false` and keep the message. Both return the queue status block.
- **BE-ADM-014** Pause, resume, enter and exit MUST be idempotent: repeating one returns 200 and the same state.

### Users

- **BE-ADM-020** `admin_users_list` MUST return all users, paginated, ordered by username, with optional filters `search` (case-insensitive substring of username, e-mail or full name), `group` (exact group name) and `is_active` (`true`/`false`/`1`/`0`). Each row includes `is_superuser` and `activated_at`. Password hashes, activation keys and tokens MUST NOT be returned.
- **BE-ADM-021** `admin_users_partial_update` accepts only `groups` (complete list of group names; replaces non-admin memberships), `is_active` and `is_admin`. Any other field (e.g. `is_superuser`, `is_staff`, `username`, `password`) MUST be ignored. PUT and POST on the users collection/item MUST return 405.
- **BE-ADM-022** A `groups` entry naming a group that does not exist MUST fail with 400 `invalid` and `fields.groups`; nothing is changed. The `admin` group in `groups` MUST be ignored (membership kept as is); admin rights change only through `is_admin`.
- **BE-ADM-023** `is_admin: true` MUST add the user to the `admin` group (creating it if missing) and set `is_staff`; `is_admin: false` MUST remove both.
- **BE-ADM-024** An admin MUST NOT be able to deactivate their own account or remove their own admin rights (400 `invalid`, `fields.is_active` / `fields.is_admin`). `is_admin: false` on a superuser MUST fail with 400 (`fields.is_admin`).
- **BE-ADM-025** Setting `is_active: true` MUST also clear the login lockout (`login_attempts = 0`, `locked_until = null`). Setting `is_active: false` MUST make the user unable to log in or use an API token ([authentication.md](authentication.md)).
- **BE-ADM-026** `admin_users_destroy` MUST delete the user and return 204. Deleting one's own account here MUST fail with 400 `cannot_delete_self` (use the profile endpoint, which enforces the last-admin rule in [accounts.md](accounts.md)). What happens to the deleted user's jobs is specified in [job-queue-worker.md](job-queue-worker.md).
- **BE-ADM-027** An unknown user id MUST return 404 `not_found`.

### Groups

- **BE-ADM-030** `admin_groups_list` MUST return all groups as a plain (unpaginated) array ordered by name, each with `id`, `name`, `member_count`.
- **BE-ADM-031** `admin_groups_create` MUST validate the name with the shared group-name rule ([accounts.md](accounts.md)) and reject a name that already exists ignoring case (400 `invalid`, `fields.name`). Success returns 201 with `member_count: 0`.
- **BE-ADM-032** `admin_groups_destroy` MUST delete the group (memberships go with it) and return 204, except the `admin` group, which MUST fail with 400 `protected_group`.

### Jobs

- **BE-ADM-040** `admin_jobs_list` MUST return all users' jobs except soft-deleted ones, paginated, newest submission first, with optional filters `state` (comma-separated list of job states; an unknown state is 400 `invalid` with `fields.state`), `user` (numeric id or case-insensitive username), `workflow` (workflow id) and `search` (job name, username, workflow name substring, or job id prefix).
- **BE-ADM-041** `admin_jobs_cancel_create` MUST cancel any user's waiting or running job with the semantics of `services.cancel_job` ([job-queue-worker.md](job-queue-worker.md)), recording "by an administrator" in the job messages, and return the job detail. A finished job MUST return 409 `invalid_state`.
- **BE-ADM-042** `admin_jobs_restart_create` MUST re-queue a `failed` or `cancelled` job as `waiting` with the same inputs and the workflow's current definition, clearing its steps, messages, outputs and logs. It MUST fail with 409 `invalid_state` for other states, 409 `workspace_removed` if the workspace was purged or the job deleted, and 409 `workflow_unavailable` if the workflow is uninstalled or disabled.
- **BE-ADM-043** An unknown or soft-deleted job id MUST return 404 `not_found`.

### Settings

- **BE-ADM-050** `admin_settings_general_retrieve` MUST return the `server.*` keys `name`, `url`, `max_running_jobs`, `max_queue_size`, `job_retention_days`, `max_upload_mb`, `maintenance`, `maintenance_message`. `admin_settings_general_update` (PUT) MUST accept any subset and leave omitted keys unchanged on disk.
- **BE-ADM-051** General settings validation: `name` non-blank, max 100; `url` empty or starting with `http://`/`https://` (trailing `/` stripped); `max_running_jobs` ≥ 1; `max_queue_size` ≥ 0; `job_retention_days` ≥ 0; `max_upload_mb` ≥ 1; `maintenance_message` max 2000. A violation MUST return 400 `invalid` with `fields.<key>` and MUST NOT write the file.
- **BE-ADM-052** `admin_settings_mail_retrieve` MUST return `backend`, `file_path`, `host`, `port`, `user`, `use_tls`, `use_ssl`, `from_email` and `password_set`. The SMTP password MUST NOT appear in any response.
- **BE-ADM-053** `admin_settings_mail_update` MUST accept any subset. `password` is write-only: empty or absent leaves the stored password unchanged; `clear_password: true` removes it. `backend` MUST be one of `smtp`, `file`, `console`; `port` 1–65535; `from_email` a valid address. `use_tls` and `use_ssl` MUST NOT both be true in the resulting settings (checked against the merged document, not just the request) — 400 `invalid`, `fields.use_ssl`.
- **BE-ADM-054** `admin_settings_mail_test` MUST send one test message using the saved mail settings to `to` (if given, a valid e-mail) or else the admin's own address. If neither exists it MUST return 400 `invalid` with `fields.to`. A delivery failure MUST return 502 `mail_failed` with the error text, and be logged at WARNING. Success returns `{message, to}`.
- **BE-ADM-055** `admin_settings_nextflow_retrieve` MUST return `binary`, `profile`, `work_dir`, the full text of `config/nextflow.config` (`config`) and `config/nextflow.env` (`env`) (empty string if the file is missing), and the read-only list of global template `variables` (`{name, scope, description}`, scope `global` only).
- **BE-ADM-056** `admin_settings_nextflow_update` MUST accept any subset; `config` and `env` replace the respective files atomically (temp file + rename), byte-for-byte (no whitespace trimming). A `ConfigError` on the `nextflow.*` keys MUST return 400 and MUST NOT write either file.
- **BE-ADM-057** `admin_settings_navbar_retrieve` MUST return the full stored `navbar` list (unfiltered). `admin_settings_navbar_update` MUST replace the whole list. Each item needs non-blank `title` (max 100) and `url` (max 500); `url` MUST be an internal path starting with a single `/` or an `http://`/`https://` URL (so `javascript:`, `data:` and `//host` are rejected) — 400 `invalid` with `fields`. `icon` defaults to `""`, `admin_only`/`auth_only` to `false`.
- **BE-ADM-058** Every settings update MUST go through `core.config.update_settings` (locked read-modify-write, validation of the resulting document, atomic write) and MUST succeed even when the stored `settings.yaml` currently has invalid keys or does not parse, as long as the result is valid ([configuration.md](configuration.md)).
- **BE-ADM-059** A `ConfigError` raised when saving MUST be returned as 400 `invalid` with the offending keys in `fields`, the section prefix stripped (`server.name` → `name`; navbar keys keep `navbar[i].url`).

### Pages

- **BE-ADM-060** `admin_pages_list` MUST list every `$CLOUDGENE_HOME/pages/<slug>.html` whose stem is a valid slug, sorted by slug, with `size` (bytes), `updated_at` (file mtime, UTC) and `deletable` (`false` for `home` and `footer`).
- **BE-ADM-061** A page slug MUST match `^[a-z0-9][a-z0-9_-]{0,63}$`. Any other slug (including `..`, `/`, upper case, `.html` suffix) on `admin_pages_retrieve`, `admin_pages_update` or `admin_pages_destroy` MUST return 400 `invalid` with `fields.slug`, and MUST NOT touch the filesystem outside `pages/`.
- **BE-ADM-062** `admin_pages_retrieve` MUST return `{slug, html, deletable}`; a missing page is 404 `not_found`.
- **BE-ADM-063** `admin_pages_update` (PUT `{html}`) MUST write the HTML verbatim (no trimming, no sanitising) atomically, returning 201 if the page was created and 200 if it was replaced. `html` may be empty.
- **BE-ADM-064** `admin_pages_destroy` MUST delete the file and return 204; `home` and `footer` MUST fail with 400 `protected`; a missing page is 404 `not_found`.
- **BE-ADM-065** Page HTML is trusted, admin-authored content: the API stores and returns it unchanged. Only admins MAY write it (BE-ADM-001). How it is served publicly is specified in [server-pages-mail.md](server-pages-mail.md).

### Logs

- **BE-ADM-070** `admin_logs_list` MUST return `SystemLog` records, paginated, newest first (`timestamp`, then `id` descending), each with `id`, `timestamp`, `level`, `component`, `logger`, `message`, `username` (null if none or the user was deleted) and `metadata`.
- **BE-ADM-071** Filters: `level` (exact), `min_level` (that level and above, order `debug < info < warning < error < critical`), `component` (exact), `search` (case-insensitive substring of the message). Level values are case-insensitive. An unknown `level` or `min_level` MUST return 400 `invalid` with `fields.level` / `fields.min_level`, not an empty list.

## Interfaces

All paths are under `/api/admin/` and accept an optional trailing slash ([api-contract.md](api-contract.md)). Request/response shapes are the `schema.yaml` components for each operation.

| operationId | Method, path | Source |
|-------------|--------------|--------|
| `admin_dashboard` | GET `dashboard/` | `admin_panel/views.py` `DashboardView` |
| `admin_queue_pause` / `admin_queue_resume` | POST `queue/pause/`, `queue/resume/` | `QueuePauseView`, `QueueResumeView` |
| `admin_maintenance_enter` / `admin_maintenance_exit` | POST `maintenance/enter/`, `maintenance/exit/` | `MaintenanceEnterView`, `MaintenanceExitView` |
| `admin_users_list`, `admin_users_retrieve`, `admin_users_partial_update`, `admin_users_destroy` | GET/GET/PATCH/DELETE `users/`, `users/{id}/` | `accounts/views.py` `AdminUserViewSet` |
| `admin_groups_list`, `admin_groups_create`, `admin_groups_destroy` | GET/POST `groups/`, DELETE `groups/{id}/` | `accounts/views.py` `AdminGroupViewSet` |
| `admin_jobs_list`, `admin_jobs_cancel_create`, `admin_jobs_restart_create` | GET `jobs/`, POST `jobs/{id}/cancel/`, `jobs/{id}/restart/` | `jobs/views.py` `AdminJobViewSet` |
| `admin_settings_general_retrieve` / `_update` | GET/PUT `settings/general/` | `GeneralSettingsView` |
| `admin_settings_mail_retrieve` / `_update` | GET/PUT `settings/mail/` | `MailSettingsView` |
| `admin_settings_mail_test` | POST `settings/mail/test/` | `MailTestView` |
| `admin_settings_nextflow_retrieve` / `_update` | GET/PUT `settings/nextflow/` | `NextflowSettingsView` |
| `admin_settings_navbar_retrieve` / `_update` | GET/PUT `settings/navbar/` | `NavbarSettingsView` |
| `admin_pages_list` | GET `pages/` | `PageListView` |
| `admin_pages_retrieve`, `admin_pages_update`, `admin_pages_destroy` | GET/PUT/DELETE `pages/{slug}/` | `PageDetailView` |
| `admin_logs_list` | GET `logs/` | `LogListView` |
| `admin_workflows_*` | `workflows/…` | see [workflows-api.md](workflows-api.md) |

Settings keys and files written:

| Operation | Writes |
|-----------|--------|
| general update | `settings.yaml` `server.*` |
| mail update | `settings.yaml` `mail.*` |
| Nextflow update | `settings.yaml` `nextflow.*`, `config/nextflow.config`, `config/nextflow.env` |
| navbar update | `settings.yaml` `navbar` (whole list) |
| queue pause/resume | `settings.yaml` `queue.paused` |
| maintenance enter/exit | `settings.yaml` `server.maintenance`, `server.maintenance_message` |
| page update/destroy | `pages/<slug>.html` |

Error codes used here: `not_authenticated` (401), `permission_denied` (403), `csrf_failed` (403), `not_found` (404), `invalid` (400), `protected` (400), `protected_group` (400), `cannot_delete_self` (400), `invalid_state` / `workspace_removed` / `workflow_unavailable` (409), `mail_failed` (502).

## Behaviour

**Settings update flow.** The view validates the request with its serializer (field types, ranges, per-request cross checks), then calls `config.update_settings` with a deep-merge patch (navbar: a callable that replaces the list). `update_settings` takes the file lock, reads the current file leniently, merges, validates the whole result against the schema and cross-field rules, and writes atomically. On `ConfigError` nothing is written and the view returns 400 via `_config_error` (`admin_panel/views.py:36`). The response is re-read from `load_settings()`, so it reflects what is on disk.

**Mail password.** The serializer pops `password` and `clear_password`. `clear_password: true` wins over `password`. The response never carries the password, only `password_set`.

**Nextflow update order.** `nextflow.*` keys are saved first; only if that succeeds are `config` and `env` written, each by `write_text_atomic`. The two files are not written as one transaction: an I/O error on the second leaves the first updated.

**Mail test.** Sending is synchronous in the request; with SMTP it can block up to the 30 s connection timeout ([server-pages-mail.md](server-pages-mail.md)).

**Dashboard workflow counts.** `total` = workflows registered in `settings.yaml` `apps[]` plus DB workflow rows with no `app_path`; `enabled` = valid and enabled; `invalid` = registered but failing validation; `disabled` = the rest.

**User update.** `groups` is normalised (trimmed, de-duplicated, `admin` removed) and replaces memberships while keeping any existing `admin` membership. The update runs in one transaction; the response is the re-read user.

**Restart.** Removes `output/`, `logs/`, `work/`, `.nextflow/`, `*params.json` and `cloudgene.config` from the workspace, deletes steps/messages/outputs, resets timestamps and the process ids, re-snapshots the workflow YAML and app directory, sets `submitted_at` to now and adds the message "Job restarted by an administrator." (`jobs/services.py:57`).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| BE-ADM-001 | `admin_panel/tests/test_api.py::PermissionMatrixTest::test_anonymous_gets_401`, `::test_non_admin_gets_403_and_nothing_changes`, `::test_admin_via_admin_group`; `accounts/tests.py::PermissionMatrixTest::test_matrix`, `::test_non_admin_gets_no_data`; `jobs/tests/test_api.py::AdminJobsApiTest::test_admin_list_filters_and_permissions`; `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` | unit, e2e |
| BE-ADM-002 | `admin_panel/tests/test_api.py::PermissionMatrixTest::test_admin_session_needs_csrf` | unit |
| BE-ADM-003 | `admin_panel/tests/test_api.py::DashboardQueueTest::test_pause_resume_maintenance_write_settings` (queue only); `e2e/tests/test_admin_dashboard.py::test_d7_logs_show_admin_actions`; per-action log assertions for users/groups/pages/settings (planned) | unit, e2e |
| BE-ADM-010 | `admin_panel/tests/test_api.py::DashboardQueueTest::test_dashboard_shape_and_counts`; `e2e/tests/test_admin_dashboard.py::test_d1_dashboard_counts_match_db` | unit, e2e |
| BE-ADM-012, 013 | `admin_panel/tests/test_api.py::DashboardQueueTest::test_pause_resume_maintenance_write_settings`; `e2e/tests/test_admin_dashboard.py::test_d1_pause_resume_queue`, `::test_d1_maintenance_mode_banner` | unit, e2e |
| BE-ADM-014 | `admin_panel/tests/test_api.py::DashboardQueueTest::test_queue_actions_idempotent` (planned) | unit |
| BE-ADM-020 | `accounts/tests.py::AdminUsersTest::test_list_shape_and_search` | unit |
| BE-ADM-021 | `accounts/tests.py::AdminUsersTest::test_privilege_fields_not_writable`, `::test_put_and_post_not_allowed`; `accounts/test_contracts.py::UserUpdateContractTest::test_admin_can_update_any_user` | unit |
| BE-ADM-022, 023 | `accounts/tests.py::AdminUsersTest::test_set_groups_by_name`, `::test_unknown_group`, `::test_admin_group_only_via_is_admin` | unit |
| BE-ADM-024 | `accounts/tests.py::AdminUsersTest::test_self_protection`, `::test_superuser_stays_admin` | unit |
| BE-ADM-025 | `accounts/tests.py::AdminUsersTest::test_activate_deactivate` | unit |
| BE-ADM-026 | `accounts/tests.py::AdminUsersTest::test_delete`; `e2e/tests/test_accounts.py::test_d3_admin_users`; `e2e/tests/test_findings_admin.py::test_c03_deleting_user_removes_the_workspace_of_a_running_job` | unit, e2e |
| BE-ADM-027 | `accounts/tests.py::AdminUsersTest::test_unknown_user_404` (planned) | unit |
| BE-ADM-030–032 | `accounts/tests.py::AdminGroupsTest::test_list_with_member_count`, `::test_create`, `::test_create_duplicate_ignoring_case`, `::test_create_invalid`, `::test_delete`, `::test_admin_group_protected`; `accounts/test_contracts.py::GroupContractTest::*` | unit, contract |
| BE-ADM-040–043 | `jobs/tests/test_api.py::AdminJobsApiTest::test_admin_list_filters_and_permissions`, `::test_restart`, `::test_restart_needs_enabled_workflow`; `e2e/tests/test_admin_dashboard.py::test_d2_admin_jobs_filter_cancel_restart`; unknown/deleted id 404 (planned) | unit, e2e |
| BE-ADM-050, 051 | `admin_panel/tests/test_api.py::GeneralSettingsTest::test_round_trip_to_disk`, `::test_partial_update_keeps_other_keys`, `::test_validation_errors_in_envelope_fields`; `e2e/tests/test_admin_settings.py::test_d5_general_settings_round_trip`, `::test_d5_general_settings_validation_error` | unit, e2e |
| BE-ADM-052, 053 | `admin_panel/tests/test_api.py::MailSettingsTest::test_password_write_only`, `::test_invalid_backend`; `e2e/tests/test_admin_settings.py::test_d5_mail_password_write_only`; `e2e/tests/test_findings_admin.py::test_c01_mail_tls_and_ssl_cannot_both_be_enabled` | unit, e2e |
| BE-ADM-054 | `admin_panel/tests/test_api.py::MailSettingsTest::test_send_test_mail_to_admin`, `::test_send_test_mail_requires_address`; `e2e/tests/test_admin_settings.py::test_d5_mail_test_lands_in_outbox`; 502 `mail_failed` path (planned) | unit, e2e |
| BE-ADM-055, 056 | `admin_panel/tests/test_api.py::NextflowSettingsTest::test_round_trip`; `e2e/tests/test_admin_settings.py::test_d5_nextflow_settings_round_trip` | unit, e2e |
| BE-ADM-057 | `admin_panel/tests/test_api.py::NavbarTest::test_round_trip_and_public_filtering`, `::test_missing_title`; `e2e/tests/test_findings_admin.py::test_c05_navbar_url_is_validated`; `e2e/tests/test_admin_settings.py::test_d6_navbar_editor` | unit, e2e |
| BE-ADM-058 | `e2e/tests/test_findings_admin.py::test_c02_invalid_settings_value_does_not_take_the_site_down`; `core/tests/test_config.py` (see [configuration.md](configuration.md)) | unit, e2e |
| BE-ADM-059 | `admin_panel/tests/test_api.py::GeneralSettingsTest::test_validation_errors_in_envelope_fields` | unit |
| BE-ADM-060–064 | `admin_panel/tests/test_api.py::PagesTest::test_admin_crud`, `::test_home_footer_not_deletable`, `::test_admin_invalid_slug`; `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` | unit, e2e |
| BE-ADM-065 | `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer` | e2e |
| BE-ADM-070, 071 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters`, `::test_unknown_level_filter_is_a_400_not_silently_empty`; `e2e/tests/test_admin_dashboard.py::test_d7_logs_show_admin_actions` | unit, e2e |
| all operations | schema-validated contract tests of each response and error envelope (planned, Article 5.1d) | contract |

## Known gaps

| ID | What the code does | Where | Severity |
|----|--------------------|-------|----------|
| BE-ADM-011 | Dashboard job counts and recent jobs use `Job.objects` and include jobs soft-deleted by their owners, while `admin_jobs_list` excludes them. | `admin_panel/views.py:304`, `admin_panel/views.py:334` | minor |
| BE-ADM-003 | User and group changes are logged on `cloudgene.auth` without `extra={'user': ...}`, so the log row has no `username`; general settings and other actions pass the actor. Admin job actions log under component `jobs`. Not wrong, but inconsistent for an audit view. | `accounts/views.py:435`, `accounts/views.py:448`, `accounts/views.py:465` | minor |
| BE-ADM-010 | Dashboard code still carries legacy indirection (`_state_field`, `_finished_field`, `LEGACY_STATES`, `app_id`/`app_name` fallbacks) for a Job model that no longer exists; `jobs/services.py:91` `queue_summary()` duplicates `queue_status()` and has no callers. | `admin_panel/views.py:31-33`, `admin_panel/views.py:289-352`, `jobs/services.py:91` | minor |
| BE-ADM-056 | `config` and `env` are written as two separate atomic writes after the YAML save; a failure part-way leaves a partial update with a 500. No validation of `nextflow.env` lines (malformed lines are silently ignored at run time by `parse_env`). | `admin_panel/views.py:174-186` | minor |
| BE-ADM-042 | Restart re-queues a job without checking maintenance mode or `max_queue_size` (submission does both). May be intended for admins; see open question. | `jobs/services.py:57` | minor |
| BE-ADM-054 | The SMTP test runs synchronously in the web request (up to 30 s) and returns the raw exception text. Acceptable for admins, but blocks a web worker. | `admin_panel/views.py:122-144`, `core/mail.py:32` | minor |
| BE-ADM-020 | An `is_active` value other than `true/false/1/0` is ignored silently instead of 400. | `accounts/views.py:422-424` | minor |
| BE-ADM-014, 027, 043 | No tests for idempotent queue actions or 404 on unknown user/job ids. | — | minor |
| Article 5.1d | No contract test validates admin responses against `schema.yaml` components. | `admin_panel/tests/test_api.py` | major |

## Open questions

1. Should deleting a group also remove its name from `apps[].groups` in `settings.yaml`? Today the stale name stays; re-creating a group with the same name silently restores workflow access ([access-control.md](access-control.md)).
2. Should admin restart respect maintenance mode and the queue size limit?
3. Should page HTML be sanitised server-side (or a Content-Security-Policy added) given that it is rendered with `v-html` on the app origin? Today it is trusted admin content by design (plans/QA_FINDINGS.md I-3).
4. The dashboard `admins` count includes inactive admins. Intended?
