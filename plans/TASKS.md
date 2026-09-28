# Task Board

Orchestrated by the lead agent. Each task runs in its own git worktree/branch and is merged to `main`
by the orchestrator after review + tests. Read `plans/SPEC.md` first; issue IDs (J1, A1, …) refer to
its issue register.

**Model policy for task agents (user instruction, 2026-09-26)**
Spawn agents on the default model (`sonnet`) unless the task genuinely needs deeper reasoning.
Opus is reserved for: cross-cutting architecture/contract design, security analysis, and triage of
conflicting evidence. Routine work — applying a known fix, writing tests to a given spec, docs,
mechanical refactors, deployment config — goes to sonnet. State the chosen model when delegating.

**Rules for every task agent**
- Stay inside your *owned paths*. If you must touch another area, keep the change minimal and list it
  under "Cross-area edits" in your final report.
- Contract changes (endpoints, payload shapes, states, config keys) → update `plans/SPEC.md` §3 in the
  same commit.
- Every bug fix gets a failing test first (unit or E2E).
- Before reporting done: `python manage.py test` green, `npx vitest run` green, `npm run build` OK,
  and your E2E scenarios green (from Phase 2 on). Report exact commands and results — never claim green
  without running.
- Commit in small logical commits on your branch; do not merge to main yourself.

Status legend: ☐ todo · ◐ in progress · ☑ merged · ✖ blocked

---

## Phase 1 — Foundations (parallel: T01 ‖ T02)

### T01 Platform foundations ☑ (merged to `rebuild` 41e2e43; unit suite re-verified by orchestrator)
Owned: `cloudgene_django/`, `requirements.txt`, `frontend/package*.json`, `frontend/vite.config.js`,
`frontend/src/api/client.js`, `frontend/src/api/auth.js` (me/login/logout only), `frontend/src/stores/auth.js`,
`frontend/src/router/index.js` (guards only), new `core/` app, `scripts/`, repo-root cruft.
Scope:
1. Settings from env (`DJANGO_SECRET_KEY`, `DEBUG` default False, `ALLOWED_HOSTS`, `DATABASE_URL`,
   `CLOUDGENE_HOME`, `CSRF_TRUSTED_ORIGINS`); remove `print`; logging config. (P1)
2. Remove Celery, django-celery-results, Channels, channels-redis, `asgi` websocket routing,
   `celery.py`, `start-celery.sh`, `jobs/consumers.py`, `jobs/routing.py`. Leave `jobs/tasks.py`/`queue.py`
   in place but unimported if needed — T03 rewrites them. (P3, §3.1)
3. `core/config.py`: the config service of SPEC §3.2 (load/validate/defaults/mtime cache/atomic
   write/lock) for `settings.yaml`, plus helpers for `pages/`, `apps/`, `jobs/` paths. Default
   `CLOUDGENE_HOME` layout committed under `./home/` (settings.yaml migrated from
   `cloudgene_config.yaml`, `pages/home.html`, `pages/footer.html`, `pages/about.html`). Unit tests.
4. DRF: SessionAuthentication (CSRF enforced) + TokenAuthentication; global exception handler producing
   the SPEC §3.5 error envelope; pagination with `page_size`; `core.permissions.IsAdmin` +
   `core.permissions.is_admin(user)`. (A9, F5)
5. `GET /api/auth/me`, rework login/logout to session (login still returns user). `GET /api/health`
   (db ok + worker heartbeat read from a `core.WorkerHeartbeat` row — T03 writes it).
6. Frontend: axios `withCredentials`, CSRF cookie/header, `apiErrorMessage()` helper, 401 handling that
   does not hard-redirect for anonymous-allowed calls, auth store boots from `/api/auth/me`, router
   guards await it. Remove token from localStorage. (A2, F6)
7. Fix frontend test tooling (align vitest with vite; tests run). Make `*/contract_tests.py` discovered or
   fold them into `tests.py`; delete tests that assert obsolete behaviour; suite green.
8. `scripts/test.sh unit|e2e|all`; schema-staleness test (`spectacular --validate` vs committed
   `schema.yaml`).
