# Full-stack E2E tests

Playwright (Python) tests that drive the **production SPA bundle served by Django**, backed by a
real DB, the job worker and real Nextflow runs. Strategy and scenario matrix:
`plans/E2E_TEST_PLAN.md`.

## Setup (once per machine)

```bash
venv/bin/pip install -r e2e/requirements.txt
venv/bin/python -m playwright install --with-deps chromium   # may need sudo for --with-deps
(cd frontend && npm install)
```

Nextflow must be on `PATH` (or set `E2E_NEXTFLOW=/usr/local/bin/nextflow`).

## Running

```bash
scripts/test.sh e2e                                 # same as below, via the repo entry point
venv/bin/python -m pytest e2e                       # everything, headless
venv/bin/python -m pytest e2e -n 4 -m "not serial"  # parallel (one stack per xdist worker)
venv/bin/python -m pytest e2e -m serial             # tests that change global state, never with -n
venv/bin/python -m pytest e2e -k deep_links         # a subset
venv/bin/python -m pytest e2e --headed --slowmo 300 # watch the browser
venv/bin/python -m pytest e2e --runxfail            # show why the xfail tests currently fail
venv/bin/python e2e/fixtures/verify_apps.py         # fixture pipelines with plain `nextflow run`
```

Each pytest process (each xdist worker) boots its own stack in `e2e/.artifacts/stack-<worker>/`:
fresh `CLOUDGENE_HOME` (`config/settings.yaml`, `pages/*.html`, `apps/<fixture apps>`, `jobs/`),
SQLite DB, `migrate`, seed, `manage.py runserver <free port> --insecure` and, if the command
exists, `manage.py run_worker`. The SPA is rebuilt (`npm run build`) only when `frontend/` sources
are newer than `static/frontend/index.html`; set `E2E_SKIP_BUILD=1` to use the existing bundle.

Every stack process runs with plain project settings configured by env (SPEC §3.2):
`DJANGO_SETTINGS_MODULE=cloudgene_django.settings`, `CLOUDGENE_HOME=<stack>/home`,
`DATABASE_URL=sqlite:////<stack>/db.sqlite3`, `DJANGO_SECRET_KEY`, `DEBUG=False` (`E2E_DEBUG=True`
to override), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `LOG_LEVEL` (`E2E_LOG_LEVEL`). Mail uses
`mail.backend: file` from the generated settings.yaml; the outbox is `$CLOUDGENE_HOME/mail`
(`stack.outbox_dir`). The admin is created with `manage.py create_admin`, other users by
`e2e/seed.py`. So a run never touches the developer's DB, `home/` or mail.

Seed data (`e2e/constants.py`, applied by `e2e/seed.py`):

| user  | password  | groups      | notes |
|-------|-----------|-------------|-------|
| admin | Admin1234 | admin       | via `manage.py create_admin` |
| alice | Alice1234 | researchers | |
| bob   | Bob12345  | —           | |

Apps: `hello` public, `all-inputs` → researchers, `fail`/`slow`/`multi-process` → admin only.
Limits: `max_running_jobs: 2`, `max_queue_size: 5`.

## Artefacts — where to look when something fails

| what | where |
|------|-------|
| one-line-per-test summary with first error, guard findings and trace path | `e2e/.artifacts/summary.txt` |
| Playwright trace (DOM snapshots, network, console per step) + screenshot, failures only | `e2e/.artifacts/playwright/<test-id>/trace.zip` → `venv/bin/python -m playwright show-trace <zip>` |
| server / worker / migrate / create_admin / seed / frontend-build logs | `e2e/.artifacts/stack-<worker>/logs/` |
| the stack's home (settings.yaml, pages, apps, job workspaces, `mail/` outbox), DB | `e2e/.artifacts/stack-<worker>/{home,db.sqlite3}` |

`e2e/.artifacts/` is wiped per stack at the start of the next run.

## Automatic guards (every test using `page`)

A test **fails after its body passed** if the browser saw a `console.error`, an uncaught exception
or unhandled rejection, a same-origin response ≥ 400 (API or asset) or a failed same-origin request.
The failure lists every finding (method, path, status, first 300 bytes of the body). If the error
is the point of the test, declare it *before* triggering it:

```python
def test_wrong_password(page, expect_api_error, expect_console_error):
    expect_api_error((400, 401), '/api/auth/login*')   # int, iterable or None (= any status)
    expect_console_error('Login failed')              # substring or re.compile(...)
```

