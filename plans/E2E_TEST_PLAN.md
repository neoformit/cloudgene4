# Full-stack E2E Test Plan

Goal: catch **integration** errors (client ↔ API ↔ worker ↔ Nextflow ↔ filesystem ↔ e-mail) that unit
tests miss, in a form that agents can run, extend and interpret unattended.

## 1. Tool choice: Playwright (Python, pytest-playwright)

Chosen over Selenium because:
- Auto-waiting locators and web-first assertions (`expect(locator).to_have_text`) remove most
  sleep/flakiness issues that plagued `qa/selenium_*.py`.
- First-class **network and console hooks**: every test can fail automatically on any JS console
  error, uncaught exception, or unexpected 4xx/5xx `/api/` response — this is the single most
  valuable signal for contract drift.
- Trace viewer (`--tracing retain-on-failure`) gives agents a zip with DOM snapshots, network and
  console per step to diagnose failures without re-running.
- Same language as the backend: fixtures can seed the DB via Django ORM / management commands and read
  the file-based e-mail outbox directly.
- Headless Chromium runs fine on this host (Playwright-managed browser; system `chromium` as fallback).

## 2. Harness (`e2e/`)

```
e2e/
  conftest.py          # stack fixtures, auto-failing hooks, helpers
  stack.py             # boots/tears down the full stack
  fixtures/apps/       # test workflows (real Nextflow pipelines, tiny & fast)
     hello/            # text input -> ::message:: + output file          (~3 s)
     all-inputs/       # every input type incl. file, folder, checkbox, list, textarea writeFile
     fail/             # exits non-zero with ::error::
     slow/             # sleeps 60 s (for cancel / queue tests)
     multi-process/    # 3 processes, 5 tasks each (progress rendering)
  fixtures/files/      # upload fixtures (small csv, a file with spaces & unicode in its name)
  pages/               # page objects (LoginPage, RunPage, JobPage, Admin*)
  tests/
    test_smoke.py
    test_auth.py
    test_workflows.py
    test_jobs_submit.py
    test_jobs_lifecycle.py
    test_queue.py
    test_admin_*.py
    test_known_bugs.py
  README.md            # how to run, how to add a test, how to read traces
```

### Stack fixture (session-scoped, `stack.py`)
1. Create temp `CLOUDGENE_HOME` (copy `e2e/fixtures/apps`, write `config/settings.yaml` with small
   limits: `max_running_jobs: 2`, `max_queue_size: 5`, mail → file backend in temp dir).
2. Temp SQLite DB (`DATABASE_URL`), `migrate`, seed: admin (`admin`/`Admin1234`), user `alice`
   (group `researchers`), user `bob` (no groups); workflow access: `hello` public, `all-inputs` →
   researchers, others → admin only.
3. Build SPA once per session if `frontend/src` is newer than `static/frontend/index.html`
   (`npm run build`), so tests exercise the **production bundle** served by Django.
4. Start `manage.py runserver <free-port> --noreload` and `manage.py run_worker` as subprocesses with
   the same env; wait for `/api/health` to report db ok + worker heartbeat.
5. Yield `Stack(base_url, home, outbox_dir, django_shell())`; on teardown terminate both, dump their
   logs into the test report dir.
Per-test isolation: jobs are namespaced by unique names; tests that mutate global settings
(maintenance, pause, limits) restore them in a finalizer and are marked `@pytest.mark.serial`.

### Automatic guards (function-scoped autouse)
- Collect `page.on("console")` errors, `page.on("pageerror")`, and every `/api/` response with status
  ≥400. At teardown, fail unless the test declared it via `expect_api_error(status, path_glob)`.
- `--tracing retain-on-failure --screenshot only-on-failure`; artefacts in `e2e/.artifacts/`.

