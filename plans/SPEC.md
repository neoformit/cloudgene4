# Cloudgene (Django port) — Product & Technical Spec

> **This is the context anchor.** Every agent working on this repo reads this first.
> When you change behaviour, contracts, or architecture, update this file in the same commit.
> Status of work items lives in `plans/TASKS.md`; the E2E strategy lives in `plans/E2E_TEST_PLAN.md`.

Last reviewed: 2026-09-19 (initial audit; T01 platform foundations; T04 accounts; T05 server config & admin).

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
- **K1 Duplicate users** (✅ T04: DB constraints on `Lower(username)`/`Lower(email)`, regression
  test `accounts.tests.K1RegressionTest` + E2E A2/D3) after register → activate → assign group. Root causes in this port:
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
`npx vitest run` (56 tests, vitest 3.2 on vite 5) — all green.

**After T03 (jobs, execution & run form):** jobs really run — `manage.py run_worker` schedules and
executes Nextflow (§3.3), the run form is generated from `cloudgene.yaml` (§4) and the job page
polls `/api/jobs/{id}/status`. K2 and K3 are fixed; `jobs/tasks.py`, `jobs/queue.py`, `JobValue`
and `JobDownload` are gone.

Status markers in the register: ✅ fixed · ◐ partially fixed (remaining work named).

### 2.1 Issue register

IDs are referenced from `TASKS.md`. Sev: **B**locker / **H**igh / **M**edium / **L**ow.

**Execution & queue (jobs/)**
| ID | Sev | Issue |
|----|-----|-------|
| J1 ✅ T03 | B | Workflows are never actually executed with Nextflow. Steps are dispatched on `classname` substrings; the Cloudgene format (`script:`, `revision:`, `params:`) is ignored; `generate_nextflow_script` fabricates a dummy `main.nf`; unknown steps "succeed" as a Python placeholder. |
| J2 ✅ T03 | B | Queue not advanced after job completion (K2). No scheduler process. `start_job` sets `running` before the task is accepted; no orphan reconciliation. |
| J3 ✅ T03 | B | Uploaded files: `UploadedFile` objects are placed into `Job.parameters` (JSONField) → crash / never written to workspace. No per-input file/folder handling, no `writeFile`, no `serialize`. |
| J4 ✅ T03 (worker reads `server.*`/`queue.paused` every tick; maintenance enforced on submit) | H | Queue config read from `queue.*` in YAML but server settings live under `server.*` (`max_jobs`, `max_queue_size`); pause flag written to YAML by web process, never read by the runner; maintenance mode not enforced on submission. |
| J5 ✅ T03 (process-group SIGTERM→SIGKILL) | H | Cancel: `celery revoke` does not kill the Nextflow process tree; status set to cancelled while process keeps running. |
| J6 ✅ T03 (polling `/status`, trace + annotations) | H | No live progress: WebSocket requires Redis + ASGI server (neither running); step/task/message model not populated from Nextflow trace; frontend polls every 20 s as fallback. |
| J7 ✅ T03 (K3) | H | Job name spaces replaced with `_` (K3 hack); job name required in UI although optional in brief. |
| J8 ✅ T03 (YAML outputs, retention `cleanup_jobs`) | M | Outputs: all files under `results/` become downloads; outputs from YAML (`download`, folder vs file) ignored; downloads expire after 7 days and workspace is `rmtree`'d 1 h after completion (results vanish). |
| J9 ✅ T03 (admin-only restart with guards) | M | `restart` wipes logs and re-queues with no guard for workflow deletion/disable; semantics differ from Cloudgene (admin-only "retire/restart"). |
| J10 ✅ T03 | M | Job delete not supported (Cloudgene allows users to delete finished jobs); job retention/cleanup policy undefined. |
| J11 ✅ T03 (`JobValue`/`JobDownload` dropped; `WorkflowExecution`/`WorkflowParameter` → T05) | L | `JobValue`, `WorkflowExecution`, `queue_position` are unused/never maintained. |

