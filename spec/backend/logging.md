# Logging

## Purpose

Defines how the backend logs: the `LOGGING` configuration, the text and JSON console formats,
the `cloudgene.*` logger namespace and its components, which events are logged, and the
database capture of application log records (`SystemLog`) that admins browse in Admin → Logs
through `admin_logs_list`.

## Scope

Covered: `LOGGING`, `LOG_LEVEL`, `LOG_FORMAT` in `cloudgene_django/settings.py`;
`core/logging_formatters.py`; `admin_panel/logging.py`; `admin_panel.models.SystemLog` usage
(fields in [data-model.md](data-model.md#interfaces)); `LogListView` and
`SystemLogSerializer` in `admin_panel/views.py` and `admin_panel/serializers.py`; the log call
sites across `accounts/`, `admin_panel/`, `core/`, `jobs/`, `workflows/`.

Out of scope: job logs shown to users (`jobs_log_retrieve`, `JobMessage`) →
[job-progress-outputs.md](job-progress-outputs.md); `cleanup_logs` command →
[management-commands.md](management-commands.md); journald/log shipping and process stdout
capture → [../deployment/README.md](../deployment/README.md); the Admin → Logs page →
frontend spec.

## Dependencies

- [api-contract.md](api-contract.md) — operation `admin_logs_list`, component
  `PaginatedSystemLogList` / `SystemLog`, error envelope, pagination.
- [access-control.md](access-control.md) — `IsAdmin`.
- [data-model.md](data-model.md) — `SystemLog` fields and indexes.
- [admin-api.md](admin-api.md) — the admin operations whose actions are logged.

## Requirements

Configuration

- **BE-LOG-001** All logging MUST go to one console `StreamHandler` (stderr). The root and
  `django` loggers MUST log at `LOG_LEVEL` (env, default `INFO`); `django` MUST NOT propagate.
  `django.db.backends` MUST be capped at INFO (no SQL echo).
- **BE-LOG-002** The `cloudgene` logger MUST log at INFO to both the console handler and the
  database handler, and MUST NOT propagate to root (no duplicate console lines).
- **BE-LOG-003** With `LOG_FORMAT` unset or any value other than `json`, console lines MUST use
  `%(asctime)s %(levelname)s %(name)s [%(process)d] %(message)s`. With `LOG_FORMAT=json` they
  MUST use `core.logging_formatters.JsonFormatter`.

JSON format

- **BE-LOG-004** `JsonFormatter` MUST emit exactly one JSON object per record with keys
  `timestamp`, `level`, `logger`, `pid`, `message`; plus `exc_info` / `stack_info` (formatted
  text) when present; plus every non-standard, non-underscore attribute passed via `extra`.
  An `extra` `user` MUST be rendered as its `username` (or the raw value if it has none);
  values that are not JSON-serialisable MUST be rendered with `str()`.

Database capture

- **BE-LOG-005** Every record of a `cloudgene` or `cloudgene.*` logger at INFO or above MUST be
  stored as one `SystemLog` row: `level` = lower-case level name; `message` = the formatted
  message; `logger` = full logger name (≤ 200 chars); `component` = the segment after
  `cloudgene.` (`cloudgene.jobs.worker` → `jobs`; ≤ 100 chars).
- **BE-LOG-006** `extra={'data': {...}}` MUST be stored in `metadata` (values that are not
  JSON-serialisable stored as `repr()`); a record with `exc_info` MUST add
  `metadata.traceback`. `extra={'user': …}` (a user instance or integer id) MUST set
  `SystemLog.user` when that user exists, else NULL.
- **BE-LOG-007** DEBUG records and records of loggers outside `cloudgene` (e.g. `django`,
  `core.config`) MUST NOT be stored.
- **BE-LOG-008** The database handler MUST never raise into the caller, MUST NOT recurse when
  writing a row itself logs, and MUST do nothing before the app registry is ready (e.g. early
  in `migrate`).

Namespace and content

- **BE-LOG-009** Application code MUST log through `logging.getLogger('cloudgene.<component>')`
  with component one of `auth`, `jobs`, `worker`, `workflows`, `admin`, `api`. No row MUST be
  filed under the legacy component `accounts`.
- **BE-LOG-010** The events in the Interfaces table MUST each produce one record at the level
  shown.
- **BE-LOG-011** Log records written on behalf of a signed-in user (own account actions, job
  actions, admin actions) MUST pass `extra={'user': <acting user>}`.
- **BE-LOG-012** Log records MUST NOT contain passwords, API token keys, activation keys,
  password-reset tokens or `mail.password`. A settings change MUST log key names only.
- **BE-LOG-013** An unhandled exception in an API view MUST be logged at ERROR on
  `cloudgene.api` with its traceback, while the client gets the 500 envelope
  ([overview.md](overview.md)).

Admin log endpoint (`admin_logs_list`, `GET /api/admin/logs/`)

- **BE-LOG-014** Access MUST be admin only. Anonymous → 401, authenticated non-admin → 403, both with
  the error envelope.
- **BE-LOG-015** Results MUST be ordered newest first (`-timestamp`, `-id`) and paginated with
  the standard pagination (`page`, `page_size` ≤ 200).
- **BE-LOG-016** The endpoint MUST support these query filters, combinable: `level` (exact, case-insensitive input),
  `min_level` (that level and more severe, order `debug < info < warning < error < critical`),
  `component` (exact), `search` (case-insensitive substring of `message`).
- **BE-LOG-017** An unknown `level` or `min_level` value MUST return 400 with the error
  envelope, code `invalid`, and the offending parameter name in `fields`; it MUST NOT return an
  empty list.
- **BE-LOG-018** Each result MUST expose `id`, `timestamp`, `level`, `component`, `logger`,
  `message`, `username` (null when no user or user deleted), `metadata` — shapes per
  `SystemLog` in [api-contract.md](api-contract.md). All fields are read-only; there is no
  write or delete operation on logs.
- **BE-LOG-019** `message` and `metadata` are stored as plain text/JSON and may contain
  user-supplied text (e.g. an attempted username); any HTML view of them MUST escape them.

## Interfaces

### Loggers and components

| Logger | Component | Used by |
|--------|-----------|---------|
| `cloudgene.auth` | `auth` | `accounts/views.py` (login, registration, activation, reset, profile, token, admin users/groups) |
| `cloudgene.accounts` | `accounts` | `accounts/backends.py` (lockout) — non-conforming, see Known gaps |
| `cloudgene.jobs` | `jobs` | `jobs/views.py`, `jobs/signals.py` |
| `cloudgene.worker` | `worker` | `jobs/worker.py`, `run_worker` |
| `cloudgene.workflows` | `workflows` | `workflows/registry.py`, `workflows/middleware.py`, `workflows/apps.py` |
| `cloudgene.admin` | `admin` | `admin_panel/views.py` |
| `cloudgene.api` | `api` | `core/exceptions.py` |
| `core.config`, `core.views` | (not stored) | config load errors, health DB errors |

### Logged events (BE-LOG-010)

| Area | Event | Level |
|------|-------|-------|
| auth | login success; login failure (invalid credentials); wrong password count; registration; activation; activation/reset mail failure (ERROR + traceback); reset requested (known / unknown); reset completed; self account deletion; API token created / revoked | INFO |
| auth | account locked after N failures | WARNING |
| auth (admin) | admin updated user (changed fields, group names); deleted user; created / deleted group | INFO |
| admin | general / mail / nextflow / navbar settings changed; page created / updated / deleted; queue paused / resumed; maintenance entered / exited; test e-mail sent | INFO |
| admin | test e-mail failed | WARNING |
| jobs | submitted; cancelled (owner / admin); deleted; restarted by admin; deleted while running | INFO |
| worker | job finished (state); row vanished while running / after claim | INFO |
| worker | orphaned job marked failed; DB locked retry; tick phase failed (locked) | WARNING |
| worker | output collection failed; tick phase failed; poll / start failed; settings unreadable | ERROR (traceback) |
| workflows | installed; uninstalled; access updated; reloaded; nextflow settings updated; group pruned | INFO |
| workflows | sync failed; group prune failed | ERROR (traceback) |
| api | oversized request (413); suspicious request (400) | WARNING |
| api | unhandled API error | ERROR (traceback) |

### `DatabaseLogHandler`

`admin_panel.logging.DatabaseLogHandler(logging.Handler)`, configured as handler `db` at INFO on
logger `cloudgene`. Helper `component_of(logger_name)`.

### Endpoint

`admin_logs_list` — `GET /api/admin/logs/` → `PaginatedSystemLogList`. Query parameters
`level`, `min_level`, `component`, `search`, `page`, `page_size`. Contract:
[api-contract.md](api-contract.md); listed with the other admin operations in
[admin-api.md](admin-api.md).

## Behaviour

Write path: `logger.info(...)` on `cloudgene.x` → console handler (formatted per
`LOG_FORMAT`) and `DatabaseLogHandler.emit` → thread-local busy flag guards recursion → skip if
apps not ready → build metadata, resolve user id (one existence query) → `SystemLog.objects.create`
→ any exception is swallowed. The write is synchronous and joins the caller's current
transaction, if any.

Read path: `LogListView` builds the queryset (`select_related('user')`), validates `level` and
`min_level` against the five level names, applies filters, and paginates.

Retention: rows accumulate until `manage.py cleanup_logs --days N` (default 30) deletes rows
older than N days ([management-commands.md](management-commands.md)); scheduling it is a
deployment concern.

Tests: the test runner lowers the `cloudgene` console handler to CRITICAL and `django.request`
to CRITICAL; the DB handler still records ([overview.md](overview.md)).

## Acceptance tests

| Req | Test | Layer |
|-----|------|-------|
| BE-LOG-001 | (planned) `core/tests/test_deploy.py::LoggingConfigTest::test_handlers_and_levels` | unit |
| BE-LOG-002 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters`; (planned) `LoggingConfigTest::test_cloudgene_does_not_propagate` | unit |
| BE-LOG-003 | (planned) `core/tests/test_deploy.py::LoggingConfigTest::test_log_format_switch` | unit |
| BE-LOG-004 | `core/tests/test_deploy.py::JsonFormatterTest::test_produces_valid_json_with_expected_keys`, `::test_extra_data_is_included` | unit |
| BE-LOG-005 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters` | unit |
| BE-LOG-006 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters`; (planned) `::test_exception_traceback_in_metadata` | unit |
| BE-LOG-007 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters` | unit |
| BE-LOG-008 | (planned) `admin_panel/tests/test_api.py::LogsTest::test_handler_swallows_db_errors` | unit |
| BE-LOG-009 | `admin_panel/tests/test_api.py::LogsTest::test_log_components_follow_the_spec`; `e2e/tests/test_findings_admin.py::test_c04_log_components_follow_the_spec`; (planned) assertion that a wrong-password login produces no `accounts` row | unit, e2e |
| BE-LOG-010 | `e2e/tests/test_admin_dashboard.py::test_d7_logs_show_admin_actions`; (planned) per-event unit tests | e2e |
| BE-LOG-011 | (planned) `admin_panel/tests/test_api.py::LogsTest::test_actions_record_acting_user` | unit |
| BE-LOG-012 | (planned) `accounts/tests.py::LogSecretsTest::test_no_secret_in_system_log` | unit |
| BE-LOG-013 | `core/tests/test_api.py::ErrorEnvelopeHandlerTest::test_unhandled_exception_becomes_500_envelope` | unit |
| BE-LOG-014 | `admin_panel/tests/test_api.py::PermissionMatrixTest::test_anonymous_gets_401`, `::test_non_admin_gets_403_and_nothing_changes`; `e2e/tests/test_findings_security.py::test_permission_matrix_admin_endpoints` | unit, e2e |
| BE-LOG-015 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters` | unit |
| BE-LOG-016 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters` | unit |
| BE-LOG-017 | `admin_panel/tests/test_api.py::LogsTest::test_unknown_level_filter_is_a_400_not_silently_empty` | unit |
| BE-LOG-018 | `admin_panel/tests/test_api.py::LogsTest::test_handler_and_filters`; (planned) contract test validating against `PaginatedSystemLogList` | unit, contract |
| BE-LOG-019 | (planned) frontend admin logs view escaping test | unit (vitest) |

## Known gaps

| Req | Current behaviour | Ref | Severity |
|-----|-------------------|-----|----------|
| BE-LOG-009 | `accounts/backends.py` logs lockout events on `cloudgene.accounts`, so they are filed under component `accounts`; a wrong-password login produces one `auth` and one `accounts` row. | `accounts/backends.py:32` | minor |
| BE-LOG-011 | `accounts/views.py` never passes `extra={'user': …}` (login, token, self-delete, admin user/group actions), and `workflows/registry.py` has no user in scope, so those rows have `user = NULL`; the actor is only in the message text. | `accounts/views.py:384`, `accounts/views.py:435`, `workflows/registry.py:443` | minor |
| BE-LOG-008 | `SystemLog.objects.create` runs inside the caller's transaction without a savepoint. On PostgreSQL a failed insert inside an `atomic()` block poisons the caller's transaction; a rolled-back transaction also drops its log rows. | `admin_panel/logging.py:62` | minor |
| BE-LOG-007 | Config load errors are logged on `core.config` and health DB errors on `core.views`, so they never reach Admin → Logs. | `core/config.py:44`, `core/views.py:17` | minor |
| — | Each stored record costs a synchronous insert (plus a user-existence query) on the request path; on SQLite a locked database silently drops the row. | `admin_panel/logging.py:60` | minor |
| BE-LOG-001 | No test pins the `LOGGING` handler/level layout or the `LOG_FORMAT` switch. | `cloudgene_django/settings.py:318` | minor |

## Open questions

- Should SystemLog retention be automatic (e.g. run by the worker) rather than relying on a
  scheduled `cleanup_logs`?
- Should the failed-login message keep the attempted username (`%r`), given users sometimes
  type a password into the username field?
