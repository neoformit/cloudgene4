# Cloudgene

A web front end for running [Nextflow](https://www.nextflow.io/) workflows: point it at a
directory with a `cloudgene.yaml` (workflow name, inputs, outputs — see
[`docs/WORKFLOW_YAML_REFERENCE.md`](docs/WORKFLOW_YAML_REFERENCE.md)) and it renders a submission
form, queues and runs the pipeline, and serves progress and outputs back to the browser. Django +
DRF backend, Vue 3 SPA, a small polling-based job worker (no Celery/Channels/Redis/WebSockets).

This is a Django/Vue port of Cloudgene 3 (Java, kept read-only in `cloudgene3/` for reference).
Architecture and the full API/data contract are in [`plans/SPEC.md`](plans/SPEC.md).

## Requirements

- Python ≥ 3.12
- Node.js 22 (for building/developing the frontend only — no Node process runs in production)
- Java 17+ (21 tested) and [Nextflow](https://www.nextflow.io/) on `PATH`, to actually run workflows
- SQLite (default) for development and small single-user installs; **PostgreSQL** for production
  (see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md))

## Layout

```
cloudgene_django/   Django project (settings from environment variables)
core/               platform: config service, auth helpers, error envelope, health, create_admin
accounts/           users, registration, groups
workflows/          workflow definitions (cloudgene.yaml) and the workflow registry
jobs/               jobs, queue, worker (run_worker) and the Nextflow runner
admin_panel/        admin API
frontend/           Vue 3 SPA (Vite); `npm run build` writes to static/frontend/
home/               default CLOUDGENE_HOME: config/settings.yaml, pages/*.html, apps/, jobs/ (ignored)
deploy/             gunicorn/systemd/nginx config for production (docs/DEPLOYMENT.md)
scripts/test.sh     runs the unit and E2E suites
```

Two processes make up a running instance: **web** (Django; serves `/api/*` and the built SPA) and
**worker** (`python manage.py run_worker` — schedules the queue and runs Nextflow; without it jobs
stay `waiting`).

## Development quick start

```bash
# 1. Python environment
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Local settings (DEBUG on, everything else defaults to SQLite/./home)
echo "DEBUG=1" > .env

# 3. Database + an administrator
python manage.py migrate
python manage.py create_admin --username admin --email admin@example.org --password Admin1234

# 4. Frontend bundle (served by Django at /static/frontend/)
(cd frontend && npm ci && npm run build)

# 5. Web server -> http://127.0.0.1:8000/
python manage.py runserver

# 6. Install a workflow (a directory with cloudgene.yaml) and run the worker
python manage.py install_workflow e2e/fixtures/apps/hello --public
python manage.py run_worker          # separate terminal; Ctrl+C stops it gracefully
```

For frontend work with hot reload, run `npm run dev` in `frontend/` (http://localhost:5173)
alongside `runserver` — Vite proxies `/api` to port 8000.

`create_admin` is idempotent: it creates the user or updates an existing one (password only if
given, also via `$CLOUDGENE_ADMIN_PASSWORD`; a random one is printed if a new user gets none), and
makes it an admin (`is_staff`, `is_superuser`, group `admin`).

Job workspaces live in `$CLOUDGENE_HOME/jobs/<job-uuid>/`; `python manage.py cleanup_jobs`
(schedule it daily — `deploy/systemd/cloudgene-cleanup.timer` in production) removes them after
`server.job_retention_days`.

### Configuration

- **Environment** (infrastructure only; full list in the docstring of `cloudgene_django/settings.py`
  and in [`deploy/cloudgene.env.example`](deploy/cloudgene.env.example)): `DEBUG` (default off),
  `DJANGO_SECRET_KEY` (default: generated once into `$CLOUDGENE_HOME/config/secret_key`),
  `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (default SQLite `db.sqlite3`),
  `CLOUDGENE_HOME` (default `./home`), `LOG_LEVEL`/`LOG_FORMAT`. A `.env` file in the repo root is
  loaded automatically.
- **Application settings** live in `$CLOUDGENE_HOME/config/settings.yaml` (server name, queue
  limits, maintenance, mail, Nextflow, navbar, installed apps) — read/written only through
  `core.config`; admins edit them from Admin -> Settings. Reference: `plans/SPEC.md` §3.2 and
  [`docs/ADMIN_GUIDE.md`](docs/ADMIN_GUIDE.md).
- **Workflows** are directories with a `cloudgene.yaml` listed in `settings.yaml` `apps:`:

  ```bash
  python manage.py install_workflow /path/to/app [--public] [--groups researchers,staff] [--copy]
  python manage.py sync_workflows          # re-read settings.yaml apps[] (also done lazily)
  ```

  See [`docs/WORKFLOW_YAML_REFERENCE.md`](docs/WORKFLOW_YAML_REFERENCE.md) for every key and input
  type, with a complete worked example at `docs/examples/cloudgene.yaml`.

### Auth for API clients

The SPA uses the Django session (cookie) with CSRF (`csrftoken` cookie -> `X-CSRFToken` header).
Scripts should use a token instead: `Authorization: Token <key>`. All API errors share one envelope
shape. See [`docs/API.md`](docs/API.md) for details, and `schema.yaml` (or `/api/schema/swagger-ui/`)
for the full OpenAPI contract.

## Tests

```bash
scripts/test.sh unit             # Django checks + tests (incl. schema.yaml staleness) + vitest, SQLite
scripts/test.sh unit --postgres  # same, Django tests against Postgres instead
scripts/test.sh e2e              # Playwright E2E (pytest e2e)
scripts/test.sh all              # unit, then e2e
```

E2E needs `playwright==1.56.0` exactly as pinned in `requirements.txt` — it must match the browser
build already installed on the host; do **not** run `pip install -r e2e/requirements.txt` or
`playwright install` yourself, or the pinned version will drift from what's on disk and Chromium
will fail to launch.

After changing any API view or serializer, regenerate the committed schema:
`python manage.py spectacular --file schema.yaml --validate`.

## Production deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full guide: nginx + gunicorn + systemd,
PostgreSQL, TLS/HSTS, upload limits, backups, log locations and health monitoring. Also:
[`docs/ADMIN_GUIDE.md`](docs/ADMIN_GUIDE.md) (settings, users/groups, workflows, queue,
maintenance, logs), [`docs/WORKFLOW_YAML_REFERENCE.md`](docs/WORKFLOW_YAML_REFERENCE.md),
[`docs/API.md`](docs/API.md), and [`plans/SPEC.md`](plans/SPEC.md) for the complete contract.
