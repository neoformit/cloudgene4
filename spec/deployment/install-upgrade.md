# Install, upgrade and rollback

## Purpose

This file specifies the operator procedures that put Cloudgene on a host and keep it current:
the first install (service user, code, virtualenv, SPA build, environment file, database,
static files, first admin, first workflow, systemd units), the upgrade sequence and what
happens to running jobs during it, rollback, and how a deployment is verified. It is derived
from the files in `deploy/` and `scripts/` and the commands they call; `docs/DEPLOYMENT.md` is
only compared against them.

## Scope

Covered:

- The order of operator steps and the commands used in each.
- The state each step must leave behind, and how to verify it.
- `scripts/smoke_gunicorn.sh` as the pre-deploy check.

Out of scope:

- Unit file contents: [process-management.md](process-management.md).
- Env variables and the env file: [environment-config.md](environment-config.md).
- Database selection, migrations rules, backups: [database.md](database.md).
- SPA build output, `collectstatic`, whitenoise: [static-assets.md](static-assets.md).
- nginx and TLS: [reverse-proxy.md](reverse-proxy.md).
- `CLOUDGENE_HOME` layout and permissions: [cloudgene-home.md](cloudgene-home.md).
- Java/Nextflow installation: [workflow-runtime.md](workflow-runtime.md).
- `check --deploy` checks themselves: [security-hardening.md](security-hardening.md).
- Command behaviour (`create_admin`, `install_workflow`, …): [../backend/management-commands.md](../backend/management-commands.md).
- `/api/health` response: [../backend/server-pages-mail.md](../backend/server-pages-mail.md) (operationId `health`).

## Dependencies

- [process-management.md](process-management.md): unit names, DEP-PROC-023 (worker stop fails running jobs), DEP-PROC-040 (operator-run commands).
- [web-server.md](web-server.md): DEP-WEB-016 (reload does not load code).
- [api-contract.md](api-contract.md): DEP-API-005 (one-off commands run with the unit environment).
- [database.md](database.md): DEP-DB-020/021 (migrate with the unit environment, before restart), DEP-DB-040 (backup contents).
- [static-assets.md](static-assets.md): SPA build to `static/frontend/`, `collectstatic` to `staticfiles/`; DEP-STATIC-030, DEP-STATIC-031, DEP-STATIC-033 (assets during and after an upgrade).
- [cloudgene-home.md](cloudgene-home.md): DEP-HOME-007 (seeding `CLOUDGENE_HOME` at first install).
- [../backend/management-commands.md](../backend/management-commands.md): BE-CMD-010..013 (`create_admin`), BE-CMD-020..025 (`install_workflow`), BE-CMD-030..032 (`sync_workflows`).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md): BE-QUEUE-014 (shutdown), orphan recovery.
- [test-harness.md](test-harness.md): `scripts/smoke_gunicorn.sh`.

## Requirements

### Layout assumed by `deploy/`

- **DEP-INST-001** The install MUST use the paths that the files in `deploy/` hard-code: code checkout at `/opt/cloudgene`, virtualenv at `/opt/cloudgene/venv`, env file at `/etc/cloudgene/cloudgene.env`, `CLOUDGENE_HOME=/var/lib/cloudgene`, a `cloudgene` system user and group. A different layout MUST edit every unit file to match.
- **DEP-INST-002** Host prerequisites MUST be present before install: Python ≥ 3.12, Node.js with npm (build time only), PostgreSQL, nginx, and Java plus Nextflow for workflows ([workflow-runtime.md](workflow-runtime.md)).

### First install

