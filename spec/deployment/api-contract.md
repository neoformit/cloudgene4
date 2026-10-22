# Deployment API contract

## Purpose

This file is the operational contract between a deployment (systemd units, nginx, gunicorn
config, environment file, monitoring) and the application. It lists everything one side relies on
the other to provide: the environment variables the code reads, the sockets that are bound and
targeted, the proxy headers the application trusts, the health endpoint and how monitoring uses
it, the URL paths for static files and the SPA, the filesystem paths and their permissions, the
signals each process handles, and the exit codes systemd sees. It is the deployment counterpart
of [../backend/api-contract.md](../backend/api-contract.md): other deployment files link here
instead of restating these facts.

## Scope

Covered:

- Every `os.environ` read in application code (`cloudgene_django/settings.py`,
  `core/middleware.py`, `core/checks.py`, `core/config.py`,
  `core/management/commands/create_admin.py`, `jobs/runner.py`, `manage.py`,
  `cloudgene_django/wsgi.py`) and in `deploy/gunicorn.conf.py`.
- Sockets in `deploy/gunicorn.conf.py`, `deploy/nginx.conf.example`,
  `deploy/cloudgene.env.example`.
- Proxy-related settings: `SECURE_PROXY_SSL_HEADER` (`settings.py:246`), gunicorn
  `forwarded_allow_ips`.
- URL routing in `cloudgene_django/urls.py` as seen from the proxy.
- Paths in `deploy/systemd/*` and `settings.py`.
- Signal handling in `jobs/management/commands/run_worker.py` and gunicorn (as configured).

Out of scope: the meaning and parsing of each variable ([environment-config.md](environment-config.md));
the HTTP API shapes (`schema.yaml`, [../backend/api-contract.md](../backend/api-contract.md));
the `Health` body ([../backend/server-pages-mail.md](../backend/server-pages-mail.md)); command
arguments ([../backend/management-commands.md](../backend/management-commands.md)); test-harness
variables (`E2E_*`, `BASE`, `SLOW_SECONDS`, `PYTHON`, `TEST_DATABASE_URL`, …) —
[test-harness.md](test-harness.md).

## Dependencies

- [environment-config.md](environment-config.md) — semantics of each variable in the table below.
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — `health` operation
  (BE-SRV-030 to BE-SRV-035, health state table).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md) — BE-QUEUE-011 (lock),
  BE-QUEUE-012 (heartbeat), BE-QUEUE-014 (graceful shutdown).
- [../backend/management-commands.md](../backend/management-commands.md) — BE-CMD-001 (exit
  status), BE-CMD-041, BE-CMD-042.
- [../backend/overview.md](../backend/overview.md) — URL routing order.
- Contract operation: `health`.

## Requirements

### Change rule

- **DEP-API-001** This file and the files in `deploy/` MUST change together. A change set that
  adds, removes or renames an environment variable, or changes a default, port, path, trusted
  header, signal behaviour or exit code, MUST in the same change set update: the code →
  `deploy/cloudgene.env.example` (and the systemd units, `gunicorn.conf.py` or
  `nginx.conf.example` when affected) → this file → [environment-config.md](environment-config.md).
- **DEP-API-002** Every value that appears in more than one `deploy/` file (the gunicorn bind
  address and nginx `proxy_pass`, `/opt/cloudgene`, `/var/lib/cloudgene`,
  `/etc/cloudgene/cloudgene.env`, the `cloudgene` user, upload size and timeouts) MUST have the
  same value in all of them.

### Environment

