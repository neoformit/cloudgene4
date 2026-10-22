# Deployment overview

## Purpose

This file fixes the production shape of a Cloudgene installation: which processes run, how
requests reach them, where state lives, what the host must provide, and how a production host
differs from a developer checkout. Every other deployment file refines one box of this picture.
The target is one Linux host managed by systemd, with nginx terminating TLS in front of gunicorn,
one job worker process, PostgreSQL and a local `CLOUDGENE_HOME` directory. There is no Docker,
Celery, Redis or Node process in production.

## Scope

| Source | Covered here |
|--------|--------------|
| `deploy/systemd/*.service`, `deploy/systemd/cloudgene-cleanup.timer` | which processes exist, their users and paths (unit details: [process-management.md](process-management.md)) |
| `deploy/nginx.conf.example` | the edge of the topology (details: [reverse-proxy.md](reverse-proxy.md)) |
| `deploy/gunicorn.conf.py` | the web process (details: [web-server.md](web-server.md)) |
| `deploy/cloudgene.env.example` | the shared environment (details: [environment-config.md](environment-config.md)) |
| `requirements.txt`, `frontend/vite.config.js` | host software requirements |
| `cloudgene_django/settings.py` (DEBUG-dependent values) | dev vs prod differences |
| `jobs/worker.py` `acquire_lock` | single-host constraint |

Out of scope: application behaviour ([../backend/overview.md](../backend/overview.md)), the SPA
([../frontend/overview.md](../frontend/overview.md)), the user guide `docs/DEPLOYMENT.md`
(contradictions with it are listed under Open questions), containers and multi-host setups (not
supported).

## Dependencies

- [api-contract.md](api-contract.md) — ports, env vars, paths, signals, exit codes.
- [environment-config.md](environment-config.md) — variable semantics.
- [process-management.md](process-management.md), [web-server.md](web-server.md),
  [reverse-proxy.md](reverse-proxy.md), [database.md](database.md),
  [static-assets.md](static-assets.md), [cloudgene-home.md](cloudgene-home.md),
  [workflow-runtime.md](workflow-runtime.md), [security-hardening.md](security-hardening.md),
  [observability.md](observability.md), [install-upgrade.md](install-upgrade.md).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md) — worker lock, heartbeat,
  orphan recovery (BE-QUEUE-011, BE-QUEUE-012, BE-QUEUE-016).
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — `health` operation.
- Contract operation: `health`.

## Requirements

Topology

- **DEP-ARCH-001** A production installation MUST consist of exactly these long-running
  processes on one host: nginx, one gunicorn master with its workers (`cloudgene-web.service`),
  one `manage.py run_worker` process (`cloudgene-worker.service`), and PostgreSQL (local or
  reachable over the network). `cloudgene-cleanup.service` MUST run only as a oneshot started by
  `cloudgene-cleanup.timer`.
