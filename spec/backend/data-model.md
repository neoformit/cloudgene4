# Data model

## Purpose

Defines every database model of the project apps, their fields, constraints, indexes and
relationships, the signal receivers that react to model changes, and the migration policy.
Business rules that use these models (job states, workflow access, lockout) live in the area
files linked from each model; this file is the single home for the stored shape.

## Scope

Covered: `core/models.py`, `accounts/models.py`, `workflows/models.py`, `jobs/models.py`,
`admin_panel/models.py`, `jobs/signals.py`, the `post_delete` receiver in `workflows/apps.py`,
the login signal receivers in `accounts/backends.py` (listed only), and all `*/migrations/`.

Out of scope: third-party models used as-is — `auth.Group`, `authtoken.Token`,
`sessions.Session` (behaviour in [authentication.md](authentication.md) and
[access-control.md](access-control.md)); state machines ([job-queue-worker.md](job-queue-worker.md));
serializer field shapes ([api-contract.md](api-contract.md)).

## Dependencies

- [configuration.md](configuration.md) — `core.config.job_dir()`, `settings.yaml` `apps[]`
  (source of truth that `Workflow` caches).
- [workflow-registry.md](workflow-registry.md) — creates/updates/deletes `Workflow` rows.
- [job-queue-worker.md](job-queue-worker.md) — owns `Job.status` transitions and workspace
  removal for running jobs.
- [accounts.md](accounts.md), [authentication.md](authentication.md) — user validation and
  lockout fields.
- [logging.md](logging.md) — writes `SystemLog`.

## Requirements

Users

- **BE-DATA-001** `accounts.User` usernames MUST be unique ignoring case and e-mails MUST be
  unique ignoring case, enforced by the database (constraints `users_username_ci_unique`,
  `users_email_ci_unique` on `Lower(...)`). Inserting a case variant MUST raise
  `IntegrityError`.
- **BE-DATA-002** Saving a `User` MUST strip the username and strip and lower-case the e-mail.
- **BE-DATA-003** Lookup by natural key (login, `createsuperuser`, Django admin) MUST ignore
  username case.
- **BE-DATA-004** `User.activation_key` and `User.password_reset_token` MUST store only the
  SHA-256 hex digest of the secret sent by e-mail, never the raw value.

Workflows

- **BE-DATA-005** A `Workflow` row MUST be treated as a cache of `settings.yaml` `apps[]` plus
  the app's `cloudgene.yaml`. Rows with an empty `app_path` MUST never be modified or deleted
  by a registry sync.
- **BE-DATA-006** When a registry-managed workflow is removed from `apps[]`, its row MUST be
  deleted if no job references it, otherwise kept with `installed=False` and
  `status='disabled'`.
- **BE-DATA-007** `Workflow.status` MUST be one of `enabled`, `disabled`, `maintenance`
  (`WorkflowStatusEnum` in `schema.yaml`).

Jobs

- **BE-DATA-008** A `Job` MUST snapshot the workflow at submission (`app_id`, `app_name`,
  `app_version`, `workflow_yaml`, `app_dir`) so it stays readable after the workflow is
  uninstalled; `Job.workflow` MUST become NULL (not cascade) when the workflow row is deleted.
- **BE-DATA-009** `Job.status` and `JobStep.status` MUST be one of `waiting`, `running`,
  `success`, `failed`, `cancelled` (`JobStatusEnum`).
- **BE-DATA-010** A job's workspace path MUST be derived only from its UUID primary key via
  `core.config.job_dir()`; `Job.name` MUST never be used in a path.
- **BE-DATA-011** Deleting a `Job` row, directly or by cascade from its `User`, MUST remove its
  workspace after the transaction commits when the job was not `running`. When it was
  `running`, the web process MUST leave the workspace alone and the worker MUST stop the
  execution and then remove it ([job-queue-worker.md](job-queue-worker.md)).
- **BE-DATA-012** Waiting jobs MUST be ordered by `(submitted_at, id)`; `queue_position()` is
  the 1-based rank in that order and `None` for any other status.
