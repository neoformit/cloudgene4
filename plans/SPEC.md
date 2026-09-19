# Cloudgene (Django port) — Product & Technical Spec

> **This is the context anchor.** Every agent working on this repo reads this first.
> When you change behaviour, contracts, or architecture, update this file in the same commit.
> Status of work items lives in `plans/TASKS.md`; the E2E strategy lives in `plans/E2E_TEST_PLAN.md`.

Last reviewed: 2026-09-19 (initial audit; T01 platform foundations).

---

## 1. What the product is

A web service that lets logged-in users run **Nextflow** workflows through a browser. It is a port of
Cloudgene 3 (Java, in `./cloudgene3/`, read-only reference). Core capabilities:

1. Users register, activate by e-mail, log in, manage their profile, API token and password.
2. Admins install multiple **workflows** (a.k.a. "applications"), each described by a `cloudgene.yaml`.
   Access to each workflow is controlled by **group membership** (or the workflow is public).
3. A **run form** is generated automatically from the workflow's `inputs`.
4. Submitted runs become **jobs** in a **queue**. Up to `max_running_jobs` run concurrently; the queue
   holds at most `max_queue_size` waiting jobs. Queue can be paused / server put in maintenance mode.
5. A **job status page** shows live progress (steps, Nextflow processes/tasks from the trace, `::message::`
   annotations from stdout), logs, and downloadable outputs.
6. Users see a **job dashboard** of their own jobs and can cancel/delete them.
7. **Admin panel**: dashboard (queue state, counts), workflows (status, access groups, Nextflow settings,
   reload), jobs (all jobs, cancel, filter), users (list/search, group membership, activate, delete),
   settings (General, Nextflow, Templates, Mail), logs.
8. **Pages**: home, footer and arbitrary pages rendered from HTML template files in the codebase,
   editable from admin. Navbar items configured in YAML.

### Known bugs from the original that MUST be fixed (acceptance criteria)
- **K1 Duplicate users** after register → activate → assign group. Root causes in this port:
  username/email uniqueness is case-sensitive (`Bob` vs `bob`, `A@x.com` vs `a@x.com`); group edits
  from the admin UI are silently dropped (`UserSerializer.groups` is read-only) so admins re-create
  users; no DB-level case-insensitive constraint. Fix: normalise (lower-case) email, case-insensitive
  unique constraints on username and email, writable group membership, idempotent activation.
- **K2 Job stuck in "pending" forever.** Root cause here: the queue is only advanced inside the web
  request that submits/cancels a job (`JobQueue.process_queue`); when a running job finishes nothing
  starts the next one; jobs are marked `running` before the Celery task is accepted, so a missing
  worker leaves jobs orphaned; config keys are read from the wrong YAML section. Fix: dedicated worker
  (see §3.3) that owns scheduling, reconciles orphans at start-up and on every tick.
- **K3 Space in "Optional job name" breaks the backend.** Job name is free text (max 255, trimmed,
  any printable characters incl. spaces/unicode). It must never be used as a filesystem path or shell
  token; the workspace is keyed by job UUID. Current hack of replacing spaces with `_` is to be removed.
  If the name is empty, default to `<workflow name> <YYYY-MM-DD HH:MM>`.

---

## 2. Current state (audit 2026-09-19)

Stack: Django 6 + DRF, Vue 3 + Vite + Pinia + Bootstrap 5 SPA served by Django catch-all route,
SQLite, Celery (sqla+sqlite broker), Channels (Redis layer). Apps: `accounts`, `workflows`, `jobs`,
`admin_panel`. Frontend in `frontend/`, builds into `static/frontend/` (git-ignored).

Test reality (the "tests pass" claim is false):
- `python manage.py test`: 58 tests, **3 fail** (`test_invalid_activation_key`,
  `test_user_login_invalid_credentials`, `test_workflow_list_unauthenticated`).
- `*/contract_tests.py` are **never discovered** by the test runner (wrong filename pattern).
- `npx vitest run` **cannot start** (vitest 4 requires vite 6+/rolldown binding; vite 5 installed).
- `qa/` contains ad-hoc Selenium/debug scripts and stale reports; none run in CI.
- Infra not present on the host: Redis, Docker. Java 17 + Nextflow are being installed at `/usr/local/bin/nextflow`.

