# Task Board

Orchestrated by the lead agent. Each task runs in its own git worktree/branch and is merged to `main`
by the orchestrator after review + tests. Read `plans/SPEC.md` first; issue IDs (J1, A1, …) refer to
its issue register.

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

### T03 Jobs, execution & run form ◐
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

### T05 Server config, workflows admin & admin panel ◐ (code complete on `worktree-agent-abae60ae3ae8457c1`; D2 E2E xfail until T03's admin job endpoints)
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

### T06 Integration run ☐
Orchestrator merges T03–T05, resolves conflicts, runs `scripts/test.sh all`. Any failure → fix task.

### T07a/b/c Exploratory QA sessions ☐ (parallel, read-only on app code)
Charters: (a) run form & job lifecycle abuse (odd inputs, big/odd files, rapid submit/cancel, reload
mid-run); (b) security & access control (IDOR, privilege escalation, CSRF, path traversal, XSS in job
names/pages); (c) admin round-trips & multi-user scenarios (settings persistence, group changes taking
effect, queue under load). Output: `plans/QA_FINDINGS.md` + red tests in `e2e/tests/test_findings_*.py`.

### T08 Fix round(s) ☐
Created by orchestrator from QA findings.

---

## Phase 4 — Production readiness

### T09 Deployment & ops ☐
Postgres support verified (run unit suite against Postgres via docker-less local install or skip
with clear note), gunicorn + whitenoise static serving, systemd unit examples for web & worker,
`cleanup_jobs` scheduling, structured logging, security settings for prod (HSTS, secure cookies),
upload size limits, `docs/` rewritten (admin guide, workflow YAML reference, deployment), final README.

---

## Log
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