### Helpers
- `login(page, user)` via UI once per user, then reuse `storage_state` for speed.
- `latest_email(to)` parses the file outbox; `extract_link(mail, "/activate/")`.
- `wait_job_state(job_id, states, timeout)` polls the API (with the page's session cookie).
- `api(user)` — a `requests.Session` logged in via the API for arrange/assert steps (never for the
  action under test).

## 3. Test matrix (scenarios → spec features)

| # | Scenario | Asserts |
|---|----------|---------|
| S1 | Anonymous visits `/`, `/pages/about`, navbar & footer from YAML/pages | home.html rendered, navbar items in YAML order, admin-only items hidden |
| A1 | Register → e-mail → activate link → login | activation mail sent, login blocked before activation, user lands logged in |
| A2 | Register duplicate username/e-mail with different case | field error shown, no second user (K1) |
| A3 | Wrong password N times → lockout message | lockout, then success after window (setting shortened) |
| A4 | Password reset: request (unknown e-mail → same message), mail link, set new pw, login | |
| A5 | Profile: change name, e-mail, password (needs current), create/revoke API token, token works with `curl`-style request | |
| A6 | Delete own account | logged out, can't log in |
| A7 | Non-admin hits `/admin/*` routes and admin APIs | redirected / 403, no data leak |
| W1 | Workflow list per user: public / group / admin visibility; disabled hidden | |
| W2 | Run form renders every input type with defaults, help, required markers | all-inputs fixture |
| J1 | Submit `hello` with **job name containing spaces & unicode** (K3) | job page shows exact name, job reaches `success`, output downloadable & content correct |
| J2 | Submit with file upload (filename with spaces) + folder (multi-file) + textarea writeFile | files arrive in workspace, params.json correct, outputs downloadable |
| J3 | Client & server validation: missing required, number out of range, unchecked terms | field errors, no job created |
| J4 | Live progress: multi-process job | UI shows running → per-process task counts increase → success without reload; `::message::` rendered |
| J5 | Failing workflow | state failed, `::error::` message shown, log tab has Nextflow log |
| J6 | Cancel running (slow) job from job page | state cancelled within 10 s, no nextflow process left (ps check) |
| J7 | Cancel waiting job; delete finished job | |
| Q1 | Queue: submit 4 slow jobs with `max_running_jobs: 2` | 2 running, 2 waiting with positions 1,2; cancel one running → a waiting one starts **without any further request** (K2) |
| Q2 | Queue full → submit rejected with clear message | |
| Q3 | Worker killed mid-job and restarted | orphan marked failed, queue continues (K2) |
| Q4 | Admin pauses queue → new job stays waiting → resume → runs | |
| Q5 | Maintenance mode: banner for users, submission blocked, admin can still submit | |
| D1 | Admin dashboard numbers match reality after the above | |
| D2 | Admin jobs: filter by state/user, cancel another user's job, restart failed job | |
| D3 | Admin users: search, add/remove group via UI → user immediately gains/loses workflow access; activate/deactivate; delete. User count unchanged (K1) | |
| D4 | Admin workflows: disable/enable, set groups/public, edit Nextflow profile/config/env → next job's `nextflow.config` contains it; reload after YAML edit picks up new input | |
| D5 | Settings General/Mail/Nextflow: change, save, reload page → persisted in `settings.yaml`; mail password not echoed; "send test mail" lands in outbox | |
| D6 | Pages/templates: edit home & footer, create new page → visible at `/pages/<slug>`; path traversal slug rejected | |
| D7 | Logs page shows entries for job failures / logins | |
| X1 | Access control: bob opens alice's job URL, output URL, log URL | 404/403, no content |
| X2 | Deep links & refresh on every SPA route while logged in/out | correct page or login redirect with `next` |

## 4. Agent-driven testing workflow

Two modes, both run by agents:

1. **Scripted regression** (`pytest e2e -n 4 -m "not serial"` then `-m serial`): run after every task
   merge. A failing test blocks the merge. The agent attaches the trace path and first failing
   assertion in its report.
2. **Exploratory QA sessions** (charter-based): an agent is given a charter (e.g. "break the run
   form", "try to see other users' data", "admin settings round-trips"), drives the app with
   Playwright scripts written on the fly under `e2e/exploratory/`, and records findings in
   `plans/QA_FINDINGS.md` (ID, steps, expected, actual, severity, trace). Each confirmed finding is
   converted into a scripted test (red) before it is fixed. The orchestrator triages findings into
   `TASKS.md`.

## 5. Other test layers (kept, but secondary)
- Django unit/API tests (`python manage.py test`): permissions, validation, worker state machine
  (with a fake `nextflow` script on PATH), trace parser, config service, contract tests validating
  responses against `schema.yaml`.
- `schema.yaml` staleness check.
- Vitest: `src/api/*` + form components against schema fixtures.
- One entrypoint: `scripts/test.sh [unit|e2e|all]`.
