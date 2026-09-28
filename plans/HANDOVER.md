# Handover — state of the repair effort (2026-09-28)

Branch: **`rebuild`** (not merged to `main`). All work below is on that branch.
Read next: `plans/SPEC.md` (what the app is + architecture), `plans/TASKS.md` (board + log),
`plans/QA_FINDINGS.md` (all 17 defects fixed — see its Status block), `plans/E2E_TEST_PLAN.md`
(how to test).

## Where things stand

| Phase | Status |
|-------|--------|
| 1 Foundations (T01 platform, T02 E2E harness) | ☑ merged |
| 2 Slices (T03 jobs/worker, T04 accounts, T05 admin/config) | ☑ merged |
| 3 Integration (T06) + exploratory QA (T07a/b/c) | ☑ done |
| T08 fix round (17 QA defects) | ☑ merged and verified |
| **4 Production readiness (T09)** | ☑ **merged and verified — see below** |

**All four phases are done.** Test state on `rebuild` (orchestrator-verified after every T09
merge/commit):
`scripts/test.sh unit` (SQLite) → **348 Django + 144 vitest** green.
`scripts/test.sh unit --postgres` (PostgreSQL 16, role/db `cloudgene`/`cloudgene` on
`127.0.0.1:5432`) → **348 Django + 144 vitest** green.
`pytest e2e` on SQLite → **183 passed, 0 failed, 0 xfailed** (4m22s).
`pytest e2e` on Postgres (`E2E_DATABASE_URL=postgres://cloudgene:cloudgene@127.0.0.1:5432/
cloudgene`) → **183 passed, 0 failed, 0 xfailed** (4m40s) — same scenario count, no
Postgres-specific regressions. `manage.py check --deploy` against
`deploy/cloudgene.env.example`: 0 issues (1 silenced, `security.W021`, by design — see the
HSTS-preload note below). `npm run build` and `scripts/smoke_gunicorn.sh --skip-build`
(production stack: gunicorn + whitenoise, `DEBUG=False`) both OK.

What was rebuilt: DB-backed worker + real Nextflow execution (trace/annotation progress, cancel,
outputs, retention), YAML-driven config/registry/pages/navbar, session+CSRF auth, case-insensitive
identity, admin panel, unified error envelope, OpenAPI contract with a staleness test, Playwright
full-stack suite, and now a production deployment story (gunicorn + systemd + nginx + Postgres,
Argon2id password hashing, JSON logging, deploy-time security checks). Celery, Channels and Redis
were removed (SPEC §3.1). The three bugs named in the original brief (duplicate users, job stuck
pending, space in job name) are fixed and covered by passing tests.

## Open work, in the order I would do it

### 1. T08 fix round — done
All 17 QA defects are fixed and merged to `rebuild`; see `plans/QA_FINDINGS.md`'s Status block for
the merge commit of each group (T08a/b/c) and `plans/TASKS.md`'s 2026-09-28 log entry for the full
verification (unit/E2E counts, the C-03 race that was found and fixed after the first merge, and
the flakiness-loop results). The four "Observations"/I-7 items in `QA_FINDINGS.md` were reviewed by
the user on 2026-09-27 and left as-is (no change).