**After T01 (platform foundations):** Celery/Channels/Redis/CORS removed; settings from env; config
service + default `CLOUDGENE_HOME` in `home/`; session+CSRF auth, error envelope, `/api/auth/me`,
`/api/health`. `scripts/test.sh unit` = `manage.py check` + `makemigrations --check` +
`manage.py test` (171 tests incl. the former contract tests and the schema-staleness test) +
`npx vitest run` (56 tests, vitest 3.2 on vite 5) — all green. Jobs are accepted but stay `pending`
until T03's worker exists.

Status markers in the register: ✅ fixed · ◐ partially fixed (remaining work named).

### 2.1 Issue register

IDs are referenced from `TASKS.md`. Sev: **B**locker / **H**igh / **M**edium / **L**ow.

**Execution & queue (jobs/)**
| ID | Sev | Issue |
|----|-----|-------|
| J1 | B | Workflows are never actually executed with Nextflow. Steps are dispatched on `classname` substrings; the Cloudgene format (`script:`, `revision:`, `params:`) is ignored; `generate_nextflow_script` fabricates a dummy `main.nf`; unknown steps "succeed" as a Python placeholder. |
| J2 | B | Queue not advanced after job completion (K2). No scheduler process. `start_job` sets `running` before the task is accepted; no orphan reconciliation. |
| J3 | B | Uploaded files: `UploadedFile` objects are placed into `Job.parameters` (JSONField) → crash / never written to workspace. No per-input file/folder handling, no `writeFile`, no `serialize`. |
| J4 | H | Queue config read from `queue.*` in YAML but server settings live under `server.*` (`max_jobs`, `max_queue_size`); pause flag written to YAML by web process, never read by the runner; maintenance mode not enforced on submission. |
| J5 | H | Cancel: `celery revoke` does not kill the Nextflow process tree; status set to cancelled while process keeps running. |
| J6 | H | No live progress: WebSocket requires Redis + ASGI server (neither running); step/task/message model not populated from Nextflow trace; frontend polls every 20 s as fallback. |
| J7 | H | Job name spaces replaced with `_` (K3 hack); job name required in UI although optional in brief. |
| J8 | M | Outputs: all files under `results/` become downloads; outputs from YAML (`download`, folder vs file) ignored; downloads expire after 7 days and workspace is `rmtree`'d 1 h after completion (results vanish). |
| J9 | M | `restart` wipes logs and re-queues with no guard for workflow deletion/disable; semantics differ from Cloudgene (admin-only "retire/restart"). |
| J10| M | Job delete not supported (Cloudgene allows users to delete finished jobs); job retention/cleanup policy undefined. |
| J11| L | `JobValue`, `WorkflowExecution`, `queue_position` are unused/never maintained. |