- **DEP-ARCH-002** All client traffic MUST enter through nginx. gunicorn MUST listen only on a
  loopback address or a local socket that clients cannot reach (see
  [DEP-WEB-002](web-server.md#process-and-binding)).
- **DEP-ARCH-003** The web process MUST NOT run workflows. Only the worker process starts
  Nextflow or command steps; a job submitted while the worker is down MUST stay `waiting` until
  a worker claims it.
- **DEP-ARCH-004** The web and worker processes MUST share the same database, the same
  `CLOUDGENE_HOME` and the same `SECRET_KEY`. Both systemd units MUST load the same
  `EnvironmentFile` (`/etc/cloudgene/cloudgene.env`).
- **DEP-ARCH-005** No Node.js process MAY run in production. Node MUST be needed only to build
  the SPA into `static/frontend/` at install or upgrade time.
- **DEP-ARCH-006** The application MUST boot without Celery, Channels or Redis installed.

Single-host constraint

- **DEP-ARCH-010** Exactly one worker MUST run against a given database. On one host this is
  enforced by the worker lock (BE-QUEUE-011); a second `run_worker` for the same
  `CLOUDGENE_HOME` MUST exit 1 and touch no job.
- **DEP-ARCH-011** Running the web or worker process on more than one host against the same
  database is NOT supported. Operators MUST NOT share one database between two hosts that each
  run `cloudgene-worker` (each worker would fail the other's jobs as orphans, BE-QUEUE-016).
- **DEP-ARCH-012** (withdrawn — see [DEP-HOME-005](cloudgene-home.md#requirements))

Platform

- **DEP-ARCH-020** The supported platform is a Linux host with systemd. The service user and
  group MUST be `cloudgene`; the checkout and virtualenv MUST be at `/opt/cloudgene` (venv at
  `/opt/cloudgene/venv`), the environment file at `/etc/cloudgene/cloudgene.env`, and
  `CLOUDGENE_HOME` at `/var/lib/cloudgene`. Other paths require editing the unit files and the
  env file together (DEP-API-002).
- **DEP-ARCH-021** The `cloudgene` user's home directory MUST be inside a path that the units
  can write (`/opt/cloudgene` by convention), because the units set `ProtectHome=true` and
  Nextflow writes `~/.nextflow`.
- **DEP-ARCH-022** The host MUST provide: Python 3 able to install `requirements.txt` (Django
  6.0, so Python ≥ 3.12); PostgreSQL with the `psycopg2` client library; nginx with TLS and
  HTTP/2; a Java runtime and the Nextflow launcher on the worker's `PATH` (or at the path in
  `settings.yaml` `nextflow.binary`, see [workflow-runtime.md](workflow-runtime.md)); and, at
  build time only, Node.js and npm for `frontend/`.

Dev vs prod

- **DEP-ARCH-030** A production process MUST run with `DEBUG` off. The differences between a
  development checkout and production MUST be only those listed in the dev/prod table under
  Interfaces, all driven by environment variables.
- **DEP-ARCH-031** `manage.py check --deploy` MUST report no issues with the production
  environment loaded ([security-hardening.md](security-hardening.md)).

## Interfaces

### Topology

```
browser ──HTTPS:443──▶ nginx ──HTTP 127.0.0.1:8000──▶ gunicorn (cloudgene-web)
   │     (HTTP:80 → 301)  │                              │  Django: /api/*, /django-admin/,
   │                      │                              │  /static/* (whitenoise), SPA index
   │                      │                              ▼
   │                      │                        PostgreSQL :5432 ◀──────────┐
   │                      │                              ▲                     │
   │                      │              CLOUDGENE_HOME (/var/lib/cloudgene)   │
   │                      │                 config/ pages/ apps/ jobs/ mail/   │
   │                      │                              ▲                     │
   │                      │                              │                     │
   │                      │         cloudgene-worker: manage.py run_worker ────┘
   │                      │              │ (flock config/worker.lock, heartbeat every tick)
   │                      │              └─▶ nextflow (Java) / command steps, one process group per job
   │                      │
cloudgene-cleanup.timer (daily) ─▶ manage.py cleanup_jobs; manage.py cleanup_logs
```

| Component | Unit / config | Runs as | Talks to |
|-----------|---------------|---------|----------|
| nginx | `deploy/nginx.conf.example` | nginx's own user | gunicorn over TCP loopback |
| web | `cloudgene-web.service` → `gunicorn -c deploy/gunicorn.conf.py cloudgene_django.wsgi:application` | `cloudgene` | DB, `CLOUDGENE_HOME` (read/write: settings, pages, uploads into job workspaces) |
| worker | `cloudgene-worker.service` → `manage.py run_worker` | `cloudgene` | DB, `CLOUDGENE_HOME`, Nextflow/Java child processes |
| cleanup | `cloudgene-cleanup.service` + `.timer` | `cloudgene` | DB, `CLOUDGENE_HOME/jobs` |
| database | PostgreSQL (`DATABASE_URL`) | postgres | — |

### Host paths (conventions)

| Path | Contents | Owner |
|------|----------|-------|
| `/opt/cloudgene` | git checkout, `venv/`, `static/frontend/` (SPA build), `staticfiles/` (collectstatic), `deploy/` | `cloudgene` |
| `/etc/cloudgene/cloudgene.env` | environment file (secrets) | root, mode `0600` |
| `/var/lib/cloudgene` | `CLOUDGENE_HOME` ([cloudgene-home.md](cloudgene-home.md)) | `cloudgene` |
| `/etc/systemd/system/cloudgene-*` | copies of `deploy/systemd/*` | root |
| `/etc/nginx/sites-available/cloudgene` | copy of `deploy/nginx.conf.example` | root |

Permissions per path: [api-contract.md](api-contract.md#filesystem-paths-and-permissions).

### Dev vs prod

| Aspect | Development (defaults, `DEBUG=1`) | Production (`cloudgene.env.example`) |
|--------|-----------------------------------|--------------------------------------|
| HTTP server | `manage.py runserver`; Vite dev server on :5173 proxies `/api` | gunicorn behind nginx |
| Database | SQLite `<repo>/db.sqlite3` (WAL, 20 s timeout) | PostgreSQL via `DATABASE_URL` |
| `CLOUDGENE_HOME` | `<repo>/home` (committed defaults) | `/var/lib/cloudgene` |
| Secret key | generated into `CLOUDGENE_HOME/config/secret_key` | `DJANGO_SECRET_KEY` (or the generated file on a single host) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | the public hostname |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:5173`, `http://127.0.0.1:5173` | `https://<host>` |
| TLS settings | all off | Secure cookies, SSL redirect, proxy SSL header, HSTS |
| Static files | whitenoise finders, autorefresh on | whitenoise (finders and `STATIC_ROOT`), autorefresh off |
| Mail fallback | file backend into `CLOUDGENE_HOME/mail` | as set in env; effective mail is `settings.yaml` |
| Logging | text | `LOG_FORMAT=json` to journald |
| `check --deploy` checks `core.W001`–`W006` | skipped (DEBUG) | active |
| Insecure MD5 hasher switch | allowed | refused (`core.E001`) |

## Behaviour

**Request path.** nginx redirects port 80 to HTTPS (except ACME challenges), terminates TLS,
and proxies every path to gunicorn with `Host`, `X-Forwarded-For`, `X-Real-IP` and
`X-Forwarded-Proto`. Django routes `/api/*` to the API (unknown paths → JSON 404),
`/django-admin/` to Django admin, `/static/*` to whitenoise, and everything else to the SPA
index (details in [api-contract.md](api-contract.md#static-and-spa-url-paths)).

**Job path.** The web process writes a `waiting` job row and its uploaded inputs into
`CLOUDGENE_HOME/jobs/<uuid>/`. The worker polls the database every tick (default 1 s), claims
jobs within the queue limits, and runs each step as a child process group. The web process
reads progress from the database and the workspace. The two processes never talk directly.

**Restart.** Restarting `cloudgene-worker` fails every running job (BE-QUEUE-014) and keeps
waiting jobs queued. Restarting `cloudgene-web` drops in-flight requests after gunicorn's
graceful timeout. Neither restart loses queued work.

**Single host.** The worker lock is a host-local `flock` on
`CLOUDGENE_HOME/config/worker.lock`. It does not protect a database shared by two hosts
(DEP-ARCH-011); nothing in the code detects that case.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-ARCH-001 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_and_exec_lines` (planned) | config |
| DEP-ARCH-002 | `core/tests/test_deploy_files.py::GunicornConfigTest::test_default_bind_is_loopback` (planned) | config |
| DEP-ARCH-003 | `core/tests/test_platform.py::SubmissionWithoutWorkerTest::test_submitted_job_waits_until_the_worker_claims_it` | unit |
| DEP-ARCH-004 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_and_worker_share_environment_file` (planned) | config |
| DEP-ARCH-005 | `scripts/smoke_gunicorn.sh` step "GET a hashed static asset" | smoke |
| DEP-ARCH-006 | `core/tests/test_platform.py::NoCeleryChannelsTest::test_django_boots_without_celery_channels_redis` | unit |
| DEP-ARCH-010 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| DEP-ARCH-011 | — host obligation; manual verification: `systemctl is-enabled cloudgene-worker` is `enabled` on exactly one host per database | — |
| DEP-ARCH-020 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_paths_and_user` (planned) | config |
| DEP-ARCH-021 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_paths_and_user` (planned) | config |
| DEP-ARCH-022 | — host obligation; manual verification at install: `python3 --version` ≥ 3.12, `nginx -V` lists `http_ssl_module` and `http_v2_module`, `sudo -u cloudgene java -version` and `nextflow -version` succeed | — |
| DEP-ARCH-030 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-ARCH-031 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-ARCH-011 | Nothing detects two workers on different hosts sharing one database; each fails the other's running jobs every tick. Already recorded as BE-QUEUE-011/016 gap. | `jobs/worker.py:617-624`, `jobs/worker.py:807-823` | minor |
| DEP-ARCH-022 | No file pins the Python or Node version (no `.python-version`, no `engines` in `frontend/package.json`); only the user docs name Python 3.12, Node 20+ and Java 17+. | `requirements.txt`, `frontend/package.json` | minor |
| DEP-ARCH-001, DEP-ARCH-004, DEP-ARCH-020 | No test reads the systemd units or nginx example; drift between them and this spec is not caught. | `deploy/systemd/*` | minor |
| DEP-ARCH-021 | The units set `ProtectHome=true` but nothing checks that the `cloudgene` user's home is outside `/home`; a home under `/home` makes Nextflow fail to write `~/.nextflow`. | `deploy/systemd/cloudgene-worker.service:27` | minor |

## Open questions

1. `docs/DEPLOYMENT.md` §4 says the worker "takes an exclusive DB lock"; the code takes a
   host-local `flock` on `CLOUDGENE_HOME/config/worker.lock` (`jobs/worker.py:807`). Docs or
   code: which is intended? This spec follows the code; the docs should be corrected. It matters
   for DEP-HOME-005 (filesystem choice) and multi-host setups. This is the single
   home of this question; process-management.md and cloudgene-home.md link here.
2. Running jobs surviving a worker restart (docs) versus being failed (code): see
   [install-upgrade.md](install-upgrade.md#open-questions) question 5.
3. Should multi-host support (shared database, several web hosts) ever be in scope? If not, the
   worker could refuse to start when the heartbeat row names a different live host.
