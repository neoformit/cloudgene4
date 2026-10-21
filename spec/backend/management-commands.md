# Management commands

## Purpose

Cloudgene adds six `manage.py` commands for tasks that run outside a web request: creating the
first administrator, installing and syncing workflows, running the job worker, and removing old
job workspaces and log records. Operators and the deployment units (systemd, e2e harness) call
them. This file specifies each command's arguments, output, exit status and whether it is safe to
run twice.

## Scope

| Command | Source |
|---------|--------|
| `create_admin` | `core/management/commands/create_admin.py` |
| `install_workflow` | `workflows/management/commands/install_workflow.py` |
| `sync_workflows` | `workflows/management/commands/sync_workflows.py` |
| `run_worker` | `jobs/management/commands/run_worker.py` |
| `cleanup_jobs` | `jobs/management/commands/cleanup_jobs.py` |
| `cleanup_logs` | `admin_panel/management/commands/cleanup_logs.py` |

Out of scope:

- Django and third-party built-ins (`migrate`, `collectstatic`, `check --deploy`, `spectacular`, `createsuperuser`): their use in deployment is in `spec/deployment/`; system checks are in [overview.md](overview.md).
- What the worker does each tick, job states, cancellation and shutdown of running jobs: [job-queue-worker.md](job-queue-worker.md).
- Workflow install/sync semantics shared with the admin API (`registry.install`, `registry.sync_all`): [workflow-registry.md](workflow-registry.md).
- Retention-related settings keys: [configuration.md](configuration.md).
- Scheduling (systemd units/timers): `spec/deployment/`.

## Dependencies

- [workflow-registry.md](workflow-registry.md): `registry.install()`, `registry.sync_all()`, `RegistryError`.
- [job-queue-worker.md](job-queue-worker.md): `Worker`, `acquire_lock()`, `drain()`, `run_forever()`, `shutdown()`.
- [configuration.md](configuration.md): `server.job_retention_days`, `job_dir()`, `jobs_dir()`.
- [access-control.md](access-control.md): the `admin` group and the admin definition.
- [data-model.md](data-model.md): `Job.purged_at`, `Job.deleted_at`, `JobOutput`, `SystemLog`.

## Requirements

### General

- **BE-CMD-001** Every command MUST exit 0 on success. A command that cannot do its job MUST exit non-zero with a one-line reason on stderr (Django `CommandError` → exit 1), not a Python traceback.
- **BE-CMD-002** Every command MUST operate on the `CLOUDGENE_HOME` and database configured for the process (environment / Django settings); none takes a home or database argument.

### create_admin

- **BE-CMD-010** `create_admin [--username U] [--email E] [--full-name N] [--password P]` MUST ensure an active administrator account `U` exists (defaults: `admin`, `admin@localhost`, `Administrator`). The user MUST end up with `is_active`, `is_staff`, `is_superuser` set, no pending activation key, and membership of the `admin` group (created if missing).
- **BE-CMD-011** The username lookup MUST be case-insensitive. If the user exists it MUST be updated in place, not duplicated (idempotent).
- **BE-CMD-012** Password source order: `--password`, then `$CLOUDGENE_ADMIN_PASSWORD`. When a new user is created and neither is given, a random password MUST be generated and printed once on stdout as `Generated password: …`. An existing user MUST keep their password unless a password is given.
- **BE-CMD-013** Output MUST be `Created admin user "U"` or `Updated admin user "U"`. The command MUST run in one transaction: on failure nothing is changed.
- **BE-CMD-014** A given password SHOULD meet the same password rules as registration ([accounts.md](accounts.md)); a rejected password MUST exit 1 with the rule's message. *(planned)*
- **BE-CMD-015** An e-mail already used by another account MUST exit 1 with a clear message, not a traceback. *(planned)*

### install_workflow

