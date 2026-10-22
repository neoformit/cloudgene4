# Process management (systemd)

## Purpose

Cloudgene runs in production as three systemd-managed processes on one host: the web process
(gunicorn), the single job worker (`manage.py run_worker`), and a daily one-shot cleanup
(`cleanup_jobs` + `cleanup_logs`) started by a timer. This file specifies the unit files: which
user they run as, where their environment comes from, which management command each unit calls,
start ordering, restart and stop behaviour, and the filesystem sandbox. The behaviour of the
commands themselves belongs to the backend spec.

## Scope

Covered:

- `deploy/systemd/cloudgene-web.service`
- `deploy/systemd/cloudgene-worker.service`
- `deploy/systemd/cloudgene-cleanup.service`
- `deploy/systemd/cloudgene-cleanup.timer`

Out of scope:

- gunicorn settings (`deploy/gunicorn.conf.py`): [web-server.md](web-server.md).
- Environment variables and the env file contents: [environment-config.md](environment-config.md).
- Command behaviour (`run_worker`, `cleanup_jobs`, `cleanup_logs`): [../backend/management-commands.md](../backend/management-commands.md).
- Worker lock, heartbeat and shutdown semantics: [../backend/job-queue-worker.md](../backend/job-queue-worker.md).
- `CLOUDGENE_HOME` layout and permissions: [cloudgene-home.md](cloudgene-home.md).
- Nextflow/Java host requirements: [workflow-runtime.md](workflow-runtime.md).
- Installing and enabling the units, and restart order on upgrade: [install-upgrade.md](install-upgrade.md).
- journald log handling: [observability.md](observability.md).

## Dependencies

- [../backend/management-commands.md](../backend/management-commands.md): BE-CMD-041 (lock, exit 1), BE-CMD-042 (SIGTERM → exit 0), BE-CMD-050..060 (cleanup).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md): BE-QUEUE-014 (graceful shutdown), orphan recovery.
- [web-server.md](web-server.md): `GUNICORN_TIMEOUT`, `GUNICORN_GRACEFUL_TIMEOUT`, `preload_app`.
- [environment-config.md](environment-config.md): `/etc/cloudgene/cloudgene.env`.
- [database.md](database.md): PostgreSQL as the production database; one worker per database.
- [cloudgene-home.md](cloudgene-home.md): `CLOUDGENE_HOME=/var/lib/cloudgene`.

## Requirements

### Common to all units

