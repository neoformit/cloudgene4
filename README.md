# Cloudgene (Django port)

A web service for running [Nextflow](https://www.nextflow.io/) workflows from the browser — a
port of Cloudgene 3 (Java, kept read-only in `cloudgene3/` for reference) to Django + Vue 3.

**Start here:** [`plans/SPEC.md`](plans/SPEC.md) (product, architecture, API contract),
[`plans/TASKS.md`](plans/TASKS.md) (work in progress), [`plans/E2E_TEST_PLAN.md`](plans/E2E_TEST_PLAN.md).

## Layout

```
cloudgene_django/   Django project (settings from environment variables)
core/               platform: config service, auth helpers, error envelope, health, create_admin
accounts/           users, registration, groups
workflows/          workflow definitions and registry
jobs/               jobs, queue and (from T03) the worker
admin_panel/        admin API
frontend/           Vue 3 SPA (Vite); `npm run build` writes to static/frontend/
home/               default CLOUDGENE_HOME: config/settings.yaml, pages/*.html, apps/, jobs/ (ignored)
scripts/test.sh     runs every test suite
```

Processes: **web** (Django; serves `/api/*` and the built SPA) and **worker**
(`python manage.py run_worker` — *provided by T03, not available yet*: until then submitted jobs
stay `pending`). There is no Redis, Celery or WebSocket server.

## Development quick start

Requirements: Python 3.12, Node 20+ (21 works), Java 17 + Nextflow for running workflows.

```bash
# 1. Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Local settings (DEBUG on, everything else defaults)
echo "DEBUG=1" > .env

# 3. Database + an administrator
python manage.py migrate
python manage.py create_admin --username admin --email admin@example.org --password Admin1234

# 4. Frontend bundle (served by Django at /static/frontend/)
(cd frontend && npm install && npm run build)

# 5. Web server → http://127.0.0.1:8000/
python manage.py runserver

# 6. Worker (separate terminal) — provided by T03
# python manage.py run_worker
```

For frontend work with hot reload run `npm run dev` in `frontend/` (http://localhost:5173) next to
`runserver`; Vite proxies `/api` to port 8000.

`create_admin` is idempotent: it creates the user or updates an existing one (password only if
given; also via `$CLOUDGENE_ADMIN_PASSWORD`; a random one is printed if a new user gets none), and
makes it an admin (`is_staff`, `is_superuser`, group `admin`).

### Configuration

* **Environment** (infrastructure only; see the docstring in `cloudgene_django/settings.py`):
  `DEBUG` (default off), `DJANGO_SECRET_KEY` (default: generated once into
  `$CLOUDGENE_HOME/config/secret_key`), `ALLOWED_HOSTS` (default `localhost,127.0.0.1,[::1]`),
  `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (default SQLite `db.sqlite3`), `CLOUDGENE_HOME`
  (default `./home`), `LOG_LEVEL`. A `.env` file in the repo root is loaded automatically.
* **Application settings** live in `$CLOUDGENE_HOME/config/settings.yaml` (server name, queue
  limits, maintenance, mail, Nextflow, navbar, installed apps). Read/write only through
  `core.config`; admins edit them in the UI. Key reference: SPEC §3.2.
* **Pages**: `$CLOUDGENE_HOME/pages/<slug>.html` (`home`, `footer`, `about`, …), editable in
  Admin → Pages; every page is served at `/pages/<slug>`.
* **Workflows** are directories with a `cloudgene.yaml` (SPEC §4) listed in `settings.yaml`
  `apps:`. Install one from the admin panel or the CLI:

  ```bash
  python manage.py install_workflow /path/to/app [--public] [--groups researchers,staff] [--copy]
  python manage.py sync_workflows          # re-read settings.yaml apps[] (also done lazily)
  ```

  Access (`enabled`, `public`, `groups`) and the per-app Nextflow `profile`/`work_dir` live in
  `apps[]`; per-app `nextflow.config`/`nextflow.env` in `$CLOUDGENE_HOME/apps/<id>/`.

### Auth for API clients

The SPA uses the Django session (cookie) with CSRF (`csrftoken` cookie → `X-CSRFToken` header).
Scripts should use a token: `Authorization: Token <key>`. All API errors have the shape
`{"error": {"message": "...", "code": "...", "fields": {"field": ["..."]}}}`.
API paths may be called with or without the trailing slash. OpenAPI: `schema.yaml` (browse at
`/api/schema/swagger-ui/`).

## Tests

```bash
scripts/test.sh unit   # Django checks + tests (incl. schema.yaml staleness) + vitest
scripts/test.sh e2e    # Playwright E2E (pytest e2e)
scripts/test.sh all    # both
```

After changing any API view or serializer regenerate the committed schema:
`python manage.py spectacular --file schema.yaml --validate`.