- **BE-CMD-020** `install_workflow PATH [--public] [--groups g1,g2] [--disabled] [--copy] [--replace]` MUST register the app (a directory containing `cloudgene.yaml`, or the YAML file) in `settings.yaml` `apps[]` and sync the workflow cache, with the semantics of `registry.install` ([workflow-registry.md](workflow-registry.md)).
- **BE-CMD-021** The command MUST support these options: `--public` makes it available to all users; `--groups` gives comma-separated group names (missing groups are created); `--disabled` installs it disabled; `--copy` first copies the app to `$CLOUDGENE_HOME/apps/<id>/`; `--replace` re-points an already installed id at this path, keeping its access rules.
- **BE-CMD-022** A relative `PATH` that exists relative to the current directory MUST be used as such (made absolute); otherwise it is resolved against `$CLOUDGENE_HOME/apps`, then `$CLOUDGENE_HOME`.
- **BE-CMD-023** On success it MUST print `Installed <id> (<name> <version>) from <stored path>` and exit 0.
- **BE-CMD-024** Not found, an invalid `cloudgene.yaml`, an id already installed without `--replace`, or an existing `--copy` target MUST exit 1 with the registry's message followed by one `  - <error>` line per validation error, and MUST NOT change `settings.yaml`.
- **BE-CMD-025** Running it twice with the same path is not idempotent: the second run MUST fail (BE-CMD-024) unless `--replace` is given, in which case it MUST succeed and leave one entry.

### sync_workflows

- **BE-CMD-030** `sync_workflows` MUST rebuild the workflow cache from `settings.yaml` `apps[]` (`registry.sync_all`) and be idempotent.
- **BE-CMD-031** It MUST print one line per app: `<id>: enabled|disabled (<yaml path>)` for valid apps, `<id>: INVALID (<path>)` plus one `  - <error>` line per error for invalid ones, then `<n> workflow(s) synced.`
- **BE-CMD-032** Invalid apps MUST NOT stop the sync of the others. The exit status MUST be 0 even if some apps are invalid (the problem is reported in the output and on the admin dashboard).

### run_worker

- **BE-CMD-040** `run_worker [--once] [--interval S] [--grace S] [--timeout S]` MUST run the job worker ([job-queue-worker.md](job-queue-worker.md)). Defaults: interval 1.0 s, grace 10 s (SIGTERM → SIGKILL when cancelling), timeout 3600 s (only with `--once`).
- **BE-CMD-041** Only one worker MAY run per `CLOUDGENE_HOME`: the command MUST take an exclusive non-blocking lock on `config/worker.lock`; if another process holds it, it MUST exit 1 with `Another worker is already running for this CLOUDGENE_HOME.` and touch no job.
- **BE-CMD-042** Without `--once` it MUST print `Worker started (interval <S>s). Stop with Ctrl+C.`, run until SIGTERM or SIGINT, then stop claiming jobs, stop running jobs as described in [job-queue-worker.md](job-queue-worker.md), print `Worker stopped.` and exit 0. The lock MUST be released on every exit path.
- **BE-CMD-043** With `--once` it MUST tick until no job is running and none can be claimed, or until `--timeout` seconds pass, then stop any still-running jobs and exit. Reaching the timeout with work left SHOULD exit non-zero. *(planned)*

### cleanup_jobs

- **BE-CMD-050** `cleanup_jobs [--days N] [--dry-run]` MUST remove the workspace of every finished job (`success`, `failed`, `cancelled`) that is soft-deleted, or that finished more than N days ago when N > 0. N defaults to `server.job_retention_days`; N ≤ 0 means "keep finished jobs forever" (deleted jobs are still purged).
- **BE-CMD-051** For each purged job it MUST delete the workspace directory and the job's `JobOutput` rows and set `purged_at` (keeping an existing value). The `Job` row MUST be kept. Waiting and running jobs MUST never be touched.
- **BE-CMD-052** It MUST also remove orphan workspaces: directories in `$CLOUDGENE_HOME/jobs/` named as a lower-case UUID that have no `Job` row and were last modified more than 1 hour ago (so a submission in progress is not removed). Other entries MUST be left alone.
- **BE-CMD-053** It MUST be idempotent: a job already purged whose workspace is gone is skipped and not counted.
- **BE-CMD-054** `--dry-run` MUST change nothing and print `would remove <path>` / `would remove orphan <path>` per item.
- **BE-CMD-055** It MUST end with `Removed|Would remove <n> job workspace(s) (retention: <N|keep> days) and <m> orphan workspace(s).` and exit 0.

