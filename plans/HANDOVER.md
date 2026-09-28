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
| **T08 fix round (17 QA defects)** | ☑ **merged and verified — see below** |
| 4 Production readiness (T09) | ☐ **on hold at user request, pending review** |

Test state on `rebuild` (orchestrator-verified after T08a/b/c merged, plus a follow-up C-03
hardening fix, `c1721d8`):
`scripts/test.sh unit` → **319 Django + 144 vitest** green.
`pytest e2e` → **183 passed, 0 failed, 0 xfailed** (4m54s). Every `xfail(strict=True)` marker for
A-01..A-05, B-01..B-05 and C-01..C-07 is gone. Flakiness loops (isolated, repeated): D6 5/5,
C-03 10/10.

What was rebuilt: DB-backed worker + real Nextflow execution (trace/annotation progress, cancel,
outputs, retention), YAML-driven config/registry/pages/navbar, session+CSRF auth, case-insensitive
identity, admin panel, unified error envelope, OpenAPI contract with a staleness test, Playwright
full-stack suite. Celery, Channels and Redis were removed (SPEC §3.1). The three bugs named in the
original brief (duplicate users, job stuck pending, space in job name) are fixed and covered by
passing tests.

## Open work, in the order I would do it

### 1. T08 fix round — done
All 17 QA defects are fixed and merged to `rebuild`; see `plans/QA_FINDINGS.md`'s Status block for
the merge commit of each group (T08a/b/c) and `plans/TASKS.md`'s 2026-09-28 log entry for the full
verification (unit/E2E counts, the C-03 race that was found and fixed after the first merge, and
the flakiness-loop results). The four "Observations"/I-7 items in `QA_FINDINGS.md` were reviewed by
the user on 2026-09-27 and left as-is (no change).

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
- Environment: this host's venv runs **Python 3.12** with Django 6.0 (raises `ObjectNotUpdated`
  from `Model.save(update_fields=...)` when a row was deleted under it — the C-03 fix leans on
  that). `playwright==1.56.0` is pinned in `requirements.txt`/the venv to match the browsers
  preinstalled at `/opt/pw-browsers`; never `pip install -r e2e/requirements.txt` or
  `playwright install` on this host, or the pinned version drifts from the installed browsers.