- **DEP-INST-003** The install MUST create the `cloudgene` system user and group, with a home directory that is writable under the units' sandbox (inside `ReadWritePaths`, not under `/home`), because Nextflow writes `$HOME/.nextflow` (DEP-PROC-006).
- **DEP-INST-004** The code, virtualenv, SPA build and `staticfiles/` MUST be created as the `cloudgene` user (or chowned to it), and Python dependencies MUST be installed with `venv/bin/pip install -r requirements.txt`.
- **DEP-INST-005** The SPA MUST be built with `npm ci && npm run build` in `frontend/` before `collectstatic`. No Node process runs in production.
- **DEP-INST-006** `/var/lib/cloudgene` MUST exist and be owned by `cloudgene:cloudgene` before any service or management command runs. `/etc/cloudgene/cloudgene.env` MUST be created from `deploy/cloudgene.env.example`, filled in, owned by root and mode `600`.
- **DEP-INST-007** The PostgreSQL role and database named in `DATABASE_URL` MUST exist, owned by that role, before `migrate`.
- **DEP-INST-008** The operator MUST then seed `CLOUDGENE_HOME` from the repository's `home/` as specified by [DEP-HOME-007](cloudgene-home.md#layout-defaults-and-first-install) (file modes: [DEP-HOME-008](cloudgene-home.md#layout-defaults-and-first-install)), and then run, as `cloudgene` and with the environment of `/etc/cloudgene/cloudgene.env` loaded, in this order: `manage.py check --deploy`, `manage.py migrate --noinput`, `manage.py collectstatic --noinput`, `manage.py create_admin --username … --email …` (password via `--password`, `$CLOUDGENE_ADMIN_PASSWORD`, or generated), and `manage.py install_workflow PATH --copy …` for each workflow. Every step MUST exit 0 before the next runs. A workflow app outside `/opt/cloudgene` and `/var/lib/cloudgene` MUST be installed with `--copy` (DEP-PROC-007).
- **DEP-INST-009** The unit files MUST then be copied to `/etc/systemd/system/`, followed by `systemctl daemon-reload` and `systemctl enable --now cloudgene-web cloudgene-worker cloudgene-cleanup.timer`. `cloudgene-cleanup.service` MUST NOT be enabled directly.
- **DEP-INST-010** nginx MUST be configured from `deploy/nginx.conf.example` and reloaded only after `nginx -t` succeeds ([reverse-proxy.md](reverse-proxy.md)).
- **DEP-INST-011** `create_admin` prints a generated password on stdout. When it is run so that output is logged (CI, journald), the password SHOULD be given explicitly instead.

### Upgrade