**Accounts (accounts/)**
| ID | Sev | Issue |
|----|-----|-------|
| A1 ✅ T04 | H | K1 duplicate users: case-sensitive uniqueness; group membership not writable via API (`groups` read-only) → admin UI changes silently ignored. |
| A2 ✅ T01 | H | Auth is DRF token in `localStorage`; plain `<a href>` links to logs/downloads carry no token → 401 → interceptor redirects to login. |
| A3 ✅ T04 | H | Profile page: password change/email change payload fields ignored by serializer; `api_token` field doesn't exist on serializer; "Create API token" calls `GET /api/auth/token/` which is a POST-only obtain-token view. |
| A4 ✅ T04 | M | Frontend and backend validation rules disagree (username: FE allows `_ -` and 3 chars, BE requires `[A-Za-z0-9]{4,}`; password lowercase rule missing in FE). |
| A5 ✅ T04 | M | Password reset endpoint reveals whether an e-mail exists (FE text implies it doesn't). Reset link `/recover/<token>` fine; activation link fine. |
| A6 ✅ T04 | M | Login lockout (`max_login_attempts`, `lockout_duration`) configured but not implemented. |
| A7 ✅ T04 | M | Non-admin users can `PUT/PATCH/DELETE` themselves with arbitrary fields incl. `is_staff`, `is_active` (UserSerializer only protects id/dates). Privilege escalation. |
| A8 ✅ T01/T04 | M | Groups endpoint: any authenticated user can POST (create) groups; group member counts unavailable. |
| A9 ✅ T01/T04 | L | Unused models `UserGroup`, `UserToken`; mixed `is_staff` / `admin` group / `is_superuser` admin semantics. `IsAdminUser` (DRF, checks `is_staff`) vs custom `IsAdminUser` (admin group) used inconsistently. |

**Workflows (workflows/)**
| ID | Sev | Issue |
|----|-----|-------|
| W1 ✅ T05 | H | No workflow registry: brief requires installed workflows declared in YAML config; today only a `load_sample_workflow` command writes one DB row. No reload, no install from path. |
| W2 ✅ T03 (`workflows/definition.py` + public API; the DB parameter table is gone) | H | Parameter model loses YAML attributes (`label`, `help`, `min/max`, `writeFile`, `serialize`, `visible`, `details`, `accept`…). Input type set too small vs Cloudgene (`local-file`, `local-folder`, `app_list`, `separator`, `info`, `agb_checkbox`, `terms_checkbox`, `radio`, `binded_list`, `string`). `label` is populated from `description`. |
| W3 ✅ T05 | M | Admin workflow list uses the public list endpoint (enabled-only), so disabled workflows vanish from admin. Status (enable/disable) not editable in UI. |
| W4 ✅ T05+T03: variable list + values in `workflows.template_utils` (`VARIABLES`, `cloudgene_variables()`), global/per-app files admin-editable; exported into the Nextflow env by T03's worker (§3.3) | M | `template_utils` reads Django settings that don't exist; global Nextflow config/env not applied; per-job variables (`CLOUDGENE_JOB_ID`, `USER_*`) missing. |
| W5 | L | Categories endpoint unused. |

**Admin/config (admin_panel/, config)**
| ID | Sev | Issue |
|----|-----|-------|
| C1 ✅ T05 | B | Settings pages are wired to `/api/admin/server-settings/` (a CRUD list of key/value rows) but read/write shaped objects (`data.mail`, `data.nextflow`, `{mail:{...}}` via POST = create row). Every settings page is broken. |
| C2 ✅ T01+T05 (`ServerSettings` removed; admin settings APIs write settings.yaml) | H | Three competing sources of truth: `cloudgene_config.yaml`, `ServerSettings` DB rows, Django `settings`. Mail settings in admin do not affect Django e-mail. |
| C3 ✅ T05 | H | Templates: brief wants HTML template files in the codebase; implemented as DB rows seeded by a command. Static page route `/pages/:slug` only works for DB rows. |
| C4 ✅ T05 | M | Navbar: YAML navbar is never loaded; frontend hard-codes Home/Jobs and appends DB items. |
| C5 ✅ T05 | M | Dashboard fields mismatch (`stats` shape vs template); logs page reads `created_at` but API returns `timestamp`; level filter uppercase vs lowercase choices. Nothing writes `SystemLog`. |
| C6 ✅ T05 (UI sends state/user/workflow; endpoint → T03) | M | Admin jobs status filter never sent (`listJobs(page)` ignores params). |
| C7 ✅ T05 | L | `Counter`, `CounterHistory` unused. |

**Frontend ↔ API contract mismatches (examples, non-exhaustive)**
| ID | Sev | Issue |
|----|-----|-------|
| F1 ✅ T03 | H | Job detail/list use `job.username`, `job.workflow_id`; API returns `user_username`, `workflow_name`. |
| F2 ✅ T03 | H | Steps tab uses `step.state`, `step.messages[].type/text`; API has `status`, messages are job-level. |
| F3 ✅ T03 (session-authenticated download/log links) | H | Results tab reads `item.count`, `item.name`; API: `download_count`, `filename`. Download/log links unauthenticated (A2). |
| F4 ✅ T03 | M | Checkbox inputs default to `false` ignoring YAML default; unchecked checkbox not sent at all → backend "required" error. `number` sent as string. |
| F5 ✅ T01 (backend handler + `apiErrorMessage`; views migrate as slices touch them) | M | Error envelope inconsistent: backend returns `{message}`, `{error}`, `{detail}`, or field dicts; frontend guesses. |
| F6 ✅ T01 | M | 401 interceptor hard-redirects to `/login` even for anonymous-allowed calls; `requiresAdmin` guard uses stale `localStorage` user. |
| F7 ✅ T05 | L | Admin sidebar/navbar link to routes that don't exist; admin layout hides public navbar entirely. |

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
| `server.max_queue_size` | int ≥0 | 50 | Max `waiting` jobs; further submissions rejected (429). `0` = unlimited |
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
| `apps[]` | list | `[]` | `{path*, enabled: true, public: false, groups: [], profile: '', work_dir: ''}`; `path` = app dir or its `cloudgene.yaml`, relative to `$CLOUDGENE_HOME/apps` (then `$CLOUDGENE_HOME`) or absolute; `profile`/`work_dir` = per-app Nextflow overrides ('' = global) |
- DB holds only runtime state: users, groups, jobs (+steps/messages/outputs), `SystemLog`, and a
  `Workflow` cache row per installed app (see *Workflow registry* below).
- Removed (T05): `ServerSettings`, `Template`, `NavbarItem`, `Counter`, `CounterHistory`, the
  `Workflow` columns `nextflow_profile/working_directory/env_vars/nextflow_config` (now read-only
  properties backed by settings.yaml + files). Still to remove: `UserGroup`, `UserToken` (T04),
  `WorkflowParameter`, `WorkflowExecution`, `JobValue` (T03, which parses the definition at request
  time).

**Workflow registry [D] (T05, `workflows/registry.py`)**
- `settings.yaml apps[]` is the source of truth for *which* apps are installed and their access
  (`enabled`, `public`, `groups` by name) + per-app `profile`/`work_dir`. Each app is a directory
  with `cloudgene.yaml`; install **references it in place** (stored relative to `apps/` when inside
  it, else absolute); `copy=True` / `install_workflow --copy` copies it to `apps/<id>/` first.
  Uninstall removes the `apps[]` entry only — files are never deleted.
- The `Workflow` row is a cache: `id, name, version, description, website, category, yaml_config`
  (raw YAML), `status` (`enabled`/`disabled`; kept for T03 querysets, `enabled` property),
  `public`, `allowed_groups` (auth.Group M2M; groups named in YAML are created), `app_path`
  (resolved yaml; empty = row not managed by the registry, e.g. created in tests — never touched by
  a sync), `errors` (list; non-empty ⇒ status disabled), `installed` (False once removed from
  `apps[]` but kept because jobs reference it; rows without jobs are deleted), `synced_at`.
  `app_location` property = app dir (`CLOUDGENE_APP_LOCATION`). `can_access(user)` unchanged.
- Sync (`registry.sync_all()`, idempotent): parses every entry through
  `workflows.definition.load_definition` (T03) via the single adapter `registry.load_definition`;
  invalid / unreadable / duplicate-id entries are reported (admin list shows `valid: false` +
  `errors`) and never get a runnable row. Triggers: `manage.py sync_workflows` (deploy, worker
  start-up — T03's `run_worker` should call `registry.sync_all()` on start), lazily from
  `workflows.middleware.WorkflowSyncMiddleware` on any `/api/` request when settings.yaml or an
  installed cloudgene.yaml changed (mtime/size), and after every admin write. Not in
  `AppConfig.ready` (unsafe during migrate).
- CLI: `manage.py install_workflow <path> [--public] [--groups a,b] [--disabled] [--copy]
  [--replace]`, `manage.py sync_workflows`.
- Per-app Nextflow files: `$CLOUDGENE_HOME/apps/<id>/nextflow.config` and `nextflow.env`
  (`registry.get_nextflow_settings(id)` → `{profile, work_dir, config, env, config_path,
  env_path}`); when the app itself lives in `apps/<id>/` these are the app's own files. The worker
  applies global config then this one (T03).
- Pages: `home` and `footer` are required (not deletable); any `^[a-z0-9][a-z0-9_-]{0,63}$` slug
  is served at `/pages/<slug>` from `pages/<slug>.html`; invalid slugs → 404 (public) / 400 (admin).

### 3.3 Job lifecycle & queue **[D]**
States: `waiting` (queued) → `running` → `success` | `failed` | `cancelled` (`Job.status` in the DB,
`state` in the API). Legacy `pending`/`completed` were data-migrated (jobs `0003_job_rework`).
Soft delete: `Job.deleted_at` (user-deleted jobs are hidden everywhere and their workspace removed);
`Job.purged_at` marks a workspace removed by retention.

- **Submit** (web, `jobs/submission.py`): `POST /api/jobs` multipart. Order of checks: workflow
  exists + `can_access` (else 404) → enabled (409 `workflow_disabled`) → maintenance (503
  `maintenance`, admins exempt) → queue full (429 `queue_full`, `max_queue_size: 0` = unlimited) →
  definition parses (409 `workflow_invalid`) → job name (K3) → per-input validation (400 with
  `fields`) → total upload size (413 `upload_too_large`). Then: workspace `jobs/<uuid>/`
  (`input/ output/ logs/`), uploads written to `input/<param-id>/<sanitised name>` (ASCII, spaces →
  `_`, de-duplicated; the original name is kept for display in `Job.uploads`), textarea `writeFile`
  content to `input/<id>/<file>`, and a `waiting` Job row with the typed values in `Job.parameters`
  (file values as paths relative to the workspace) plus a snapshot of the workflow YAML/app dir.
  The workspace is removed if anything fails.
- **Worker loop** (`manage.py run_worker`, ~1 s tick): heartbeat → read `settings.yaml` → reconcile
  orphans (any `running` job this worker does not execute: its process group is killed if it still
  belongs to the job, the job fails with "The worker was restarted…") → poll running executions
  (stdout/trace progress, cancellation, exit) → cancel `waiting` jobs flagged for cancellation →
  unless `queue.paused`, claim the oldest `waiting` jobs (atomic `status=waiting → running` UPDATE)
  up to `server.max_running_jobs` and launch them. One instance per `CLOUDGENE_HOME` (`fcntl` lock
  on `config/worker.lock`); SIGTERM/SIGINT stop it gracefully (running jobs are terminated and
  marked failed); `--once` drains the queue and exits (tests).
- **Execution** (`jobs/runner.py`, one step at a time, each a subprocess in its own process group):
  `nextflow -log logs/[stepN-]nextflow.log run <script> [-r rev] -params-file [stepN-]params.json
  -c <global nextflow.config> -c <app nextflow.config> -c <job>/cloudgene.config [-profile p]
  -w <work> -with-trace logs/[stepN-]trace.txt -with-report … -with-timeline … -ansi-log false`,
  cwd = the job workspace, stdout+stderr appended to `logs/stdout.txt`. `cloudgene.config` is
  generated per job (trace fields incl. `process`/`workdir`, `overwrite = true`). `script` is
  resolved against the app dir; if no such file exists it is passed through as a remote pipeline
  name. Environment: the worker's env + `config/nextflow.env` + `apps/<id>/nextflow.env`
  (`KEY=VALUE`, `${VAR}` expanded) + `CLOUDGENE_JOB_ID`, `CLOUDGENE_JOB_NAME`, `CLOUDGENE_USER_NAME`,
  `CLOUDGENE_USER_EMAIL`, `CLOUDGENE_USER_FULL_NAME`, `CLOUDGENE_APP_ID`, `CLOUDGENE_APP_VERSION`,
  `CLOUDGENE_APP_LOCATION`, `CLOUDGENE_SERVICE_NAME`, `CLOUDGENE_SERVICE_URL`,
  `CLOUDGENE_CONTACT_EMAIL`. `params.json` = step `params` + serialisable inputs (numbers as
  numbers, checkbox as its mapped value or bool, files/folders/`writeFile` as absolute paths) +
  each serialisable output as `<job>/output/<output id>`. Steps that are not Nextflow steps
  (`classname:`, `cmd:`, other `type:`) fail the job with the parser's message.
- **Progress**: stdout task lines (`[PROCESS ab/123456] NAME (1)` / `… Submitted process > …`) and
  the trace file (read incrementally) give per-process counts `{name, label, submitted, running,
  completed, failed, total}` stored on `JobStep.processes`. Annotations `::message::`, `::notice::`,
  `::warning::`, `::error::`, `::group type=…::`/`::endgroup::` become `JobMessage` rows (levels
  `info|success|warning|error`); they are read from the Nextflow stdout **and** from each finished
  task's `cloudgene.out`/`.command.out`, de-duplicated between the two sources. `::debug::`,
  `::log::` and counter commands are ignored.
- **Cancel**: the web process sets `cancel_requested` (a `waiting` job is cancelled immediately in
  the same request). The worker sends SIGTERM to the process group, SIGKILL after a 10 s grace
  period, then marks the job `cancelled`.
- **Outputs**: after a run, every output with `download: true` is listed into `JobOutput` rows
  (`output_id`, `path` relative to `output/`, `size`); symlinks are followed only inside the job
  workspace and its work dir. Downloads are streamed by an authenticated view; paths come from the
  DB and are re-validated (no `..`, no absolute paths, must resolve inside the job).
- **Delete / retention**: users delete finished jobs (soft delete + workspace removed); deleting a
  Job row (e.g. user deletion) removes the workspace via a `post_delete` signal; `manage.py
  cleanup_jobs` removes workspaces of jobs finished more than `server.job_retention_days` ago
  (0 = keep) and orphan workspace dirs without a Job row (older than 1 h). `expires_at` in the API
  is `finished_at + job_retention_days`.
- **Restart** (admin only): a `failed`/`cancelled` job with an intact workspace is re-queued with
  the same inputs; steps/messages/outputs and `output/ logs/ work/` are reset and the **current**
  workflow definition is snapshotted again. 409 if the workflow is gone or disabled.
- Job name (K3): free text, trimmed, ≤255, control characters stripped, default
  `<workflow name> <YYYY-MM-DD HH:MM>`. Never used in a path or command line.

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
- **Login errors** (T04): 400 `invalid_credentials` (unknown user and wrong password look the
  same), 403 `account_inactive` (only after a correct password), 429 `account_locked` with
  `Retry-After`. Failed logins are counted per user (`User.login_attempts`); reaching
  `security.max_login_attempts` locks the account for `security.lockout_duration` s (0 = off);
  a correct password during the lock is refused; success or a password reset resets the counter.
  Usernames are matched ignoring case. Login updates `last_login`.
- **Identity** (T04, K1): username unique ignoring case (stored stripped, case preserved), e-mail
  stored stripped + lower-cased and unique; DB constraints `users_username_ci_unique`,
  `users_email_ci_unique` on `Lower(...)`. Migration `accounts.0003` aborts with a list of
  existing case-duplicates (nothing merged automatically).
- **Field rules** (A4): `accounts/validation.py` is the source; username `^[A-Za-z0-9]{4,150}$`,
  e-mail `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` (≤254), password 6–128 chars with a
  digit, a lower- and an upper-case letter (Cloudgene rules; Django's `AUTH_PASSWORD_VALIDATORS`
  are not applied), full name required (≤255), group name `^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$`.
  Mirrored in `frontend/src/utils/validation.js`; both test suites run
  `accounts/validation_cases.json`.
- **Registration**: with `security.require_activation` the account is inactive and an activation
  link `<server.url or request host>/activate/<key>` is mailed (mail failure → 503 `mail_failed`,
  nothing created); otherwise active at once. Activation `POST /api/auth/activate/{key}` is
  idempotent: `{status: activated|already_active, message}`; re-using the link never re-activates
  an account an admin deactivated. Keys and reset tokens are random (`secrets.token_urlsafe`) and
  stored only as sha256.
- **Password reset**: request always 200 with the same message (mail only for active accounts);
  link `/recover/<token>`, single use, expires after 24 h; confirm validates the password rules.
- **API tokens**: one DRF token per user, created/regenerated with `POST /api/me/token` (key shown
  once), revoked with `DELETE /api/me/token`. `/api/auth/token/` (obtain_auth_token) is removed.

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
          POST /api/auth/password-reset {email}  POST /api/auth/password-reset/{token}
                {password, password_confirm?}
Profile   GET/PATCH /api/me → User + api_token: {created}|null
            PATCH {full_name?, email?, password?, password_confirm?, current_password?}
            (current_password required when email or password changes; other keys ignored)
          POST /api/me/token → 201 {token, created}   DELETE /api/me/token → {message}
          DELETE /api/me {password} → {message}; logs out (400 last_admin for the only admin)
          User = {id, username, email, full_name, is_active, is_admin, groups: [names],
                  date_joined, last_login}
Server    GET /api/server  → {name, url, maintenance, maintenance_message, navbar[{title, url,
          icon, admin_only, auth_only}] (already filtered for the viewer), footer_html} (public)
          GET /api/pages/{slug} → {slug, html}  (public; home, about, …; 404 missing/unsafe slug)
Workflows GET /api/workflows  GET /api/workflows/{id}  (id, name, version, description, website,
          category, inputs[] with full typed schema, outputs[])
Jobs      GET /api/jobs?state=&page=   POST /api/jobs (multipart: workflow, job_name, <input ids>)
          GET /api/jobs/{id}  GET /api/jobs/{id}/status (light, for polling)
          POST /api/jobs/{id}/cancel  DELETE /api/jobs/{id}
          GET /api/jobs/{id}/log  (text/plain)   GET /api/jobs/{id}/outputs/{file_id}
Admin     GET /api/admin/dashboard → {queue: {paused, maintenance, maintenance_message, running,
          waiting, max_running, max_queue, worker: {ok, last_seen, age_seconds, pid}},
          jobs: {total, waiting, running, success, failed, cancelled},
          users: {total, active, admins}, workflows: {total, enabled, disabled, invalid},
          recent_jobs: [{id, name, state, workflow{id,name}, user{id,username}, submitted_at,
          started_at, finished_at}]}  (legacy pending/completed counted as waiting/success)
          POST /api/admin/queue/{pause|resume}  POST /api/admin/maintenance/{enter {message?}|exit}
          → queue block; they write `queue.paused` / `server.maintenance(_message)`
          GET /api/admin/jobs?state=&user=&workflow=&search=  POST /api/admin/jobs/{id}/cancel
          POST /api/admin/jobs/{id}/restart
          GET /api/admin/users?search=&group=&is_active=&page=&page_size= (paginated;
              row = User + is_superuser, activated_at; search: username/email/full name)
          GET /api/admin/users/{id}
          PATCH /api/admin/users/{id} {groups: [names], is_active, is_admin} → row. `groups`
              replaces membership by **name**; the `admin` group is ignored there and managed
              only by `is_admin` (admin group + is_staff together). Cannot deactivate/un-admin
              yourself; superusers stay admin (400).
          DELETE /api/admin/users/{id} → 204 (400 cannot_delete_self)
          GET /api/admin/groups → plain array [{id, name, member_count}] (not paginated)
          POST /api/admin/groups {name} → 201 (name unique ignoring case)
          DELETE /api/admin/groups/{id} → 204 (400 protected_group for `admin`)
          (old /api/users/ and /api/groups/ are removed)
          GET /api/admin/workflows → [{id, name, version, description, category, path, yaml_path,
          index, enabled, public, groups[], valid, errors[], warnings[], job_count}] (unpaginated;
          all apps incl. disabled + invalid)   GET /api/admin/workflows/{id} (+ yaml)
          PATCH /api/admin/workflows/{id} {enabled?, public?, groups[]? (names)}
          DELETE /api/admin/workflows/{id} (uninstall)   POST /api/admin/workflows/{id}/reload
          POST /api/admin/workflows/install {path, enabled?, public?, groups?, copy?} → 201;
          400 fields.path = definition errors; 409 id already installed
          POST /api/admin/workflows/sync
          GET/PUT /api/admin/workflows/{id}/nextflow {profile, work_dir, config, env} (+ read-only
          config_path, env_path, variables[{name, scope, description}])
          GET/PUT /api/admin/settings/general {name, url, max_running_jobs, max_queue_size,
          job_retention_days, max_upload_mb, maintenance, maintenance_message} (PUT = any subset)
          GET/PUT /api/admin/settings/mail {backend, file_path, host, port, user, use_tls, use_ssl,
          from_email, password_set (read)}; `password` write-only (''/absent = unchanged),
          `clear_password: true` removes it   POST /api/admin/settings/mail/test {to?} → {message,
          to} (default: the admin's e-mail; 502 `mail_failed` on SMTP errors)
          GET/PUT /api/admin/settings/nextflow {binary, profile, work_dir, config, env} (+ variables)
          GET/PUT /api/admin/settings/navbar {navbar: [...]} (errors keyed `navbar[i].title`)
          GET /api/admin/pages → [{slug, size, updated_at, deletable}]
          GET/PUT/DELETE /api/admin/pages/{slug} {html} (PUT creates → 201; home/footer → 400
          `protected` on DELETE)
          GET /api/admin/logs?level=&min_level=&component=&search=&page= → paginated
          [{id, timestamp, level (lower-case), component, logger, message, username, metadata}]
Health    GET /api/health → {status: ok|degraded|error, db: {ok}, worker: {ok, last_seen,
          age_seconds, pid}}; 200 unless the DB is down (503); no/stale worker = "degraded"
```
Exact request/response shapes are defined by the serializers and `schema.yaml`; this list is the
scope. Slice owners may refine paths but must update this section.

**Jobs & admin jobs (T03) — exact shapes.** Lists are paginated; every job payload uses `state`
(never `status`).

```jsonc
// item of GET /api/jobs, GET /api/admin/jobs   (JobListSerializer)
{"id": "<uuid>", "name": "My run 🚀", "state": "running",          // waiting|running|success|failed|cancelled
 "workflow_id": "hello", "workflow_name": "Hello", "workflow_version": "1.0.0",
 "user": "alice", "user_id": 2,
 "submitted_at": "...", "started_at": "...|null", "finished_at": "...|null",
 "duration_seconds": 12.5, "queue_position": null,                 // 1-based, only while waiting
 "cancel_requested": false, "expires_at": "...|null", "purged_at": null,
 "can_cancel": true, "can_delete": false, "can_restart": false}

// GET /api/jobs/{id}/status  = the item above plus
{"updated_at": "...", "error_message": "", "outputs_count": 2,
 "steps": [{"id": 7, "order": 0, "name": "Say hello", "state": "running",
            "started_at": "...", "finished_at": null,
            "processes": [{"name": "SAY", "label": "Saying", "submitted": 3, "running": 1,
                           "completed": 2, "failed": 0, "total": 3}]}],
 "messages": [{"id": 1, "level": "info", "text": "…", "step": 7, "created_at": "..."}]}

// GET /api/jobs/{id}, POST /api/jobs (201), POST .../cancel, POST /api/admin/jobs/{id}/{cancel,restart}
// = the status payload plus
{"inputs": [{"id": "message", "label": "Message", "type": "text", "value": "hi",
             "files": [{"name": "my data ü.csv", "size": 36}]}],   // value = display value
 "outputs": [{"id": 11, "output_id": "outdir", "label": "Output folder", "name": "hello.txt",
              "path": "outdir/hello.txt", "size": 3, "download_count": 0,
              "url": "/api/jobs/<uuid>/outputs/11/"}],
 "log_url": "/api/jobs/<uuid>/log/"}
```
- `POST /api/jobs` (multipart or JSON): `workflow` (id, `workflow_id` also accepted), optional
  `job_name` (`name` is accepted as an alias unless the workflow has an input called `name`), and
  one field per input id (`folder` inputs repeat the field; checkboxes send `true`/`false`).
  Errors: 400 `invalid` with `fields`, 404 `not_found` (unknown/forbidden workflow), 409
  `workflow_disabled` / `workflow_invalid`, 429 `queue_full`, 503 `maintenance`, 413
  `upload_too_large`.
- `GET /api/jobs?state=` accepts a comma-separated list; unknown values → 400. The list shows the
  caller's own jobs only (admins included); deleted jobs are never listed.
- `POST /api/jobs/{id}/cancel` → 200 job (`cancelled` when it was waiting, otherwise `running` with
  `cancel_requested: true`); 409 `invalid_state` when the job already finished.
- `DELETE /api/jobs/{id}` → 204 (finished jobs only, else 409 `invalid_state`); removes the
  workspace. Object access is owner-or-admin; everyone else gets **404** (jobs, status, log,
  outputs, cancel, delete).
- `GET /api/jobs/{id}/log` → `text/plain`: the worker/Nextflow stdout plus the tail of each
  `nextflow.log`.
- `GET /api/jobs/{id}/outputs/{file_id}` streams the file (`?inline=1` to display instead of
  download); 404 for a foreign/missing/unsafe path.
- `GET /api/admin/jobs` (admin only) lists **all** users' jobs with `?state=&user=<id|username>&
  workflow=<id>&search=<name|user|workflow|id prefix>`; `POST /api/admin/jobs/{id}/cancel` and
  `…/restart` return the job (restart: 409 `invalid_state`, `workspace_removed` or
  `workflow_unavailable`).
- Helper for the admin dashboard (T05): `jobs.services.queue_summary()` →
  `{paused, maintenance, running, waiting, max_running, max_queue}`.
- Workflows (public): `GET /api/workflows[/{id}]` returns `{id, name, description, version,
  website, author, logo, category_name, status, public, inputs[], outputs[], definition_errors[],
  max_upload_mb}`; `inputs`/`outputs` are `InputParam.to_dict()`/`OutputParam.to_dict()` (§4).

### 3.7 Frontend
- Vue 3 + Vite 5/6 + Pinia + Bootstrap 5. `src/api/*.js` is the only HTTP layer.
- Route guards use `/api/auth/me` (fetched on boot) — not `localStorage`.
- Job page polls `/api/jobs/{id}/status` while active; shows steps → tasks (from trace), messages,
  queue position, elapsed time; tabs: Details, Results, Logs.
- Dynamic form supports every input type in §4, client-side validation mirrors server rules, sends
  `multipart/form-data`, displays field-level errors from the envelope.
- Every interactive element that E2E tests need has a stable `data-testid`.

### 3.8 Application logging → Admin → Logs (T05)
- Log through `logging.getLogger('cloudgene.<area>')` (`cloudgene.jobs`, `cloudgene.auth`,
  `cloudgene.workflows`, `cloudgene.admin`, `cloudgene.api`, …). Records at INFO+ are stored in
  `admin_panel.SystemLog` by `admin_panel.logging.DatabaseLogHandler` (configured in
  `settings.LOGGING`), `component` = `<area>`. Pass `extra={'user': user, 'data': {...}}` to attach
  the acting user and JSON metadata. The handler never raises.
- What to log: logins/failed logins/lockouts (T04), job state changes and failures (T03), admin
  actions (T05: settings, pages, workflows, queue, maintenance).
- Retention: `manage.py cleanup_logs [--days 30]` (schedule with `cleanup_jobs`).

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
- 2026-09-20 (T03): job lifecycle, worker loop, Nextflow command/env/params, progress parsing,
  outputs/downloads, retention and restart written out (§3.3); job + admin-job payload shapes and
  error codes (§3.6); workflow definition parser rules and Python API (§4). State names are
  `waiting/running/success/failed/cancelled`, exposed as `state`; job submission fields are
  `workflow` + `job_name`; `WorkflowParameter`/`WorkflowExecution` removed (workflows 0004).
- 2026-09-19 (T05): workflow registry decisions (§3.2), per-app `apps[].profile/work_dir`, pages
  rules, admin/server endpoint shapes (§3.6), logging convention + SystemLog (§3.8); obsolete
  admin models removed.
- 2026-09-19 (T04): identity rules (case-insensitive username/e-mail, normalisation), shared
  field rules, login error codes + lockout, activation/reset token handling, profile/token and
  admin users/groups shapes (§3.4, §3.6); admin group managed via `is_admin` only; groups list
  unpaginated.
- 2026-09-19 (T01): config service API + `settings.yaml` key table (§3.2); auth details (login
  returns `{user}`, CSRF on login, 401 for unauthenticated, admin incl. superuser) (§3.4); error
  codes, optional trailing slash, pagination limits (§3.5); health payload (§3.6); worker
  heartbeat (§3.1).
- 2026-09-19: Initial audit. Decisions [D] in §3: drop Celery/Channels/Redis for DB worker + polling;
  YAML+files as single config source; session+CSRF auth for SPA; unified error envelope; state names
  `waiting/running/success/failed/cancelled`.
