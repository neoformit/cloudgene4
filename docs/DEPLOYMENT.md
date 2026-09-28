# Deployment

Production target (`plans/SPEC.md` §3.1, orchestrator decision 2026-09-28): a single Linux host
running **nginx** (TLS termination) → **gunicorn** (web) + **`manage.py run_worker`** (one job
worker instance), both managed by **systemd**, backed by **PostgreSQL**. No Docker in scope.
SQLite remains supported for development and small single-user installs only — see the SQLite
warning under [Health monitoring](#health-monitoring--manage.py-check---deploy) below.

This doc assumes a checkout at `/opt/cloudgene`, a `cloudgene` system user/group owning it, and
`CLOUDGENE_HOME=/var/lib/cloudgene` for runtime data (jobs, mail outbox, generated secret key,
`settings.yaml`, pages, installed workflow apps). Adjust paths to taste; the unit files and env
example in `deploy/` use these.

## 1. Install

```bash
# System packages (adjust for your distro): Python 3.12, PostgreSQL, nginx, Java 17+ and
# Nextflow (the worker shells out to `nextflow`; see plans/SPEC.md §3.1/§4).
sudo useradd --system --home /opt/cloudgene --create-home cloudgene
sudo -u cloudgene git clone <repo-url> /opt/cloudgene
cd /opt/cloudgene

python3.12 -m venv venv
venv/bin/pip install -r requirements.txt

# Frontend build (Node 20+; only needed at install/upgrade time — the built output is served
# statically, no Node process runs in production).
cd frontend && npm ci && npm run build && cd ..

sudo mkdir -p /var/lib/cloudgene
sudo chown cloudgene:cloudgene /var/lib/cloudgene

sudo mkdir -p /etc/cloudgene
sudo cp deploy/cloudgene.env.example /etc/cloudgene/cloudgene.env
sudo chmod 600 /etc/cloudgene/cloudgene.env   # holds the DB password
# edit /etc/cloudgene/cloudgene.env — see "Configure" below
```

PostgreSQL (adjust to your install method):

```bash
sudo -u postgres createuser cloudgene
sudo -u postgres createdb -O cloudgene cloudgene
sudo -u postgres psql -c "ALTER USER cloudgene WITH PASSWORD '<a real password>';"
```

## 2. Configure

Edit `/etc/cloudgene/cloudgene.env` (every variable it can hold is listed, with comments, in
`deploy/cloudgene.env.example` — keep the two files in sync when a new env var is added).
At minimum, set:

- `DJANGO_SECRET_KEY` — a long random value (`python -c "import secrets; print(secrets.token_urlsafe(50))"`).
  Required when running more than one web host behind a load balancer (each host must agree);
  optional on a single host (falls back to an auto-generated
  `$CLOUDGENE_HOME/config/secret_key`, created once and shared by web + worker).
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` — your real hostname(s).
- `DATABASE_URL` — `postgres://cloudgene:<password>@127.0.0.1:5432/cloudgene`.
- `DJANGO_SECURE_COOKIES=1`, `DJANGO_SECURE_SSL_REDIRECT=1`, `DJANGO_BEHIND_TLS_PROXY=1`,
  `DJANGO_HSTS_SECONDS=31536000` — once nginx is serving this over HTTPS (all default off, so a
  first boot without TLS still works for smoke-testing before you have a certificate).

Application-level configuration (server name, queue limits, mail, Nextflow binary/profile,
navbar, installed workflows) lives in `$CLOUDGENE_HOME/config/settings.yaml`, not the env file —
see `docs/ADMIN_GUIDE.md` and `plans/SPEC.md` §3.2. It is created with defaults on first run
(`core.config.ensure_home()`, called by `migrate`/`run_worker`/the web process) and is editable
from Admin → Settings without a restart (both web and worker read it through a cached, mtime-
watching config service).

Then run migrations and collect static files:

```bash
sudo -u cloudgene /opt/cloudgene/venv/bin/python manage.py migrate
sudo -u cloudgene /opt/cloudgene/venv/bin/python manage.py collectstatic --noinput
```

(`collectstatic` is required in production: with `DEBUG=False`, whitenoise serves from
`STATIC_ROOT`, which only `collectstatic` populates — the `STATICFILES_DIRS` finders it uses in
dev are not consulted. Re-run it on every deploy that changed the frontend, i.e. every deploy
that ran `npm run build`.)

## 3. First admin user

```bash
sudo -u cloudgene /opt/cloudgene/venv/bin/python manage.py create_admin \
  --username admin --email admin@example.org --password '<a real password>'
```

Idempotent — re-running it with `--password` updates an existing user's password (e.g. to reset
a forgotten admin password); without `--password` it leaves an existing user's password alone.
Omit `--password` (and `$CLOUDGENE_ADMIN_PASSWORD`) entirely to have one generated and printed
once.