- **DEP-PROC-001** Every Cloudgene service unit MUST run as `User=cloudgene` and `Group=cloudgene`, never as root.
- **DEP-PROC-002** Every service unit MUST set `WorkingDirectory=/opt/cloudgene` and load its environment from `EnvironmentFile=/etc/cloudgene/cloudgene.env`, so web, worker and cleanup see the same `DATABASE_URL`, `CLOUDGENE_HOME` and secret key.
- **DEP-PROC-003** Every service unit MUST run Python and gunicorn from the virtualenv at `/opt/cloudgene/venv/bin/`, not a system interpreter.
- **DEP-PROC-004** Every service unit MUST set `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict` and `ProtectHome=true`.
- **DEP-PROC-005** Every service unit MUST list in `ReadWritePaths=` each directory it writes to: at least `CLOUDGENE_HOME` (`/var/lib/cloudgene`).
- **DEP-PROC-006** The worker unit's `ReadWritePaths=` MUST also cover every Nextflow work directory configured outside `CLOUDGENE_HOME` (`nextflow.work_dir` or `apps[].work_dir` in `settings.yaml`, see `jobs/runner.py:work_dir_for`) and the service user's Nextflow home (`$HOME/.nextflow`, or `NXF_HOME` if set in `nextflow.env`). The operator MUST add such paths when configuring them; otherwise jobs fail with a permission error.
- **DEP-PROC-007** Workflow app directories registered without `--copy` SHOULD lie on a path the sandbox lets the web and worker read. Under `ProtectHome=true`, paths under `/home`, `/root` and `/run/user` are not readable.
- **DEP-PROC-008** Units that need the database MUST be ordered `After=postgresql.service`. Long-running units (web, worker) MUST also declare `Wants=postgresql.service` so a local PostgreSQL is started with them.
- **DEP-PROC-009** No service unit MAY list the code checkout (`/opt/cloudgene`), its virtualenv or its static build directories (`static/`, `staticfiles/`) in `ReadWritePaths=`, so that neither the web process nor a workflow step can modify application code. The checkout SHOULD be owned by root and be read-only for `cloudgene`. Anything a unit must write (a SQLite database, `NXF_HOME`) MUST live outside the checkout. This is the single home of the "code not writable by the services" rule; [DEP-SEC-023](security-hardening.md#requirements) and [DEP-RT-015](workflow-runtime.md#environment-and-secrets) link here.

### Web (`cloudgene-web.service`)

- **DEP-PROC-010** The web unit MUST start gunicorn as `ExecStart=/opt/cloudgene/venv/bin/gunicorn -c /opt/cloudgene/deploy/gunicorn.conf.py cloudgene_django.wsgi:application` with `Type=simple`. It calls no management command.
- **DEP-PROC-011** The web unit MUST restart on any exit (`Restart=always`, `RestartSec=5`).
- **DEP-PROC-012** `systemctl reload cloudgene-web` MUST send SIGHUP to the gunicorn master (`ExecReload=/bin/kill -s HUP $MAINPID`). What gunicorn does on SIGHUP with `preload_app` on (no new code; restart required) is [DEP-WEB-016](web-server.md#timeouts-and-lifecycle).
- **DEP-PROC-013** The web unit's `TimeoutStopSec` MUST be longer than gunicorn's graceful shutdown period (`GUNICORN_GRACEFUL_TIMEOUT`, [DEP-WEB-012](web-server.md#timeouts-and-lifecycle)), so gunicorn, not systemd, ends in-flight requests. Today `TimeoutStopSec=310` versus `graceful_timeout=30`.
- **DEP-PROC-014** The web unit MUST be enabled under `multi-user.target`.

### Worker (`cloudgene-worker.service`)

- **DEP-PROC-020** The worker unit MUST run `ExecStart=/opt/cloudgene/venv/bin/python manage.py run_worker` (no `--once`) with `Type=simple`.
- **DEP-PROC-021** Exactly one worker unit MUST be enabled per database. The unit relies on `run_worker`'s lock (BE-CMD-041): a second instance on the same host exits 1 without touching jobs.
- **DEP-PROC-022** The worker unit MUST restart on any exit (`Restart=always`, `RestartSec=5`). A restart that races a still-running old instance MUST end with the new instance exiting 1 on the lock and being retried, never with two workers claiming jobs.
- **DEP-PROC-023** The worker unit MUST stop the worker with SIGTERM (`KillSignal=SIGTERM`) so `run_worker` runs its graceful shutdown (BE-CMD-042, BE-QUEUE-014): stop claiming, stop each running job's process group, mark those jobs `failed`, release the lock, exit 0.
- **DEP-PROC-024** The worker unit's `TimeoutStopSec` MUST be at least as long as the worker's worst-case shutdown at the configured `server.max_running_jobs` (about 10 s per running job, BE-QUEUE-014). Today it is fixed at 120 s.
- **DEP-PROC-025** When systemd stops or restarts the worker unit, every process the worker started (Nextflow and command steps) MUST end with it. No job process MAY outlive the unit. (Today guaranteed by the default `KillMode=control-group`.)
- **DEP-PROC-026** The worker unit MUST be enabled under `multi-user.target`. It MUST NOT depend on the web unit, and the web unit MUST NOT depend on it; either can be restarted alone.

### Cleanup (`cloudgene-cleanup.service` + `.timer`)

- **DEP-PROC-030** The cleanup service MUST be `Type=oneshot` and run, in order, `manage.py cleanup_jobs` and `manage.py cleanup_logs` with no arguments, so retention comes from `server.job_retention_days` and the `cleanup_logs` default of 30 days.
- **DEP-PROC-031** The cleanup service MUST have no `[Install]` section; it MUST be started only by `cloudgene-cleanup.timer`.
- **DEP-PROC-032** The timer MUST fire once a day (`OnCalendar=daily`), MUST spread its start by up to 30 minutes (`RandomizedDelaySec=1800`), and MUST catch up a run missed while the host was down (`Persistent=true`). It MUST be enabled under `timers.target`.
- **DEP-PROC-033** The cleanup service MUST be safe to run while the worker runs: it MUST NOT touch waiting or running jobs (BE-CMD-051).
- **DEP-PROC-034** A failure of `cleanup_jobs` SHOULD NOT prevent `cleanup_logs` from running. (planned)

### Command map (handoff from the backend spec)

- **DEP-PROC-040** The management commands called by systemd units MUST be exactly those in the table under Interfaces. Any other command (`migrate`, `collectstatic`, `create_admin`, `install_workflow`, `sync_workflows`, `check --deploy`) is run by the operator, as described in [install-upgrade.md](install-upgrade.md), and MUST NOT be added to a unit's `ExecStart`/`ExecStartPre` without updating this file.

## Interfaces

### Units

| Unit | Type | Runs | Restart | Stop | Install target |
|------|------|------|---------|------|----------------|
| `cloudgene-web.service` | simple | `venv/bin/gunicorn -c deploy/gunicorn.conf.py cloudgene_django.wsgi:application` | always, 5 s | SIGTERM, `TimeoutStopSec=310` | `multi-user.target` |
| `cloudgene-worker.service` | simple | `venv/bin/python manage.py run_worker` | always, 5 s | SIGTERM, `TimeoutStopSec=120` | `multi-user.target` |
| `cloudgene-cleanup.service` | oneshot | `manage.py cleanup_jobs`, then `manage.py cleanup_logs` | none | default | none (timer only) |
| `cloudgene-cleanup.timer` | timer | `cloudgene-cleanup.service` | — | — | `timers.target` |

### Which unit calls which management command

| Command | Called by | Arguments | Exit codes the unit sees |
|---------|-----------|-----------|--------------------------|
| `run_worker` | `cloudgene-worker.service` | none | 0 after SIGTERM; 1 if the lock is held (unit restarts after 5 s) |
| `cleanup_jobs` | `cloudgene-cleanup.service` (1st `ExecStart`) | none (`--days` from `settings.yaml`) | 0 |
| `cleanup_logs` | `cloudgene-cleanup.service` (2nd `ExecStart`) | none (30 days) | 0 |
| `migrate`, `collectstatic`, `check --deploy`, `create_admin`, `install_workflow`, `sync_workflows` | operator only ([install-upgrade.md](install-upgrade.md)) | — | — |

### Shared settings

| Setting | Value (all three services) |
|---------|----------------------------|
| `User` / `Group` | `cloudgene` / `cloudgene` |
| `WorkingDirectory` | `/opt/cloudgene` |
| `EnvironmentFile` | `/etc/cloudgene/cloudgene.env` |
| `After` | `network.target postgresql.service` |
| `Wants` | `postgresql.service` (web, worker only) |
| Sandbox | `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadWritePaths=/opt/cloudgene /var/lib/cloudgene` |

### Writable paths each process needs

| Path | Web | Worker | Cleanup | Covered by `ReadWritePaths` |
|------|-----|--------|---------|-----------------------------|
| `CLOUDGENE_HOME` (`/var/lib/cloudgene`): `config/`, `jobs/`, `pages/`, `apps/`, `mail/` | yes | yes | yes (`jobs/`) | yes |
| `/tmp` (upload temp files, Java/Nextflow temp) | yes | yes | no | private per unit (`PrivateTmp=true`) |
| `$HOME/.nextflow` (service user home; `/opt/cloudgene` in the documented setup) | no | yes | no | yes, only if the home is under `/opt/cloudgene` |
| Nextflow work dir outside `CLOUDGENE_HOME` | no | yes | no | no — operator must add it (DEP-PROC-006) |
| `/opt/cloudgene` (code, venv, `static/`, `staticfiles/`) | no (yes only if `DATABASE_URL` is unset and the SQLite default `db.sqlite3` is used) | same | same | yes |

## Behaviour

**Boot.** `network.target` and (if local) `postgresql.service` start first; web and worker then
start in parallel. Neither checks that migrations are applied. The worker tolerates a database
that is not yet reachable: each tick phase logs the error and retries next tick
([../backend/job-queue-worker.md](../backend/job-queue-worker.md)).

**Worker stop.** `systemctl stop cloudgene-worker` sends SIGTERM. With the default
`KillMode=control-group`, systemd sends it to every process in the unit's cgroup at once, so
Nextflow process groups receive SIGTERM directly as well as from the worker. The worker then
stops each running job in turn (SIGTERM, up to 5 s, SIGKILL, up to 5 s wait) and marks it
`failed` with `The worker was shut down while this job was running; the job was stopped.`
Waiting jobs stay `waiting` and are claimed by the next worker. If shutdown exceeds
`TimeoutStopSec`, systemd SIGKILLs the cgroup; the jobs still marked `running` are failed as
orphans by the next worker's startup reconcile.

**Worker crash.** `Restart=always` restarts it after 5 s. Leftover job processes in the cgroup
are killed by systemd before the restart; the new worker fails their jobs as orphans.

**Double start.** If a second worker starts while the first still holds
`CLOUDGENE_HOME/config/worker.lock`, it exits 1 with `Another worker is already running for this
CLOUDGENE_HOME.` and systemd retries every 5 s. At this rate (2 starts per 10 s) the default
start-rate limit (5 per 10 s) is not reached.

**Web stop.** systemd sends SIGTERM; gunicorn's graceful shutdown (DEP-WEB-012, 30 s by
default) bounds in-flight requests, so `TimeoutStopSec=310` is only systemd's backstop
(DEP-PROC-013). Details: [web-server.md](web-server.md#behaviour) "Stop and restart".

**Cleanup run.** The timer fires daily at 00:00 plus 0–30 min. `cleanup_jobs` runs first; if it
exits non-zero, systemd does not run `cleanup_logs` and marks the service failed.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-PROC-001 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_run_as_cloudgene_user` (planned) | config |
| DEP-PROC-002 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_share_environment_file_and_workdir` (planned) | config |
| DEP-PROC-003 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_use_venv_binaries` (planned) | config |
| DEP-PROC-004 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_sandboxed` (planned) | config |
| DEP-PROC-005 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_read_write_paths_cover_cloudgene_home` (planned) | config |
| DEP-PROC-006 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_worker_read_write_paths_cover_nextflow_home` (planned) | config |
| DEP-PROC-008 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_ordered_after_postgresql` (planned) | config |
| DEP-PROC-009 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_read_write_paths_exclude_code_checkout` (planned) | config |
| DEP-PROC-010 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_execstart` (planned); gunicorn command line also exercised by `scripts/smoke_gunicorn.sh` | config, smoke |
| DEP-PROC-011 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_and_worker_restart_always` (planned) | config |
| DEP-PROC-012 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_reload_sends_hup` (planned) | config |
| DEP-PROC-013 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_stop_timeout_exceeds_graceful_timeout` (planned) | config |
| DEP-PROC-014 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_install_targets` (planned) | config |
| DEP-PROC-020 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_worker_execstart` (planned) | config |
| DEP-PROC-021 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| DEP-PROC-022 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock`; `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_and_worker_restart_always` (planned) | unit, config |
| DEP-PROC-023 | `jobs/tests/test_worker.py::ShutdownTest::test_shutdown_stops_running_jobs`; `jobs/tests/test_worker.py::RunWorkerCommandTest::test_sigterm_stops_gracefully` (planned) | unit |
| DEP-PROC-024 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_worker_stop_timeout_covers_max_running_jobs` (planned) | config |
| DEP-PROC-025 | `jobs/tests/test_worker.py::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed` (recovery side only); systemd behaviour not tested | unit |
| DEP-PROC-026 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_install_targets` (planned) | config |
| DEP-PROC-030 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_cleanup_runs_both_commands` (planned) | config |
| DEP-PROC-031 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_install_targets` (planned) | config |
| DEP-PROC-032 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_cleanup_timer_schedule` (planned) | config |
| DEP-PROC-033 | `jobs/tests/test_api.py::CleanupCommandTest::test_retention` | unit |
| DEP-PROC-040 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_unit_command_map` (planned) | config |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-PROC-024 | `TimeoutStopSec=120` is fixed. Shutdown stops jobs one after another, up to ~10 s each, so more than ~12 running jobs exceed it; systemd then SIGKILLs the worker mid-shutdown (jobs are failed later as orphans). Also noted as BE-QUEUE-014 gap. | `deploy/systemd/cloudgene-worker.service:20`, `jobs/worker.py:798-801` | minor |
| DEP-PROC-013 | Requirement holds (310 > 30), but the unit comment says gunicorn may take up to `GUNICORN_TIMEOUT` (300 s) to finish an upload on stop; gunicorn's SIGTERM path uses `graceful_timeout` (30 s). Uploads longer than 30 s are cut off on every stop/restart and the 310 s value is never used. This is the single home of this gap; api-contract.md and web-server.md link here. | `deploy/systemd/cloudgene-web.service:16-18`, `deploy/gunicorn.conf.py:38` | minor |
| DEP-PROC-006 | `ReadWritePaths` does not include admin-configured Nextflow work dirs outside `CLOUDGENE_HOME`; nothing checks this at config time, so a job fails at run time. | `deploy/systemd/cloudgene-worker.service:26`, `jobs/runner.py:work_dir_for` | minor |
| DEP-PROC-006 | Nextflow's home (`$HOME/.nextflow`) is only writable if the `cloudgene` user's home is under `/opt/cloudgene`; a home under `/home` is hidden by `ProtectHome=true`. The units do not set `NXF_HOME` or `HOME`. | `deploy/systemd/cloudgene-worker.service:23-27` | minor |
| DEP-PROC-009 | All three units list `/opt/cloudgene` (code checkout and venv) in `ReadWritePaths=`, and the install clones the checkout as `cloudgene`. A compromised web process or any workflow step can rewrite the application code that the web unit loads on its next start. Only the SQLite default database file and the documented `NXF_HOME` (`/opt/cloudgene/.nextflow`) rely on it. | `deploy/systemd/cloudgene-web.service:25`, `cloudgene-worker.service:26`, `cloudgene-cleanup.service:21` | major |
| DEP-PROC-034 | Two `ExecStart=` lines in a oneshot unit run sequentially and stop at the first failure; a failing `cleanup_jobs` skips `cleanup_logs`. | `deploy/systemd/cloudgene-cleanup.service:15-16` | minor |
| DEP-PROC-023 | The worker comment relies on its own SIGTERM forwarding, but `KillMode` is the default `control-group`, so systemd signals Nextflow directly at the same time. Harmless today, but the ordered per-job stop is not what actually happens. | `deploy/systemd/cloudgene-worker.service:18-21` | minor |
| DEP-PROC-021 | The single-worker guarantee is a host-local `flock`. Nothing stops a second host with its own `CLOUDGENE_HOME` from running a worker against the same database (BE-QUEUE-011 gap). | `jobs/worker.py:acquire_lock` | minor |
| — | No test reads the unit files at all; every unit-level requirement above has only a planned config test. | `core/tests/` | minor |
| DEP-PROC-008 | `After=network.target` only; with a remote PostgreSQL, units do not wait for `network-online.target`. | `deploy/systemd/*.service:3` | minor |

## Open questions

1. Should the worker unit use `KillMode=mixed` so only `run_worker` receives SIGTERM and it alone stops the jobs, with systemd's SIGKILL to the rest as the backstop?
2. Should `TimeoutStopSec` for the worker be derived from `server.max_running_jobs` (documented formula), or should the worker stop jobs in parallel so the bound is constant?
3. DEP-PROC-009 removes `/opt/cloudgene` from `ReadWritePaths=`. That also removes the SQLite default (`<repo>/db.sqlite3`) and the documented Nextflow home (`/opt/cloudgene/.nextflow`, DEP-RT-006). Confirm that both must move (SQLite under `CLOUDGENE_HOME`; `NXF_HOME` per [workflow-runtime.md](workflow-runtime.md#open-questions) question 5), and whether install should clone the checkout as root.
4. Should the web and worker units run `manage.py migrate --check` as `ExecStartPre` so a forgotten migration fails the start instead of serving errors?
5. Worker "exclusive DB lock" (docs) versus `flock` (code): see [overview.md](overview.md#open-questions) question 1.
6. Running jobs surviving a worker restart (docs) versus being failed (code): see [install-upgrade.md](install-upgrade.md#open-questions) question 5.
7. Upload temp files in the per-unit private `/tmp`: see [web-server.md](web-server.md#open-questions) question 3.
8. Should `ExecReload` be removed from `cloudgene-web.service` (or `preload_app` defaulted off, [DEP-WEB-016](web-server.md#timeouts-and-lifecycle)), so `systemctl reload` cannot be mistaken for a code reload?
9. Whether the cleanup unit should also prune old static assets (DEP-STATIC-032) is open in [static-assets.md](static-assets.md#open-questions) question 2. If it should, DEP-PROC-030 and DEP-PROC-040 change with it.