- **BE-DATA-013** Deleting a `User` MUST delete their jobs (and steps, messages, outputs) and
  their API token; it MUST set `SystemLog.user` and `Workflow.created_by` to NULL.

Groups

- **BE-DATA-014** Deleting an `auth.Group` MUST remove its name from every
  `settings.yaml` `apps[].groups` list. A failure MUST be logged on `cloudgene.workflows` and
  MUST NOT block the delete.

Worker heartbeat

- **BE-DATA-015** `WorkerHeartbeat` MUST hold one row per worker name (normally `default`).
  The worker is alive when `now - last_seen <= 30 s`.

Migrations

- **BE-DATA-016** Committed migrations MUST match the models: `manage.py makemigrations --check
  --dry-run` MUST report no changes (run by `scripts/test.sh unit`).
- **BE-DATA-017** A data migration that cannot apply safely MUST abort and change nothing,
  naming the rows an admin must fix (as `accounts/0003_case_insensitive_identity` does for case
  duplicates). Data migrations SHOULD provide a reverse function.
- **BE-DATA-018** Migrations MUST work on both SQLite and PostgreSQL.

## Interfaces

All tables are named explicitly with `db_table`. Primary keys are `BigAutoField` unless noted.

### `core.WorkerHeartbeat` — table `worker_heartbeat`

| Field | Type | Notes |
|-------|------|-------|
| `name` | char(64), **PK**, default `default` | |
| `hostname` | char(255), default `''` | |
| `pid` | int, null | |
| `started_at` | datetime, null | |
| `last_seen` | datetime | set by `beat()` |
| `info` | JSON, default `{}` | |

Methods: `beat(name, hostname, pid, started_at, info)` upserts with `last_seen=now`;
`status(name)` → `{ok, last_seen, age_seconds, pid}` (used by `health`); `STALE_AFTER = 30 s`.

### `accounts.User` — table `users` (extends `AbstractUser`)

| Field | Type | Notes |
|-------|------|-------|
| `username` | char(150), unique | stripped on save; CI unique (BE-DATA-001) |
| `email` | email, unique | stripped + lower-cased on save; CI unique |
| `full_name` | char(255), default `''` | `REQUIRED_FIELDS = ['email', 'full_name']` |
| `activation_key` | char(255), null | SHA-256 of the e-mailed key; kept after activation |
| `activated_at` | datetime, null | |
| `password_reset_token` | char(255), null | SHA-256 of the e-mailed token |
| `password_reset_expires` | datetime, null | |
| `locked_until` | datetime, null | lockout ([authentication.md](authentication.md)) |
| `login_attempts` | int, default 0 | |
| inherited | `password`, `is_active`, `is_staff`, `is_superuser`, `groups`, `user_permissions`, `last_login`, `date_joined`, `first_name`, `last_name` | |

Constraints: `users_username_ci_unique` (`Lower('username')`), `users_email_ci_unique`
(`Lower('email')`). Manager: `UserManager.get_by_natural_key` uses `username__iexact`.
Helpers: `hash_token(raw)`, `new_token() -> (raw, hashed)`, `make_admin()` (adds group `admin`
and `is_staff`), `is_admin_user()` → `core.permissions.is_admin` ([access-control.md](access-control.md)).
`clean()` applies `accounts.validation` rules ([accounts.md](accounts.md)).

### `workflows.WorkflowCategory` — table `workflow_categories`

| Field | Type | Notes |
|-------|------|-------|
| `name` | char(255), unique | created by the registry from `cloudgene.yaml` `category` |
| `description` | text | |
| `created_at` | datetime, auto | |

Ordering `name`.

### `workflows.Workflow` — table `workflows`