### cleanup_logs

- **BE-CMD-060** `cleanup_logs [--days N]` (default 30) MUST delete `SystemLog` records older than N days and print `Deleted <n> log entries older than <N> days.` It MUST be idempotent. N < 0 MUST be treated as 0.

## Interfaces

```
python manage.py create_admin [--username admin] [--email admin@localhost] [--full-name Administrator] [--password P]
python manage.py install_workflow PATH [--public] [--groups a,b] [--disabled] [--copy] [--replace]
python manage.py sync_workflows
python manage.py run_worker [--once] [--interval 1.0] [--grace 10] [--timeout 3600]
python manage.py cleanup_jobs [--days N] [--dry-run]
python manage.py cleanup_logs [--days 30]
```

| Command | Env vars read | Files touched | Idempotent | Exit 1 when |
|---------|---------------|---------------|------------|-------------|
| `create_admin` | `CLOUDGENE_ADMIN_PASSWORD` | DB only | yes | (planned: bad password, e-mail taken) |
| `install_workflow` | — | `settings.yaml`, `apps/<id>/` with `--copy` | no (yes with `--replace`) | not found, invalid, already installed, copy target exists |
| `sync_workflows` | — | DB only | yes | never (by design) |
| `run_worker` | — | `config/worker.lock`, job workspaces | n/a | lock held |
| `cleanup_jobs` | — | `jobs/<uuid>/` | yes | never |
| `cleanup_logs` | — | DB only | yes | never |

Callers: `deploy/systemd/cloudgene-worker.service` (`run_worker`), `deploy/systemd/cloudgene-cleanup.service` (`cleanup_jobs`, `cleanup_logs`), `e2e/stack.py` (`create_admin`, `sync_workflows`, `run_worker`).

## Behaviour

**create_admin flow.** Look up the user by username ignoring case → create an unsaved `User` if
missing (generating a password if none was given) → set the password if one was given → set the
admin flags and clear the activation key → save → add to the `admin` group. Because the command
always sets `is_active`, re-running it also re-enables a deactivated admin; it does not clear a
login lockout.

**install_workflow vs admin API.** The command and `admin_workflows_install` share
`registry.install`; the command adds the cwd-relative path rule (BE-CMD-022) and maps
`RegistryError` to `CommandError`.

**cleanup_jobs selection.** `deleted_at IS NOT NULL OR finished_at < now − N days` (second term
only when N > 0), always intersected with finished states. Missing workspaces are ignored
(`rmtree(..., ignore_errors=True)`).

