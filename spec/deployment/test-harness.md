# Test Harness

## Purpose

This file specifies the machinery that runs Cloudgene's test suites against real processes: the
single entry point `scripts/test.sh`, the production-server smoke test
`scripts/smoke_gunicorn.sh`, and the Playwright e2e harness under `e2e/` (stack boot, fixtures,
guards, helpers, seed data, fixture apps, exploratory probes). It also specifies the planned
hosted CI that runs them. It owns harness **mechanics** (what is built, booted, asserted, torn
down and how it exits). Suite **policy** (which suites must pass, layer rules, coverage,
traceability) is owned by [backend tests](../backend/tests.md) and
[frontend tests](../frontend/tests.md).

## Scope

| Path | What |
|---|---|
| `scripts/test.sh` | Entry point: `unit`, `e2e`, `all` modes, `--postgres` flag |
| `scripts/smoke_gunicorn.sh` | Builds SPA, collectstatic, boots gunicorn, asserts shell/asset/health |
| `e2e/stack.py` | Per-process stack: home, DB, build, `runserver`, `run_worker`, teardown |
| `e2e/conftest.py` | Fixtures, Playwright output dir, `summary.txt` |
| `e2e/guards.py` | Browser error guard plugin |
| `e2e/helpers.py`, `e2e/admin_helpers.py` | API client, polling, outbox, `/proc` scan, DB arrange helpers |
| `e2e/seed.py`, `e2e/constants.py` | Seed users/workflows; shared seed constants |
| `e2e/pytest.ini`, `e2e/requirements.txt`, `e2e/.gitignore` | pytest config, harness deps, ignored `.artifacts/` |
| `e2e/fixtures/apps/`, `e2e/fixtures/files/`, `e2e/fixtures/verify_apps.py` | Fixture workflows, upload files, plain-Nextflow check |
| `e2e/exploratory/` | Opt-in probes, `serve.py`, `arrange.py`, `matrix.py`, `probe.py` |
| (absent) CI configuration | Planned hosted CI (DEP-HARN-070 to DEP-HARN-075) |

Out of scope: the content of test modules (`e2e/tests/*.py`, Django tests, vitest) and suite
policy — see [backend tests](../backend/tests.md) BE-TEST-001, BE-TEST-009, BE-TEST-013..016,
BE-TEST-019, BE-TEST-021 and [frontend tests](../frontend/tests.md) FE-TEST-001, FE-TEST-007,
FE-TEST-008. Page objects (`e2e/pages/`) are covered by FE-TEST-009. Traceability of
deployment requirements is in [tests.md](tests.md). The Django test runner
(`core/test_runner.py`) is BE-TEST-011.

## Dependencies

- [backend/tests.md](../backend/tests.md) — step order of `scripts/test.sh unit` (BE-TEST-001),
  DB engines (BE-TEST-009), e2e isolation/guard/serial/exploratory policy (BE-TEST-013..016),
  CI policy (BE-TEST-019).
- [backend/server-pages-mail.md](../backend/server-pages-mail.md) — `health` operation
  (`/api/health/`), pages, file mail backend.
- [backend/job-queue-worker.md](../backend/job-queue-worker.md) — `run_worker`, heartbeat.
- [backend/management-commands.md](../backend/management-commands.md) — `create_admin`,
  `sync_workflows`, `run_worker`.
- [backend/workflow-registry.md](../backend/workflow-registry.md) — `registry.sync_all` used by seed.
- [backend/configuration.md](../backend/configuration.md) — `settings.yaml` schema written by the stack.
- [environment-config.md](environment-config.md) — `DATABASE_URL`, `DEBUG`,
  `INSECURE_FAST_PASSWORD_HASHING`, `CLOUDGENE_E2E`, `GUNICORN_*`.
- [web-server.md](web-server.md) — `deploy/gunicorn.conf.py` booted by the smoke test.
- [static-assets.md](static-assets.md) — SPA build, collectstatic, asset caching asserted by smoke.
- [security-hardening.md](security-hardening.md) — `check --deploy`, core.E001 (fast hashing guard).
- Contract operations used by the harness (via `e2e/helpers.py` and `stack.py`): `health`,
  `auth_login_create`, `jobs_create`, `jobs_status_retrieve`, `jobs_cancel_create`; see
  [backend/api-contract.md](../backend/api-contract.md).

## Requirements

**`scripts/test.sh`** (step order and modes: BE-TEST-001)

- **DEP-HARN-001** — `scripts/test.sh` MUST `cd` to the repository root before running anything,
  so it behaves the same from any working directory. It MUST pick the interpreter as `$PYTHON`,
  else `./venv/bin/python` if executable, else `python3`.