9. Remove cruft: `qa/` debug scripts & stale reports (keep nothing that isn't runnable), 
   `IMPLEMENTATION_SUMMARY.md`, `TEST_SUMMARY.md`, `ui-plan.md`, `plans/contracts.md` (superseded),
   `cloudgene_config.yaml` (moved), `sample_workflow.yaml` (replaced by T03 fixtures). Update README
   dev quick-start (web + worker).
Done when: app boots with `runserver` alone; login/logout/me work via SPA with session; all existing
suites green; README quick-start accurate.

### T02 E2E harness ☑ (merged d5ab6eb; orchestrator re-ran: 52 passed, 7 xfailed, 1 skipped, 3m48s)
Owned: `e2e/` (new), `frontend/src/**` **only** for adding `data-testid` attributes.
Scope: implement E2E_TEST_PLAN §2 — stack fixture, auto-failing console/network guards, tracing,
helpers, page-object skeletons, fixture Nextflow apps (`hello`, `all-inputs`, `fail`, `slow`,
`multi-process`) each with a `cloudgene.yaml` per SPEC §4 and verified to run with plain
`nextflow run` in < 10 s (except slow), upload fixtures, `e2e/README.md`.
Write smoke tests S1 + A1(login part) + X2 now; they may be red until T01/T03 land — mark with
`pytest.mark.xfail(strict=False, reason="needs T0x")` and list them. Stack must tolerate a missing
`run_worker` command (skip worker, mark worker-dependent tests skipped).
Done when: `pytest e2e` runs headless on this host, produces traces on failure, and a human-readable
summary; fixture apps verified with Nextflow 26.04 (`/usr/local/bin/nextflow`).

---

## Phase 2 — Vertical slices (parallel after Phase 1 merge: T03 ‖ T04 ‖ T05)

Each slice owns its backend **and** frontend so both sides of every contract are changed together, and
writes the E2E scenarios listed.

### T03 Jobs, execution & run form ☑ (merged a11820f) (branch ready for review)
Owned: `jobs/`, `workflows/definition.py` (new: YAML parsing/validation of a workflow, SPEC §4),
public workflow endpoints (`workflows/views.py` public viewset + serializers for inputs/outputs),
`frontend/src/views/public/{WorkflowSubmit,JobList,JobDetail}View.vue`, `frontend/src/components/{jobs,workflows}/`,
`frontend/src/api/{jobs,workflows}.js`, `frontend/src/stores/jobs.js`.
Issues: J1–J11, W2, W4 (per-job vars), F1–F4, K2, K3.
Scope: SPEC §3.3 end to end — `run_worker` command (scheduler, executor, heartbeat, orphan
reconciliation, pause/maintenance from config), Nextflow runner, trace + stdout annotation parser,
state rename + data migration, submission with uploads, outputs & authenticated downloads, cancel
(process-group kill), delete, admin restart, retention `cleanup_jobs` command, status endpoint and
frontend polling, dynamic form for all SPEC §4 input types with client validation and field errors.
E2E: W2, J1–J7, Q1–Q5, X1 (jobs parts).

### T04 Accounts, profile & user admin ☑ (merged 1dbe4d6)
Owned: `accounts/`, `frontend/src/views/public/{Register,Activate,Login,PasswordReset,PasswordRecovery,Profile}View.vue`,
`frontend/src/views/admin/AdminUsersView.vue`, `frontend/src/components/admin/Group*.vue`,
`frontend/src/api/users.js`, `frontend/src/api/auth.js` (non-T01 parts).
Issues: A1, A3–A8, K1.
Scope: case-insensitive unique username/email (migration that detects & reports existing duplicates),
e-mail normalisation, idempotent activation, shared validation rules (backend is source; frontend
mirrors and shows server field errors), non-enumerating password reset, lockout, `/api/me` profile
endpoints (password change requires current password), token create/revoke, self-delete, admin
users/groups endpoints under `/api/admin/` with writable groups & is_active, no mass-assignment,
group member counts; mail sending uses mail settings from config service.
E2E: A1–A7, D3, X1 (profile/admin parts).

### T05 Server config, workflows admin & admin panel ☑ (merged 055f079) (code complete on `worktree-agent-abae60ae3ae8457c1`; D2 E2E xfail until T03's admin job endpoints)
Owned: `admin_panel/`, `workflows/` except `definition.py` and public endpoints, `core/` pages/navbar
views, `frontend/src/views/admin/**` except AdminUsersView, `frontend/src/components/layout/`,
`frontend/src/views/public/{Home,StaticPage}View.vue`, `frontend/src/stores/server.js`,
`frontend/src/api/admin.js`, `App.vue`.
Issues: W1, W3, W5, C1–C7, F7, (J4 via config keys, coordinate with T03 through SPEC).
Scope: `GET /api/server`, `/api/pages/{slug}`, navbar from YAML, maintenance banner; workflow registry
(install/reload/sync from `settings.yaml` → Workflow cache rows; access groups/public/enabled stored in
YAML); admin workflows (incl. disabled), per-app Nextflow settings files; admin settings
General/Mail/Nextflow (typed endpoints, write-only secrets, test mail); pages editor; dashboard incl.
queue controls (pause/resume, maintenance); admin jobs view (filters, cancel/restart — uses T03's
endpoints per SPEC §3.6); logs view (DB log handler or file tail); remove obsolete models.
E2E: S1, W1, D1, D2, D4–D7.

**Slice coordination points** (all via SPEC §3; update it first, then code):
- Workflow definition object (T03 `definition.py`) is consumed by T05 registry → T03 publishes the
  function signature `load_definition(path) -> WorkflowDefinition` early in its branch (first commit)
  and the orchestrator cherry-picks it for T05 if needed.
- Queue/maintenance keys in `settings.yaml` (`server.max_running_jobs`, `server.max_queue_size`,
  `server.maintenance`, `server.maintenance_message`, `queue.paused`) — defined by T01's config
  service (`core.config.get/set_value/update_settings`, key table in SPEC §3.2); T03 reads, T05 writes.
- Worker liveness: T03's `run_worker` calls `core.models.WorkerHeartbeat.beat(...)` each tick.
- Admin job actions endpoints are implemented by T03; T05 builds the UI.

---

## Phase 3 — Integration & agent-driven QA

### T06 Integration run ☑
Orchestrator merges T03–T05, resolves conflicts, runs `scripts/test.sh all`. Any failure → fix task.

### T07a/b/c Exploratory QA sessions ☑ (merged 7ea5329) (parallel, read-only on app code)
Charters: (a) run form & job lifecycle abuse (odd inputs, big/odd files, rapid submit/cancel, reload
mid-run); (b) security & access control (IDOR, privilege escalation, CSRF, path traversal, XSS in job
names/pages); (c) admin round-trips & multi-user scenarios (settings persistence, group changes taking
effect, queue under load). Output: `plans/QA_FINDINGS.md` + red tests in `e2e/tests/test_findings_*.py`.

### T08 Fix round ☑ — 17 defects in `plans/QA_FINDINGS.md` (read the entry for each ID first)
Three parallel sonnet agents, split by owned paths. Each finding already has a red
`xfail(strict=True)` test (`e2e/tests/test_findings_*.py`); fixing it = delete the marker and see
the test pass. Also add a Django unit test next to the code for each fix. C-06/C-07 have no red
test: write one. Rules from the top of this file apply (owned paths, SPEC §3 updated in the same
commit as any contract change, regenerate `schema.yaml` after API changes).

**User decisions (2026-09-27):**
- B-01: **keep `/django-admin/`** (all admin users are trusted) but route every login surface
  through the same lockout. Do not remove or env-gate the Django admin.
- The four "Observations"/I-7 items (omitted checkbox default, triple `::error::`, NUL bytes,
  registration revealing existing usernames) are **out of scope** — leave behaviour as is.

#### T08a Security & accounts ☑ (merged f4f3c61) — B-01, B-02, B-03, B-04
Owned: `accounts/`, `cloudgene_django/urls.py`, any new `admin.py`/auth-backend module,
`jobs/views.py` **only** `output_download`, matching frontend account views if a message changes.
- **B-01**: move the lockout (check `locked_until`, count failures, reset on success) out of
  `accounts.views.LoginView` into something every `authenticate()` call goes through — e.g. a custom
  authentication backend that refuses locked users plus a `user_login_failed` receiver that counts
  failures, keyed on the case-insensitive username. `LoginView` keeps returning 429
  `account_locked` exactly as today (existing lockout tests must stay green). The Django admin login
  must refuse a locked account and its wrong passwords must count.
- **B-02**: password change (`PATCH /api/me`) and password reset confirm delete the user's DRF
  `Token`. Mention it in SPEC §3.4 and in the profile UI's success message if there is one.
- **B-03**: no Django admin page may show a token key. Unregister DRF's `TokenProxy`/`Token` admin
  (or replace with a ModelAdmin that never renders `key`). Also check the `User` admin does not
  expose it.
- **B-04**: `output_download` must never serve active content on the app origin. Always
  `Content-Disposition: attachment` unless the type is on a small safe allowlist for inline
  (text/plain, image/png|jpeg|gif, application/pdf, application/json served as text/plain is fine);
  HTML/SVG/XML/JS/unknown → `application/octet-stream` + attachment. Add
  `Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff` on every download. Check
  what the frontend does with `?inline=1` and keep its preview working for the allowed types.

#### T08b Jobs, uploads & worker ☑ (merged d0fa260; C-03 hardened in c1721d8) — A-04, A-02, A-01/B-05, A-05, C-03, A-03 (worker half)
Owned: `jobs/` (except `output_download` view), `workflows/workflow_bridge*` if needed,
`core/exceptions.py`, upload settings in `cloudgene_django/settings.py`,
`frontend/src/components/workflows/form/` (only if A-05 needs it).
- **A-04**: one function decides a job's Nextflow work dir (per-app `apps[].work_dir`, else global,
  else default). `runner.work_dir_for` and `outputs._allowed_roots` must both use it, and so must
  `resolve_output_file`. Also add the fixture-free check that a symlink-published output under a
  per-app work dir is collected (the exploratory repro is `e2e/exploratory/probe_workdir.py`).