Declarations only allow errors; they don't require them. `tests/test_harness_selftest.py` proves
the guards work (inner pytest run against a fake origin).

## Fixtures & helpers

| name | what |
|------|------|
| `stack` | session `Stack`: `base_url`, `home`, `outbox_dir`, `manage(*args)`, `django_shell(code)`, `read_settings()/write_settings()`, `require_worker()`, `worker_available` |
| `page` | pytest-playwright page with guards attached; `page.goto('/jobs')` is relative to the stack |
| `login(page, user, fresh=False)` | UI login once per user per stack, then reuses the storage state; `fresh=True` always uses the UI and doesn't cache (use it when the test logs out) |
| `user_page(user)` | extra browser context + page (guarded) logged in as `user` — for multi-user tests |
| `api(user=None)` | `helpers.ApiClient` (requests session: session cookie + CSRF, legacy token) for **arrange/assert only**: `get_json`, `post_json`, `submit_job(workflow, name, params, files)`, `get_job`, `job_status`, `cancel_job` |
| `requires_worker` | skip unless `run_worker` runs (or call `stack.require_worker()` mid-test) |
| `server_settings` | `update(section, **values)` on settings.yaml, restored after the test — mark the test `serial` |
| `expect_api_error`, `expect_console_error` | see above |
| `helpers.wait_job_state(client, job_id, states, timeout)` | API polling; fails fast on an unwanted final state |
| `helpers.latest_email(stack.outbox_dir, to=...)`, `extract_link(msg, '/activate/')` | file outbox |
| `e2e.pages` | `Navbar`, `LoginPage`, `RunPage`, `JobPage` page objects |

## Writing a test

1. Put it in `e2e/tests/test_<area>.py`; name it after the scenario ID in the plan (S1, J1, Q1…) in the
   module docstring.
2. Drive the **action under test through the UI**; use `api()` only to arrange or to assert
   server-side state.
3. Locate elements by `data-testid` only (`page.get_by_test_id(...)`). If an element lacks one, add
   it to the Vue component (attribute-only change). Current ids: `navbar`, `nav-brand`, `nav-home`,
   `nav-jobs`, `nav-item` (each configurable navbar entry — keep it when the navbar comes from YAML),
   `nav-user-menu`, `nav-profile`, `nav-admin`, `nav-logout`, `nav-signup`, `nav-login`, `footer`,
   `login-username/-password/-submit/-error`, `home-content`, `workflow-card` (`data-workflow-id`),
   `workflow-run`, `page-content`, `page-not-found`, `run-form`, `workflow-title`, `job-name`,
   `job-submit`, `run-error`, `input-<param id>` (wrapper of each run-form input), `job-state`
   (`data-state` = job state), `job-title`, `job-cancel`, `job-queue-position`, `job-tab-details`,
   `job-tab-results`, `job-tab-logs`, `job-output-link` (`data-filename`), `job-error`.
4. Use web-first assertions (`expect(locator).to_have_text(...)`) — never `sleep` to wait for UI.
5. Namespace any data you create (unique job names / users) so tests can run in any order.
6. Mark tests that change global state (settings.yaml, queue pause, maintenance, limits) with
   `@pytest.mark.serial` and restore state in a fixture finalizer (`server_settings` does this).
7. Tests for behaviour that isn't built yet: `@pytest.mark.xfail(strict=False, reason="needs T0x: <what>")`.
   Remove the marker in the task that implements it.

## Interpreting results (for agents)

- **FAILED with "unexpected browser error(s)"**: the scenario worked visually but the page hit a
  4xx/5xx or logged an error — usually a frontend↔API contract drift. The finding names the
  request; check the server log for the traceback.
- **FAILED on a locator/assertion**: open the trace; the "Aria snapshot" in the error shows what
  the page rendered instead.
- **ERROR at setup of `stack`**: the stack didn't boot (build, migrate, seed, runserver, worker).
  The message includes the tail of the relevant log in `e2e/.artifacts/stack-*/logs/`.
- **XFAIL**: expected until the named task lands. **XPASS**: that task landed — remove the marker.
- **SKIPPED "no `manage.py run_worker` command"**: worker not implemented yet (T03).
- Report: exact command, totals line, and for each failure the first error line + trace path from
  `summary.txt`. Never re-run until green without explaining the flake.