- **DEP-HARN-002** — `--postgres` MUST be accepted anywhere after the mode and removed from the
  argument list. In `unit` mode it MUST set `DATABASE_URL` to `$TEST_DATABASE_URL` (default
  `postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene`) for `manage.py test` only. The script
  MUST NOT start a database server.
- **DEP-HARN-003** — The script MUST run with `set -euo pipefail`: the first failing step MUST end
  the run with that step's non-zero exit status, and `==> OK (<mode>)` MUST be printed only when
  every step passed. Arguments other than `--postgres` MUST reach `pytest e2e` unchanged in `e2e`
  and `all` modes.
- **DEP-HARN-004** (planned) — `--postgres` in `e2e` or `all` mode MUST run the e2e suite on
  Postgres by exporting `E2E_DATABASE_URL=$TEST_DATABASE_URL`, or the script MUST exit 2 with a
  usage line. It MUST NOT be silently ignored.
- **DEP-HARN-005** — The vitest step MUST run `npm ci` in `frontend/` when
  `frontend/node_modules` is missing, then `npx vitest run`.

**`scripts/smoke_gunicorn.sh`**

- **DEP-HARN-010** — Unless the first argument is `--skip-build`, the script MUST run
  `npm run build` in `frontend/`. It MUST exit 1 with `FAIL:` when
  `static/frontend/index.html` is missing afterwards.
- **DEP-HARN-011** — The script MUST run against a throw-away environment: a `mktemp -d`
  directory holding `CLOUDGENE_HOME` and a SQLite `DATABASE_URL`, `DEBUG=False`, a fixed
  non-secret `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS=127.0.0.1,localhost`. On any exit it MUST kill
  gunicorn and delete that directory.
- **DEP-HARN-012** — It MUST run `migrate --noinput` and `collectstatic --noinput --clear` (into the
  `STATIC_ROOT` of DEP-HARN-017), print the log and exit 1 if either fails, and exit 1 if
  `<STATIC_ROOT>/frontend/index.html` does not exist afterwards.
- **DEP-HARN-013** — It MUST boot the production server exactly as deployed:
  `gunicorn -c deploy/gunicorn.conf.py cloudgene_django.wsgi:application` (the venv's `gunicorn`
  if present), with `GUNICORN_BIND=127.0.0.1:<free port>` and `GUNICORN_WORKERS=1`.
- **DEP-HARN-014** — It MUST assert, exiting 1 with a `FAIL:` line on the first miss: `GET /`
  succeeds and contains `<div id="app">`; the first `/static/frontend/assets/index-*.js` path in
  that body returns 200; `GET /api/health` succeeds and its body contains a `status` field.
- **DEP-HARN-015** (planned) — The readiness wait (50 × 0.2 s) MUST fail the script with the
  gunicorn log when the server never answers, instead of falling through to the next step.
- **DEP-HARN-016** (planned) — The smoke test MUST assert that the hashed asset response carries a
  long-lived `Cache-Control` as required by [static-assets.md](static-assets.md), and that the
  health body has `db.ok: true`. Today both are only printed.