- **A-02**: set `DATA_UPLOAD_MAX_NUMBER_FILES` from config/env to a generous value (e.g. 10 000;
  document in SPEC), and map Django's `TooManyFilesSent`, `TooManyFieldsSent`, `RequestDataTooBig`
  (and other `SuspiciousOperation` upload errors) to the error envelope in
  `core/exceptions.api_exception_handler` — 413 `upload_too_large` / 400 as appropriate, never 500.
  Make sure the run form shows the message.
- **A-01/B-05**: a file part for a non-file input is a 400 `invalid` with `fields.<id>`; values for
  non-file inputs are read from `request.POST` (or `_get` rejects `UploadedFile`s). A typed value plus
  a file part for the same text field → 400 as well.
- **A-05**: `jobs/submission.parse_number` accepts exactly what `formModel.js`'s regex accepts
  (ASCII only: no `_`, no Unicode digits). Keep the existing rejects/min/max behaviour; decide on
  surrounding whitespace consistently with the frontend (check what the form sends).
- **C-03**: deleting a Job row whose execution is running must stop the execution *first* (or mark
  it and let the worker kill it and then remove the workspace), so nothing recreates the directory.
  The worker must treat "row vanished" (`JobStep.NotUpdated`, `DoesNotExist`) as a designed path:
  kill the process group, remove the workspace, log one INFO/WARNING line — no traceback.