| Field | Type | Notes |
|-------|------|-------|
| `id` | char(255), **PK** | app id from `cloudgene.yaml` |
| `name`, `description`, `version` (char 50, default `1.0.0`), `website` (URL) | | from `cloudgene.yaml` |
| `category` | FK `WorkflowCategory`, null, **CASCADE** | |
| `yaml_config` | text | raw `cloudgene.yaml` |
| `nextflow_script`, `config_file` | text | legacy, unused by the runner |
| `app_path` | text, default `''` | resolved `cloudgene.yaml` path; `''` = not registry-managed |
| `errors` | JSON list | validation errors of the last sync |
| `installed` | bool, default true | false once removed from `apps[]` but kept for its jobs |
| `synced_at` | datetime, null | |
| `status` | char(20), choices `enabled`/`disabled`/`maintenance`, default `enabled` | |
| `allowed_groups` | M2M `auth.Group` | mirror of `apps[].groups` |
| `public` | bool, default false | mirror of `apps[].public` |
| `created_at`, `updated_at` | datetime, auto | |
| `created_by` | FK `User`, null, SET_NULL | |

Ordering `name`. Properties `nextflow_profile`, `working_directory`, `nextflow_config`,
`env_vars` read `settings.yaml` / `$CLOUDGENE_HOME/apps/<id>/` (not columns).
`can_access(user)` → [access-control.md](access-control.md).

### `jobs.Job` — table `jobs`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID, **PK**, default `uuid4` | workspace name |
| `name` | char(255), blank | free text, never in paths |
| `workflow` | FK `Workflow`, null, **SET_NULL**, `related_name='jobs'` | |
| `app_id`, `app_name`, `app_version`, `workflow_yaml`, `app_dir` | snapshot | BE-DATA-008 |
| `user` | FK `User`, **CASCADE**, `related_name='jobs'` | owner |
| `status` | char(20), `JobState.CHOICES`, default `waiting` | |
| `cancel_requested` | bool | |
| `submitted_at` | datetime, default now | |
| `started_at`, `finished_at` | datetime, null | |
| `updated_at` | datetime, auto | |
| `parameters` | JSON dict | resolved inputs ([job-submission.md](job-submission.md)) |
| `uploads` | JSON dict | `{input_id: [{name, path, size}]}` |
| `pid`, `pgid` | int, null | worker only |
| `current_step` | int | |
| `error_message` | text | |
| `deleted_at` | datetime, null | soft delete by owner; `Job.objects.visible()` excludes |
| `purged_at` | datetime, null | workspace removed by retention |

Indexes: `(status, submitted_at)`, `(user, status)`. Default ordering `-submitted_at`.
Queryset: `visible()`, `waiting_in_order()`. Helpers: `is_active`, `is_finished`, `workspace`,
`duration_seconds()`, `queue_position()`, `expires_at()` (`finished_at +
server.job_retention_days`, `None` if 0), `can_cancel()`, `can_delete()`, `can_restart()`.
`JobState`: `ACTIVE = (waiting, running)`, `FINISHED = (success, failed, cancelled)`.

### `jobs.JobStep` — table `job_steps`

`job` (FK CASCADE, `steps`), `order` (int), `name`, `status` (`JobState.CHOICES`, default
`waiting`), `started_at`, `finished_at`, `processes` (JSON list of
`{name, label, submitted, running, completed, failed, total}`). Ordering `(order, id)`.

### `jobs.JobMessage` — table `job_messages`

`job` (FK CASCADE, `messages`), `step` (FK `JobStep`, null, SET_NULL), `level`
(`debug`/`info`/`success`/`warning`/`error`, default `info`), `text`, `created_at`.
Ordering `(created_at, id)`.

### `jobs.JobOutput` — table `job_outputs`

`job` (FK CASCADE, `outputs`), `output_id` (YAML output id), `label`, `path` (relative to
`<job>/output/`), `size` (bigint), `download_count`, `created_at`. Ordering
`(output_id, path)`. Property `name` = last path segment.

### `admin_panel.SystemLog` — table `system_logs`