- **DEP-HARN-017** (planned) — The smoke test MUST collect static files into a `STATIC_ROOT`
  inside its throw-away directory (DEP-HARN-011) and MUST NOT clear or rewrite the checkout's
  `staticfiles/`. Reason: the upgrade procedure runs it on the production checkout
  ([DEP-INST-020](install-upgrade.md#upgrade)), where clearing `staticfiles/` deletes the previous
  release's assets ([DEP-STATIC-030](static-assets.md#releases-and-open-tabs)). Run without
  `--skip-build`, its build step (DEP-HARN-010) rewrites the checkout's `static/frontend/`; on a
  live install it SHOULD be run with `--skip-build` after the procedure's own build.

**e2e stack (`e2e/stack.py`)** (isolation policy: BE-TEST-013)

- **DEP-HARN-020** — Each pytest process MUST start one stack named after `PYTEST_XDIST_WORKER`
  (else `main`) under `$E2E_ARTIFACTS` (default `e2e/.artifacts/`)`/stack-<name>/`. The directory
  MUST be deleted at the start of the next stack with the same name and MUST be kept after the
  run. The stack MUST write `stack.json` (`base_url`, `home`, `db`, `outbox`, `worker`,
  `health_endpoint`). `e2e/.artifacts/` MUST be git-ignored.
- **DEP-HARN-021** — The SPA bundle MUST be rebuilt (`npm run build`) when any of
  `frontend/index.html`, `vite.config.js`, `package.json`, `src/**`, `public/**` is newer than
  `static/frontend/index.html`, under an exclusive lock on `.artifacts/.build.lock` so parallel
  workers build once. `E2E_SKIP_BUILD=1` MUST skip this. Missing `frontend/node_modules` or a failed
  build MUST raise `StackError` naming the fix or the log tail.
- **DEP-HARN-022** — The stack home MUST contain `config/settings.yaml` generated from
  `e2e/constants.py` (server name/url, `max_running_jobs: 2`, `max_queue_size: 5`, file mail backend
  with outbox `mail/`, `nextflow.binary`, navbar, `apps[]` access rules), an empty
  `config/nextflow.env`, a `config/nextflow.config`, `pages/{home,footer,about}.html` with the
  markers in `PAGE_MARKERS`, a copy of each fixture app in `apps/`, and empty `jobs/` and `mail/`.
- **DEP-HARN-023** — Without `E2E_DATABASE_URL` the stack MUST use `<root>/db.sqlite3`. With it,
  the stack MUST create database `<db-of-url>_e2e_<name>` on that server (terminating leftover
  backends and dropping any existing one first), point `DATABASE_URL` at it, and drop it in
  `stop()`. The URL's own database MUST NOT be written.
- **DEP-HARN-024** — Every stack process MUST get: `DJANGO_SETTINGS_MODULE`, `CLOUDGENE_HOME`,
  `DATABASE_URL`, `DJANGO_SECRET_KEY=e2e-not-secret-<name>`, `DEBUG=$E2E_DEBUG` (default `False`),
  `LOG_LEVEL=$E2E_LOG_LEVEL` (default `INFO`), `ALLOWED_HOSTS=127.0.0.1,localhost`,
  `CSRF_TRUSTED_ORIGINS=<base_url>`, `NXF_ANSI_LOG=false`, the repo on `PYTHONPATH`, the Nextflow
  directory first on `PATH`, and `INSECURE_FAST_PASSWORD_HASHING=1` with `CLOUDGENE_E2E=1` unless
  `E2E_REAL_HASHING=1`.
- **DEP-HARN-025** — Boot MUST run in this order, each step logged to `logs/<step>.log`:
  `migrate --noinput`; `create_admin` with the admin from `constants.USERS`; `e2e.seed users`;
  `runserver 127.0.0.1:<free port> --noreload --insecure`; wait until `health` returns 200 (90 s);
  if `manage.py help run_worker` succeeds, `run_worker` and wait until `health` reports
  `worker.ok` (30 s); `e2e.seed workflows`. A server or worker that exits during start-up, a
  timeout, or a failing step MUST raise `StackError` with the log tail, after `stop()` has run.
- **DEP-HARN-026** — Server and worker MUST run in their own process groups. `stop()` MUST send
  SIGTERM to each group, wait up to 15 s, then SIGKILL, and only then drop the Postgres database.
- **DEP-HARN-027** — Nextflow MUST be resolved as `$E2E_NEXTFLOW`, else `nextflow` on `PATH`,
  else `/usr/local/bin/nextflow`. (planned) Stack start MUST fail with `StackError` when that path
  is not an executable file, rather than letting jobs fail later.
- **DEP-HARN-028** — The e2e stack MUST serve the production bundle (`static/frontend/`) with
  `DEBUG=False`. It uses `runserver`, not gunicorn; the production server path is covered only by
  the smoke test (DEP-HARN-013).

**pytest wiring (`e2e/conftest.py`, `e2e/pytest.ini`)**

- **DEP-HARN-030** — The `stack` fixture MUST be session-scoped and started only when a test
  requests it (directly or via `base_url`, `api`, `login`, …); the pytest-base-url autouse check
  MUST be neutralised so stack-free tests (the guard self-test) do not boot it.
- **DEP-HARN-031** — `login(page, user)` MUST log in through the UI once per user per session and
  reuse the saved storage state afterwards; `fresh=True` MUST always use the UI and not cache.
- **DEP-HARN-032** — `server_settings` MUST write `settings.yaml` atomically (temp file +
  rename), wait 1.1 s after each update so mtime-based caches reload, and restore the original
  file at teardown.
- **DEP-HARN-033** — On failure, Playwright traces and screenshots MUST be kept under
  `e2e/.artifacts/playwright/<test-id>/` (`--tracing retain-on-failure --screenshot
  only-on-failure`). The controlling process MUST write `e2e/.artifacts/summary.txt` with a totals
  line and, per test, outcome, duration, first error line, guard findings and trace path.
- **DEP-HARN-034** — `e2e/pytest.ini` MUST register the `serial` and `worker` markers, set
  `testpaths = tests`, and ignore `DeprecationWarning`. (planned) It MUST add `--strict-markers`
  and, when run under xdist, a collection hook MUST error on any `serial` test (mechanism for
  BE-TEST-015).
- **DEP-HARN-035** (planned) — `e2e/pytest.ini` MUST set `xfail_strict = true`, so an `xfail`
  test that starts passing fails the run (default for the strict-xfail rule of
  [BE-TEST-016](../backend/tests.md#requirements)).

**Guards (`e2e/guards.py`)** (rule: BE-TEST-014)

- **DEP-HARN-036** — The guard MUST record, per browser context it is attached to: console
  messages of type `error` except those starting `Failed to load resource`; page errors; same-origin
  responses ≥ 400; same-origin failed requests except `ERR_ABORTED`. Origin MUST be the
  `base_url`, else the first navigated origin. `expect_api_error(status, glob)` MUST accept an
  int, an iterable or `None` (any) and match the glob (fnmatch) against the path with and without
  the query. `expect_console_error(p)` MUST accept a substring or compiled regex and apply to
  console errors and page errors. After the test body, the guard MUST wait 150 ms per page, add an
  `e2e-guard` report section and fail the test if issues remain; inside an `xfail` test the
  failure MUST count as xfailed.

**Helpers, seed and constants**

- **DEP-HARN-040** — `helpers.ApiClient` MUST send `Referer` on every request, `X-CSRFToken` from
  the `csrftoken` cookie on unsafe methods, and a 30 s timeout. `json_or_raise` MUST raise
  `ApiError` naming method, path, status and the first 500 bytes of the body.
- **DEP-HARN-041** (planned) — Harness helpers MUST call only operations in `schema.yaml` at their
  documented paths. The legacy fallbacks (no-slash and slash retries, DRF token from the login
  body, `/status` → job detail, `wait_ready` SPA-root fallback, `worker_ok` legacy shapes,
  `admin_helpers` `state`/`status` field sniffing and `LEGACY_TO_SPEC`) MUST be removed so a
  removed or renamed endpoint fails the suite.
- **DEP-HARN-042** — `wait_job_state` MUST fail as soon as the job reaches an unwanted final state
  and on timeout, with the last payload in the message. `latest_email` MUST wait up to its timeout
  for a matching message in the file outbox and fail naming the outbox.
- **DEP-HARN-043** — Helpers that arrange data in the database (`admin_helpers.create_jobs`,
  `delete_jobs`, `job_state_counts`, `db_counts`) MUST run through `manage.py shell -c` in the
  stack environment. The pytest process MUST NOT import Django.
- **DEP-HARN-044** — `e2e/seed.py users` MUST be idempotent and create groups `admin` and
  `researchers` and every non-admin user in `constants.USERS` (active, password set, groups set).
  `e2e/seed.py workflows` MUST sync the registry and exit non-zero listing every fixture app that
  is missing from `apps[]` or invalid.
- **DEP-HARN-045** — `e2e/constants.py` MUST be the single source of seed users, app access rules,
  queue limits, navbar and page markers for both the stack and the tests, and MUST NOT import
  Django.

**Dependencies and browser**

- **DEP-HARN-050** (planned) — The e2e Python dependencies MUST be pinned to exact versions in one
  file, including `playwright==<version>` matching the Chromium build installed on the host
  (today 1.56.0 per the repository README), and the setup instructions MUST name that one file.
- **DEP-HARN-051** — The guard self-test MUST locate browsers through `PLAYWRIGHT_BROWSERS_PATH`
  (default `~/.cache/ms-playwright`) resolved before pytester changes `HOME`.

**Fixture apps and exploratory probes**

- **DEP-HARN-055** — Every app in `e2e/fixtures/apps/` MUST be listed in `constants.APPS`, be
  valid for the registry, and pass `e2e/fixtures/verify_apps.py` (plain `nextflow run` with
  `-params-file`, trace and log; non-zero exit on any failed check).
- **DEP-HARN-056** — `e2e/exploratory/serve.py` MUST boot one stack named `explore`, print
  `BASE_URL=`, `HOME=`, `WORKER=` lines, and stop it (including the Postgres database) on SIGINT or
  SIGTERM.
- **DEP-HARN-057** — `e2e/exploratory/matrix.py` MUST enumerate every path and method in
  `schema.yaml`, substitute ids from the `arrange.py` output, call each as anonymous, `bob`,
  `alice` and `admin`, skip the calls listed in `DESTRUCTIVE` and admin writes for `admin`
  (reported `n/a`), and write the rows to a JSON file. It MUST NOT assert (BE-TEST-008 owns the
  asserting version).

**Hosted CI** (policy: BE-TEST-019)

- **DEP-HARN-070** (planned) — The repository MUST contain a hosted CI configuration that runs on
  every push and pull request: job `unit-sqlite` (`scripts/test.sh unit`), job `unit-postgres`
  (`scripts/test.sh unit --postgres` against a Postgres service of the version required by
  [database.md](database.md), `TEST_DATABASE_URL` pointing at it, role with `CREATEDB`), and job
  `smoke` (`scripts/smoke_gunicorn.sh`).
- **DEP-HARN-071** (planned) — `unit-sqlite`, `unit-postgres` and `smoke` MUST be required status
  checks for merging. Because they run the schema staleness test (BE-TEST-002), the migrations
  check (BE-TEST-005) and vitest (FE-TEST-001), a stale `schema.yaml`, a missing migration or a
  failing vitest MUST block the merge.
- **DEP-HARN-072** (planned) — In `unit-postgres`, `ClaimConcurrencyTest` MUST run and MUST NOT be
  skipped; the job MUST fail if it reports a skip.
- **DEP-HARN-073** (planned) — CI MUST run job `e2e` (SQLite: `pytest e2e -n 4 -m "not serial"`,
  then `pytest e2e -m serial`) and job `e2e-postgres` (same with `E2E_DATABASE_URL`) nightly, on
  release tags and on manual dispatch. `e2e` SHOULD also run on pull requests that touch
  `frontend/`, `e2e/` or an API module.
- **DEP-HARN-074** (planned) — CI MUST pin Python 3.12, Node 22, Java 21, a fixed Nextflow version
  and the Playwright version/browser of DEP-HARN-050, and MUST upload `e2e/.artifacts/` (summary,
  traces, stack logs) when an e2e job fails.
- **DEP-HARN-075** (planned) — CI MUST NOT need production secrets; it uses only the fixed test
  credentials of the harness.

## Interfaces

### Commands

```bash
scripts/test.sh [unit|e2e|all] [--postgres] [pytest args...]   # unknown mode: exit 2
scripts/smoke_gunicorn.sh [--skip-build]                       # exit 0 OK, 1 FAIL
python e2e/fixtures/verify_apps.py [app ...] [--nextflow PATH] [--keep]
E2E_ARTIFACTS=<dir> python -m e2e.exploratory.serve
BASE=<url> python -m e2e.exploratory.arrange > ids.json
BASE=<url> python -m e2e.exploratory.matrix ids.json [out.json]
```

Usage of `pytest e2e` (parallel, serial, subsets) is listed in
[backend tests › Commands](../backend/tests.md#commands).

### Environment variables read by the harness

| Variable | Read by | Effect |
|---|---|---|
| `PYTHON` | `test.sh`, `smoke_gunicorn.sh` | Interpreter |
| `TEST_DATABASE_URL` | `test.sh --postgres` | Postgres for Django tests |
| `E2E_ARTIFACTS` | `stack.py` | Artefact root (default `e2e/.artifacts`) |
| `E2E_PYTHON` | `stack.py` | Interpreter for `manage.py` (default current) |
| `E2E_NEXTFLOW` | `stack.py` | Nextflow binary |
| `E2E_DATABASE_URL` | `stack.py` | Postgres server for per-stack databases |
| `E2E_SKIP_BUILD` | `stack.py` | `1` = never rebuild the SPA |
| `E2E_DEBUG`, `E2E_LOG_LEVEL` | `stack.py` | `DEBUG`, `LOG_LEVEL` of the stack |
| `E2E_REAL_HASHING` | `stack.py` | `1` = production password hasher |
| `E2E_EXPLORATORY` | `e2e/exploratory/conftest.py` | `1` = collect `test_probe_*.py` |
| `PLAYWRIGHT_BROWSERS_PATH` | `test_harness_selftest.py` | Browser location |
| `BASE` | exploratory scripts | Running stack URL |

### Stack layout

```
e2e/.artifacts/
  .build.lock                 summary.txt          playwright/<test-id>/{trace.zip,*.png}
  stack-<worker>/
    stack.json   db.sqlite3 (SQLite only)
    logs/{frontend-build,migrate,create_admin,seed,server,worker}.log
    home/{config/{settings.yaml,nextflow.config,nextflow.env},pages/,apps/<fixtures>,jobs/,mail/}
```

### Fixture apps

| App | Access (`constants.APPS`) | Exercises |
|---|---|---|
| `hello` | public | Simplest success path; `::message::`; text input written verbatim (unicode, quotes) to `hello.txt`; downloadable output folder |
| `all-inputs` | `researchers` | Every input type (separator, info/label HTML, text, string, number min/max, textarea + `writeFile`, list, radio, checkbox, file `accept`, folder, local-file/folder, hidden, `serialize: false`, agb/terms checkboxes); step `params` |
| `fail` | `admin` | Failing Nextflow process with `::error::` |
| `slow` | `admin` | Long-running job (default 60 s) for queue, cancel and limits |
| `multi-process` | `admin` | Three labelled processes × N tasks; per-app `nextflow.config` for concurrency on one CPU |
| `command-steps` | `researchers` | Nextflow step followed by `command` steps (bash pipeline, scripts in `bin/`, exit 7, sleep, zip); env placeholders; `details`/`help`; needs `/usr/bin/{bash,grep,sed,sort}` and `python3` on the host |
| `e2e/exploratory/apps/probe-env` | probes only | Reports env/params/profile given to Nextflow |
| `e2e/exploratory/apps/symlink-out` | probes only | `publishDir` default (symlink) outputs |

## Behaviour

**`test.sh` flow.** Parse mode (default `all`), strip `--postgres`, resolve Python, run steps
under `set -euo pipefail`. `e2e` mode skips with exit 0 when `e2e/` does not exist (left from the
bootstrap period). `all` runs `unit` then `e2e`; extra args go only to pytest, so a single Django
test cannot be selected through the script (BE-TEST-001 gap).

**Smoke flow.** Build → temp env → migrate → collectstatic into the repo's `staticfiles/` →
`check --deploy` (output printed, result ignored) → gunicorn on a free port → poll
`/api/health` up to 10 s → assert shell, asset, health → trap cleans up. No worker runs, so
`health` reports `status: degraded` with 200, which the smoke test accepts. `smoke_gunicorn.sh`
is not called by `test.sh`.

**Stack lifecycle.** `stack` fixture → `start_stack(name)` → tests → `stop()`. A crash during
boot calls `stop()` before re-raising, so no orphaned processes or Postgres databases remain; a
killed pytest leaves processes and the database, and the next run with the same worker name drops
the database first. Ports come from binding port 0 and closing, so another process can take the
port before `runserver` binds it (rare; boot then fails with the server log).

**Worker absence.** If `run_worker` is not a command, tests using `requires_worker` skip with a
reason; if the worker process died, they fail naming `worker.log`. The `worker` marker is a label
only; nothing reads it.

**Exploratory.** `pytest e2e` collects `e2e/exploratory/` but its conftest ignores
`test_probe_*.py` unless `E2E_EXPLORATORY=1`. `probes_*.py`, `arrange.py`, `matrix.py` are scripts,
never collected. They use their own `probe.Client` (session + CSRF + `Origin`) against `BASE`.

**CI (planned).** Two tiers: required per-PR jobs (`unit-sqlite`, `unit-postgres`, `smoke`), and
scheduled full-stack jobs (`e2e`, `e2e-postgres`). Serial e2e tests run in a second, non-parallel
invocation.

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| DEP-HARN-001 | `core/tests/test_harness_scripts.py::TestShTest::test_runs_from_repo_root_with_python_override` (planned) | config |
| DEP-HARN-002 | `core/tests/test_harness_scripts.py::TestShTest::test_postgres_flag_sets_database_url_for_django_tests_only` (planned) | config |
| DEP-HARN-003 | `core/tests/test_harness_scripts.py::TestShTest::test_failing_step_exits_non_zero_without_ok` (planned) | config |
| DEP-HARN-004 | `core/tests/test_harness_scripts.py::TestShTest::test_postgres_flag_in_e2e_mode_is_not_ignored` (planned) | config |
| DEP-HARN-005 | `scripts/test.sh unit` step "Frontend unit tests (vitest)" | smoke |
| DEP-HARN-010 | `scripts/smoke_gunicorn.sh` step "Building the SPA" | smoke |
| DEP-HARN-011 | `scripts/smoke_gunicorn.sh` (trap on EXIT) | smoke |
| DEP-HARN-012 | `scripts/smoke_gunicorn.sh` step "collectstatic" | smoke |
| DEP-HARN-013 | `scripts/smoke_gunicorn.sh` step "Starting gunicorn" | smoke |
| DEP-HARN-014 | `scripts/smoke_gunicorn.sh` steps "GET / (SPA shell)", "GET a hashed static asset", "GET /api/health" | smoke |
| DEP-HARN-015 | `core/tests/test_harness_scripts.py::SmokeScriptTest::test_readiness_timeout_fails` (planned) | config |
| DEP-HARN-016 | `scripts/smoke_gunicorn.sh` Cache-Control and `db.ok` assertions (planned) | smoke |
| DEP-HARN-017 | `core/tests/test_deploy.py::StaticConfigTest::test_smoke_script_uses_throwaway_static_root` (planned) | config |
| DEP-HARN-020 | `e2e/tests/test_harness_selftest.py::test_stack_root_and_stack_json` (planned) | e2e |
| DEP-HARN-021 | `e2e/tests/test_harness_selftest.py::test_bundle_rebuilt_only_when_sources_newer` (planned) | e2e |
| DEP-HARN-022 | `e2e/tests/test_smoke.py::test_home_renders_home_template` | e2e |
| DEP-HARN-022 | `e2e/tests/test_smoke.py::test_footer_renders_footer_template` | e2e |
| DEP-HARN-022 | `e2e/tests/test_smoke.py::test_about_page_renders_pages_file` | e2e |
| DEP-HARN-022 | `e2e/tests/test_smoke.py::test_navbar_items_from_yaml_in_order` | e2e |
| DEP-HARN-023 | `e2e/tests/test_harness_selftest.py::test_postgres_database_per_worker_created_and_dropped` (planned) | e2e |
| DEP-HARN-024 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_e2e_flag_set` | unit |
| DEP-HARN-024 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_logged_in` | e2e |
| DEP-HARN-025 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous` | e2e |
| DEP-HARN-025 | `e2e/tests/test_jobs.py::test_failing_workflow` | e2e |
| DEP-HARN-026 | `e2e/tests/test_harness_selftest.py::test_stop_kills_process_groups` (planned) | e2e |
| DEP-HARN-027 | `e2e/tests/test_harness_selftest.py::test_missing_nextflow_fails_stack_start` (planned) | e2e |
| DEP-HARN-028 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous` | e2e |
| DEP-HARN-030 | `e2e/tests/test_harness_selftest.py::test_guards_fail_tests_on_browser_errors` | e2e |
| DEP-HARN-031 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_logged_in` | e2e |
| DEP-HARN-032 | `e2e/tests/test_harness_selftest.py::test_server_settings_restored` (planned) | e2e |
| DEP-HARN-033 | `e2e/tests/test_harness_selftest.py::test_summary_written` (planned) | e2e |
| DEP-HARN-034 | `e2e/tests/test_harness_selftest.py::test_serial_rejected_under_xdist` (planned) | e2e |
| DEP-HARN-035 | `core/tests/test_harness_scripts.py::PytestIniTest::test_xfail_strict_true` (planned) | config |
| DEP-HARN-036 | `e2e/tests/test_harness_selftest.py::test_guards_fail_tests_on_browser_errors` | e2e |
| DEP-HARN-040 | `e2e/tests/test_accounts.py::test_a2_case_variant_duplicates_rejected` | e2e |
| DEP-HARN-041 | `e2e/tests/test_harness_selftest.py::test_helpers_use_schema_paths_only` (planned) | e2e |
| DEP-HARN-042 | `e2e/tests/test_accounts.py::test_a1_register_activate_login` | e2e |
| DEP-HARN-043 | `e2e/tests/test_harness_selftest.py::test_no_django_import_in_pytest_process` (planned) | e2e |
| DEP-HARN-044 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_logged_in` | e2e |
| DEP-HARN-045 | `e2e/tests/test_harness_selftest.py::test_no_django_import_in_pytest_process` (planned) | e2e |
| DEP-HARN-050 | `core/tests/test_harness_scripts.py::RequirementsPinTest::test_e2e_requirements_pinned` (planned) | config |
| DEP-HARN-051 | `e2e/tests/test_harness_selftest.py::test_guards_fail_tests_on_browser_errors` | e2e |
| DEP-HARN-055 | `e2e/fixtures/verify_apps.py` (all apps) | smoke |
| DEP-HARN-055 | `core/tests/test_harness_scripts.py::FixtureAppsTest::test_every_fixture_app_listed_in_constants` (planned) | config |
| DEP-HARN-056 | — (manual: `python -m e2e.exploratory.serve`) (planned) | smoke |
| DEP-HARN-057 | — (manual: `python -m e2e.exploratory.matrix`) (planned) | smoke |
| DEP-HARN-070 | `core/tests/test_harness_scripts.py::CiConfigTest::test_required_jobs_present` (planned) | config |
| DEP-HARN-071 | `core/tests/test_harness_scripts.py::CiConfigTest::test_required_jobs_present` (planned) | config |
| DEP-HARN-072 | `core/tests/test_harness_scripts.py::CiConfigTest::test_postgres_job_fails_on_concurrency_skip` (planned) | config |
| DEP-HARN-073 | `core/tests/test_harness_scripts.py::CiConfigTest::test_e2e_jobs_scheduled` (planned) | config |
| DEP-HARN-074 | `core/tests/test_harness_scripts.py::CiConfigTest::test_toolchain_pinned_and_artifacts_uploaded` (planned) | config |
| DEP-HARN-075 | `core/tests/test_harness_scripts.py::CiConfigTest::test_no_secrets_referenced` (planned) | config |

Smoke-layer rows cite a script step; the step passing is the test.

## Known gaps

| Req | What the code does today | Where | Severity |
|---|---|---|---|
| DEP-HARN-070, DEP-HARN-071, DEP-HARN-072, DEP-HARN-073, DEP-HARN-074, DEP-HARN-075 | No hosted CI configuration exists (no `.github/`, no other CI file). Schema staleness, migrations check, Postgres, smoke and e2e run only by hand. (Also BE-TEST-019.) | repository root | major |
| DEP-HARN-050 | Neither `requirements.txt` nor `e2e/requirements.txt` pins Playwright; `e2e/requirements.txt` uses `>=` ranges and no `playwright` line, so `pytest-playwright>=0.7` pulls the latest `playwright`. The root README states `playwright==1.56.0` is "pinned in `requirements.txt`" — it never was. A fresh install can mismatch the preinstalled Chromium and fail to launch. | `e2e/requirements.txt:1-6`, `requirements.txt`, `README.md:114-117` | major |
| DEP-HARN-004 | `--postgres` in `e2e` mode is stripped and ignored; the e2e run uses SQLite with no warning. | `scripts/test.sh:24-33`, `:65-72` | minor |
| DEP-HARN-015 | The readiness loop never fails; after 10 s it falls through and the next `curl` fails with a less useful message (gunicorn log printed only for `GET /`). | `scripts/smoke_gunicorn.sh:154-160` | minor |
| DEP-HARN-016 | `Cache-Control` of the asset is printed, not asserted; `health` only checked for the substring `"status"`. `check --deploy` result ignored (`|| true`). | `scripts/smoke_gunicorn.sh:131-133`, `:171-177` | minor |
| DEP-HARN-017 | `collectstatic --clear` writes into the checkout's own `staticfiles/` (`STATIC_ROOT_OVERRIDE` is exported but nothing reads it). On a developer machine it wipes collected files; run on a production host as `docs/DEPLOYMENT.md` §5 suggests, it deletes the previous release's chunks (breaking DEP-STATIC-030) and, without `--skip-build`, rewrites the served tree under the running process. This is the single home of this gap; static-assets.md links here. | `scripts/smoke_gunicorn.sh:120`, `:127`; `cloudgene_django/settings.py:210` | major |
| DEP-HARN-041 | Helpers and stack carry pre-T01 fallbacks (path retries, token login, `/status` → detail, SPA-root readiness, legacy worker/state shapes) that can hide a removed or renamed endpoint. | `e2e/helpers.py:46-60`, `:89-113`; `e2e/stack.py:295-299`, `:346-362`; `e2e/admin_helpers.py:4-5`, `:20-31` | minor |
| DEP-HARN-027 | No check that the Nextflow path exists; a missing binary surfaces as failed jobs in worker tests. | `e2e/stack.py:41` | minor |
| DEP-HARN-034 | No `--strict-markers`; `serial` is not enforced under `-n` (BE-TEST-015); the `worker` marker is described as skipping but nothing reads it. | `e2e/pytest.ini:4-7` | minor |
| DEP-HARN-035 | `xfail_strict = false`; a non-strict `xfail` that starts passing goes unnoticed. | `e2e/pytest.ini:8` | minor |
| — | `smoke_gunicorn.sh` is not run by `scripts/test.sh` in any mode. | `scripts/test.sh:74-79` | minor |
| — | `--skip-build` is honoured only as the first argument of `smoke_gunicorn.sh`; any other argument is ignored silently. | `scripts/smoke_gunicorn.sh:99-100` | minor |
| — | `create_admin --password` puts the admin password on the command line of a child process (visible in `ps`); acceptable for fixed test credentials only. | `e2e/stack.py:415-417` | minor |
| — | `command-steps` fixture hard-codes `/usr/bin/bash`, `/usr/bin/grep`, `/usr/bin/sed`, `/usr/bin/sort`; it fails on hosts where these live elsewhere. | `e2e/fixtures/apps/command-steps/cloudgene.yaml` | minor |

## Open questions

1. **Install instructions conflict.** `e2e/README.md` says `pip install -r e2e/requirements.txt`
   and `playwright install --with-deps chromium`; the root `README.md` says never to do either
   because the browser build is preinstalled and must match `playwright==1.56.0`. Which is the
   supported setup for developers and for CI (DEP-HARN-050, DEP-HARN-074)?
2. **Pinning strength.** Resolved: BE-TEST-021 is now a MUST (exact `==` pins), with the
   `playwright` pin and browser coupling owned by DEP-HARN-050. See
   [BE-TEST-021](../backend/tests.md#requirements).
3. **Double home for isolation mechanics.** Resolved: BE-TEST-013 now states only the isolation
   policy and links DEP-HARN-020..025 and DEP-HARN-027 for the mechanics. See
   [BE-TEST-013](../backend/tests.md#requirements).
4. **xfail policy.** Resolved: BE-TEST-016 now requires every `xfail` in `e2e/tests/` to be
   `strict=True`, with DEP-HARN-035 as the default. See
   [BE-TEST-016](../backend/tests.md#requirements).
5. **CI host and e2e on PRs.** BE-TEST-019 requires e2e "at least nightly"; DEP-HARN-073 adds a
   SHOULD for PRs touching `frontend/`, `e2e/` or API modules. Confirm, and pick the CI host
   (affects the file path for DEP-HARN-070).
6. **gunicorn in e2e.** Should the e2e stack boot gunicorn with `deploy/gunicorn.conf.py` instead
   of `runserver --insecure`, so the browser suite exercises the production server and
   whitenoise (DEP-HARN-028)?