### 2. T09 production readiness — done
Merged in order T09b `ebaeed4` (Postgres) → T09a `63aee1b` (deploy & ops: gunicorn, systemd,
nginx, Argon2id, deploy checks, JSON logging, JSON body-size limit, `docs/DEPLOYMENT.md`) → T09c
part 1 `d3f9cbe` (docs rewrite: `ADMIN_GUIDE.md`, `WORKFLOW_YAML_REFERENCE.md`, `API.md`) — all
three merged cleanly (no manual conflict resolution needed, including in `e2e/stack.py` which both
T09a and T09b touched). Two follow-up orchestrator commits: `563d8a9` made `SECURE_HSTS_PRELOAD`
opt-in and off by default (T09a had it default on with HSTS, which is wrong — preload is a
hard-to-reverse commitment covering every subdomain once submitted to browsers' preload lists);
`7f72ce1` (T09c part 2) rewrote `README.md` — every quick-start step was actually run against a
scratch `CLOUDGENE_HOME` on this host — added a docs link check, and corrected
`docs/ADMIN_GUIDE.md`, which never mentioned the "last remaining admin" guard on a lone admin's own
`DELETE /api/me` (400 `last_admin`, already tested); `plans/QA_FINDINGS.md`'s claim that last-admin
deletion is refused was the accurate one. Full verification: `scripts/test.sh unit` green on both
SQLite and Postgres (348 Django + 144 vitest each), `npm run build` and
`scripts/smoke_gunicorn.sh --skip-build` OK, `manage.py check --deploy` clean against
`deploy/cloudgene.env.example` (0 issues, 1 silenced by design), full `pytest e2e` green on both
SQLite (183 passed, 4m22s) and Postgres (183 passed, 4m40s). See `plans/TASKS.md`'s 2026-09-28 log
entry for the complete write-up (login timing, the HSTS decision, the worker
`ProtectSystem=strict`/`ReadWritePaths` note, and the JSON-body-limit/nginx note).

Login timing on this host (real hashers): PBKDF2 ~0.329 s, Argon2id ~0.085 s (~4x faster) — the
earlier ~3 s figure noted after T04 did not reproduce. The E2E stack still sets
`INSECURE_FAST_PASSWORD_HASHING=1` (opt out with `E2E_REAL_HASHING=1`); a startup check
(`core.checks`, `core.E001`) now refuses to run with that switch on when `DEBUG` is off unless
`CLOUDGENE_E2E=1` is also set, so it can't leak into production.

### 3. Known gaps in the testing itself
- Postgres is now fully verified (T09b/T09, 2026-09-28): unit suite and the full E2E suite both
  green against PostgreSQL 16, plus a dedicated concurrency test proving the worker's claim UPDATE
  is race-free. See `plans/SPEC.md` §3.1 and `e2e/README.md`.
- Not probed: worker killed mid-job beyond scenario Q3, `max_running_jobs: 0`, maintenance toggled
  mid-run, very large pipeline logs, `local-file`/`local-folder` path semantics, HTTPS `Referer`
  checks, load/DoS.
- Exploratory probes live in `e2e/exploratory/` and are skipped by `pytest e2e`; run them with
  `E2E_EXPLORATORY=1 E2E_SKIP_BUILD=1 venv/bin/python -m pytest e2e/exploratory -q -s`.
- The e2e suite takes ~4-5 min per full run on this host; don't run several stacks concurrently —
  they can contend on SQLite/Postgres and produce false failures.
- No real systemd boot test was done (the units in `deploy/systemd/` are reviewed and used by
  `scripts/smoke_gunicorn.sh` in spirit, but never actually installed and started under systemd on
  a real machine — worth doing before a first production rollout).
- No load/stress test of the worker or the web process (concurrent submissions, sustained upload
  traffic, queue depth under real load) — only functional/concurrency-correctness tests exist.

## Process notes for whoever picks this up
- Agents worked in git worktrees off `rebuild`; the orchestrator merged and re-verified each one.
  Agent branches `worktree-agent-*` are all merged and can be deleted.
- Per user instruction: **spawn task agents on `sonnet`**, reserving `opus` for architecture,
  security analysis and conflicting-evidence triage (see the model policy at the top of `TASKS.md`).
- Keep `plans/SPEC.md` updated in the same commit as any contract change; `schema.yaml` must be
  regenerated after API changes or its staleness test fails.
- `task.md` and `briefing.md` in the repo root are the user's own files — leave them uncommitted.
- Environment: this host's venv runs **Python 3.12** with Django 6.0 (raises `ObjectNotUpdated`
  from `Model.save(update_fields=...)` when a row was deleted under it — the C-03 fix leans on
  that). `playwright==1.56.0` is pinned in `requirements.txt`/the venv to match the browsers
  preinstalled at `/opt/pw-browsers`; never `pip install -r e2e/requirements.txt` or
  `playwright install` on this host, or the pinned version drifts from the installed browsers.