- **DEP-API-003** The application MUST read configuration from the process environment only
  through the variables in the [environment variable table](#environment-variables). Code that
  reads a new variable MUST add it to that table and to `deploy/cloudgene.env.example`.
- **DEP-API-004** Every variable marked "prod: yes" in the table MUST be set in
  `/etc/cloudgene/cloudgene.env`; `manage.py check --deploy` MUST warn when any of
  `DJANGO_SECRET_KEY` (weak), `DATABASE_URL` (SQLite), `ALLOWED_HOSTS` (`*`),
  `DJANGO_SECURE_COOKIES`, `DJANGO_SECURE_SSL_REDIRECT` or `DJANGO_HSTS_SECONDS` is missing or
  unsafe with `DEBUG` off ([security-hardening.md](security-hardening.md)).
- **DEP-API-005** Every process that touches production data — the units and every one-off
  `manage.py` command (`migrate`, `collectstatic`, `create_admin`, `install_workflow`,
  `check --deploy`) — MUST run with the variables of `/etc/cloudgene/cloudgene.env` loaded.
  (planned: a documented or scripted way to do this as the `cloudgene` user)
- **DEP-API-006** Variables marked "never in prod" MUST NOT be set in
  `/etc/cloudgene/cloudgene.env`. If `INSECURE_FAST_PASSWORD_HASHING=1` is set with `DEBUG` off
  and `CLOUDGENE_E2E` unset, every `manage.py` command MUST fail with check `core.E001` (exit 1)
  and the MD5 hasher MUST NOT be used.

### Sockets

- **DEP-API-010** (withdrawn — see [DEP-WEB-002](web-server.md#process-and-binding), which owns the
  gunicorn bind rule; the address is listed in the [Sockets](#sockets-1) table)
- **DEP-API-011** nginx MUST `proxy_pass` to the same address gunicorn binds. nginx MUST listen
  on 80 (redirect only, plus `/.well-known/acme-challenge/`) and 443 (TLS).
- **DEP-API-012** The worker and the cleanup service MUST NOT listen on any socket.

### Proxy headers

- **DEP-API-020** nginx MUST pass the client's `Host` header unchanged (`proxy_set_header Host
  $host`). The application MUST validate it against `ALLOWED_HOSTS` and MUST answer 400 for a
  host not in the list. The application MUST NOT read `X-Forwarded-Host`.
- **DEP-API-021** When `DJANGO_BEHIND_TLS_PROXY` is true, Django MUST treat a request as HTTPS
  exactly when `X-Forwarded-Proto: https` is present (`SECURE_PROXY_SSL_HEADER`). nginx MUST set
  `X-Forwarded-Proto $scheme` on every proxied request, overwriting any client value.
- **DEP-API-022** gunicorn MUST trust forwarded headers only from `GUNICORN_FORWARDED_ALLOW_IPS`
  (default `127.0.0.1`).
- **DEP-API-023** The application MUST NOT use `X-Forwarded-For` or `X-Real-IP` for any
  decision, with one exception: the client address used to throttle the anonymous auth endpoints
  MUST be taken from `X-Forwarded-For` as specified in
  [BE-AUTH-027](../backend/authentication.md#requirements) (planned). Today client IP addresses
  are available only in nginx's access log.

### Health

- **DEP-API-030** `GET /api/health/` (`health`, also reachable as `/api/health`) MUST be served
  through nginx without authentication. Status codes as seen by a probe:

  | Condition | HTTP | Body `status` |
  |-----------|------|---------------|
  | DB reachable, worker heartbeat fresh, config valid | 200 | `ok` |
  | DB reachable, worker heartbeat stale (> 30 s) or `settings.yaml` invalid | 200 | `degraded` |
  | DB unreachable | 503 | `error` |
  | gunicorn down or not accepting | 502 (from nginx) | — (nginx page) |
  | gunicorn slower than `proxy_read_timeout` | 504 (from nginx) | — |
  | `Host` not in `ALLOWED_HOSTS` | 400 | — (HTML) |
  | HTTP request to gunicorn without `X-Forwarded-Proto: https` while `DJANGO_SECURE_SSL_REDIRECT=1` | 301 | — |

- **DEP-API-031** A load balancer or liveness probe MUST use the HTTP status only: 200 = web
  process healthy; anything else = unhealthy. It MUST NOT treat `degraded` as down, because a
  stopped worker does not stop the web process from serving.
- **DEP-API-032** Monitoring MUST alert when the body's `status` is not `ok` for longer than one
  probe interval (recommended: probe every 30–60 s, alert after 2 consecutive failures). A
  `degraded` result with `worker.ok=false` means `cloudgene-worker` is down or stuck; with
  `config.ok=false` it means `settings.yaml` has invalid keys (listed in `config.errors`).
- **DEP-API-033** Probes MUST go through nginx at the public host name over HTTPS
  (`curl -fsS https://<host>/api/health/`). A probe that talks to gunicorn directly MUST send a
  `Host` in `ALLOWED_HOSTS` and `X-Forwarded-Proto: https`, or it gets 400 or 301
  (DEP-API-030).

### Static and SPA paths

- **DEP-API-040** The application MUST serve the paths in the
  [URL path table](#static-and-spa-url-paths) itself (whitenoise for `/static/`), so a plain
  `location / { proxy_pass … }` in nginx is sufficient. nginx MAY serve `/static/` directly from
  `/opt/cloudgene/staticfiles/` after `collectstatic`.
- **DEP-API-041** Every path that is not under `/api/`, `/static/` or `/django-admin/` MUST
  return the SPA `index.html` with `Cache-Control: no-cache` and a `csrftoken` cookie, or 503
  with a plain HTML "frontend has not been built" page if `static/frontend/index.html` is
  missing. Unknown `/api/` paths MUST return the JSON 404 envelope, never the SPA.

### Filesystem

- **DEP-API-050** The paths in the [filesystem table](#filesystem-paths-and-permissions) MUST
  exist with at least the listed access for the listed user before the units start. The web and
  worker processes MUST be able to create files under `CLOUDGENE_HOME`; if they cannot, start-up
  MUST fail (non-zero exit) rather than run without a secret key.
- **DEP-API-051** `/etc/cloudgene/cloudgene.env` MUST be mode `0600` and MUST NOT be readable by
  the `cloudgene` user or any other non-root user, because it holds `DJANGO_SECRET_KEY` and the
  database password.
- **DEP-API-052** (withdrawn — see [DEP-ENV-030](environment-config.md#secret-key); the
  [filesystem table](#filesystem-paths-and-permissions) keeps the path as an entry)
- **DEP-API-053** Any directory the worker writes outside `/opt/cloudgene` and
  `/var/lib/cloudgene` (for example a `nextflow.work_dir` set elsewhere) MUST be added to
  `ReadWritePaths=` of `cloudgene-worker.service`; otherwise jobs using it fail.

### Signals and exit codes

- **DEP-API-060** gunicorn's master MUST handle `HUP` (re-read `gunicorn.conf.py`, replace
  workers gracefully), `TERM` (graceful stop within `GUNICORN_GRACEFUL_TIMEOUT`) and `INT`/`QUIT`
  (immediate stop), as in the [signal table](#signals). `systemctl reload cloudgene-web` MUST send
  `HUP`.
- **DEP-API-061** The worker MUST handle `TERM` and `INT` as a graceful stop (BE-QUEUE-014) and
  exit 0 within `TimeoutStopSec` of `cloudgene-worker.service` (120 s) for any number of running
  jobs up to `server.max_running_jobs`. The worker has no reload; it MUST NOT be sent `HUP`.
- **DEP-API-062** Commands started by systemd MUST use the exit codes in the
  [exit code table](#exit-codes). Every non-zero exit MUST write a one-line reason to stderr
  (journald) (BE-CMD-001).
- **DEP-API-063** `manage.py check --deploy` exits 0 when it finds only warnings. A deploy step
  or CI job that gates on it MUST either run it with `--fail-level WARNING` or check that its
  output says `System check identified no issues`.

## Interfaces

### Environment variables

"prod" column: **yes** = must be set in `/etc/cloudgene/cloudgene.env`; **opt** = optional;
**never** = must not be set in production. Semantics, parsing and failure behaviour:
[environment-config.md](environment-config.md).

| Name | prod | Default | Consumer |
|------|------|---------|----------|
| `DEBUG` | yes (`False`) | off | `settings.py:61` |
| `DJANGO_SECRET_KEY` | yes | read/generate `CLOUDGENE_HOME/config/secret_key` | `settings.py:67` |
| `ALLOWED_HOSTS` | yes | `localhost,127.0.0.1,[::1]` | `settings.py:91` |
| `CSRF_TRUSTED_ORIGINS` | yes | DEBUG: `http://localhost:5173,http://127.0.0.1:5173`; else empty | `settings.py:93` |
| `DATABASE_URL` | yes | `sqlite:///<repo>/db.sqlite3` | `settings.py:155` (dj-database-url) |
| `DB_CONN_MAX_AGE` | opt | `0` (example: `60`) | `settings.py:158` |
| `CLOUDGENE_HOME` | yes | `<repo>/home` | `settings.py:64`; fallback in `core/config.py:290` |
| `LOG_LEVEL` | opt | `INFO` | `settings.py:313` |
| `LOG_FORMAT` | opt | `standard` (example: `json`) | `settings.py:316` |
| `DJANGO_SECURE_COOKIES` | yes (`1`) | off | `settings.py:235` |
| `DJANGO_SECURE_SSL_REDIRECT` | yes (`1`) | off | `settings.py:236` |
| `DJANGO_BEHIND_TLS_PROXY` | yes (`1`) | off | `settings.py:246` |
| `DJANGO_HSTS_SECONDS` | yes | `0` | `settings.py:237` |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | opt | on when `DJANGO_HSTS_SECONDS` > 0 | `settings.py:241` |
| `DJANGO_HSTS_PRELOAD` | opt | off | `settings.py:245` |
| `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES` | opt | `10000` | `settings.py:301` |
| `API_JSON_BODY_MAX_MB` | opt | `10` | `core/middleware.py:15` |
| `EMAIL_BACKEND` | opt | `django.core.mail.backends.filebased.EmailBackend` | `settings.py:306` |
| `DEFAULT_FROM_EMAIL` | opt | `noreply@localhost` | `settings.py:308` |
| `CLOUDGENE_ADMIN_PASSWORD` | opt (one-off) | none (password generated) | `core/management/commands/create_admin.py:33` |
| `GUNICORN_BIND` | opt | `127.0.0.1:8000` | `deploy/gunicorn.conf.py:22` |
| `GUNICORN_WORKERS` | opt | `min(2 × CPUs + 1, 8)` | `deploy/gunicorn.conf.py:29` |
| `GUNICORN_THREADS` | opt | `1` | `deploy/gunicorn.conf.py:30` |
| `GUNICORN_WORKER_CLASS` | opt | `sync` | `deploy/gunicorn.conf.py:31` |
| `GUNICORN_TIMEOUT` | opt | `300` | `deploy/gunicorn.conf.py:37` |
| `GUNICORN_GRACEFUL_TIMEOUT` | opt | `30` | `deploy/gunicorn.conf.py:38` |
| `GUNICORN_KEEPALIVE` | opt | `5` | `deploy/gunicorn.conf.py:39` |
| `GUNICORN_FORWARDED_ALLOW_IPS` | opt | `127.0.0.1` | `deploy/gunicorn.conf.py:43` |
| `GUNICORN_ACCESS_LOG` | opt | `-` (stdout) | `deploy/gunicorn.conf.py:45` |
| `GUNICORN_ERROR_LOG` | opt | `-` (stderr) | `deploy/gunicorn.conf.py:46` |
| `GUNICORN_LOG_LEVEL` | opt | `info` | `deploy/gunicorn.conf.py:47` |
| `GUNICORN_MAX_REQUESTS` | opt | `10000` | `deploy/gunicorn.conf.py:51` |
| `GUNICORN_MAX_REQUESTS_JITTER` | opt | `500` | `deploy/gunicorn.conf.py:52` |
| `GUNICORN_PRELOAD_APP` | opt | `1` | `deploy/gunicorn.conf.py:54` |
| `DJANGO_SETTINGS_MODULE` | opt | `cloudgene_django.settings` (set by `manage.py`, `wsgi.py`) | Django |
| `INSECURE_FAST_PASSWORD_HASHING` | never | unset | `settings.py:188`, `core/checks.py:39` |
| `CLOUDGENE_E2E` | never | unset | `settings.py:189`, `core/checks.py:41` |

Inherited by workflow processes: the worker passes its whole environment (including `PATH`,
`HOME`, `JAVA_HOME`, `NXF_*` and every variable above) to Nextflow and command steps, then
overlays `config/nextflow.env`, the app's `nextflow.env` and the `CLOUDGENE_*` job variables
(`jobs/runner.py:117`; [workflow-runtime.md](workflow-runtime.md), BE-RUN-019 gap).

### Sockets

| Listener | Address | Configured in | Target of |
|----------|---------|---------------|-----------|
| nginx HTTP | `:80` | `nginx.conf.example:9` | clients (301 to HTTPS; ACME from `/var/www/html`) |
| nginx HTTPS | `:443` (TLS 1.2/1.3, HTTP/2) | `nginx.conf.example:17` | clients |
| gunicorn | `GUNICORN_BIND`, default `127.0.0.1:8000` | `gunicorn.conf.py:22` | nginx `proxy_pass http://127.0.0.1:8000` (`nginx.conf.example:44`) |
| PostgreSQL | from `DATABASE_URL`, example `127.0.0.1:5432` | `cloudgene.env.example:22` | web, worker, cleanup |
| dev only: runserver | `127.0.0.1:8000` | `manage.py runserver` | Vite dev proxy `/api` → `http://localhost:8000` |
| dev only: Vite | `:5173` | `frontend/vite.config.js` | developer browser |

A Unix socket (`GUNICORN_BIND=unix:/path`) works with gunicorn but needs a writable directory
under `ProtectSystem=strict` (for example `RuntimeDirectory=`) and a matching nginx
`proxy_pass http://unix:/path`; the shipped files do not do this.

### Trusted headers

| Header | Set by nginx | Trusted by | Effect |
|--------|--------------|------------|--------|
| `Host` | `$host` | Django (`ALLOWED_HOSTS`) | host validation; host part of `build_absolute_uri` (e-mail links when `server.url` is empty) |
| `X-Forwarded-Proto` | `$scheme` | Django when `DJANGO_BEHIND_TLS_PROXY=1` (any peer); gunicorn from `GUNICORN_FORWARDED_ALLOW_IPS` | `request.is_secure()`: SSL redirect decision, `https` in absolute URLs |
| `X-Forwarded-For` | `$proxy_add_x_forwarded_for` | nobody today; DRF throttling (planned, BE-AUTH-027) | client address for auth throttling (planned) |
| `X-Real-IP` | `$remote_addr` | nobody | none |
| `X-Forwarded-Host` | not set | nobody (`USE_X_FORWARDED_HOST` off) | none |

### Static and SPA URL paths

| Path | Served by | Response |
|------|-----------|----------|
| `/api/…` (known) | DRF views | JSON; trailing slash optional ([../backend/api-contract.md](../backend/api-contract.md)) |
| `/api/…` (unknown) | `core.views.api_not_found` | 404 JSON error envelope |
| `/api/health/` | `health` | see DEP-API-030 |
| `/api/schema/`, `/api/schema/swagger-ui/` | drf-spectacular | OpenAPI document, Swagger UI |
| `/django-admin/…` | Django admin | HTML |
| `/static/frontend/index.html`, `/static/frontend/assets/<name>-<hash>.js|css` | whitenoise (finders, or `STATIC_ROOT` after `collectstatic`) | built SPA (Vite `base` `/static/frontend/`) |
| `/static/…` (other) | whitenoise | Django admin / DRF assets |
| anything else (`/`, `/jobs/…`, …) | `core.views.spa_index` | `static/frontend/index.html`, `Cache-Control: no-cache`, sets `csrftoken`; 503 HTML if not built |
| `/.well-known/acme-challenge/…` (port 80) | nginx from `/var/www/html` | ACME files |

Caching headers and the build/collectstatic flow: [static-assets.md](static-assets.md).

### Filesystem paths and permissions

| Path | Owner / mode | web | worker | cleanup | nginx | Notes |
|------|--------------|-----|--------|---------|-------|-------|
| `/etc/cloudgene/cloudgene.env` | root, `0600` | — | — | — | — | read by systemd (as root) via `EnvironmentFile=` |
| `/opt/cloudgene` | `cloudgene` | r | r | r | — | code, venv; `WorkingDirectory=`; in `ReadWritePaths` |
| `/opt/cloudgene/static/frontend/` | `cloudgene` | r | — | — | — | written by `npm run build` (as `cloudgene`) |
| `/opt/cloudgene/staticfiles/` | `cloudgene` | r | — | — | r+x (only if nginx serves `/static/`) | written by `collectstatic` |
| `~cloudgene` (`/opt/cloudgene`) | `cloudgene` | — | rw | — | — | Nextflow's `~/.nextflow` |
| `/var/lib/cloudgene` (`CLOUDGENE_HOME`) | `cloudgene:cloudgene`, `0750` recommended | rw | rw | rw | — | layout: [cloudgene-home.md](cloudgene-home.md) |
| `CLOUDGENE_HOME/config/secret_key` | `cloudgene`, `0600` | r (create once) | r (create once) | r | — | only when `DJANGO_SECRET_KEY` unset; generation: [DEP-ENV-030](environment-config.md#secret-key) |
| `CLOUDGENE_HOME/config/worker.lock` | `cloudgene` | — | rw (flock) | — | — | contains the worker pid |
| `CLOUDGENE_HOME/config/.settings.lock` | `cloudgene` | rw | rw | — | — | settings write lock |
| `CLOUDGENE_HOME/jobs/` | `cloudgene` | rw | rw | rw | — | job workspaces |
| `CLOUDGENE_HOME/mail/` | `cloudgene` | rw | rw | — | — | file mail backend outbox |
| `/tmp` | private per unit (`PrivateTmp=true`) | rw | rw | rw | — | Django streams uploads > 10 MiB to temp files here before the view moves them |
| `/var/www/html/.well-known/` | root | — | — | — | r | ACME |

All three units run with `ProtectSystem=strict`, `ProtectHome=true`,
`ReadWritePaths=/opt/cloudgene /var/lib/cloudgene` (DEP-API-053).

### Signals

| Process | Signal | Behaviour | Sent by |
|---------|--------|-----------|---------|
| gunicorn master | `HUP` | re-read `gunicorn.conf.py`, start new workers, stop old ones gracefully. With `GUNICORN_PRELOAD_APP=1` (default) application code is **not** reloaded ([DEP-WEB-016](web-server.md#requirements)), and the environment file is not re-read | `systemctl reload cloudgene-web` (`ExecReload`) |
| gunicorn master | `TERM` | graceful stop: stop accepting, wait up to `GUNICORN_GRACEFUL_TIMEOUT` (30 s) for workers, then kill them | `systemctl stop/restart` |
| gunicorn master | `INT`, `QUIT` | immediate stop | manual |
| gunicorn master | `USR1` | reopen log files | manual / logrotate (only if logging to files) |
| gunicorn master | `TTIN`, `TTOU` | add / remove one worker | manual |
| `run_worker` | `TERM`, `INT` | stop claiming, finish the tick, stop each running job (SIGTERM to its group, ≤ 5 s, SIGKILL, mark `failed`), release lock, exit 0 (BE-QUEUE-014) | `systemctl stop/restart` (`KillSignal=SIGTERM`) |
| `run_worker` | `HUP` | not handled: Python's default action kills the process at once; running jobs become orphans and are failed at the next start (BE-QUEUE-016) | must not be sent |
| `run_worker` | `KILL` | as `HUP` | systemd after `TimeoutStopSec=120` |
| `run_worker --once` | any | no handlers installed | — |
| cleanup commands | any | no handlers; default actions | — |

### Exit codes

| Command (unit) | 0 | Non-zero | systemd reaction |
|----------------|---|----------|------------------|
| `gunicorn …` (`cloudgene-web`) | clean stop | non-zero on start-up failure: with `preload_app` on (default) a settings/import error fails in the master; with it off, gunicorn halts with 3 (worker failed to boot) or 4 (app failed to load) | `Restart=always`, `RestartSec=5` |
| `manage.py run_worker` (`cloudgene-worker`) | graceful stop after `TERM`/`INT` | 1 = lock held (`Another worker is already running for this CLOUDGENE_HOME.`), system check error (`core.E001`), or start-up exception | `Restart=always`, `RestartSec=5` |
| `manage.py cleanup_jobs` (`cloudgene-cleanup`) | always on completion (BE-CMD-055) | 1 = uncaught exception (e.g. DB unreachable) | oneshot fails; the second `ExecStart` (`cleanup_logs`) does not run; timer fires again next day |
| `manage.py cleanup_logs` (`cloudgene-cleanup`) | always on completion (BE-CMD-060) | 1 = uncaught exception | oneshot fails |
| `manage.py check --deploy` (manual / CI) | no errors (warnings allowed) | 1 = at least one Error (or Warning with `--fail-level WARNING`) | — |
| `manage.py migrate`, `collectstatic` (manual) | success | 1 | — |

## Behaviour

**Loading the environment.** systemd reads `/etc/cloudgene/cloudgene.env` as root and passes the
variables to the process it starts as `cloudgene`. `settings.py` then loads `<repo>/.env` without
overriding variables already set. `gunicorn.conf.py` is evaluated before Django settings, so
`GUNICORN_*` values in `.env` are ignored ([environment-config.md](environment-config.md)).

**HTTPS detection.** Two mechanisms decide `request.is_secure()`. With
`DJANGO_BEHIND_TLS_PROXY=1` Django reads `X-Forwarded-Proto` from any peer. Without it, Django
falls back to the WSGI scheme, which gunicorn sets to `https` when a peer in
`GUNICORN_FORWARDED_ALLOW_IPS` sends `X-Forwarded-Proto: https`. With the defaults (gunicorn on
loopback, nginx on the same host) both give the same answer. If gunicorn were reachable from
other hosts, the first mechanism would let any client claim HTTPS, which is why DEP-WEB-002
requires loopback by default and a proxy-only firewall otherwise.

**Redirect loop guard.** `DJANGO_SECURE_SSL_REDIRECT=1` without a working HTTPS signal (nginx not
setting `X-Forwarded-Proto`, or both mechanisms off) makes every request redirect to itself
over HTTPS: a redirect loop for browsers and a 301 for probes.

**Restart vs reload.** An upgrade (new code or new env values) needs `systemctl restart`, not
`reload`, for both services: see [DEP-WEB-016](web-server.md#requirements) for the web and
DEP-API-061 for the worker.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-API-001 | `core/tests/test_deploy_files.py::EnvContractTest::test_every_env_read_is_in_env_example` (planned) | config |
| DEP-API-002 | `core/tests/test_deploy_files.py::DeployFilesConsistencyTest::test_bind_paths_and_user_agree` (planned) | config |
| DEP-API-003 | `core/tests/test_deploy_files.py::EnvContractTest::test_every_env_read_is_in_env_example` (planned) | config |
| DEP-API-004 | `core/tests/test_deploy.py::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit |
| DEP-API-004 | `core/tests/test_deploy.py::DeployChecksTest::test_allowed_hosts_wildcard_warning` | unit |
| DEP-API-004 | `core/tests/test_deploy.py::DeployChecksTest::test_secret_key_weak_warning` | unit |
| DEP-API-004 | `core/tests/test_deploy.py::DeployChecksTest::test_secure_transport_warnings` | unit |
| DEP-API-004 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-API-005 | (planned) `scripts/manage_prod.sh` wrapper test, `core/tests/test_deploy_files.py::ManageWrapperTest::test_loads_env_file` (planned) | config |
| DEP-API-006 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e` | unit |
| DEP-API-006 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_e2e_flag_set` | unit |
| DEP-API-006 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_debug` | unit |
| DEP-API-006 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_flag_unset` | unit |
| DEP-API-011 | `core/tests/test_deploy_files.py::DeployFilesConsistencyTest::test_bind_paths_and_user_agree` (planned) | config |
| DEP-API-012 | `core/tests/test_deploy_files.py::ListenSocketTest::test_only_web_process_binds_a_socket` (planned; static scan of worker and cleanup command modules for `bind`/`listen`) | config |
| DEP-API-020 | `core/tests/test_proxy.py::ProxyHeaderTest::test_unknown_host_is_400` (planned) | unit |
| DEP-API-021 | `core/tests/test_proxy.py::ProxyHeaderTest::test_forwarded_proto_marks_request_secure` (planned) | unit |
| DEP-API-022 | `core/tests/test_deploy_files.py::GunicornConfigTest::test_forwarded_allow_ips_default` (planned) | config |
| DEP-API-023 | `core/tests/test_proxy.py::ProxyHeaderTest::test_no_code_reads_forwarded_for_or_real_ip` (planned; static scan, allow-list BE-AUTH-027) | config |
| DEP-API-030 | `core/tests/test_api.py::HealthTest::test_health_without_worker` | unit |
| DEP-API-030 | `core/tests/test_api.py::HealthTest::test_health_with_fresh_and_stale_heartbeat` | unit |
| DEP-API-030 | `core/tests/test_api.py::HealthTest::test_health_reports_a_broken_settings_file` | unit |
| DEP-API-030 | `core/tests/test_api.py::HealthTest::test_health_db_down` | unit |
| DEP-API-030 | `scripts/smoke_gunicorn.sh` step "GET /api/health" | smoke |
| DEP-API-031 | — host obligation; manual verification: stop `cloudgene-worker` and confirm the probe still reports the web process healthy (health answers 200 `degraded`) | — |
| DEP-API-032 | — host obligation; manual verification: stop `cloudgene-worker` for two probe intervals and confirm an alert fires | — |
| DEP-API-033 | `scripts/smoke_gunicorn.sh` with TLS env set (planned) | smoke |
| DEP-API-040 | `scripts/smoke_gunicorn.sh` step "GET a hashed static asset" | smoke |
| DEP-API-041 | `core/tests/test_api.py::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie` | unit |
| DEP-API-041 | `core/tests/test_api.py::MiscRoutingTest::test_spa_missing_build_message` | unit |
| DEP-API-041 | `core/tests/test_api.py::MiscRoutingTest::test_unknown_api_path_is_json_404` | unit |
| DEP-API-041 | `scripts/smoke_gunicorn.sh` step "GET / (SPA shell)" | smoke |
| DEP-API-050 | `core/tests/test_settings_env.py::SecretKeyTest::test_unwritable_home_fails_start` (planned) | unit |
| DEP-API-051 | — host obligation; manual verification: `stat -c '%U %a' /etc/cloudgene/cloudgene.env` prints `root 600` and `sudo -u cloudgene cat /etc/cloudgene/cloudgene.env` is refused | — |
| DEP-API-053 | — host obligation; manual verification: for each `work_dir` outside `/opt/cloudgene` and `/var/lib/cloudgene`, `systemctl show -p ReadWritePaths cloudgene-worker` lists it | — |
| DEP-API-060 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_reload_sends_hup` (planned) | config |
| DEP-API-061 | `jobs/tests/test_worker.py::ShutdownTest::test_shutdown_stops_running_jobs` | unit |
| DEP-API-061 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_sigterm_exits_zero_and_releases_lock` (planned) | unit |
| DEP-API-062 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| DEP-API-063 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-API-005 | Nothing loads `/etc/cloudgene/cloudgene.env` for one-off commands, and nothing in `deploy/` or `scripts/` runs a command with the unit environment. Settings load only `<repo>/.env`. The user docs run `sudo -u cloudgene venv/bin/python manage.py migrate` (and `collectstatic`, `create_admin`, `check --deploy`) without it; such a command silently uses SQLite at `/opt/cloudgene/db.sqlite3` and `CLOUDGENE_HOME=/opt/cloudgene/home`, so production PostgreSQL is never migrated and the admin is created in the wrong database. The env file is root-only (DEP-API-051), so the `cloudgene` user cannot source it either. This is the single home of this gap; DEP-DB-020, DEP-INST-008 and DEP-INST-021 link here. | `deploy/systemd/*.service:EnvironmentFile`; `cloudgene_django/settings.py:41,64,155-160`; `docs/DEPLOYMENT.md:79,145` (§2–§3, §5) | major |
| DEP-API-003 | `deploy/cloudgene.env.example` claims to list every variable the app reads, but omits `CLOUDGENE_ADMIN_PASSWORD`, `GUNICORN_WORKER_CLASS`, `GUNICORN_GRACEFUL_TIMEOUT`, `GUNICORN_KEEPALIVE`, `GUNICORN_ACCESS_LOG`, `GUNICORN_ERROR_LOG`, `GUNICORN_LOG_LEVEL`, `GUNICORN_MAX_REQUESTS`, `GUNICORN_MAX_REQUESTS_JITTER`, `GUNICORN_PRELOAD_APP`. No test compares the example with the code. | `deploy/cloudgene.env.example:3-5`, `deploy/gunicorn.conf.py:31-54` | minor |
| DEP-API-033 | With `DJANGO_SECURE_SSL_REDIRECT=1` and `ALLOWED_HOSTS` set to the public name, a local probe of `http://127.0.0.1:8000/api/health/` gets 400 (host) or 301 (redirect); health is not in `SECURE_REDIRECT_EXEMPT` and `127.0.0.1` is not allowed. `scripts/smoke_gunicorn.sh` does not set the TLS variables, so it does not exercise this. | `cloudgene_django/settings.py:91`, `:236`; `scripts/smoke_gunicorn.sh:33-38` | minor |
| DEP-API-020, DEP-API-021 | No test sends proxied requests (Host, `X-Forwarded-Proto`) through gunicorn or nginx; the e2e stack uses `runserver` without a proxy. | `e2e/stack.py:419` | minor |
| DEP-API-062 | In `cloudgene-cleanup.service` a failing `cleanup_jobs` prevents `cleanup_logs` from running that day. | `deploy/systemd/cloudgene-cleanup.service:15-16` | minor |
| DEP-API-061 | `run_worker` does not handle `HUP`; an accidental `kill -HUP` kills it without graceful shutdown. | `jobs/management/commands/run_worker.py:38-39` | minor |

## Open questions

1. How should DEP-API-005 be met? Options: ship a wrapper (for example `scripts/manage-prod`)
   that runs `manage.py` as `cloudgene` with `/etc/cloudgene/cloudgene.env` loaded (e.g. via
   `systemd-run --uid=cloudgene --property=EnvironmentFile=… --pipe --wait`), which the docs then
   use; or make settings also load `/etc/cloudgene/cloudgene.env` (or a path from
   `CLOUDGENE_ENV_FILE`). The env file is root-owned `0600` (DEP-API-051), so the `cloudgene`
   user cannot read it directly. This is the single home of this question; database.md and
   install-upgrade.md link here.
2. Should `/api/health/` be added to `SECURE_REDIRECT_EXEMPT` (and `127.0.0.1` accepted for it),
   so a local probe works without crafted headers?
3. (Moved) Removing `ExecReload` from `cloudgene-web.service`: see
   [process-management.md](process-management.md#open-questions).