- **A-03 (worker half)**: split `Worker.tick()` so a `database is locked` in one phase (heartbeat,
  reconcile, poll, claim) doesn't abandon the others; retry briefly on `OperationalError` locked.

#### T08c Config, admin & logs ☑ (merged d3cfa83) — C-02, A-03 (registry/DB half), C-01, C-05, C-04, C-06, C-07
Owned: `core/config.py`, `core/views.py` (health), `workflows/registry.py`, `admin_panel/`,
DATABASES block of `cloudgene_django/settings.py`, logger names anywhere (C-04, keep those edits
minimal and list them), `frontend/src/views/admin/`.
- **C-02**: a cold start with an invalid `settings.yaml` must not 500 the site. Load fail-safe:
  fall back to defaults per invalid key (or whole document if YAML is unparseable), remember the
  validation errors, log them once at ERROR. `/api/health` reports `status: "degraded"` with a
  `config: {ok: false, errors: [...]}` block naming the key(s). Admin settings PUTs must work in
  that state (write a corrected document). Show the config error on the admin dashboard.
- **A-03 (registry/DB)**: `registry.list_apps()` and every other read path use
  `sync_if_changed()` — a plain GET must not write. SQLite: enable WAL and
  `OPTIONS['transaction_mode'] = 'IMMEDIATE'` (only when the engine is sqlite). Note in SPEC that
  Postgres is the production database.