| Field | Type | Notes |
|-------|------|-------|
| `timestamp` | datetime, auto_now_add, indexed | |
| `level` | char(20), choices `debug`/`info`/`warning`/`error`/`critical` | |
| `message` | text | |
| `component` | char(100) | second segment of the logger name |
| `logger` | char(200) | full logger name |
| `user` | FK `User`, null, SET_NULL | |
| `metadata` | JSON dict | `extra={'data': …}` plus `traceback` |

Indexes `(timestamp, level)`, `(component, level)`. Ordering `(-timestamp, -id)`. Semantics in
[logging.md](logging.md).

### Relationships

```
User 1─* Job 1─* JobStep 1─* JobMessage(step, SET_NULL)
           │ 1─* JobMessage
           │ 1─* JobOutput
Workflow 1─* Job (SET_NULL)          WorkflowCategory 1─* Workflow (CASCADE)
Workflow *─* Group (allowed_groups)  User *─* Group
User 1─1 authtoken.Token (CASCADE)   User 1─* SystemLog (SET_NULL)
```

### Signal receivers

| Signal | Sender | Receiver | Effect |
|--------|--------|----------|--------|
| `post_delete` | `jobs.Job` | `jobs.signals.remove_workspace` | BE-DATA-011 (`transaction.on_commit`) |
| `post_delete` | `auth.Group` | `workflows.apps._prune_deleted_group` (`dispatch_uid='workflows.prune_deleted_group'`) | BE-DATA-014 |
| `user_login_failed`, `user_logged_in` | auth | `accounts.backends.count_failed_login`, `reset_login_attempts` | lockout ([authentication.md](authentication.md)) |

### Migrations

| App | Migrations | Notes |
|-----|-----------|-------|
| `core` | `0001_initial` | `WorkerHeartbeat` |
| `accounts` | `0001_initial`, `0002_password_reset_token`, `0003_case_insensitive_identity` | 0003: aborts on case duplicates, normalises, hashes stored activation keys, adds CI constraints |
| `workflows` | `0001`–`0004` | 0003 registry cache fields; 0004 drops `WorkflowExecution`, `WorkflowParameter` |
| `jobs` | `0001`–`0004` | 0003 renames states (`pending→waiting`, `completed→success`, step `skipped→cancelled`) and fills snapshots (reversible); 0004 drops `JobDownload`, `JobValue` |
| `admin_panel` | `0001_initial`, `0002_remove_obsolete_models` | 0002 drops `ServerSettings`, `NavbarItem`, `Template`, `Counter`, `CounterHistory` |

## Behaviour

Workspace removal on delete (`jobs/signals.py`): the receiver captures `id` and `status` before
the delete returns (Django clears the pk), resolves `job_dir(id)` (skips silently on an invalid
id), and registers an `on_commit` callback. On commit: `running` → log on `cloudgene.jobs` and
leave the directory; anything else → `rmtree(ignore_errors=True)`. A rolled-back delete removes
nothing.

Soft vs hard delete: an owner's delete sets `deleted_at` (row kept, hidden by `visible()`);
admin user deletion and retention purges are described in [jobs-api.md](jobs-api.md) and
[management-commands.md](management-commands.md).

Migration policy: new migrations are generated with `makemigrations`, committed with the model
change, and never edited after release. Schema removals go in a separate migration after the
data has moved (pattern of `jobs/0003` + `0004`). A migration that would silently merge or drop
user data must instead stop with an explanation.

## Acceptance tests

