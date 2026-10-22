# Database

## Purpose

Cloudgene stores users, groups, jobs, job steps/messages/outputs, the worker heartbeat and the
admin system log in one relational database shared by the web process, the worker and the
cleanup command. Production uses PostgreSQL; development, tests and small single-user installs
may use SQLite. This file specifies how the database is selected and configured, the
connection settings, how migrations are applied on deploy, the one-worker-per-database rule,
what must be backed up with the database, and the tests that only run against PostgreSQL.

## Scope

Covered:

- `cloudgene_django/settings.py:153-170` (`DATABASES`, SQLite `OPTIONS`).
- `core/checks.py:check_database_engine` (`core.W001`).
- `deploy/cloudgene.env.example` (`DATABASE_URL`, `DB_CONN_MAX_AGE`).
- `requirements.txt` (`dj-database-url`, `psycopg2-binary`).
- `scripts/test.sh unit --postgres`, `e2e/stack.py` (`E2E_DATABASE_URL`), `jobs/tests/test_claim_concurrency.py`.
- Backup and restore of the database together with `CLOUDGENE_HOME`.

Out of scope:

- Models and migrations themselves: [../backend/data-model.md](../backend/data-model.md).
- Worker claim/lock and SQLite lock retries: [../backend/job-queue-worker.md](../backend/job-queue-worker.md).
- The `/api/health` database probe: [../backend/server-pages-mail.md](../backend/server-pages-mail.md) (operationId `health`).
- Running `migrate` during install and upgrade: [install-upgrade.md](install-upgrade.md) (this file states the rules; that file places them in the procedure).
- `CLOUDGENE_HOME` layout: [cloudgene-home.md](cloudgene-home.md).
- Every other environment variable: [environment-config.md](environment-config.md).
- Installing and tuning the PostgreSQL server itself.

## Dependencies

- [environment-config.md](environment-config.md): env file loading, `.env` in the repo root.
- [process-management.md](process-management.md): all units load the same `EnvironmentFile`; DEP-PROC-021 (one worker unit).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md): BE-QUEUE-011 (lock), BE-QUEUE-013 (SQLite "database is locked" retries).
- [../backend/configuration.md](../backend/configuration.md): `settings.yaml`, `secret_key` under `CLOUDGENE_HOME/config/`.
- [security-hardening.md](security-hardening.md): `check --deploy` as a whole.
- [test-harness.md](test-harness.md): `scripts/test.sh`, `e2e/stack.py`.
- [api-contract.md](api-contract.md): DEP-API-005 (one-off commands run with the unit environment).
- [workflow-runtime.md](workflow-runtime.md): DEP-RT-014 (step processes run as the `cloudgene` OS user, the reason for DEP-DB-061).

## Requirements

### Selection and connection

- **DEP-DB-001** The database MUST be selected only by the `DATABASE_URL` environment variable, parsed with `dj_database_url`. When it is unset, the database MUST be SQLite at `<repo>/db.sqlite3`.
- **DEP-DB-002** A production deployment MUST use PostgreSQL (`DATABASE_URL=postgres://…`). `deploy/cloudgene.env.example` MUST set a PostgreSQL URL.
- **DEP-DB-003** `manage.py check --deploy` MUST report warning `core.W001` ("Using SQLite with DEBUG off …", hint "Set DATABASE_URL to a postgres:// URL.") when the engine is SQLite and `DEBUG` is off, and MUST report nothing for PostgreSQL or when `DEBUG` is on.
- **DEP-DB-004** Persistent connections MUST be controlled by `DB_CONN_MAX_AGE` (seconds, default `0` = close after each request). The production example MUST set it to `60`.
- **DEP-DB-005** When persistent connections are enabled, a connection broken by a PostgreSQL restart MUST NOT fail the next request. (planned: `CONN_HEALTH_CHECKS=True`)
- **DEP-DB-006** The long-running worker MUST drop stale or broken connections at the start of every tick (`close_old_connections()`), since it never passes through Django's request cycle.
- **DEP-DB-007** The PostgreSQL driver (`psycopg2-binary`) MUST be installed by `requirements.txt`, so no extra install step is needed for PostgreSQL.

### SQLite (development and small installs)

- **DEP-DB-010** With SQLite, settings MUST default the connection `OPTIONS` to `timeout=20` (wait up to 20 s for a lock), `transaction_mode='IMMEDIATE'` (take the write lock at `BEGIN`, so a read-then-write transaction cannot fail mid-way with "database is locked") and `init_command='PRAGMA journal_mode=WAL;'` (readers do not block the writer). Values given in `DATABASE_URL` MUST win over these defaults.
- **DEP-DB-011** These options MUST NOT be applied to PostgreSQL.
- **DEP-DB-012** A SQLite database used by both web and worker MUST be a local file on a filesystem that supports WAL shared memory (not NFS), readable and writable by the service user, in a directory that the service user can write to (WAL needs `-wal`/`-shm` files beside it).