- **C-01**: TLS/SSL mutual exclusion validated against the merged (resulting) mail document, not the
  request body; also add the rule to the `core/config.py` schema so a hand-edited file is caught.
- **C-05**: navbar `url` must be an internal path (`/…`, not `//…`) or `http(s)://…`; reject
  everything else with a field error. Harden `AppNavbar.vue` to only render those as links too.
- **C-04**: logger names follow SPEC §3.8 (`cloudgene.auth`, `cloudgene.jobs`,
  `cloudgene.workflows`, `cloudgene.admin`, `cloudgene.api`; keep `cloudgene.worker` if SPEC lists
  it, else add it to SPEC). Job submit/cancel/delete in the web process log under `cloudgene.jobs`.
  Update the Logs page hint to the real list.
- **C-06**: unknown `level`/`min_level` on `/api/admin/logs/` → 400 like the jobs `state` filter.
- **C-07**: the admin workflow row reports the effective state (a broken/invalid app is not
  `enabled: true`) — pick a contract (e.g. keep `enabled` as configured and add `effective_status`,
  or make `enabled` effective) and put it in SPEC; update the admin UI.

**Merge order** (orchestrator): T08b → T08c → T08a, re-running `scripts/test.sh unit` after each and
the full `pytest e2e` after the last. Expected end state: 0 xfailed findings tests, 0 failed.

---

## Phase 4 — Production readiness

> **HOLD (user instruction, 2026-09-20): do not start Phase 4 until the user has reviewed Phase 3.**

### T09 Deployment & ops ☐
Postgres support verified (run unit suite against Postgres via docker-less local install or skip
with clear note), gunicorn + whitenoise static serving, systemd unit examples for web & worker,
`cleanup_jobs` scheduling, structured logging, security settings for prod (HSTS, secure cookies),
upload size limits, `docs/` rewritten (admin guide, workflow YAML reference, deployment), final README.

---