**run_worker signals.** SIGTERM/SIGINT set a stop flag; the loop finishes its current tick, then
calls `shutdown()`. With `--once` no signal handlers are installed.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| BE-CMD-001 | covered per command below; traceback-free failure for `create_admin` (planned) | unit |
| BE-CMD-002 | all command tests run against a temporary `CLOUDGENE_HOME` (`workflows/test_registry.py::TempHomeMixin`) | unit |
| BE-CMD-010–013 | `core/tests/test_api.py::CreateAdminCommandTest::test_create_and_update_idempotent`; generated-password output and env-var source (planned) | unit |
| BE-CMD-014, 015 | `core/tests/test_api.py::CreateAdminCommandTest::test_rejects_weak_password`, `::test_email_taken` (planned) | unit |
| BE-CMD-020, 021, 023 | `workflows/test_registry.py::CommandsTest::test_install_workflow_command` | unit |
| BE-CMD-022 | `workflows/test_registry.py::CommandsTest::test_install_relative_path_order` (planned) | unit |
| BE-CMD-024 | `workflows/test_registry.py::CommandsTest::test_install_workflow_command_invalid` | unit |
| BE-CMD-025 | `workflows/test_registry.py::CommandsTest::test_install_twice_needs_replace` (planned) | unit |
| BE-CMD-030–032 | `workflows/test_registry.py::CommandsTest::test_sync_workflows_command`; `e2e/tests/test_admin_workflows.py` (uses the command in setup) | unit, e2e |
| BE-CMD-040, 041 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| BE-CMD-042 | `e2e/tests/test_queue.py::test_worker_restart_fails_orphans_and_queue_continues` | e2e |
| BE-CMD-043 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_timeout_exit_code` (planned) | unit |
| BE-CMD-050–053 | `jobs/tests/test_api.py::CleanupCommandTest::test_retention`, `::test_deleting_a_user_removes_job_workspaces` | unit |
| BE-CMD-054, 055 | `jobs/tests/test_api.py::CleanupCommandTest::test_dry_run` (planned) | unit |
| BE-CMD-060 | `admin_panel/tests/test_api.py::LogsTest::test_cleanup_logs` | unit |

## Known gaps

| ID | What the code does | Where | Severity |
|----|--------------------|-------|----------|
| BE-CMD-014 | `create_admin` accepts any password, including ones registration would reject (e.g. `--password x`). | `core/management/commands/create_admin.py:33-43` | major |
| BE-CMD-015 | An `--email` already used by another user raises `IntegrityError` (traceback) instead of a `CommandError`. For an existing user `--email` and `--full-name` are silently ignored. | `core/management/commands/create_admin.py:40-48` | minor |
| BE-CMD-012 | The generated password is printed to stdout, which systemd/journald or CI logs may keep. Documented behaviour, but worth a warning in the output. | `core/management/commands/create_admin.py:54-55` | minor |
| BE-CMD-022 | The `PATH` help text says "`$CLOUDGENE_HOME/apps`, then cwd", but the code tries cwd first, then `$CLOUDGENE_HOME/apps`, then `$CLOUDGENE_HOME`. | `workflows/management/commands/install_workflow.py:11-12`, `:24-25`; `workflows/registry.py:148` | minor |
| BE-CMD-024 | With `--copy`, the app is copied to `apps/<id>/` before the "already installed" check, so a rejected install leaves the copied directory behind. | `workflows/registry.py:417-435` | minor |
| BE-CMD-021 | `--groups` creates groups with `get_or_create` without the group-name validation the admin API applies ([admin-api.md](admin-api.md) BE-ADM-031), and is case-sensitive, so `Lab` and `lab` can both exist. | `workflows/registry.py:395-399` | minor |
| BE-CMD-030 | `sync_workflows` help says it runs at worker start; the worker does not call it (the web process syncs lazily via `WorkflowSyncMiddleware`). | `workflows/management/commands/sync_workflows.py:7` | minor |
| BE-CMD-043 | `run_worker --once` exits 0 after hitting `--timeout`, even though it stopped still-running jobs. | `jobs/worker.py:785-796`, `jobs/management/commands/run_worker.py:35-37` | minor |
| BE-CMD-060 | `cleanup_logs --days -5` deletes everything older than now but prints "older than -5 days". | `admin_panel/management/commands/cleanup_logs.py:19-21` | minor |
| BE-CMD-050 | `cleanup_jobs --days` accepts negative values silently (treated as keep). | `jobs/management/commands/cleanup_jobs.py:35-41` | minor |
| — | `cleanup_jobs` and `cleanup_logs` write nothing to the application log, so purges are invisible in Admin → Logs. | `jobs/management/commands/cleanup_jobs.py`, `admin_panel/management/commands/cleanup_logs.py` | minor |

## Open questions

1. Should `sync_workflows` exit non-zero when any app is invalid, so a deploy script can fail fast? Today it always exits 0.
2. Should `create_admin` refuse to print a generated password when stdout is not a TTY?
3. Should `cleanup_jobs` and `cleanup_logs` log a summary on `cloudgene.*` so retention runs appear in Admin → Logs?