### Migrations

- **DEP-DB-020** Schema changes MUST be applied with `manage.py migrate --noinput`, run as the service user with the same environment as the units (same `DATABASE_URL`, `CLOUDGENE_HOME`; [DEP-API-005](api-contract.md#environment)).
- **DEP-DB-021** On upgrade, migrations MUST be applied after the new code is in place and before the web and worker are restarted on it.
- **DEP-DB-022** The repository MUST contain every migration its models need: `manage.py makemigrations --check --dry-run` MUST exit 0 (run by `scripts/test.sh unit`).
- **DEP-DB-023** A systemd unit MUST NOT run `migrate` automatically (see [DEP-PROC-040](process-management.md#requirements)); migrations are an operator step.

### One worker per database

- **DEP-DB-030** At most one `run_worker` process MUST run against a given database. Within one host this is enforced by the `CLOUDGENE_HOME/config/worker.lock` lock (BE-CMD-041); across hosts the operator MUST ensure it.
- **DEP-DB-031** Even if two workers briefly overlap (e.g. during a restart), a waiting job MUST be claimed by at most one of them. On PostgreSQL this MUST hold under real row-level concurrency.

### Backup and restore

- **DEP-DB-040** A backup MUST contain the database and, from `CLOUDGENE_HOME`, at least `config/` (`settings.yaml`, `nextflow.config`, `nextflow.env`, `secret_key` if `DJANGO_SECRET_KEY` is not set), `pages/` and `apps/`, taken at about the same time. `jobs/` and `mail/` MAY be excluded; then a restored job keeps its DB row and history but its output files are gone.
- **DEP-DB-041** The PostgreSQL backup SHOULD be a consistent dump (`pg_dump -Fc`) and be restored with `pg_restore` into an empty database, followed by `manage.py migrate` (a no-op when the code matches).
- **DEP-DB-042** A SQLite backup MUST be taken with SQLite's online backup (`sqlite3 db.sqlite3 ".backup …"`) or with both web and worker stopped; copying the file alone while WAL is in use MAY lose recent writes.
- **DEP-DB-043** The worker MUST be stopped while a database or `jobs/` restore is applied, and started only after both are restored; on start it fails any job still marked `running` as an orphan.
- **DEP-DB-044** If `DJANGO_SECRET_KEY` changes on restore (or the `secret_key` file is not restored), all sessions MUST be treated as invalid; users log in again. No other data depends on the key.

### Role and access

- **DEP-DB-060** The PostgreSQL role named in the production `DATABASE_URL` MUST NOT be a superuser (`rolsuper` false). It SHOULD NOT have `CREATEROLE` or `CREATEDB`; it needs only ownership of the Cloudgene database (DEP-INST-007).
- **DEP-DB-061** `pg_hba.conf` MUST NOT let the `cloudgene` OS user connect to the Cloudgene database, or as the application's role, without a password: no `trust` rule, and no `peer` or `ident` rule that maps the `cloudgene` OS user to that role, for local sockets or `127.0.0.1`/`::1`. The application MUST authenticate with the password in `DATABASE_URL` (`scram-sha-256`). Reason: workflow step processes run as the `cloudgene` OS user ([DEP-RT-014](workflow-runtime.md#environment-and-secrets)).

### PostgreSQL-only tests

- **DEP-DB-050** Tests whose assertions only mean something with real row-level concurrency MUST skip on SQLite with a message naming `scripts/test.sh unit --postgres`, and MUST run when `DATABASE_URL` is PostgreSQL.
- **DEP-DB-051** `scripts/test.sh unit --postgres` MUST run the Django test suite with `DATABASE_URL=$TEST_DATABASE_URL` (default `postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene`) and MUST NOT start a PostgreSQL server itself.
- **DEP-DB-052** The e2e stack MUST run on SQLite by default and on PostgreSQL when `E2E_DATABASE_URL` is set, creating one database per stack at start-up and dropping it at teardown.
- **DEP-DB-053** A release SHOULD pass the unit suite against PostgreSQL, since that is the production database. (planned: no CI configuration exists in the repository)

## Interfaces

### Environment

| Variable | Default | Production example | Read by |
|----------|---------|--------------------|---------|
| `DATABASE_URL` | `sqlite:///<repo>/db.sqlite3` | `postgres://cloudgene:change-me@127.0.0.1:5432/cloudgene` | `settings.py:155-160` |
| `DB_CONN_MAX_AGE` | `0` | `60` | `settings.py:158` |
| `TEST_DATABASE_URL` | `postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene` | — | `scripts/test.sh` (`--postgres`) |
| `E2E_DATABASE_URL` | unset (SQLite) | — | `e2e/stack.py:42` |

### SQLite options (defaults, `setdefault`)

```python
OPTIONS = {
    'timeout': 20,
    'transaction_mode': 'IMMEDIATE',
    'init_command': 'PRAGMA journal_mode=WAL;',
}
```

### Commands

```
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py check --deploy            # core.W001 on SQLite with DEBUG off
scripts/test.sh unit --postgres
pg_dump -Fc cloudgene > cloudgene-YYYY-MM-DD.dump
pg_restore -d cloudgene cloudgene-YYYY-MM-DD.dump
```

### What a backup contains

| Item | Required | Why |
|------|----------|-----|
| Database | yes | users, groups, jobs, steps, messages, outputs, logs |
| `CLOUDGENE_HOME/config/` | yes | `settings.yaml` (installed apps, access rules, server settings) exists only on disk; `secret_key` when no env key |
| `CLOUDGENE_HOME/pages/` | yes | admin-edited HTML pages |
| `CLOUDGENE_HOME/apps/` | yes (unless reproducible) | apps installed with `--copy` or uploaded |
| `CLOUDGENE_HOME/jobs/` | optional | job inputs/outputs/logs; large; retention trims it |
| `CLOUDGENE_HOME/mail/` | optional | file mail backend outbox |
| `/etc/cloudgene/cloudgene.env` | yes (kept secret) | DB password, secret key |
| `CLOUDGENE_HOME/config/worker.lock`, `.settings.lock`, `.*.tmp` | no | runtime lock/temporary files |

## Behaviour

**Selection.** `dj_database_url.config()` reads `DATABASE_URL` once at settings import. If the
engine is SQLite, the three options above are added unless the URL already sets them. Nothing
else in settings depends on the engine. `check --deploy` warns about SQLite only when `DEBUG` is
off.

**Connections.** Web requests reuse a connection for up to `DB_CONN_MAX_AGE` seconds. Without
`CONN_HEALTH_CHECKS`, a reused connection killed by a PostgreSQL restart raises on its first
query, so one request per gunicorn worker fails after a database restart. The worker calls
`close_old_connections()` at the start of each tick, so it recovers on the next tick. Peak
connection count is gunicorn workers × threads (default up to 8) + 1 worker + 1 cleanup run.

**SQLite contention.** Web and worker share one writer lock. Writers wait up to 20 s; the worker
also retries "database is locked" errors in its tick phases (BE-QUEUE-013). This is why
PostgreSQL is required in production (DEP-DB-002).

**Migrations on deploy.** There is no automatic migration and no startup check. The old web and
worker keep running on the old code while `migrate` runs, so a migration must not break the code
that is still running until the restart (see [install-upgrade.md](install-upgrade.md)).

**Restore.** Stop the worker; restore the database (empty database + `pg_restore`) and
`CLOUDGENE_HOME` files; run `migrate`; start the worker; restart the web. Jobs that were
`running` in the backup are failed as orphans by the worker's startup reconcile; `waiting` jobs
run again.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-DB-001 | `core/tests/test_settings_env.py::DatabaseSettingsTest::test_database_url_selects_engine_and_defaults_to_sqlite` (planned) | unit |
| DEP-DB-002 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-DB-003 | `core/tests/test_deploy.py::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit |
| DEP-DB-004 | `core/tests/test_settings_env.py::DatabaseSettingsTest::test_conn_max_age_from_env` (planned) | unit |
| DEP-DB-005 | `core/tests/test_settings_env.py::DatabaseSettingsTest::test_conn_health_checks_enabled` (planned) | unit |
| DEP-DB-006 | `jobs/tests/test_worker.py::WorkerTickConnectionTest::test_tick_closes_old_connections` (planned) | unit |
| DEP-DB-007 | `scripts/test.sh unit --postgres` (installs nothing extra; fails at import if the driver is missing) | unit |
| DEP-DB-010 | `core/tests/test_settings_env.py::DatabaseSettingsTest::test_sqlite_options_defaults` (planned) | unit |
| DEP-DB-011 | `core/tests/test_settings_env.py::DatabaseSettingsTest::test_postgres_has_no_sqlite_options` (planned) | unit |
| DEP-DB-012 | `e2e/tests/test_findings_jobs.py::test_a03_admin_workflow_list_does_not_write_on_every_read` (web + worker on one SQLite file) | e2e |
| DEP-DB-020 | `scripts/smoke_gunicorn.sh` (step "Migrating a throw-away DB") | smoke |
| DEP-DB-021 | `scripts/smoke_upgrade.sh` (planned; see DEP-INST-022) | smoke |
| DEP-DB-022 | `scripts/test.sh unit` (step "Migrations up to date") | unit |
| DEP-DB-023 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_unit_command_map` (planned) | config |
| DEP-DB-030 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| DEP-DB-031 | `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job`, `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest::test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once` (PostgreSQL only) | unit |
| DEP-DB-040 | `scripts/smoke_backup_restore.sh` (planned) | smoke |
| DEP-DB-042 | `scripts/smoke_backup_restore.sh` (planned, SQLite mode) | smoke |
| DEP-DB-043 | `jobs/tests/test_worker.py::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed` | unit |
| DEP-DB-044 | `core/tests/test_settings_env.py::SecretKeyRotationTest::test_sessions_invalid_after_key_change` (planned) | unit |
| DEP-DB-050 | `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job` (skips on SQLite) | unit |
| DEP-DB-051 | `scripts/test.sh unit --postgres` | unit |
| DEP-DB-052 | `e2e/tests/test_stack.py::test_postgres_stack_creates_and_drops_its_database` (planned; today exercised only by running the suite with `E2E_DATABASE_URL` set) | e2e |
| DEP-DB-060 | — host obligation. Manual: `sudo -u postgres psql -tAc "select rolsuper, rolcreaterole, rolcreatedb from pg_roles where rolname = '<role from DATABASE_URL>'"` prints `f\|f\|f` (`rolsuper` MUST be `f`). | — |
| DEP-DB-061 | — host obligation. Manual: as `cloudgene` with no password available (`sudo -u cloudgene env -u PGPASSWORD psql -w -d <db> -c 'select 1'`, then the same with `-h 127.0.0.1 -U <role>`), both connections MUST be refused. | — |

Planned tests are listed in [tests.md](tests.md) as gaps.

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-DB-020 | No mechanism runs `migrate` with the unit environment; without it `migrate` silently migrates `/opt/cloudgene/db.sqlite3` and leaves PostgreSQL unmigrated. Details: [DEP-API-005 gap](api-contract.md#known-gaps). | `cloudgene_django/settings.py:41`, `:155-160` | major |
| DEP-DB-002 | A missing `DATABASE_URL` in production falls back to SQLite silently; only `check --deploy` (run by hand) warns. | `cloudgene_django/settings.py:157`, `core/checks.py:113-125` | minor |
| DEP-DB-005 | `CONN_HEALTH_CHECKS` is not set; with `DB_CONN_MAX_AGE=60` one request per gunicorn worker fails after a PostgreSQL restart. | `cloudgene_django/settings.py:155-160` | minor |
| DEP-DB-030 | The single-worker lock is host-local; two hosts sharing one database each run a worker without error (BE-QUEUE-011). | `jobs/worker.py:acquire_lock` | minor |
| DEP-DB-040 | No backup or restore tooling or test exists; only user documentation describes it. | `scripts/` | minor |
| DEP-DB-053 | There is no CI configuration in the repository; PostgreSQL-only tests run only when someone runs `scripts/test.sh unit --postgres` by hand, and are skipped (reported as skips, not failures) in the default run. | `scripts/test.sh:50-57`, `jobs/tests/test_claim_concurrency.py:26-30` | minor |
| DEP-DB-010, DEP-DB-001, DEP-DB-004 | No test asserts the `DATABASES` settings (engine selection, SQLite options, `CONN_MAX_AGE`). | `cloudgene_django/settings.py:155-170` | minor |

## Open questions

1. How operator commands get the unit environment (wrapper or settings loading the env file): see [api-contract.md](api-contract.md#open-questions) question 1.
2. Should settings refuse to start (error, not warning) when `DEBUG` is off and `DATABASE_URL` is unset, instead of falling back to SQLite?
3. Should `CONN_HEALTH_CHECKS` be enabled whenever `DB_CONN_MAX_AGE > 0`?
4. Is SQLite with `DEBUG` off a supported configuration ("small single-user installs" per the check message), or development only? `core.W001` and `docs/DEPLOYMENT.md` say the former.
5. Should migrations follow an "expand then contract" rule (no column drop/rename in the same release that stops using it), so the running old code survives `migrate` during an upgrade? Nothing states this today.