## 4. systemd services

```bash
sudo cp deploy/systemd/cloudgene-*.service deploy/systemd/cloudgene-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudgene-web cloudgene-worker cloudgene-cleanup.timer
```

- **`cloudgene-web`** — gunicorn (`deploy/gunicorn.conf.py`), bound to `127.0.0.1:8000` by
  default; nginx proxies to it. `Restart=always`.
- **`cloudgene-worker`** — `manage.py run_worker`, the single long-running job scheduler/executor
  (SPEC §3.1/§3.3). Exactly one instance may run at a time; it takes an exclusive DB lock and a
  second instance exits immediately rather than fighting the first, so `Restart=always` here is
  safe even across a brief double-start during a restart. It runs Nextflow per job step in its
  own process group and handles cancellation/graceful shutdown (SIGTERM) itself.
- **`cloudgene-cleanup.{service,timer}`** — daily `cleanup_jobs` (workspace retention, per
  `settings.yaml`'s `server.job_retention_days`) + `cleanup_logs` (default 30 days of
  `SystemLog` rows; `--days N` to change). Safe to run with the worker live.

Both `cloudgene-web.service` and `cloudgene-worker.service` set `ProtectSystem=strict` with
`ReadWritePaths=/opt/cloudgene /var/lib/cloudgene`. If you configure a per-app or global Nextflow
`work_dir` outside those two paths (`nextflow.work_dir` / `apps[].work_dir` in `settings.yaml` —
QA_FINDINGS I-6 notes an admin can point this anywhere, by design), add that path to
`ReadWritePaths=` in `cloudgene-worker.service` too, or the worker will fail to write there.

nginx:

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/cloudgene
# edit server_name and certificate paths
sudo ln -s /etc/nginx/sites-available/cloudgene /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Keep `client_max_body_size` in the nginx config `>=` `settings.yaml`'s `server.max_upload_mb`
(default 1024 MB) — nginx would otherwise reject a large-but-otherwise-valid upload with its own
413 before Django ever sees it. If you change one, change the other.

## 5. Upgrade

```bash
cd /opt/cloudgene
sudo -u cloudgene git pull
sudo -u cloudgene venv/bin/pip install -r requirements.txt
sudo -u cloudgene bash -c 'cd frontend && npm ci && npm run build'
sudo -u cloudgene venv/bin/python manage.py migrate
sudo -u cloudgene venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart cloudgene-web cloudgene-worker
```

Run migrations before restarting the worker: a running worker is unaffected by a `pip install`/
`npm run build` until it restarts, but a schema the new code expects must exist first. There is
no special job-draining step — `cloudgene-worker` forwards SIGTERM to any Nextflow process group
it owns and waits for it to exit before stopping (graceful shutdown, SPEC §3.3), and a `waiting`
job simply resumes once the new worker process starts and claims it.

Before deploying, run `scripts/smoke_gunicorn.sh` (builds the SPA, `collectstatic`s, boots
gunicorn with `DEBUG=False` against a throw-away DB, and fetches `/`, a hashed static asset and
`/api/health`) to catch a broken build or static-serving regression before it reaches nginx.

## 6. Backups