## Log
- 2026-09-20 T03 (branch `worktree-agent-aef1c0812f594f342`): jobs slice done. `workflows/definition.py`
  (cloudgene.yaml parser/validator, SPEC §4 + Python API); job model rework + data migration
  (`waiting/running/success/failed/cancelled`, `JobStep.processes`, `JobMessage`, `JobOutput`,
  `cancel_requested`, `deleted_at`, `purged_at`; `JobValue`/`JobDownload` dropped, `jobs/tasks.py`
  and `jobs/queue.py` removed); `manage.py run_worker` (single-instance lock, heartbeat, orphan
  reconciliation, pause/maintenance from config, atomic claim, Nextflow per step in its own process
  group, cancel SIGTERM→SIGKILL, graceful shutdown, `--once`); trace + stdout progress and
  `::message::` annotations (stdout **and** task `.command.out`, de-duplicated); submission with
  uploads/`writeFile`/typed params; outputs + authenticated downloads with traversal protection;
  jobs API incl. `/status`, cancel, delete, log, admin list/cancel/restart; `cleanup_jobs` and
  `install_workflow` commands; run form for every input type with client validation + field errors;
  job list/detail with polling (no WebSocket code left); E2E W2, J1–J7, Q1–Q5, X1 (jobs).
  Results: `manage.py test` 270 OK, `npx vitest run` 106 OK, `npm run build` OK, E2E see the T03
  report. Issues closed: J1–J11, W2, F1–F4, K2, K3 (W4 partly: admin editing of the Nextflow files
  is T05's).
- 2026-09-20 T05 (branch `worktree-agent-abae60ae3ae8457c1`): workflow registry
  (`workflows/registry.py`: settings.yaml `apps[]` → `Workflow` cache rows; install by path
  (reference in place, `--copy` optional), uninstall, reload, access, per-app Nextflow settings;
  adapter to T03's `definition.load_definition` with a built-in fallback validator; lazy sync
  middleware + `sync_workflows` / `install_workflow` commands; unknown group names ignored with a
  warning and pruned when a Group is deleted). Public `GET /api/server` + `/api/pages/{slug}`;
  admin dashboard/queue/maintenance, settings general|mail(+test)|nextflow|navbar, pages CRUD,
  logs, workflows API. `SystemLog` DB log handler for `cloudgene.*` (SPEC §3.8) + `cleanup_logs`.
  SPA: server store from `/api/server`, YAML navbar, footer, maintenance banner, Home/StaticPage,
  all admin views rewritten (dashboard controls, jobs filters, workflows, pages editor, logs),
  admin keeps the top navbar, sidebar only links real routes. Removed `ServerSettings`, `Template`,
  `NavbarItem`, `Counter*`, `config_loader`, `load_sample_workflow`, `WorkflowGroupModal`,
  `TemplateEditorView`. Issues W1, W3, C1–C7, F7 fixed; W4 partly (variable list/values; export →
  T03). Results: `manage.py test` 244 OK, vitest 152 OK, `npm run build` OK, `pytest e2e` see report.
- 2026-09-19 T04 (branch `worktree-agent-a6b97498ae34ab06e`): case-insensitive unique
  username/e-mail with `Lower()` constraints + normalisation (migration 0003 aborts listing
  existing duplicates; drops `UserGroup`/`UserToken`/unused fields); shared validation rules
  (`accounts/validation.py` ↔ `frontend/src/utils/validation.js`, one case table); idempotent
  POST activation, `require_activation`; per-user lockout (429 `account_locked`); non-enumerating
  hashed single-use reset; `/api/me` (+token, self-delete); `/api/admin/users|groups` (groups by
  name, `is_admin` toggle, member counts); `/api/auth/token/`, `/api/users/`, `/api/groups/`
  removed. Frontend views rewritten with server field errors and `data-testid`s; initials
  avatar. E2E `e2e/tests/test_accounts.py` (A1–A7, D3, X1 profile/admin).
- 2026-09-19 T01 (branch `worktree-agent-a64a5398a72765053`): Celery/Channels/Redis/CORS removed;
  env-driven settings + logging + whitenoise; `core` app (config service, `is_admin`/`IsAdmin`, error
  envelope handler, pagination, `WorkerHeartbeat`, `/api/health`, `/api/auth/me`, SPA view with CSRF
  cookie, JSON 404 for `/api/*`, optional trailing slash, `core.mail`, `create_admin`, temp-home test
  runner); session+CSRF login/logout; default `home/`; frontend session auth, `apiErrorMessage`,
  guards await `/me`; vitest 3.2; contract tests discovered; schema staleness test;
  `scripts/test.sh`; cruft removed; README rewritten. Results: `manage.py test` 171 OK, vitest 56 OK,
  `npm run build` OK. Cross-area edits and hand-over notes are in the T01 report.
- 2026-09-19: Audit complete; SPEC, E2E plan and task board drafted. Java 17 + Nextflow 26.04.6
  installed at `/usr/local/bin/nextflow` (verified: trace file + `::message::` stdout).
- 2026-09-19: T01 merged (171 Django + 56 vitest green). Phase 2 slices T03/T04/T05 started in parallel before T02 lands; they adopt the E2E harness when it merges.
- 2026-09-19: All four agents paused by an API session limit mid-task; resumed with context intact.
- 2026-09-19: T02 merged. Harness notes: per-xdist-worker stack, auto-fail guards on console/pageerror/
  API ≥400, summary at `e2e/.artifacts/summary.txt`. Nextflow fixture runs take 11–25 s on this 1-CPU
  host (JVM start-up), not <10 s. T02 findings routed to slices: submit contract must accept
  `workflow`/`name` (T03), WebSocket console errors on job page (T03, J6), legacy loader rejects §4
  types (T05, W2), escaped description HTML on home cards (T05), dashboard counts "-" (T05, C5), admin
  users Groups column empty (T04, A1), reset reveals account existence (T04, A5).
- 2026-09-20: T04 merged and re-verified by orchestrator: 230 Django + 114 vitest + e2e 61 passed /
  7 xfailed / 1 skipped. One e2e failure found on re-run (test_a3_lockout) was a host-speed problem,
  not an app bug: PBKDF2 costs ~3 s per check here, longer than the test's 3 s lockout window, so the
  lock expired during the login it should have blocked. Fixed in e80c5ad by an opt-in
  `INSECURE_FAST_PASSWORD_HASHING` env switch used only by the E2E stack (`E2E_REAL_HASHING=1`
  restores the production hasher). NOTE for T09: ~3 s per login on this class of host is a real
  production concern — review hasher/iterations and consider caching.
- 2026-09-20: T05 merged and re-verified by orchestrator on `rebuild`: 244 Django + 152 vitest OK;
  e2e 90 passed / 2 xfailed / 1 skipped (5m32s). The 2 e2e failures T05 reported were the pre-fix
  hashing/lockout interference (e80c5ad), not T05 regressions — they do not reproduce on `rebuild`.
  Remaining xfail/skip are all T03-dependent: D2 admin jobs, J1 unicode job name, Q1 queue (no worker).
- 2026-09-20: T03 merged. **Phase 2 complete.** Orchestrator verification on `rebuild` (a11820f):
  `scripts/test.sh unit` = 282 Django + 144 vitest OK; `pytest e2e` = **109 passed, 0 failed, 0 skipped,
  0 xfailed** (9m45s) — every scenario in E2E_TEST_PLAN §3 now runs against the real stack incl.
  Nextflow. K1/K2/K3 all covered by passing tests. T07 exploratory QA started.
- 2026-09-27: T07a/b/c merged. 17 confirmed defects in `plans/QA_FINDINGS.md`, each with a red
  `xfail(strict=True)` test; plus a green endpoint x role permission matrix (66 operations x 4 roles,
  58 tests). Highest severity: B-01 (/django-admin bypasses login lockout, session accepted by the
  API), A-04 (per-app nextflow work_dir silently discards all job outputs), C-02 (one bad
  settings.yaml value 500s the whole app and is unrepairable from the UI), A-03 (SQLite write
  contention -> intermittent 500s; admin workflow list writes on every read), A-02 (>100 uploaded
  files -> bare 500). Session ends here: see `plans/HANDOVER.md` for pickup.
- 2026-09-28: T08a/b/c merged to `rebuild` in order (T08b `d0fa260`, T08c `d3cfa83`, T08a
  `f4f3c61`). One merge conflict (`jobs/views.py`, two sides adding an import line — kept both);
  everything else auto-merged cleanly. `schema.yaml` regenerated (no diff both times) rather than
  hand-merged. Orchestrator verification after each merge: unit suites green throughout (296→305→
  **317 Django + 144 vitest** final); `npm run build` OK; full `pytest e2e` = **183 passed, 0
  failed, 0 xfailed** (4m44s) — every A-01..A-05/B-01..B-05/C-01..C-07 `xfail` marker is gone.
  Flakiness loop (5x): D6 5/5 passed; **C-03 failed 4/6 isolated runs** — root-caused to a genuine
  race in T08b's own C-03 fix (not a merge interaction): `Worker.claim()` set a job's status to
  `running` before its pid/pgid were persisted, and the post_delete signal only killed the process
  group when pgid/pid were present, so a delete landing in that window skipped the kill and
  rmtree'd immediately while Nextflow kept writing, recreating `.nextflow/`/`logs/` moments later.
  Reported to the user; fixed on their instruction in a follow-up commit `c1721d8` (design: **the
  worker owns the workspace of any claimed job** — the post_delete signal now only removes the
  workspace immediately for a job that was never claimed or already finished, and for a `running`
  job does nothing at all; the worker detects a vanished row at every write point (claim, current
  step, pid/pgid, a cheap pre-Popen existence re-check, JobStep/Job saves) plus a per-tick
  existence check in `poll_executions()` — since a quiet running execution may not write anything
  in a given tick — and always converges on `Execution.vanish()`: kill the process group, wait for
  it to exit, then remove the workspace). Re-verified after the fix: unit **319 Django + 144
  vitest** OK; C-03 **10/10** isolated runs passed; D6 **5/5**; full `pytest e2e` re-run once more
  = **183 passed, 0 failed, 0 xfailed** (4m54s). Notes for T09: C-03's cleanup is entirely
  worker-owned now (no /proc kill from the web process, so the same-host assumption from the first
  T08b fix is gone — if web and worker are ever split across hosts this still holds, since only the
  worker touches the process/workspace); the orphan sweep in `manage.py cleanup_jobs` remains the
  backstop when no worker is running at all. SQLite now uses WAL + `transaction_mode=IMMEDIATE`
  (Postgres remains the intended production database). `playwright==1.56.0` must stay pinned in the
  venv to match `/opt/pw-browsers` on this host — never `pip install -r e2e/requirements.txt` or
  `playwright install`. Docs updated (`QA_FINDINGS.md`, this file, `HANDOVER.md`) and pushed to
  `origin/rebuild`.

