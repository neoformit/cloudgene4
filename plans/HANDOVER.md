# Handover — state of the repair effort (2026-09-27)

Branch: **`rebuild`** (not merged to `main`). All work below is on that branch.
Read next: `plans/SPEC.md` (what the app is + architecture), `plans/TASKS.md` (board + log),
`plans/QA_FINDINGS.md` (17 open defects), `plans/E2E_TEST_PLAN.md` (how to test).

## Where things stand

| Phase | Status |
|-------|--------|
| 1 Foundations (T01 platform, T02 E2E harness) | ☑ merged |
| 2 Slices (T03 jobs/worker, T04 accounts, T05 admin/config) | ☑ merged |
| 3 Integration (T06) + exploratory QA (T07a/b/c) | ☑ done — fix round T08 **not started** |
| 4 Production readiness (T09) | ☐ **on hold at user request, pending review** |

Test state on `rebuild` (orchestrator-verified):
`scripts/test.sh unit` → 282 Django + 144 vitest green.
`pytest e2e` → **167 passed, 16 xfailed, 0 failed** (11m37s). The 16 `xfail(strict=True)` tests
encode the open QA defects and will **fail loudly when each is fixed** (that is the signal to
delete the marker).

What was rebuilt: DB-backed worker + real Nextflow execution (trace/annotation progress, cancel,
outputs, retention), YAML-driven config/registry/pages/navbar, session+CSRF auth, case-insensitive
identity, admin panel, unified error envelope, OpenAPI contract with a staleness test, Playwright
full-stack suite. Celery, Channels and Redis were removed (SPEC §3.1). The three bugs named in the
original brief (duplicate users, job stuck pending, space in job name) are fixed and covered by
passing tests.

## Open work, in the order I would do it

### 1. T08 fix round — 17 QA defects (details + repro in `plans/QA_FINDINGS.md`)
Each has a red test; fixing one means deleting its `xfail` marker and seeing it pass.

**Do first (correctness/security):**
- **B-01 High** `/django-admin/` bypasses login lockout entirely and its session is accepted by the
  whole API. Decide: disable the Django admin in production, or route it through the same lockout.
- **A-04 High** a per-workflow Nextflow `work_dir` silently discards all results (job succeeds,
  no outputs). Two code paths disagree on allowed roots; `runner.work_dir_for` vs
  `outputs._allowed_roots`.
- **C-02 High** one invalid value in `settings.yaml` → every endpoint 500 after restart, `/api/health`
  still says `ok`, and the admin API cannot repair it. Needs fail-safe load + health check that
  reflects config validity.
- **A-03 High** SQLite write contention → intermittent 500s and skipped worker ticks; `GET
  /api/admin/workflows/` writes on every read (registry sync). Fix the write-on-read; consider WAL
  and a retry, and note Postgres is the production answer.
- **A-02 High** >100 files in a folder input → bare 500 (`DATA_UPLOAD_MAX_NUMBER_FILES` unset and
  Django's upload exceptions not mapped to the error envelope).
- **B-02/B-03 Medium** password change/reset leaves the API token valid; superuser can read every
  token in cleartext via Django admin.
- **B-04 Medium** job outputs served with a sniffed content type (`?inline=1`) → stored XSS from an
  HTML output on the app origin.
- **C-01 Medium** mail TLS/SSL mutual exclusion bypassable field-by-field → registration and password
  reset silently stop working.
- **C-03 Medium** deleting a user with a running job leaves the workspace behind and logs an
  unhandled `JobStep.NotUpdated` traceback.
- **A-01 / B-05 Medium** a file part sent for a text input is accepted and its filename becomes the
  value (DRF merges POST and FILES; `jobs/submission.py:_get` should reject file-like values).

**Then (polish):** A-05 number parsing differs FE/BE; C-04 log `component` values don't match the
documented filters; C-05 navbar `url` accepts `javascript:`; C-06 unknown `?level=` returns 200+empty
while unknown `?state=` returns 400; C-07 a broken app shows `enabled: true` while submissions 409.

**Product decisions needed (recorded as observations, not defects):** an omitted checkbox becomes
`false` even when the YAML default is `true`; a failed job can show the same `::error::` three times;
NUL bytes in text inputs reach `params.json`; registration reveals whether a username/e-mail exists
(currently deliberate).

### 2. T09 production readiness (on hold pending user review)
Postgres verification, gunicorn + static serving, systemd units for web **and worker**, structured
logging, prod security settings (HSTS/secure cookies/SSL redirect — `manage.py check --deploy` is
clean once `DJANGO_SECURE_COOKIES`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS` are set),
upload limits, `cleanup_jobs`/`cleanup_logs` scheduling, rewriting `docs/` (still stale from the old
implementation) and the final README.

Also for T09: **login costs ~3 s of PBKDF2 on a small host** — review hasher/iterations. The E2E
stack sets `INSECURE_FAST_PASSWORD_HASHING=1` (opt out with `E2E_REAL_HASHING=1`); that switch must
never be set in production.

### 3. Known gaps in the testing itself
- No Postgres run anywhere; everything is SQLite (A-03 is partly an artefact of that).
- Not probed: worker killed mid-job beyond scenario Q3, `max_running_jobs: 0`, maintenance toggled
  mid-run, very large pipeline logs, `local-file`/`local-folder` path semantics, HTTPS `Referer`
  checks, load/DoS.
- Exploratory probes live in `e2e/exploratory/` and are skipped by `pytest e2e`; run them with
  `E2E_EXPLORATORY=1 E2E_SKIP_BUILD=1 venv/bin/python -m pytest e2e/exploratory -q -s`.
- The e2e suite takes ~10 min on a 1-CPU host (JVM start-up dominates); don't run several stacks
  concurrently — they contend on SQLite and produce false failures.

## Process notes for whoever picks this up
- Agents worked in git worktrees off `rebuild`; the orchestrator merged and re-verified each one.
  Agent branches `worktree-agent-*` are all merged and can be deleted.
- Per user instruction: **spawn task agents on `sonnet`**, reserving `opus` for architecture,
  security analysis and conflicting-evidence triage (see the model policy at the top of `TASKS.md`).
- Keep `plans/SPEC.md` updated in the same commit as any contract change; `schema.yaml` must be
  regenerated after API changes or its staleness test fails.
- `task.md` and `briefing.md` in the repo root are the user's own files — leave them uncommitted.