Two things need backing up; both are needed together for a consistent restore (a job's DB row
references its `$CLOUDGENE_HOME/jobs/<uuid>/` workspace, and `settings.yaml` is only on disk):

- **Database** (Postgres): `pg_dump` on a schedule (e.g. nightly, via cron or another systemd
  timer), e.g. `pg_dump -Fc cloudgene > cloudgene-$(date +%F).dump`; restore with `pg_restore`.
- **`$CLOUDGENE_HOME`** (`/var/lib/cloudgene` in this doc): `config/` (settings.yaml, generated
  secret_key, global nextflow.config/env), `pages/`, `apps/` (installed workflow definitions —
  large ones may be worth excluding if they are reproducible from elsewhere and only referenced
  in place), `jobs/` (running/finished job workspaces — can be large; retention already trims
  finished ones per `server.job_retention_days`), `mail/` (the `file` mail backend's outbox, if
  used). A file-level backup tool (restic, borg, tar+cron) works fine; there is no live-backup
  API. `jobs/` may be worth excluding from tight-RPO backups if churn/size make it impractical —
  a job's status/history in the DB survives without it, only its output files are lost.

Stop `cloudgene-worker` (or accept a small race with a job mid-write) before restoring `jobs/` on
top of a running system; there is no need to stop `cloudgene-web`.

## 7. Log locations

- **stdout/stderr of both systemd services** → journald: `journalctl -u cloudgene-web -f`,
  `journalctl -u cloudgene-worker -f`. Set `LOG_FORMAT=json` in the env file for structured
  lines (`core.logging_formatters.JsonFormatter`) if you forward these to a log shipper;
  default is human-readable text.
- **Application log records** (`cloudgene.*` loggers — SPEC §3.8: `cloudgene.auth`,
  `cloudgene.jobs`, `cloudgene.worker`, `cloudgene.workflows`, `cloudgene.admin`, `cloudgene.api`)
  at INFO+ are *also* stored in the DB (`admin_panel.SystemLog`) and shown in Admin → Logs, with
  filters by level/component. This is independent of the console output above and survives
  `cleanup_logs`' retention window rather than journald's own log rotation.
- **Nextflow's own logs** live per job under `$CLOUDGENE_HOME/jobs/<uuid>/logs/` (`.nextflow.log`,
  trace file, per-step stdout/stderr) — surfaced in the job detail page's Logs tab, not in
  journald or SystemLog.

## 8. Health monitoring

`GET /api/health` (anonymous, no auth) returns:

```json
{"status": "ok", "db": {"ok": true},
 "worker": {"ok": true, "last_seen": "...", "age_seconds": 4, "pid": 12345},
 "config": {"ok": true, "errors": []}}
```

`status` is `"ok"`, `"degraded"` (e.g. the worker heartbeat is stale — over 30s old or missing —
or `settings.yaml` failed validation and fell back to defaults for the bad key(s), listed in
`config.errors`; the site still serves), or `"error"` (the DB itself is unreachable). Point an
uptime check (cron+curl, Nagios/Icinga, a hosted monitor) at it; a `"degraded"` status with a
non-empty `config.errors` also shows on the Admin dashboard.

`manage.py check --deploy` should be run once after configuring `/etc/cloudgene/cloudgene.env`
(and again after any change to it) and must report no issues. It warns/errors on: cookies not
marked Secure, no SSL redirect, no HSTS, a weak/short `SECRET_KEY`, `ALLOWED_HOSTS=['*']`, SQLite
in use with `DEBUG` off (Postgres is the intended production database — SQLite works but
serialises every writer across the web and worker processes sharing one file), and — as a hard
`Error`, not just a deploy-check warning, so it blocks *any* `manage.py` command including
`migrate` — `INSECURE_FAST_PASSWORD_HASHING` set without `DEBUG` or `CLOUDGENE_E2E=1` (test/E2E
only; never set either in this env file).

```bash
sudo -u cloudgene /opt/cloudgene/venv/bin/python manage.py check --deploy
```