**Accounts (accounts/)**
| ID | Sev | Issue |
|----|-----|-------|
| A1 | H | K1 duplicate users: case-sensitive uniqueness; group membership not writable via API (`groups` read-only) → admin UI changes silently ignored. |
| A2 ✅ T01 | H | Auth is DRF token in `localStorage`; plain `<a href>` links to logs/downloads carry no token → 401 → interceptor redirects to login. |
| A3 | H | Profile page: password change/email change payload fields ignored by serializer; `api_token` field doesn't exist on serializer; "Create API token" calls `GET /api/auth/token/` which is a POST-only obtain-token view. |
| A4 | M | Frontend and backend validation rules disagree (username: FE allows `_ -` and 3 chars, BE requires `[A-Za-z0-9]{4,}`; password lowercase rule missing in FE). |
| A5 | M | Password reset endpoint reveals whether an e-mail exists (FE text implies it doesn't). Reset link `/recover/<token>` fine; activation link fine. |
| A6 | M | Login lockout (`max_login_attempts`, `lockout_duration`) configured but not implemented. |
| A7 | M | Non-admin users can `PUT/PATCH/DELETE` themselves with arbitrary fields incl. `is_staff`, `is_active` (UserSerializer only protects id/dates). Privilege escalation. |
| A8 ◐ T01: groups endpoint admin-only; counts → T04 | M | Groups endpoint: any authenticated user can POST (create) groups; group member counts unavailable. |
| A9 ◐ T01: one `is_admin()`/`IsAdmin`; unused models → T04 | L | Unused models `UserGroup`, `UserToken`; mixed `is_staff` / `admin` group / `is_superuser` admin semantics. `IsAdminUser` (DRF, checks `is_staff`) vs custom `IsAdminUser` (admin group) used inconsistently. |

**Workflows (workflows/)**
| ID | Sev | Issue |
|----|-----|-------|
| W1 | H | No workflow registry: brief requires installed workflows declared in YAML config; today only a `load_sample_workflow` command writes one DB row. No reload, no install from path. |
| W2 | H | Parameter model loses YAML attributes (`label`, `help`, `min/max`, `writeFile`, `serialize`, `visible`, `details`, `accept`…). Input type set too small vs Cloudgene (`local-file`, `local-folder`, `app_list`, `separator`, `info`, `agb_checkbox`, `terms_checkbox`, `radio`, `binded_list`, `string`). `label` is populated from `description`. |
| W3 | M | Admin workflow list uses the public list endpoint (enabled-only), so disabled workflows vanish from admin. Status (enable/disable) not editable in UI. |
| W4 | M | `template_utils` reads Django settings that don't exist; global Nextflow config/env not applied; per-job variables (`CLOUDGENE_JOB_ID`, `USER_*`) missing. |
| W5 | L | Categories endpoint unused. |

**Admin/config (admin_panel/, config)**
| ID | Sev | Issue |
|----|-----|-------|
| C1 | B | Settings pages are wired to `/api/admin/server-settings/` (a CRUD list of key/value rows) but read/write shaped objects (`data.mail`, `data.nextflow`, `{mail:{...}}` via POST = create row). Every settings page is broken. |
| C2 ◐ T01: `settings.yaml` via `core.config` is the store, Django settings infra-only, `core.mail` reads mail config; `ServerSettings` removal & admin wiring → T05 | H | Three competing sources of truth: `cloudgene_config.yaml`, `ServerSettings` DB rows, Django `settings`. Mail settings in admin do not affect Django e-mail. |
| C3 | H | Templates: brief wants HTML template files in the codebase; implemented as DB rows seeded by a command. Static page route `/pages/:slug` only works for DB rows. |
| C4 | M | Navbar: YAML navbar is never loaded; frontend hard-codes Home/Jobs and appends DB items. |
| C5 | M | Dashboard fields mismatch (`stats` shape vs template); logs page reads `created_at` but API returns `timestamp`; level filter uppercase vs lowercase choices. Nothing writes `SystemLog`. |
| C6 | M | Admin jobs status filter never sent (`listJobs(page)` ignores params). |
| C7 | L | `Counter`, `CounterHistory` unused. |

**Frontend ↔ API contract mismatches (examples, non-exhaustive)**
| ID | Sev | Issue |
|----|-----|-------|
| F1 | H | Job detail/list use `job.username`, `job.workflow_id`; API returns `user_username`, `workflow_name`. |
| F2 | H | Steps tab uses `step.state`, `step.messages[].type/text`; API has `status`, messages are job-level. |
| F3 | H | Results tab reads `item.count`, `item.name`; API: `download_count`, `filename`. Download/log links unauthenticated (A2). |
| F4 | M | Checkbox inputs default to `false` ignoring YAML default; unchecked checkbox not sent at all → backend "required" error. `number` sent as string. |
| F5 ✅ T01 (backend handler + `apiErrorMessage`; views migrate as slices touch them) | M | Error envelope inconsistent: backend returns `{message}`, `{error}`, `{detail}`, or field dicts; frontend guesses. |
| F6 ✅ T01 | M | 401 interceptor hard-redirects to `/login` even for anonymous-allowed calls; `requiresAdmin` guard uses stale `localStorage` user. |
| F7 | L | Admin sidebar/navbar link to routes that don't exist; admin layout hides public navbar entirely. |

**Platform / production readiness**
| ID | Sev | Issue |
|----|-----|-------|
| P1 ✅ T01 | H | `DEBUG=True`, hard-coded `SECRET_KEY`, `ALLOWED_HOSTS=['*']`, `CORS_ALLOW_ALL_ORIGINS=True` defaults; `print()` in settings. |
| P2 ✅ T01 | H | Test suites broken (see §2). No single command runs all tests. |
| P3 ✅ T01 (worker itself → T03) | M | Hard dependency on Redis (channels) and a Celery worker that isn't documented/started. |
| P4 ◐ T01: logging config + `/api/health`; deployment docs/structured logs → T09 | M | No structured logging, no health endpoint, no deployment docs (gunicorn/static/Postgres). |
| P5 ✅ T01 | L | Repo cruft: `qa/` debug scripts & reports, `IMPLEMENTATION_SUMMARY.md`, `TEST_SUMMARY.md`, `ui-plan.md`, `start-celery.sh`, `schema.yaml` (stale). |

---

## 3. Target architecture (decisions)

Decisions marked **[D]** were made during the 2026-09-19 audit to reduce moving parts. Change them only
by updating this section.

### 3.1 Processes
- **web**: Django (WSGI; `runserver` in dev, gunicorn in prod). Serves `/api/*` and the built SPA.
- **worker**: `python manage.py run_worker` — a long-running DB-backed scheduler/executor. **[D]**
  Replaces Celery + Channels + Redis. Single worker per deployment (enforced by a DB lock row / pid file).
  Liveness: the worker calls `core.models.WorkerHeartbeat.beat(pid=..., hostname=..., started_at=...)`
  every tick (row `name="default"`); `/api/health` reports it (stale after 30 s).
- **DB**: SQLite for dev/test, PostgreSQL supported for prod (`DATABASE_URL`).
- No Redis. No WebSockets. **[D]** Live status = client polling (2 s while job active, backoff to 10 s)
  of a cheap status endpoint. This mirrors Cloudgene 3 and is robust behind any proxy.

### 3.2 Configuration — single source of truth **[D]**
- `CLOUDGENE_HOME` (env, default repo root in dev) contains:
  - `config/settings.yaml` — server, queue, mail, nextflow, navbar, installed workflows (list of paths
    + access groups + enabled flag). This file is the *only* place for these settings.
  - `config/nextflow.config`, `config/nextflow.env` — global Nextflow config & env (admin-editable).
  - `pages/*.html` — `home.html`, `footer.html`, and any `<slug>.html` served at `/pages/<slug>`.
  - `apps/<id>/cloudgene.yaml` (+ `main.nf` etc.) — installed workflows.
  - `apps/<id>/nextflow.config`, `nextflow.env` — per-workflow overrides (admin-editable).
  - `jobs/<job-uuid>/` — job workspaces (`input/`, `output/`, `logs/`, `work/`).
- The config service `core/config.py` loads & validates `settings.yaml` (schema + defaults),
  caches by mtime/size/inode, and writes atomically (temp file + `os.replace`) under an exclusive
  `fcntl` lock on `config/.settings.lock`. Web and worker both read through it, so admin changes
  reach the worker without restart. API (module-level functions):
  - read: `load_settings(force=False) -> dict` (validated deep copy, defaults filled; missing file
    = defaults; an invalid file raises `ConfigError` unless a valid version is cached, then that is
    kept and an error logged), `get('server.max_running_jobs', default=None)`.
  - write: `set_value('queue.paused', True)`, `update_settings(dict_to_deep_merge | fn(doc))`,
    `save_settings(doc)`; all validate and return the new settings; `ConfigError.errors` maps dotted
    key paths (`server.max_running_jobs`, `navbar[0].url`) to message lists (use as API `fields`).
  - paths: `cloudgene_home()`, `config_dir()`, `settings_path()`, `nextflow_config_path()`,
    `nextflow_env_path()`, `pages_dir()`, `apps_dir()`, `jobs_dir()`, `app_dir(id)`, `job_dir(uuid)`,
    `page_path(slug)` (slugs `^[a-z0-9][a-z0-9_-]{0,63}$`, else `ValueError` — traversal-safe).
  - files: `read_page(slug) -> str|None`, `write_page`, `delete_page`, `list_pages()`,
    `read_text(path)`, `write_text_atomic(path, text)`, `parse_env(text) -> dict`, `ensure_home()`.
  - Unknown keys are preserved (not validated), so slices can add keys; add them to the schema and
    the table below when they become official.
- Django `settings.py` only holds infra settings from env (`DJANGO_SECRET_KEY` — else generated once
  into `$CLOUDGENE_HOME/config/secret_key`; `DEBUG` default off; `ALLOWED_HOSTS`;
  `CSRF_TRUSTED_ORIGINS`; `DATABASE_URL`; `CLOUDGENE_HOME` default `./home`; `LOG_LEVEL`;
  `DJANGO_SECURE_COOKIES`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS`,
  `DJANGO_BEHIND_TLS_PROXY`). Mail settings come from `settings.yaml` at send time via
  `core.mail.send_mail()` / `get_connection()` (the Django test runner's locmem outbox is honoured).
- The default `CLOUDGENE_HOME` is committed as `./home/` (runtime dirs `jobs/`, `mail/` and the
  generated `secret_key` are git-ignored). The Django test runner copies it to a temp dir per run.

`settings.yaml` keys (schema, defaults and validation: `core.config.SCHEMA`):

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `server.name` | str | `Cloudgene` | Service name (navbar, e-mails) |
| `server.url` | str | `''` | Public base URL for e-mail links (empty = request host) |
| `server.max_running_jobs` | int ≥1 | 2 | Jobs the worker runs concurrently |
| `server.max_queue_size` | int ≥0 | 50 | Max `waiting` jobs; further submissions rejected |
| `server.maintenance` | bool | false | Non-admin submissions blocked, banner shown |
| `server.maintenance_message` | str | *(text)* | Banner / rejection message |
| `server.job_retention_days` | int ≥0 | 7 | Workspace retention for `cleanup_jobs` (0 = keep) |
| `server.max_upload_mb` | int ≥1 | 1024 | Max total upload size per submission |
| `queue.paused` | bool | false | Worker starts no new jobs while true |
| `security.max_login_attempts` | int ≥0 | 5 | Failed logins before lockout (0 = off) |
| `security.lockout_duration` | int ≥0 | 300 | Lockout seconds |
| `security.require_activation` | bool | true | New accounts need e-mail activation |
| `mail.backend` | `smtp`/`file`/`console` | `file` | Delivery backend |
| `mail.file_path` | str | `mail` | Outbox dir for `file` (relative to `CLOUDGENE_HOME`) |
| `mail.host` / `mail.port` | str / int | `localhost` / 587 | SMTP server |
| `mail.user` / `mail.password` | str | `''` | SMTP auth (password write-only in APIs) |
| `mail.use_tls` / `mail.use_ssl` | bool | true / false | SMTP transport security |
| `mail.from_email` | str | `noreply@localhost` | Sender address |
| `nextflow.binary` | str | `nextflow` | Nextflow executable |
| `nextflow.profile` | str | `''` | Default `-profile` |
| `nextflow.work_dir` | str | `''` | Work dir (empty = `<job>/work`) |
| `navbar[]` | list | `[]` | `{title*, url*, icon, admin_only: false, auth_only: false}` |
| `apps[]` | list | `[]` | `{path*, enabled: true, public: false, groups: []}`; `path` = app dir or its `cloudgene.yaml`, relative to `$CLOUDGENE_HOME/apps` or absolute |
- DB holds only runtime state: users, groups, jobs (+steps/messages/outputs), and a `Workflow` cache
  row per installed app (synced from YAML on start-up and on admin "reload").
- Remove `ServerSettings`, `Template`, `NavbarItem`, `Counter*`, `UserGroup`, `UserToken`,
  `WorkflowExecution`, `JobValue` models (migration).

### 3.3 Job lifecycle & queue **[D]**
States: `waiting` (queued) → `running` → `success` | `failed` | `cancelled`.
(Rename from pending/completed; keep `pending` only as legacy alias in data migration.) Additional
flag: `deleted` (soft) for user-deleted jobs.

- **Submit** (web): validate inputs against workflow definition; reject with 503 if maintenance mode
  (admins exempt) or 429/409 if queue full; create Job(`waiting`), create workspace, save uploads to
  `input/<param-id>/<filename>` (sanitised filename), store resolved parameter values (paths, not file
  objects) in `Job.parameters`. Transaction-safe; on failure the workspace is removed.
- **Worker loop** (every ~1 s): read config; if not paused, claim oldest `waiting` jobs up to
  `max_running_jobs` using an atomic conditional UPDATE (`status=waiting → running`), spawn executor
  (subprocess in its own process group), poll running executors, parse trace/stdout into steps,
  finalise. On start-up: any `running` job with no live process → `failed` ("worker restarted").
- **Execution** (per step in `workflow.steps`): Nextflow step = `nextflow run <script> [-r revision]
  -params-file params.json -c global.config -c app.config [-profile p] -w work -with-trace
  logs/trace.txt -with-report ... -log logs/nextflow.log` with env from `nextflow.env` files and
  `CLOUDGENE_*` variables. Params = step `params` + serialisable inputs + output paths. Stdout
  `::message::`, `::warning::`, `::error::`, `::group::`/`::endgroup::` annotations become job messages.
  Unknown step types fail the job with a clear message (never silently "succeed").
- **Progress**: trace file (tab-separated) parsed incrementally → per-process task counts
  (submitted/running/completed/failed) shown as steps/tasks in the UI.
- **Cancel**: `waiting` → `cancelled` immediately; `running` → worker sends SIGTERM to process group,
  SIGKILL after grace period, then `cancelled`. Web only sets `cancel_requested=True`.
- **Outputs**: for each YAML output with `download: true`, collect files under `output/<id>/` into
  `JobOutput` rows (relative path, size). Downloads served by an authenticated streaming view with path
  traversal protection. Retention: configurable `job_retention_days` (default 7) via a
  `cleanup_jobs` command; UI shows expiry.
- Job name (K3): free text, trimmed, ≤255, default generated. Never used in paths.

### 3.4 Authentication **[D]**
- SPA uses **Django session auth + CSRF** (cookie `csrftoken`, header `X-CSRFToken`). This makes
  `<a href>` downloads/log links work and removes tokens from `localStorage`.
- **API tokens** (DRF `Token`) for programmatic access: user creates/revokes one token from profile.
- `GET /api/auth/me` always 200: `{"authenticated": bool, "user": User|null}`; it also sets the
  `csrftoken` cookie (as does every SPA page via `ensure_csrf_cookie`). Router guards await it.
- `POST /api/auth/login {username, password}` → 200 `{"user": User}` plus a session cookie (no token
  in the response); CSRF is enforced on login too (login CSRF). `POST /api/auth/logout` → 200 always.
  Login rotates the CSRF token: clients re-read the cookie (the axios client does so per request).
- Authentication order: `TokenAuthentication`, then `SessionAuthentication` → unauthenticated
  requests to protected endpoints get **401** (`WWW-Authenticate: Token`), not 403. Session requests
  with unsafe methods need `X-CSRFToken`; token requests don't.
- Admin = `is_superuser` **or** `is_staff` **or** member of group `admin` — one helper
  `core.permissions.is_admin(user)` + `IsAdmin` / `IsAdminOrReadOnly` permission classes
  (`User.is_admin_user()` delegates to it).
- Frontend: one 401 hook (`onUnauthorized` in `api/client.js`) resets the store and leaves only
  protected pages; there is no hard redirect.
- Lockout after `max_login_attempts` for `lockout_duration` seconds.

### 3.5 API conventions (the contract) **[D]**
- All endpoints under `/api/`. JSON in/out except job submission (`multipart/form-data`) and file
  downloads.
- Error envelope everywhere: `{"error": {"message": str, "code": str, "fields": {field: [str]}}}`
  via `core.exceptions.api_exception_handler` (`fields` always present; nested fields dotted, e.g.
  `nested.a`; non-field errors only in `message`; for field errors `message` = `"<field>: <msg>"`).
  Codes: DRF defaults (`invalid`, `not_authenticated`, `authentication_failed`,
  `permission_denied`, `not_found`, `method_not_allowed`, `throttled`, …) plus `csrf_failed`,
  `server_error` (unhandled exception: logged, generic message) and view-specific codes. Views
  return non-exception errors with `core.exceptions.error_response(message, code, status)`.
  Unknown `/api/...` paths → 404 envelope. Schema: component `Error`, added as `default` response
  on every operation. Frontend: `apiErrorMessage(err)`, `apiFieldErrors(err)`, `apiErrorCode(err)`
  from `src/api/client.js` (a transitional interceptor also copies `error.message` to
  `data.message` for views not yet migrated — remove at T06).
- Paths are canonical **with** a trailing slash (as in `schema.yaml`); `core.middleware` also
  routes the slash-less form (e.g. `POST /api/auth/login`) without a redirect.
- Lists are paginated `{count, next, previous, results}` with `?page=&page_size=` (default 20,
  max 200; `core.pagination.StandardPagination`).
- Timestamps ISO-8601 UTC. IDs: job UUID strings, workflow slug strings, user/group integers.
- The OpenAPI document generated by drf-spectacular (`python manage.py spectacular --file
  schema.yaml`) is committed; a test fails if it is stale. Every view has explicit serializers so
  the schema is accurate. Backend contract tests validate real responses against the schema; frontend
  API modules are the only place that calls `client` and are unit-tested against schema fixtures.

### 3.6 Endpoint inventory (target)
```
Auth      POST /api/auth/login  POST /api/auth/logout  GET /api/auth/me
          POST /api/auth/register  POST /api/auth/activate/{key}
          POST /api/auth/password-reset  POST /api/auth/password-reset/{token}
Profile   GET/PATCH /api/me  (full_name, email, password+current_password)
          POST /api/me/token  DELETE /api/me/token  DELETE /api/me
Server    GET /api/server  → {name, maintenance, maintenance_message, navbar[], footer_html,
                              user?} (public)
          GET /api/pages/{slug} → {slug, html}  (public; home, about, …)
Workflows GET /api/workflows  GET /api/workflows/{id}  (id, name, version, description, website,
          category, inputs[] with full typed schema, outputs[])
Jobs      GET /api/jobs?state=&page=   POST /api/jobs (multipart: workflow, name, <input ids>)
          GET /api/jobs/{id}  GET /api/jobs/{id}/status (light, for polling)
          POST /api/jobs/{id}/cancel  DELETE /api/jobs/{id}
          GET /api/jobs/{id}/log  (text/plain)   GET /api/jobs/{id}/outputs/{output_id}/{path}
Admin     GET /api/admin/dashboard  (queue: {paused, maintenance, running, waiting, max_running,
          max_queue}, counts, recent jobs)
          POST /api/admin/queue/{pause|resume}  POST /api/admin/maintenance/{enter|exit}
          GET /api/admin/jobs?state=&user=&workflow=  POST /api/admin/jobs/{id}/cancel
          POST /api/admin/jobs/{id}/restart
          GET /api/admin/users?search=  PATCH /api/admin/users/{id} (groups[], is_active)
          DELETE /api/admin/users/{id}
          GET/POST /api/admin/groups  DELETE /api/admin/groups/{id}
          GET /api/admin/workflows  PATCH /api/admin/workflows/{id} (enabled, groups[], public)
          POST /api/admin/workflows/{id}/reload  POST /api/admin/workflows/install {path}
          GET/PUT /api/admin/workflows/{id}/nextflow (profile, work_dir, config, env)
          GET/PUT /api/admin/settings/general|mail|nextflow   POST /api/admin/settings/mail/test
          GET /api/admin/pages  GET/PUT /api/admin/pages/{slug}
          GET /api/admin/logs?level=  (from Python logging → DB handler or log file tail)
Health    GET /api/health → {status: ok|degraded|error, db: {ok}, worker: {ok, last_seen,
          age_seconds, pid}}; 200 unless the DB is down (503); no/stale worker = "degraded"
```
Exact request/response shapes are defined by the serializers and `schema.yaml`; this list is the
scope. Slice owners may refine paths but must update this section.

### 3.7 Frontend
- Vue 3 + Vite 5/6 + Pinia + Bootstrap 5. `src/api/*.js` is the only HTTP layer.
- Route guards use `/api/auth/me` (fetched on boot) — not `localStorage`.
- Job page polls `/api/jobs/{id}/status` while active; shows steps → tasks (from trace), messages,
  queue position, elapsed time; tabs: Details, Results, Logs.
- Dynamic form supports every input type in §4, client-side validation mirrors server rules, sends
  `multipart/form-data`, displays field-level errors from the envelope.
- Every interactive element that E2E tests need has a stable `data-testid`.

---

## 4. Workflow YAML contract (supported subset of Cloudgene 3)

```yaml
id: hello            # slug, required
name: Hello          # required
version: 1.0.0
description: <html allowed>
website/author/logo/category: optional
workflow:
  steps:             # required, ≥1
    - name: Say hello
      type: nextflow   # default when `script` present
      script: main.nf  # relative to app dir, or a GitHub repo (owner/repo)
      revision: 1.0    # optional
      params: {..}     # extra params merged into params.json
      processes: [{process: X, label: .., view: ..}]   # optional progress rendering hints
  inputs:
    - id: name         # required, becomes params key
      description: Label shown in UI
      type: text|string|number|textarea|list|radio|checkbox|file|folder|local-file|local-folder|
            separator|info|label|terms_checkbox|agb_checkbox
      value: default
      values: {key: label}          # list/radio; checkbox: {true: x, false: y}
      required: true (default) | false
      visible: true
      help / details: text
      writeFile: file.txt           # textarea: write content to file, pass path
      serialize: true               # include in params.json
      accept: .vcf.gz,.csv          # file inputs
      min / max                     # number
  outputs:
    - id: outdir
      description: Output
      type: folder|file|local-folder|local-file
      download: true
      serialize: true
```
Unknown `type` → validation error at install/reload. `classname:` steps (Java) → unsupported error.

Rules enforced by the parser (`workflows/definition.py`, owned by T03):
- `id` (app) must match `^[a-z0-9][a-z0-9_-]{0,63}$` (it is also the app dir name); `name` required;
  `workflow.steps` needs ≥1 step. Input/output ids match `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, are unique
  across inputs+outputs, and must not be `workflow` or `job_name` (reserved multipart fields).
- Unknown input/output `type` → error. Accepted aliases: `label` for `description`, `write_file` for
  `writeFile`. `list`/`radio` need `values` (mapping `key: label`, or a list of scalars /
  `{key,label}`); a default not among the keys is ignored with a warning. `number`: `value`/`min`/`max`
  numeric, `min <= max`. `checkbox`: `values` optional but, if given, needs both `true` and `false`
  keys; default = `value` (bool, or the mapped true value); never "required". `terms_checkbox` /
  `agb_checkbox` must be checked to submit (unless `required: false`). `writeFile` only on `textarea`, plain file name.
  `separator`/`info`/`label` are display-only (never submitted, never in params). `local-file` /
  `local-folder` behave like `file` / `folder` (browser upload). Output `download` and `serialize`
  default to `true`; output `type` defaults to `folder`.
- Steps: `type: nextflow` or no `type` (default `script: main.nf`). Steps with `classname:`, `cmd:`
  or another `type` load with `type: "unsupported"` + `error` and a definition warning; a job that
  reaches such a step fails with that message (never silently succeeds).

Python API (stable contract for the registry, T05):
```python
from workflows.definition import load_definition, parse_definition, DefinitionError
d = load_definition(path_or_yaml)   # app dir | path to cloudgene.yaml | YAML str/bytes | dict
# -> WorkflowDefinition(id, name, version, description, website, author, logo, category,
#      steps: [Step(name, type, script, revision, params, processes, error)],
#      inputs: [InputParam(id, type, label, value, values[{key,label}], checkbox_values,
#               required, visible, help, details, write_file, serialize, accept, min, max)],
#      outputs: [OutputParam(id, type, label, download, serialize)],
#      warnings: [str], app_dir: Path|None, source_path, raw: dict, yaml_text: str)
# d.input(id), d.output(id), d.value_inputs, d.to_dict()
# DefinitionError.errors -> ["workflow.inputs[2].type: unknown type \"x\" ...", ...]
```
The `Workflow` DB row caches the raw YAML (`yaml_config`); the web process and worker re-parse it
with `load_definition(workflow.yaml_config)` (cheap) — there is no per-parameter table. Each job
stores a snapshot of the YAML it was submitted with (`Job.workflow_yaml`) and runs against it.

---

## 5. Non-functional requirements
- All user-facing flows covered by E2E tests (see `E2E_TEST_PLAN.md`) running against the full stack
  (built SPA + Django + worker + real Nextflow).
- `make test` (or `./scripts/test.sh`) runs: Django tests, schema-staleness check, vitest, E2E.
- No console errors and no unexpected 4xx/5xx on any page during E2E.
- Security: object-level permission checks on every job/output/log; admin endpoints admin-only;
  path traversal protection on downloads/pages; CSRF on session auth; no mass-assignment of privilege
  fields; uploads size-limited (`max_upload_mb` setting); secrets never returned by settings APIs
  (mail password write-only).
- Works with SQLite (dev/test) and Postgres (prod).

## 6. Changelog of spec decisions
- 2026-09-19 (T01): config service API + `settings.yaml` key table (§3.2); auth details (login
  returns `{user}`, CSRF on login, 401 for unauthenticated, admin incl. superuser) (§3.4); error
  codes, optional trailing slash, pagination limits (§3.5); health payload (§3.6); worker
  heartbeat (§3.1).
- 2026-09-19: Initial audit. Decisions [D] in §3: drop Celery/Channels/Redis for DB worker + polling;
  YAML+files as single config source; session+CSRF auth for SPA; unified error envelope; state names
  `waiting/running/success/failed/cancelled`.