| Req | Test | Layer |
|-----|------|-------|
| BE-DATA-001 | `accounts/tests.py::UserModelTest::test_db_rejects_case_variant_username`, `::test_db_rejects_case_variant_email` | unit |
| BE-DATA-002 | `accounts/tests.py::UserModelTest::test_email_normalised_and_username_stripped` | unit |
| BE-DATA-003 | `accounts/tests.py::UserModelTest::test_natural_key_lookup_ignores_case`; `accounts/tests.py::DjangoAdminLockoutTest::test_wrong_passwords_count_towards_lockout_case_insensitive` | unit |
| BE-DATA-004 | `accounts/tests.py::RegistrationTest::test_register_sends_activation_mail_and_stores_hashed_key`; `accounts/tests.py::PasswordResetTest::test_token_hashed_single_use` | unit |
| BE-DATA-005 | `workflows/test_registry.py::RegistrySyncTest` | unit |
| BE-DATA-006 | `workflows/test_registry.py::RegistryInstallTest::test_uninstall_removes_entry_and_row`; (planned) `::test_uninstall_keeps_row_with_jobs_as_not_installed` | unit |
| BE-DATA-007 | `core/tests/test_schema.py::SchemaStalenessTest::test_committed_schema_is_up_to_date` | contract |
| BE-DATA-008 | (planned) `jobs/tests/test_api.py::JobLifecycleApiTest::test_job_readable_after_workflow_uninstall` | unit |
| BE-DATA-009 | `core/tests/test_schema.py::SchemaStalenessTest::test_committed_schema_is_up_to_date` | contract |
| BE-DATA-010 | `core/tests/test_config.py::PathsAndPagesTest::test_traversal_rejected` | unit |
| BE-DATA-011 | `jobs/tests/test_worker.py::DeletedWhileRunningTest::test_deleting_a_waiting_job_removes_the_workspace_immediately`, `::test_deleting_a_running_job_leaves_the_workspace_to_the_worker`; `jobs/tests/test_api.py::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces`; `e2e/tests/test_findings_admin.py::test_c03_deleting_user_removes_the_workspace_of_a_running_job` | unit, e2e |
| BE-DATA-012 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_queue_positions` | unit |
| BE-DATA-013 | `jobs/tests/test_api.py::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces`; (planned) `admin_panel/tests/test_api.py::LogsTest::test_user_delete_keeps_log_rows` | unit |
| BE-DATA-014 | `workflows/test_registry.py::RegistryAccessTest::test_deleted_group_is_pruned_from_settings` | unit |
| BE-DATA-015 | `jobs/tests/test_worker.py::WorkerQueueTest::test_heartbeat`; `core/tests/test_api.py::HealthTest::test_health_with_fresh_and_stale_heartbeat` | unit |
| BE-DATA-016 | `scripts/test.sh unit` step "Migrations up to date" | unit |
| BE-DATA-017 | `accounts/tests.py::DuplicateDetectionTest::test_find_case_duplicates` | unit |
| BE-DATA-018 | `scripts/test.sh unit --postgres` | unit |

## Known gaps

| Req | Current behaviour | Ref | Severity |
|-----|-------------------|-----|----------|
| BE-DATA-005 | `Workflow.category` uses `on_delete=CASCADE`: deleting a category (e.g. in the Django admin) deletes its workflow rows, which then cascade `Job.workflow` to NULL. The registry recreates rows on the next sync only if still in `apps[]`. `SET_NULL` would match the "cache" role. | `workflows/models.py:42` | minor |
| BE-DATA-009 | Allowed status values are enforced only by Django `choices` (not validated on `save()` or by a DB check constraint); worker writes are trusted. | `jobs/models.py:60`, `jobs/models.py:149` | minor |
| BE-DATA-008 | No test proves a job stays readable after its workflow is uninstalled. | `jobs/models.py:53` | minor |
| — | `JobOutput` has no uniqueness on `(job, output_id, path)`; a repeated collection could duplicate rows. | `jobs/models.py:181` | minor |
| — | `Workflow.nextflow_script`, `config_file`, `created_by` are legacy columns not written by the registry. | `workflows/models.py:46`, `workflows/models.py:70` | minor |
| — | `SystemLog.timestamp` is the DB insert time (`auto_now_add`), not the log record's creation time. | `admin_panel/models.py:21` | minor |

## Open questions

- Should `Job.status` / `JobStep.status` get a `CheckConstraint` on the allowed values?
- Should the legacy `Workflow` columns (`nextflow_script`, `config_file`, `created_by`) be
  dropped in a migration?