- **DEP-INST-020** Before an upgrade, the operator SHOULD take a backup as in DEP-DB-040 and SHOULD run `scripts/smoke_gunicorn.sh` on the new revision. What the script does and must not touch: [test-harness.md](test-harness.md#requirements) DEP-HARN-010..017.
- **DEP-INST-021** An upgrade MUST run, in order: update the code (`git pull` or checkout of a tag); `venv/bin/pip install -r requirements.txt`; `npm ci && npm run build` in `frontend/`; `manage.py migrate --noinput`; `manage.py collectstatic --noinput` (without `--clear`, [DEP-STATIC-033](static-assets.md#releases-and-open-tabs)); then `systemctl restart cloudgene-worker cloudgene-web`. All `manage.py` steps MUST use the unit environment ([DEP-API-005](api-contract.md#environment)).
- **DEP-INST-022** `migrate` MUST complete before either service is restarted on the new code (DEP-DB-021). If `migrate` fails, the services MUST NOT be restarted.
- **DEP-INST-023** The web MUST be restarted, not reloaded, to pick up new code ([DEP-WEB-016](web-server.md#timeouts-and-lifecycle)). The worker MUST be restarted on every upgrade that changes Python code.
- **DEP-INST-024** Restarting the worker MUST be treated as stopping every running job: each running job ends `failed` with `The worker was shut down while this job was running; the job was stopped.` Waiting jobs MUST stay `waiting` and run on the new worker. An operator who must not lose running jobs SHOULD pause the queue (`queue.paused` in Admin → Settings), wait until no job is running, then upgrade and unpause.
- **DEP-INST-025** (withdrawn — see [DEP-STATIC-031](static-assets.md#releases-and-open-tabs))
- **DEP-INST-026** (withdrawn — see [DEP-STATIC-030](static-assets.md#releases-and-open-tabs) and [DEP-STATIC-033](static-assets.md#releases-and-open-tabs))
- **DEP-INST-027** If the new revision adds or changes workflow apps under `settings.yaml` control, the operator MAY run `manage.py sync_workflows`; it exits 0 even when apps are invalid, so its output MUST be read.

### Rollback

- **DEP-INST-030** A rollback to revision R MUST: stop the worker; if the release applied migrations, either reverse them with `manage.py migrate <app> <migration>` while the newer code is still checked out, or restore the pre-upgrade database backup; check out R; reinstall its requirements; rebuild the SPA; `collectstatic`; restart worker and web.
- **DEP-INST-031** A rollback MUST NOT run code R against a schema with migrations R does not know about. (planned: there is no check that enforces it)

### Verification

- **DEP-INST-040** After install or upgrade, `manage.py check --deploy` run with the production environment MUST report no issues (exit 0, "System check identified no issues").
- **DEP-INST-041** After install or upgrade, `GET /api/health` through nginx MUST return 200 with `status` `"ok"` once the worker's first heartbeat is written (within about 30 s); `"degraded"` means the worker is down or `settings.yaml` is invalid.
- **DEP-INST-042** After install or upgrade, `systemctl is-active cloudgene-web cloudgene-worker` MUST report `active` for both, and `systemctl list-timers cloudgene-cleanup.timer` MUST show a next run.
- **DEP-INST-043** (withdrawn — see [DEP-HARN-010, DEP-HARN-011, DEP-HARN-012, DEP-HARN-013, DEP-HARN-014, DEP-HARN-017](test-harness.md#requirements))

## Interfaces

### First install (reference sequence)

```bash
# as root
useradd --system --user-group --home-dir /opt/cloudgene --no-create-home cloudgene
install -d -o cloudgene -g cloudgene /opt/cloudgene /var/lib/cloudgene
install -d -m 755 /etc/cloudgene
sudo -u cloudgene git clone <repo-url> /opt/cloudgene
sudo -u cloudgene python3.12 -m venv /opt/cloudgene/venv
sudo -u cloudgene /opt/cloudgene/venv/bin/pip install -r /opt/cloudgene/requirements.txt
sudo -u cloudgene sh -c 'cd /opt/cloudgene/frontend && npm ci && npm run build'
install -m 600 -o root -g root /opt/cloudgene/deploy/cloudgene.env.example /etc/cloudgene/cloudgene.env
# edit /etc/cloudgene/cloudgene.env; create the PostgreSQL role and database

# as cloudgene, with /etc/cloudgene/cloudgene.env loaded (see Known gaps: no wrapper exists)
manage.py check --deploy
manage.py migrate --noinput
manage.py collectstatic --noinput
manage.py create_admin --username admin --email admin@example.org
manage.py install_workflow /path/to/app --copy [--public | --groups g1,g2]

# as root
cp deploy/systemd/cloudgene-*.service deploy/systemd/cloudgene-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cloudgene-web cloudgene-worker cloudgene-cleanup.timer
```

### Upgrade (reference sequence)

```bash
sudo -u cloudgene git -C /opt/cloudgene pull          # or checkout a tag
sudo -u cloudgene /opt/cloudgene/venv/bin/pip install -r /opt/cloudgene/requirements.txt
sudo -u cloudgene sh -c 'cd /opt/cloudgene/frontend && npm ci && npm run build'
# with the unit environment:
manage.py migrate --noinput
manage.py collectstatic --noinput
systemctl restart cloudgene-worker cloudgene-web
```

### Step table

| Step | Command | Run as | Needs env file | Exit on failure |
|------|---------|--------|----------------|-----------------|
| Python deps | `venv/bin/pip install -r requirements.txt` | cloudgene | no | non-zero |
| SPA build | `npm ci && npm run build` (in `frontend/`) | cloudgene | no | non-zero |
| Deploy checks | `manage.py check --deploy` | cloudgene | yes | 1 on errors; warnings print but exit 0 |
| Migrate | `manage.py migrate --noinput` | cloudgene | yes | 1 |
| Static | `manage.py collectstatic --noinput` | cloudgene | yes | 1 |
| Admin | `manage.py create_admin …` | cloudgene | yes | 1 |
| Workflow | `manage.py install_workflow PATH --copy …` | cloudgene | yes | 1 (BE-CMD-024) |
| Units | `systemctl enable --now …` / `restart …` | root | — | non-zero |
| Pre-deploy smoke | `scripts/smoke_gunicorn.sh [--skip-build]` | any user with the venv | no (own throw-away env) | 1 |

### Verification commands

```bash
manage.py check --deploy                    # with the production env
curl -fsS https://<host>/api/health         # status "ok"
systemctl is-active cloudgene-web cloudgene-worker
systemctl list-timers cloudgene-cleanup.timer
```

## Behaviour

**Order of first install.** The env file must exist before any `manage.py` command, because
settings read `DATABASE_URL`, `CLOUDGENE_HOME` and the secret key at import. If
`DJANGO_SECRET_KEY` is unset, the first command creates `CLOUDGENE_HOME/config/secret_key`; it
must be created as `cloudgene` so the services can read it. `CLOUDGENE_HOME` subdirectories are
created lazily by the code that writes them; `settings.yaml` is created on first write (a missing
file loads as defaults, BE-CONF-002). Seeding from the repository's `home/` is
[DEP-HOME-007](cloudgene-home.md#layout-defaults-and-first-install), the first step of DEP-INST-008;
no tooling automates it (gap owned by cloudgene-home.md).

**Upgrade window.** While `pip install`, `npm run build`, `migrate` and `collectstatic` run, the
old web and worker keep serving and running jobs on the old code. Two hazards follow:

1. `npm run build` rewrites the served SPA tree under the running web: see
   [static-assets.md](static-assets.md#behaviour) "Deploy window today" (DEP-STATIC-031) and
   "Redeploy with tabs open" (DEP-STATIC-030).
2. `migrate` changes the schema under the running old code.

**Running jobs.** `systemctl restart cloudgene-worker` stops the worker (SIGTERM). Every running
job is stopped and marked `failed`; waiting jobs stay queued. A queue pause before the upgrade
avoids losing work. Order of restart (worker first, then web) does not matter for correctness:
the web only enqueues jobs, and the worker claims them on its next tick.

**Rollback.** There is no tooling. The database cannot be rolled back after the new code has
been removed unless the backup is restored, because reversing a migration needs the migration
file that the newer code ships.

**Verification.** `check --deploy` validates configuration only. `/api/health` validates the
database, the worker heartbeat and `settings.yaml`. Neither exercises a workflow run; running a
small job from the installed workflow is the end-to-end check.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-INST-001 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_share_environment_file_and_workdir` (planned) | config |
| DEP-INST-002 | `scripts/smoke_install.sh` (planned) | smoke |
| DEP-INST-003 | `scripts/smoke_install.sh` (planned) | smoke |
| DEP-INST-004 | `scripts/smoke_install.sh` (planned) | smoke |
| DEP-INST-005 | `scripts/smoke_gunicorn.sh` (step "Building the SPA") | smoke |
| DEP-INST-006 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` (env file content only) | config |
| DEP-INST-007 | `scripts/smoke_install.sh` (planned) | smoke |
| DEP-INST-008 | `scripts/smoke_gunicorn.sh` (migrate, collectstatic, check --deploy); `core/tests/test_api.py::CreateAdminCommandTest::test_create_and_update_idempotent`; `workflows/test_registry.py::CommandsTest::test_install_workflow_command` | smoke, unit |
| DEP-INST-009 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_install_targets` (planned) | config |
| DEP-INST-010 | `core/tests/test_deploy_files.py::NginxExampleTest::test_nginx_t_accepts_example` (planned) | config |
| DEP-INST-021 | `scripts/smoke_upgrade.sh` (planned) | smoke |
| DEP-INST-022 | `scripts/smoke_upgrade.sh` (planned) | smoke |
| DEP-INST-023 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_reload_sends_hup` (planned) | config |
| DEP-INST-024 | `jobs/tests/test_worker.py::ShutdownTest::test_shutdown_stops_running_jobs` | unit |
| DEP-INST-027 | `workflows/test_registry.py::CommandsTest::test_sync_workflows_command` | unit |
| DEP-INST-030 | `scripts/smoke_upgrade.sh` (planned, rollback leg) | smoke |
| DEP-INST-031 | `scripts/smoke_upgrade.sh` (planned, rollback leg) | smoke |
| DEP-INST-040 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-INST-041 | `core/tests/test_api.py::HealthTest::test_health_with_fresh_and_stale_heartbeat`; `scripts/smoke_gunicorn.sh` (step "GET /api/health") | unit, smoke |
| DEP-INST-042 | `scripts/smoke_install.sh` (planned) | smoke |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-INST-008, DEP-INST-021 | No mechanism runs `manage.py` with the unit environment, so the documented commands migrate SQLite and create the admin in the wrong database. Details: [DEP-API-005 gap](api-contract.md#known-gaps). | `cloudgene_django/settings.py:41,64,155-160` | major |
| DEP-INST-024 | Every upgrade fails all running jobs; there is no drain or "restart when idle" mode. Pausing the queue first is possible but not part of any procedure. | `jobs/worker.py:798-801`, `:372-386` | minor |
| DEP-INST-031 | Nothing stops older code starting against a newer schema; there is no `migrate --check` at start and no rollback procedure or tooling. | `deploy/systemd/*.service` | minor |
| DEP-INST-002, DEP-INST-003, DEP-INST-004, DEP-INST-007, DEP-INST-042 | No automated install test; only `scripts/smoke_gunicorn.sh` (no systemd, no PostgreSQL, no nginx, no worker). | `scripts/` | minor |
| DEP-INST-011 | `create_admin` prints a generated password on stdout (BE-CMD-012). | `core/management/commands/create_admin.py:54-55` | minor |

## Open questions

1. `docs/DEPLOYMENT.md` §1 runs `useradd --system --home /opt/cloudgene --create-home cloudgene` and then `git clone … /opt/cloudgene`. `--create-home` creates the directory (with skeleton files on most distros), so the clone fails on a non-empty target. It also runs `python3.12 -m venv venv` and `npm ci` as the invoking user, not `cloudgene`. Which sequence is intended? This file uses `--no-create-home` and runs every build step as `cloudgene`.
2. How `manage.py` gets the unit environment: see [api-contract.md](api-contract.md#open-questions) question 1.
3. Production static path (`collectstatic` versus whitenoise finders): see [static-assets.md](static-assets.md#open-questions) question 1.
4. `ensure_home()` and seeding `CLOUDGENE_HOME`: see [cloudgene-home.md](cloudgene-home.md#open-questions) question 1.
5. `docs/DEPLOYMENT.md` §5 says there is "no special job-draining step" and the worker "waits for [Nextflow] to exit" (implying running jobs survive a restart); running jobs are in fact stopped and marked `failed` (DEP-INST-024, BE-QUEUE-014). The docs should say so. Should the upgrade procedure require pausing the queue, or should the worker gain a drain mode? This is the single home of this question; overview.md and process-management.md link here.
6. (Answered elsewhere) The build strategy that keeps the running site consistent is the release switch of [DEP-STATIC-031](static-assets.md#releases-and-open-tabs).
7. `docs/DEPLOYMENT.md` §5 restarts `cloudgene-web cloudgene-worker` together; this file names the worker first only for readability. Is any order required?
