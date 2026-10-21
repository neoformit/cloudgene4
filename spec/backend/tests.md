# Backend Tests

## Purpose

This file defines how the backend is tested: the test layers, the fixtures and runners they use,
the commands that run them, the rules the test suite itself must meet, and a traceability table
that maps every backend requirement (`BE-*-NNN`) to the tests that prove it. It is the
section-level `tests.md` required by [Article 7.2](../constitution.md#article-7--tests).

## Scope

In scope:

| Path | What |
|---|---|
| `scripts/test.sh` | Single entry point for all suites |
| `core/test_runner.py` | `CloudgeneTestRunner` (`TEST_RUNNER` in `cloudgene_django/settings.py:352`) |
| `*/tests.py`, `*/test_*.py`, `*/tests/test_*.py`, `workflows/tests_yaml_reference_example.py` | Django unit and contract tests |
| `core/tests/test_schema.py` | `schema.yaml` staleness gate |
| `jobs/tests/test_claim_concurrency.py` | Postgres-only concurrency test |
| `jobs/tests/helpers.py` | Fixture apps, fake `nextflow`, users, `TempHomeMixin` |
| `workflows/test_fixtures/apps/` | Fixture apps for registry/definition tests (`hello`, `other`, `invalid`, `broken-yaml`) |
| `e2e/` (`conftest.py`, `stack.py`, `guards.py`, `seed.py`, `pages/`, `tests/`, `fixtures/apps/`) | Playwright full-stack suite |
| `e2e/exploratory/` | Exploratory probes (not regression tests) |

Out of scope: frontend vitest tests and frontend contract tests (see
[frontend tests](../frontend/tests.md)), except that `scripts/test.sh unit` runs vitest; deployment
smoke tests (`scripts/smoke_gunicorn.sh`, see [deployment tests](../deployment/tests.md)).

## Dependencies

- [api-contract.md](api-contract.md) — operation catalogue by `operationId`, error envelope;
  contract tests validate against `schema.yaml` (Article 5.1c, 5.1d).
- [configuration.md](configuration.md) — `CLOUDGENE_HOME`, `settings.yaml`, `nextflow.binary`
  (tests swap these).
- [data-model.md](data-model.md) — migrations (migrations check) and the two DB engines.
- [job-queue-worker.md](job-queue-worker.md), [job-runner.md](job-runner.md) — worker and runner
  behaviour exercised with the fake `nextflow` and, in e2e, real Nextflow.
- [management-commands.md](management-commands.md) — `create_admin`, `run_worker`, `migrate` used by
  the e2e stack.
- [deployment/test-harness.md](../deployment/test-harness.md) — e2e stack mechanics, `xfail_strict`
  default and e2e dependency pins (DEP-HARN-020..027, DEP-HARN-035, DEP-HARN-050).
- Every other file in this section — their **Acceptance tests** tables are the input for the
  traceability table below.

## Requirements

**Runner and gates**

- **BE-TEST-001** — `scripts/test.sh unit` MUST run, in this order and stopping at the first
  failure: `manage.py check`, `manage.py makemigrations --check --dry-run`, `manage.py test`,
  `npx vitest run` (in `frontend/`). Any failing step MUST make the script exit non-zero.
  `scripts/test.sh e2e` MUST run `pytest e2e` with the remaining arguments; `all` (the default)
  MUST run `unit` then `e2e`. An unknown mode MUST exit 2 with a usage line.
- **BE-TEST-002** — The Django suite MUST fail when the committed `schema.yaml` differs from the
  output of `manage.py spectacular --file <tmp> --validate`, and the failure message MUST name the
  regenerate command (Article 5.1c, BE-API-002).
- **BE-TEST-003** (planned) — Backend contract tests MUST validate real response bodies against
  `schema.yaml` (Article 5.1d) through one shared helper,
  `core/tests/contract.py::assert_matches_schema(response, operation_id)`, which:
  1. loads and parses `schema.yaml` once per process;
  2. finds the operation by `operationId` (an unknown `operationId` fails the test);
  3. picks the response object for `response.status_code`, else `default` (today `Error`); a
     status that has neither fails the test;
  4. validates the JSON body (or the empty body for 204) against that response's schema with
     `$ref` resolution and OpenAPI 3.0 semantics (`nullable`, `readOnly`, `writeOnly`), using a
     pinned OpenAPI validator (`openapi-core`, or `jsonschema` + `referencing` on the converted
     component) listed in a test-only requirements file (`requirements-dev.txt`), not in
     `requirements.txt`;
  5. reports the failing JSON path and the schema keyword in the assertion message.
  Every test in `*/test_contracts.py` MUST call it on each response it asserts, success and error.
- **BE-TEST-004** (planned) — Every `operationId` in `schema.yaml` MUST be validated by
  `assert_matches_schema` in at least one success-path test and one error-path test (error
  envelope, Article 5.2). A static check, `core/tests/test_schema.py::ContractCoverageTest`, MUST
  collect the literal `operationId` arguments passed to the helper in test sources and fail,
  listing the operations that are missing.
- **BE-TEST-005** — The migrations check (`makemigrations --check --dry-run`) MUST pass; a model
  change without its migration MUST fail `scripts/test.sh unit` (BE-DATA-016).
- **BE-TEST-006** (planned) — A schema lint test MUST fail when `schema.yaml` contains an untyped
  or free-form response field that is not in the accepted-untyped list of
  [api-contract.md](api-contract.md) (BE-API-004).
- **BE-TEST-007** (planned) — A test MUST fail when a test run observes an error `code` that is not
  in the error-code table of [api-contract.md](api-contract.md) (BE-API-024).
- **BE-TEST-008** (planned) — An authorisation matrix test MUST call every `/api/` operation as
  anonymous, user, other user and admin and compare the status with the access rule stated in the
  owning spec file (BE-API-035). `e2e/exploratory/matrix.py` is the prototype; it prints, it does
  not assert.

**Databases**

- **BE-TEST-009** — The Django suite MUST pass on SQLite (default) and on Postgres
  (`scripts/test.sh unit --postgres`). A test that is only meaningful on one engine MUST
  `skipTest` with a reason naming the command that runs it; it MUST NOT pass vacuously.
- **BE-TEST-010** — The worker claim MUST have a Postgres concurrency test in which several
  threads race the conditional UPDATE for the same job(s) and exactly one claim wins per job
  (BE-QUEUE-006).

**Isolation and fixtures**

- **BE-TEST-011** — Django tests MUST NOT modify the committed `home/`, the developer database or
  real mail. The test runner MUST copy `CLOUDGENE_HOME` (without `jobs/` and `mail/`) to a
  temporary directory, point `CLOUDGENE_HOME` at it, clear the config cache, use a fast password
  hasher, and delete the copy at teardown. Tests that install apps or write settings MUST use a
  per-test temporary home (`TempHomeMixin`).
- **BE-TEST-012** — The Django suite MUST NOT need Nextflow. Tests that run steps MUST use the fake
  `nextflow` written by `jobs/tests/helpers.py::install_fake_nextflow` (behaviour from
  `params.json`: `fake_mode` = `success|fail|sleep`, `fake_tasks`), or plain command steps.
- **BE-TEST-013** — The e2e suite MUST run against an isolated stack it builds itself, one per
  pytest/xdist worker, and MUST NOT touch the developer's database, `home/` or mail. Tests that
  need the worker MUST use the `requires_worker` fixture and skip when it is absent. Stack
  mechanics (paths, DB naming, boot order, Nextflow resolution): [DEP-HARN-020, DEP-HARN-021,
  DEP-HARN-022, DEP-HARN-023, DEP-HARN-024, DEP-HARN-025,
  DEP-HARN-027](../deployment/test-harness.md#requirements).
- **BE-TEST-014** — Every e2e test that uses `page` MUST fail when the browser sees a
  `console.error`, an uncaught exception, an unhandled rejection, a same-origin response ≥ 400 or a
  failed same-origin request, unless the test declared it first with `expect_api_error` /
  `expect_console_error` (`e2e/guards.py`). `e2e/tests/test_harness_selftest.py` MUST prove this.
- **BE-TEST-015** — e2e tests that change global server state (settings, queue, maintenance) MUST
  carry the `serial` marker and MUST NOT run under `-n`.
- **BE-TEST-016** — Exploratory probes in `e2e/exploratory/` MUST NOT be collected by `pytest e2e`
  unless `E2E_EXPLORATORY=1`. A confirmed finding MUST get a regression test in
  `e2e/tests/test_findings_*.py`, marked `xfail(strict=True)` while the defect exists. Every
  `xfail` in `e2e/tests/` MUST be `strict=True` (default via
  [DEP-HARN-035](../deployment/test-harness.md#requirements)).

**Coverage and traceability**

- **BE-TEST-017** — Every MUST requirement in `spec/backend/` MUST map to at least one named test
  in the table below. A test cited as existing MUST exist under that name. A requirement whose
  tests are all `(planned)` is a gap until one exists.
- **BE-TEST-018** — Behaviour that a user triggers in the browser and that reaches the API MUST have
  at least one e2e test (Article 7.3).
- **BE-TEST-019** (planned) — A hosted CI job MUST run, on every push and pull request,
  `scripts/test.sh unit` (SQLite) and `scripts/test.sh unit --postgres` against a Postgres service;
  the e2e suite MUST run at least nightly and before a release.
- **BE-TEST-020** (planned) — A traceability check (`scripts/spec_trace.py`, run by
  `scripts/test.sh unit`) MUST parse the **Acceptance tests** tables of `spec/backend/*.md`, fail
  on a requirement ID with no row, and fail on a test cited without `(planned)` that does not
  exist.
- **BE-TEST-021** — Test-only Python dependencies (`e2e/requirements.txt`, and the planned
  `requirements-dev.txt`) MUST be pinned to exact versions (`==`), like `requirements.txt`. The
  `playwright` pin and its coupling to the installed browser build are owned by
  [DEP-HARN-050](../deployment/test-harness.md#requirements).

## Interfaces

### Commands

```bash
scripts/test.sh                 # = all: unit, then e2e
scripts/test.sh unit            # check, migrations check, Django tests (SQLite), vitest
scripts/test.sh unit --postgres # same, Django tests with DATABASE_URL=$TEST_DATABASE_URL
                                #   (default postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene)
scripts/test.sh e2e [pytest args]   # python -m pytest e2e …
PYTHON=/path/to/python scripts/test.sh unit   # interpreter: $PYTHON, else ./venv/bin/python, else python3
```

`scripts/test.sh` passes extra arguments only to pytest in `e2e` mode. To run part of the Django
suite, call `manage.py test` directly:

```bash
python manage.py test jobs                                         # one app
python manage.py test jobs.tests.test_worker                       # one module
python manage.py test jobs.tests.test_worker.WorkerCancelTest      # one class
python manage.py test core.tests.test_schema.SchemaStalenessTest.test_committed_schema_is_up_to_date
python manage.py test accounts.tests                               # app-level tests.py
DATABASE_URL=postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene \
  python manage.py test jobs.tests.test_claim_concurrency          # Postgres-only test
python manage.py spectacular --file schema.yaml --validate         # regenerate after an API change
```

Postgres runs need a reachable server; Django creates and drops `test_<db>`, so the role needs
`CREATEDB`. Nothing in the repo starts Postgres.

e2e (see `e2e/README.md` for setup: `pip install -r e2e/requirements.txt`,
`playwright install chromium`, Nextflow on `PATH`):

```bash
python -m pytest e2e                         # everything, headless
python -m pytest e2e -n 4 -m "not serial"    # parallel, one stack per worker
python -m pytest e2e -m serial               # global-state tests, never with -n
python -m pytest e2e -k deep_links           # subset
python -m pytest e2e/tests/test_jobs.py::test_name
E2E_DATABASE_URL=postgres://… python -m pytest e2e -n 4 -m "not serial"
E2E_SKIP_BUILD=1 …                           # reuse the built SPA bundle
E2E_EXPLORATORY=1 E2E_SKIP_BUILD=1 python -m pytest e2e/exploratory -q -s   # probes
python e2e/fixtures/verify_apps.py           # fixture pipelines with plain `nextflow run`
```

Failure artefacts: `e2e/.artifacts/summary.txt`, `e2e/.artifacts/playwright/<test>/trace.zip`,
`e2e/.artifacts/stack-<worker>/logs/`.

### Test layers

| Layer | Where | Runner | DB | Nextflow | What it proves |
|---|---|---|---|---|---|
| unit | `accounts/tests.py`, `admin_panel/tests/`, `core/tests/`, `jobs/tests/`, `workflows/tests.py`, `workflows/test_definition.py`, `workflows/test_registry.py`, `workflows/tests_yaml_reference_example.py` | `manage.py test` (`CloudgeneTestRunner`) | SQLite or Postgres test DB | fake (`install_fake_nextflow`) | Models, parsing, registry, worker state machine, views via DRF test client |
| contract | `accounts/test_contracts.py`, `workflows/test_contracts.py` | `manage.py test` | as unit | — | Status codes and response fields per operation. Today hand-written field checks; MUST validate against `schema.yaml` (BE-TEST-003) |
| schema gate | `core/tests/test_schema.py` | `manage.py test` | none (`SimpleTestCase`) | — | `schema.yaml` not stale; platform paths and `Error` present |
| concurrency | `jobs/tests/test_claim_concurrency.py` | `manage.py test` with `DATABASE_URL` Postgres | Postgres only (skips on SQLite) | — | Claim race safety |
| gates | `scripts/test.sh unit` steps | bash | — | — | `check`, migrations up to date |
| e2e | `e2e/tests/test_*.py` | pytest + pytest-playwright (+ xdist) | per-stack SQLite or Postgres | real | Browser + API through the production SPA bundle, real worker and Nextflow |
| exploratory | `e2e/exploratory/` | pytest with `E2E_EXPLORATORY=1`, or scripts | stack | real | Charter-based probes; print, do not assert; not regression tests |

Size today: 374 Django test methods (accounts 105, admin_panel 31, core 72, jobs 91,
workflows 75) and 99 e2e test functions.

### Fixtures

| Fixture | Used by | Notes |
|---|---|---|
| `CloudgeneTestRunner` | all Django tests | Temp copy of `CLOUDGENE_HOME` (no `jobs/`, `mail/`), MD5 hasher, quiet `django.request` and `cloudgene` stream handlers |
| `jobs/tests/helpers.py` | jobs, core, admin tests | `TempHomeMixin`, `make_app`, `make_user`, `install_fake_nextflow`, `pid_alive` |
| `workflows/test_fixtures/apps/` | `workflows/test_registry.py`, `test_definition.py` | `hello`, `other`, `invalid`, `broken-yaml` |
| `e2e/fixtures/apps/` | e2e stack | `hello` (public), `all-inputs` (researchers), `fail`, `slow`, `multi-process` (admin only), `command-steps` |
| `e2e/fixtures/files/` | e2e uploads | input files |
| `e2e/constants.py`, `e2e/seed.py` | e2e | users `admin`, `alice` (researchers), `bob`; `max_running_jobs: 2`, `max_queue_size: 5` |
| `e2e/conftest.py` | e2e | `stack`, `base_url`, `page` (guarded), `login`, `user_page`, `api`, `requires_worker`, `server_settings` |
| `e2e/exploratory/apps/` | probes | `probe-env`, `symlink-out` |

### Traceability legend

Path aliases used in the table: `acct` = `accounts/tests.py`, `acct-c` =
`accounts/test_contracts.py`, `adm` = `admin_panel/tests/test_api.py`, `core-api` /
`core-cfg` / `core-dep` / `core-plat` / `core-schema` = `core/tests/test_{api,config,deploy,platform,schema}.py`,
`jobs-api` / `jobs-claim` / `jobs-cmd` / `jobs-prog` / `jobs-worker` =
`jobs/tests/test_{api,claim_concurrency,command_steps,progress,worker}.py`, `wf` =
`workflows/tests.py`, `wf-c` = `workflows/test_contracts.py`, `wf-def` =
`workflows/test_definition.py`, `wf-reg` = `workflows/test_registry.py`, `wf-yref` =
`workflows/tests_yaml_reference_example.py`, `e2e:x` = `e2e/tests/test_x.py`, `fe:` =
`frontend/src/`. Other paths are written in full (mostly planned new files). `::name` continues
the previous `file::Class`. `(p)` = planned test. **Status**: `exists` = at least one cited test
exists; `exists+planned` = exists, with further planned tests; `planned` = only planned tests;
`none` = no test cited.

## Behaviour

**Unit run.** `scripts/test.sh unit` resolves the interpreter, runs the gates, then
`manage.py test`. Django discovers `test*.py` in every app. `CloudgeneTestRunner` sets up the
temp home before any test; tests that change `settings.yaml` or install apps use
`TempHomeMixin` or `override_settings(CLOUDGENE_HOME=…)` and `config.clear_cache()`. Worker tests
point `nextflow.binary` at the fake script, which writes a trace file, a log, and
`invocation.json` (argv, env, params, cwd) that tests assert on. With `--postgres`,
`DATABASE_URL` is set only for `manage.py test`; `check`, the migrations check and vitest are
unchanged. vitest runs `npm ci` first when `frontend/node_modules` is missing.

**Schema gate.** `SchemaStalenessTest` regenerates the schema into a temp file with
`--validate` and compares the text with the committed file. Any serializer, view or
`extend_schema` change without a regenerated `schema.yaml` fails the suite.

**Contract validation (planned, BE-TEST-003).** A contract test makes the request with the DRF
test client, asserts the status, then calls `assert_matches_schema(response, '<operationId>')`.
Field-level assertions stay only for values the schema cannot express (for example "only public
workflows"). Error-path tests validate the `Error` envelope. `ContractCoverageTest`
(BE-TEST-004) keeps the set of validated operations equal to the set in `schema.yaml`.

**Concurrency.** `ClaimConcurrencyTest` is a `TransactionTestCase`; on a non-Postgres vendor
it calls `skipTest` with the command to run it. On Postgres it lines up 8 threads behind a
barrier and asserts one winner per job.

**e2e run.** The session fixture `stack` builds the SPA bundle if `frontend/` is newer than
`static/frontend/index.html` (skip with `E2E_SKIP_BUILD=1`), writes the stack home and
`settings.yaml` (mail backend `file`, outbox `$CLOUDGENE_HOME/mail`), migrates, seeds and starts
`runserver --insecure` on a free port plus `run_worker`. Tests drive the browser through page
objects (`e2e/pages/`) and use `api(...)` only to arrange or assert. The guard turns unexpected
browser errors into failures after the body passed. `e2e/tests/test_findings_*.py` hold
regression tests for QA findings.

**Exploratory.** `e2e/exploratory/conftest.py` ignores `test_probe_*.py` unless
`E2E_EXPLORATORY=1`. Probes print observations; confirmed findings move into
`test_findings_*.py`.

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| BE-TEST-001 | `scripts/test.sh` itself (by inspection); `scripts/test.sh` self-test (planned) | gate |
| BE-TEST-002 | `core/tests/test_schema.py::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit |
| BE-TEST-003 | `core/tests/test_contract_helper.py::AssertMatchesSchemaTest::test_rejects_wrong_type`, `::test_unknown_operation_fails`, `::test_undocumented_status_fails` (planned) | unit |
| BE-TEST-004 | `core/tests/test_schema.py::ContractCoverageTest::test_every_operation_validated` (planned) | unit |
| BE-TEST-005 | `scripts/test.sh unit` step "Migrations up to date" | gate |
| BE-TEST-006 | `core/tests/test_schema.py::SchemaLintTest::test_no_untyped_fields_outside_allow_list` (planned) | unit |
| BE-TEST-007 | `core/tests/test_schema.py::ErrorCodeRegistryTest::test_codes_in_table` (planned) | unit |
| BE-TEST-008 | `e2e/tests/test_findings_security.py::test_permission_matrix_admin_endpoints`, `::test_permission_matrix_requires_authentication`, `::test_permission_matrix_object_access` (partial); full matrix (planned) | e2e |
| BE-TEST-009 | `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest` (skip reason); `scripts/test.sh unit --postgres` run | unit |
| BE-TEST-010 | `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job`, `::test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once` | unit |
| BE-TEST-011 | `core/tests/test_runner.py::RunnerIsolationTest::test_home_is_temp_copy` (planned) | unit |
| BE-TEST-012 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` (fake binary) | unit |
| BE-TEST-013 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous` (boots the stack); stack-isolation assertion (planned) | e2e |
| BE-TEST-014 | `e2e/tests/test_harness_selftest.py::test_guards_fail_tests_on_browser_errors` (pytester run of the `test_*` cases above it, asserts `passed=3, failed=5, xfailed=1`) | e2e |
| BE-TEST-015 | marker check (planned): a collection hook that fails when a test uses `server_settings` without `serial` | e2e |
| BE-TEST-016 | `e2e/exploratory/conftest.py` `collect_ignore_glob` (by inspection); `core/tests/test_harness_scripts.py::XfailPolicyTest::test_every_e2e_xfail_is_strict` (planned) | e2e, config |
| BE-TEST-017 | `scripts/spec_trace.py` (planned, BE-TEST-020); this file's table (generated by hand, 2026-10-21) | gate |
| BE-TEST-018 | see the e2e entries in the table below; [frontend tests](../frontend/tests.md) | e2e |
| BE-TEST-019 | CI configuration (planned) | gate |
| BE-TEST-020 | `scripts/spec_trace.py` (planned) | gate |
| BE-TEST-021 | `core/tests/test_harness_scripts.py::RequirementsPinTest::test_e2e_requirements_pinned` (planned) | config |

### Traceability table

Built on 2026-10-21 by parsing every **Acceptance tests** table in `spec/backend/*.md` and
resolving each cited test against the source with Python `ast` (class and method names). All
493 requirement IDs defined in the other files appear below. 1 051 citations were resolved: 962
to existing tests (410 distinct), 89 to planned tests (81 distinct). Updated 2026-10-21 for
BE-AUTH-024 and BE-AUTH-027. No test cited as existing
was missing.

### [overview.md](overview.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-ARCH-001 | MUST | `core-plat::NoCeleryChannelsTest::test_django_boots_without_celery_channels_redis` | unit | exists |
| BE-ARCH-002 | MUST | `core-plat::SubmissionWithoutWorkerTest::test_submitted_job_waits_until_the_worker_claims_it` | unit | exists |
| BE-ARCH-003 | MUST | `core-plat::AppReadyTest::test_migrate_on_empty_db_does_not_query_workflows` (p) | unit | planned |
| BE-ARCH-004 | MUST | `core-api::MiscRoutingTest::test_unknown_api_path_is_json_404` | unit | exists |
| BE-ARCH-005 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie` | unit | exists |
| BE-ARCH-006 | MUST | `core-api::MiscRoutingTest::test_spa_missing_build_message` | unit | exists |
| BE-ARCH-007 | MUST | `core-api::AuthSessionTest::test_login_me_logout_flow_without_trailing_slash` | unit | exists |
| BE-ARCH-008 | MUST | `core-schema::SchemaStalenessTest::test_platform_endpoints_documented` | unit | exists |
| BE-ARCH-009 | MUST | `acct::DjangoAdminLockoutTest` | unit | exists |
| BE-ARCH-010 | MUST | `core-dep::JsonBodySizeLimitMiddlewareTest` | unit | exists |
| BE-ARCH-011 | MUST | `wf-reg::RegistrySyncTest::test_sync_if_changed_detects_settings_edit`; `wf-reg::WorkflowSyncMiddlewareTest::test_sync_failure_is_logged_and_request_succeeds` (p) | unit | exists+planned |
| BE-ARCH-012 | MUST | `core-api::AuthSessionTest::test_login_requires_csrf`, `::test_session_write_without_csrf_rejected` | unit | exists |
| BE-ARCH-013 | MUST | `core-dep::SecurityHeadersTest::test_x_frame_options_deny` (p) | unit | planned |
| BE-ARCH-014 | MUST | `core-api::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope` | unit | exists |
| BE-ARCH-015 | MUST | `core-api::ErrorEnvelopeHandlerTest::test_unhandled_exception_becomes_500_envelope` | unit | exists |
| BE-ARCH-016 | MUST | `core-api::MiscRoutingTest::test_middleware_error_on_api_path_is_json_500` (p) | unit | planned |
| BE-ARCH-017 | MUST | `core-api::MiscRoutingTest::test_pagination_page_size` | unit | exists |
| BE-ARCH-018 | MUST | settings assertion test (p) | — | planned |
| BE-ARCH-019 | MUST | `core-dep::SecretKeyFileTest::test_generated_once_mode_0600` (p) | unit | planned |
| BE-ARCH-020 | MUST | `core-cfg::CommittedHomeTest::test_committed_settings_yaml_is_valid_and_complete` | unit | exists |
| BE-ARCH-021 | MUST | `jobs-claim::ClaimConcurrencyTest` | unit | exists |
| BE-ARCH-022 | MUST | `core-dep::PasswordHasherTest::test_argon2_is_the_default_hasher` | unit | exists |
| BE-ARCH-023 | MUST | `core-dep::InsecureHashingCheckTest` | unit | exists |
| BE-ARCH-024 | MUST | `core-dep::DeployChecksTest`; `core-dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | unit | exists |
| BE-ARCH-025 | MUST | `core-plat::TestRunnerIsolationTest::test_cloudgene_home_is_a_temp_copy` (p) | unit | planned |

### [api-contract.md](api-contract.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-API-001 | MUST | `core-schema::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit | exists |
| BE-API-002 | MUST | `core-schema::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit | exists |
| BE-API-003 | MUST | `core-schema::SchemaStalenessTest::test_platform_endpoints_documented` | unit | exists |
| BE-API-004 | MUST | schema lint for untyped fields (BE-TEST-006) (p) | — | planned |
| BE-API-005 | MUST | `core-schema::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit | exists |
| BE-API-006 | MUST | `core/tests/contract.py` response validation (BE-TEST-003) (p) | — | planned |
| BE-API-007 | SHOULD | per-operation error statuses check (p) | — | planned |
| BE-API-008 | MUST (planned) | schema lint for nullable fields (p); `core/tests/contract.py` response validation (BE-TEST-003) (p) | contract | planned |
| BE-API-010 | MUST | `core-api::AuthSessionTest::test_login_me_logout_flow_without_trailing_slash`; `core-api::HealthTest::test_health_without_worker` | unit | exists |
| BE-API-011 | MUST | `core-api::AuthSessionTest::test_login_me_logout_flow_without_trailing_slash`; `core-api::HealthTest::test_health_without_worker` | unit | exists |
| BE-API-012 | MUST | `core-api::MiscRoutingTest::test_unknown_api_path_is_json_404` | unit | exists |
| BE-API-013 | MUST | 405 envelope test (p) | — | planned |
| BE-API-020 | MUST | `core-api::ErrorEnvelopeHandlerTest::test_validation_error_fields`, `::test_non_field_validation_error`, `::test_other_api_exceptions`; `core-api::AuthSessionTest::test_login_errors_use_envelope`; `adm::GeneralSettingsTest::test_validation_errors_in_envelope_fields`; `e2e:auth::test_login_wrong_password_shows_error` | unit, e2e | exists |
| BE-API-021 | MUST | `core-api::ErrorEnvelopeHandlerTest::test_validation_error_fields`, `::test_non_field_validation_error`, `::test_other_api_exceptions`; `core-api::AuthSessionTest::test_login_errors_use_envelope`; `adm::GeneralSettingsTest::test_validation_errors_in_envelope_fields` | unit | exists |
| BE-API-022 | MUST | `core-api::ErrorEnvelopeHandlerTest::test_unhandled_exception_becomes_500_envelope` | unit | exists |
| BE-API-023 | MUST | `core-dep::JsonBodySizeLimitMiddlewareTest::test_rejects_oversized_json_body_by_content_length_alone`, `::test_exempts_multipart_regardless_of_content_length`; `core-api::ErrorEnvelopeHandlerTest::test_upload_suspicious_operations_are_4xx_not_500`; `jobs-api::SubmissionTest::test_upload_size_limit` | unit | exists |
| BE-API-024 | MUST | error-code registry check (BE-TEST-007) (p) | — | planned |
| BE-API-030 | MUST | `core-api::TokenAuthTest::test_token_auth_without_csrf`; `core-api::AuthSessionTest::test_login_requires_csrf`, `::test_session_write_without_csrf_rejected`; `adm::PermissionMatrixTest::test_admin_session_needs_csrf`; `e2e:auth::test_login_and_logout_via_ui` | unit, e2e | exists |
| BE-API-031 | MUST | `core-api::TokenAuthTest::test_token_auth_without_csrf`; `core-api::AuthSessionTest::test_login_requires_csrf`, `::test_session_write_without_csrf_rejected`; `adm::PermissionMatrixTest::test_admin_session_needs_csrf`; `e2e:auth::test_login_and_logout_via_ui` | unit, e2e | exists |
| BE-API-032 | MUST | `core-api::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope`, `::test_bad_token_is_401_envelope`; `adm::PermissionMatrixTest::test_anonymous_gets_401` | unit | exists |
| BE-API-033 | MUST | `core-api::AdminPermissionTest::test_admin_endpoints_use_is_admin`; `adm::PermissionMatrixTest::test_non_admin_gets_403_and_nothing_changes`; `acct::PermissionMatrixTest::test_matrix` | unit | exists |
| BE-API-034 | MUST | `jobs-api::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`, `::test_output_traversal_and_foreign_ids` | unit | exists |
| BE-API-035 | MUST | auth matrix over all operations (BE-TEST-008) (p) | — | planned |
| BE-API-040 | MUST | `core-api::MiscRoutingTest::test_pagination_page_size` | unit | exists |
| BE-API-041 | MUST | unpaginated-list shape test (p) | — | planned |
| BE-API-050 | MUST | via BE-TEST-003 (p) | — | planned |
| BE-API-051 | MUST | via BE-TEST-003 (p) | — | planned |
| BE-API-052 | MUST | `jobs-api::SubmissionTest::test_legacy_name_field_and_json_body`, `::test_all_input_types_are_resolved_and_stored` | unit | exists |
| BE-API-053 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `jobs-api::OutputDownloadContentTypeTest::test_html_never_served_as_html`, `::test_svg_never_served_inline`, `::test_txt_is_safe_and_can_be_inline`, `::test_png_is_safe_and_can_be_inline` | unit | exists |
| BE-API-028 | MUST | `core-api::HealthTest::test_health_db_down` | unit | exists |
| BE-API-060 | MUST | review only; enforced indirectly by BE-API-002 | — | none |

### [data-model.md](data-model.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-DATA-001 | MUST | `acct::UserModelTest::test_db_rejects_case_variant_username`, `::test_db_rejects_case_variant_email` | unit | exists |
| BE-DATA-002 | MUST | `acct::UserModelTest::test_email_normalised_and_username_stripped` | unit | exists |
| BE-DATA-003 | MUST | `acct::UserModelTest::test_natural_key_lookup_ignores_case`; `acct::DjangoAdminLockoutTest::test_wrong_passwords_count_towards_lockout_case_insensitive` | unit | exists |
| BE-DATA-004 | MUST | `acct::RegistrationTest::test_register_sends_activation_mail_and_stores_hashed_key`; `acct::PasswordResetTest::test_token_hashed_single_use` | unit | exists |
| BE-DATA-005 | MUST | `wf-reg::RegistrySyncTest` | unit | exists |
| BE-DATA-006 | MUST | `wf-reg::RegistryInstallTest::test_uninstall_removes_entry_and_row`, `::test_uninstall_keeps_row_with_jobs_as_not_installed` (p) | unit | exists+planned |
| BE-DATA-007 | MUST | `core-schema::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit | exists |
| BE-DATA-008 | MUST | `jobs-api::JobLifecycleApiTest::test_job_readable_after_workflow_uninstall` (p) | unit | planned |
| BE-DATA-009 | MUST | `core-schema::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit | exists |
| BE-DATA-010 | MUST | `core-cfg::PathsAndPagesTest::test_traversal_rejected` | unit | exists |
| BE-DATA-011 | MUST | `jobs-worker::DeletedWhileRunningTest::test_deleting_a_waiting_job_removes_the_workspace_immediately`, `::test_deleting_a_running_job_leaves_the_workspace_to_the_worker`; `jobs-api::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces`; `e2e:findings_admin::test_c03_deleting_user_removes_the_workspace_of_a_running_job` | unit, e2e | exists |
| BE-DATA-012 | MUST | `jobs-api::JobLifecycleApiTest::test_queue_positions` | unit | exists |
| BE-DATA-013 | MUST | `jobs-api::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces`; `adm::LogsTest::test_user_delete_keeps_log_rows` (p) | unit | exists+planned |
| BE-DATA-014 | MUST | `wf-reg::RegistryAccessTest::test_deleted_group_is_pruned_from_settings` | unit | exists |
| BE-DATA-015 | MUST | `jobs-worker::WorkerQueueTest::test_heartbeat`; `core-api::HealthTest::test_health_with_fresh_and_stale_heartbeat` | unit | exists |
| BE-DATA-016 | MUST | `test.sh` step "Migrations up to date" (`makemigrations --check`) | gate | exists |
| BE-DATA-017 | MUST | `acct::DuplicateDetectionTest::test_find_case_duplicates` | unit | exists |
| BE-DATA-018 | MUST | `test.sh unit --postgres` run | gate | exists |

### [configuration.md](configuration.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-CONF-001 | MUST | `core-cfg::PathsAndPagesTest::test_paths` | unit | exists |
| BE-CONF-002 | MUST | `core-cfg::ConfigLoadTest::test_missing_file_yields_defaults` | unit | exists |
| BE-CONF-003 | MUST | `core-cfg::ConfigLoadTest::test_partial_file_filled_with_defaults_and_unknown_keys_kept` | unit | exists |
| BE-CONF-004 | MUST | `core-cfg::ConfigLoadTest::test_validation_errors_are_keyed_by_path`, `::test_broken_key_after_valid_load_falls_back_to_its_default` | unit | exists |
| BE-CONF-005 | MUST | `core-cfg::ConfigLoadTest::test_invalid_yaml_falls_back_to_defaults` | unit | exists |
| BE-CONF-006 | MUST | `core-cfg::ConfigLoadTest::test_config_status_ok_after_a_clean_load`; `core-api::HealthTest::test_health_reports_a_broken_settings_file`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e | exists |
| BE-CONF-007 | MUST | `core-cfg::ConfigLoadTest::test_numeric_strings_coerced` | unit | exists |
| BE-CONF-008 | MUST | `core-cfg::ConfigLoadTest::test_navbar_url_must_be_internal_or_http_in_a_hand_edited_file`, `::test_mail_tls_and_ssl_mutually_exclusive_in_a_hand_edited_file`; `e2e:findings_admin::test_c01_mail_tls_and_ssl_cannot_both_be_enabled`, `::test_c05_navbar_url_is_validated` | unit, e2e | exists |
| BE-CONF-009 | MUST | `core-cfg::ConfigLoadTest::test_external_edit_picked_up_via_mtime`, `::test_cache_hit_does_not_reparse` | unit | exists |
| BE-CONF-010 | MUST | `core-cfg::ConfigLoadTest::test_returned_dict_is_a_copy` | unit | exists |
| BE-CONF-011 | MUST | `core-cfg::ConfigWriteTest::test_set_value_persists_and_validates`, `::test_failed_write_leaves_original_intact` | unit | exists |
| BE-CONF-012 | MUST | `core-cfg::ConfigWriteTest::test_save_is_atomic_no_temp_files_left`, `::test_failed_write_leaves_original_intact` | unit | exists |
| BE-CONF-013 | MUST | `core-cfg::ConfigWriteTest::test_concurrent_writers_from_processes_do_not_lose_updates` | unit | exists |
| BE-CONF-014 | MUST | `core-cfg::ConfigWriteTest::test_update_settings_repairs_a_broken_file`, `::test_update_settings_deep_merge_and_callable` | unit | exists |
| BE-CONF-015 | MUST | `core-cfg::ConfigWriteTest::test_new_settings_file_is_owner_only` (p) | unit | planned |
| BE-CONF-016 | MUST | `core-cfg::ConfigWriteTest::test_cache_updated_after_write` (p) | unit | planned |
| BE-CONF-017 | MUST | `core-cfg::PathsAndPagesTest::test_traversal_rejected` | unit | exists |
| BE-CONF-018 | MUST | `core-cfg::CommittedHomeTest::test_committed_settings_yaml_is_valid_and_complete` | unit | exists |
| BE-CONF-019 | MUST | `core-cfg::CommittedHomeTest::test_committed_layout` | unit | exists |
| BE-CONF-020 | MUST | `core-cfg::PathsAndPagesTest::test_parse_env` | unit | exists |

### [authentication.md](authentication.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-AUTH-001 | MUST | `acct::LoginTest::test_success_updates_last_login_and_session`; `core-api::AuthSessionTest::test_login_me_logout_flow_without_trailing_slash`; `acct-c::AuthContractTest::test_valid_login_returns_user_and_session`; `e2e:auth::test_login_and_logout_via_ui` | unit, contract, e2e | exists |
| BE-AUTH-002 | MUST | `acct::LoginTest::test_username_case_insensitive`, `::test_email_is_not_a_login_name` (p) | unit | exists+planned |
| BE-AUTH-003 | MUST | `acct::LoginTest::test_unknown_user_and_wrong_password_same_answer`; `core-api::AuthSessionTest::test_login_errors_use_envelope`; `acct-c::AuthContractTest::test_wrong_credentials_returns_400`; `e2e:auth::test_login_wrong_password_shows_error` | unit, contract, e2e | exists |
| BE-AUTH-004 | MUST | `acct-c::AuthContractTest::test_missing_username_returns_400_with_username_error`, `::test_missing_password_returns_400_with_password_error` | contract | exists |
| BE-AUTH-005 | MUST | `core-api::AuthSessionTest::test_inactive_user_cannot_login`; `acct::ActivationTest::test_login_blocked_before_activation`, `::test_inactive_with_wrong_password_gets_generic_message` | unit | exists |
| BE-AUTH-006 | MUST | `acct::LoginTest::test_lockout_after_max_attempts`; `e2e:accounts::test_a3_lockout` | unit, e2e | exists |
| BE-AUTH-007 | MUST | `acct::DjangoAdminLockoutTest::test_locked_account_rejected_with_correct_password`, `::test_wrong_passwords_count_towards_lockout_case_insensitive`; `e2e:findings_security::test_b01_django_admin_login_bypasses_lockout`; `acct::LoginTest::test_attempts_during_lock_do_not_extend_it` (p) | unit, e2e | exists+planned |
| BE-AUTH-008 | MUST | `acct::LoginTest::test_success_resets_counter`, `::test_lockout_after_max_attempts`; `acct::DjangoAdminLockoutTest::test_successful_login_resets_counter` | unit | exists |
| BE-AUTH-009 | MUST | `acct::LoginTest::test_lockout_disabled_with_zero` | unit | exists |
| BE-AUTH-010 | MUST | `core-api::AuthSessionTest::test_login_requires_csrf` | unit | exists |
| BE-AUTH-011 | MUST | `acct::LoginTest::test_login_allowed_in_maintenance_mode` (p) | unit | planned |
| BE-AUTH-012 | MUST | `acct::LoginTest::test_obtain_token_endpoint_removed` | unit | exists |
| BE-AUTH-013 | MUST | `acct::PermissionMatrixTest::test_matrix`; `acct-c::AuthContractTest::test_logout_returns_200`; `core-api::AuthSessionTest::test_session_write_without_csrf_rejected` | unit, contract | exists |
| BE-AUTH-014 | MUST | `core-api::AuthSessionTest::test_me_anonymous`; `e2e:findings_security::test_permission_matrix_public` | unit, e2e | exists |
| BE-AUTH-015 | MUST | `core-api::AuthSessionTest::test_session_write_without_csrf_rejected`; `core-api::ErrorEnvelopeHandlerTest::test_other_api_exceptions`; `core-api::MiscRoutingTest::test_csrf_failure_view_api_and_non_api` (p) | unit | exists+planned |
| BE-AUTH-016 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`; `core-api::AuthSessionTest::test_login_requires_csrf` | unit | exists |
| BE-AUTH-017 | MUST | `core-dep::CookieFlagsTest::test_session_and_csrf_cookie_flags` (p) | unit | planned |
| BE-AUTH-018 | MUST | `core-dep::CookieFlagsTest::test_csrf_trusted_origins_default` (p) | unit | planned |
| BE-AUTH-019 | MUST | `core-api::TokenAuthTest::test_token_auth_without_csrf`; `acct::ApiTokenTest::test_token_client_needs_no_csrf` | unit | exists |
| BE-AUTH-020 | MUST | `core-api::TokenAuthTest::test_bad_token_is_401_envelope` | unit | exists |
| BE-AUTH-021 | MUST | `core-api::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope`; `e2e:findings_security::test_permission_matrix_requires_authentication` | unit, e2e | exists |
| BE-AUTH-022 | MUST | `core-api::TokenAuthTest::test_deactivated_user_token_and_session_rejected` (p) | unit | planned |
| BE-AUTH-023 | MUST | `core-dep::PasswordHasherTest::test_argon2_is_the_default_hasher`, `::test_pbkdf2_hash_is_upgraded_to_argon2_on_login` | unit | exists |
| BE-AUTH-024 | MUST | `core-dep::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e`, `::test_clean_when_e2e_flag_set`, `::test_clean_when_debug`, `::test_clean_when_flag_unset` | unit | exists |
| BE-AUTH-025 | MUST | `acct::LoginTest::test_password_not_logged` (p) | unit | planned |
| BE-AUTH-026 | SHOULD (planned) | `acct::ThrottleTest::test_login_throttled_per_address` (p) | unit | planned |
| BE-AUTH-027 | MUST (planned) | `acct::ThrottleTest::test_throttle_keys_on_rightmost_forwarded_address` (p) | unit | planned |

### [accounts.md](accounts.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-ACCT-001 | MUST | `acct::UserModelTest::test_email_normalised_and_username_stripped`, `::test_db_rejects_case_variant_username`, `::test_db_rejects_case_variant_email`, `::test_natural_key_lookup_ignores_case` | unit | exists |
| BE-ACCT-002 | MUST | `acct::ValidationRulesTest`; `acct::UserModelTest::test_clean_uses_shared_rules` | unit | exists |
| BE-ACCT-003 | MUST | `acct::ValidationRulesTest::test_frontend_module_mirrors_messages`; `fe:utils/validation.test.js`; `e2e:accounts::test_a2_client_side_rules_match_server` | unit, unit (vitest), e2e | exists |
| BE-ACCT-004 | MUST | `acct::DuplicateDetectionTest::test_find_case_duplicates`, `::test_check_raises_with_list` | unit | exists |
| BE-ACCT-005 | MUST | `acct::RegistrationTest::test_all_field_errors_reported`, `::test_password_mismatch`; `acct-c::RegistrationContractTest` | unit, contract | exists |
| BE-ACCT-006 | MUST | `acct::RegistrationTest::test_case_variants_rejected`, `::test_integrity_error_is_field_error` (p); `acct::K1RegressionTest::test_no_duplicate_users`; `acct-c::RegistrationContractTest::test_duplicate_username_returns_400_with_username_error`; `e2e:accounts::test_a2_case_variant_duplicates_rejected` | unit, contract, e2e | exists+planned |
| BE-ACCT-007 | MUST | `acct::RegistrationTest::test_privilege_fields_ignored` | unit | exists |
| BE-ACCT-008 | MUST | `acct::RegistrationTest::test_register_sends_activation_mail_and_stores_hashed_key`, `::test_link_uses_server_url`; `acct-c::RegistrationContractTest::test_valid_registration_returns_201_with_user`; `e2e:accounts::test_a1_register_activate_login` | unit, contract, e2e | exists |
| BE-ACCT-009 | MUST | `acct::RegistrationTest::test_mail_failure_rolls_back` | unit | exists |
| BE-ACCT-010 | MUST | `acct::RegistrationTest::test_without_activation_account_is_active` | unit | exists |
| BE-ACCT-011 | MUST | `acct::ActivationTest::test_invalid_key`, `::test_raw_hash_is_not_a_key`, `::test_get_not_allowed` | unit | exists |
| BE-ACCT-012 | MUST | `acct::ActivationTest::test_activate_is_idempotent`, `::test_deactivated_user_cannot_reactivate_with_old_link`; `e2e:accounts::test_a1_register_activate_login` | unit, e2e | exists |
| BE-ACCT-013 | MUST | `acct::PasswordResetTest::test_same_answer_for_known_unknown_and_inactive`, `::test_missing_email_is_field_error`; `acct-c::PasswordResetContractTest` | unit, contract | exists |
| BE-ACCT-014 | MUST | `acct::PasswordResetTest::test_token_hashed_single_use`, `::test_expires_after_24h`, `::test_new_request_invalidates_previous_link` (p) | unit | exists+planned |
| BE-ACCT-015 | MUST | `acct::PasswordResetTest::test_token_hashed_single_use`, `::test_expired`, `::test_password_rules`, `::test_reset_clears_lockout`, `::test_reset_revokes_api_token`; `e2e:accounts::test_a4_password_reset` | unit, e2e | exists |
| BE-ACCT-016 | MUST | `acct::ProfileTest::test_get`; `acct::ApiTokenTest::test_create_use_regenerate_revoke` | unit | exists |
| BE-ACCT-017 | MUST | `acct::ProfileTest::test_no_mass_assignment`, `::test_put_not_allowed`, `::test_update_full_name`; `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api` | unit, e2e | exists |
| BE-ACCT-018 | MUST | `acct::ProfileTest::test_email_change_requires_current_password`, `::test_email_unique_ignoring_case`, `::test_blank_password_means_unchanged`, `::test_password_change` | unit | exists |
| BE-ACCT-019 | MUST | `acct::ProfileTest::test_password_change`, `::test_password_change_revokes_api_token`, `::test_password_change_ends_other_sessions` (p); `e2e:findings_security::test_b02_password_change_revokes_api_token` | unit, e2e | exists+planned |
| BE-ACCT-020 | MUST | `acct::ApiTokenTest::test_create_use_regenerate_revoke`; `e2e:accounts::test_a5_profile_name_email_password_token` | unit, e2e | exists |
| BE-ACCT-021 | MUST | `acct::ApiTokenTest::test_create_use_regenerate_revoke`, `::test_revoke_without_token` (p) | unit | exists+planned |
| BE-ACCT-022 | MUST | `acct::DjangoAdminTokenExposureTest`; `e2e:findings_security::test_b03_token_keys_not_readable_in_django_admin` | unit, e2e | exists |
| BE-ACCT-023 | MUST | `acct::SelfDeleteTest::test_requires_password` | unit | exists |
| BE-ACCT-024 | MUST | `acct::SelfDeleteTest::test_last_admin_cannot_delete_self` | unit | exists |
| BE-ACCT-025 | MUST | `acct::SelfDeleteTest::test_delete_logs_out`; `jobs-api::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces`; `e2e:accounts::test_a6_delete_own_account` | unit, e2e | exists |
| BE-ACCT-026 | MUST | `acct::RegistrationTest::test_link_uses_server_url`, `::test_link_falls_back_to_request_host` (p) | unit | exists+planned |

### [access-control.md](access-control.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-ACL-001 | MUST | `core-api::IsAdminTest::test_admin_definition`; `core-api::AdminPermissionTest::test_admin_endpoints_use_is_admin`; `acct::PermissionMatrixTest::test_admin_via_group_only`; `acct::UserModelTest::test_admin_helpers` | unit | exists |
| BE-ACL-002 | MUST | `acct::AdminUsersTest::test_admin_group_only_via_is_admin`, `::test_self_protection`, `::test_superuser_stays_admin`; `acct::AdminGroupsTest::test_admin_group_protected`; `e2e:accounts::test_d3_admin_users` | unit, e2e | exists |
| BE-ACL-003 | MUST | `core-schema::PermissionInventoryTest::test_every_api_view_declares_permission_classes` (p) | unit | planned |
| BE-ACL-004 | MUST | `acct::PermissionMatrixTest::test_matrix`; `core-api::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope`; `e2e:findings_security::test_permission_matrix_admin_endpoints`, `::test_permission_matrix_requires_authentication` | unit, e2e | exists |
| BE-ACL-005 | MUST | `acct::PermissionMatrixTest::test_non_admin_gets_no_data`; `acct-c::GroupContractTest::test_non_admin_cannot_create_group`; `acct-c::UserUpdateContractTest::test_user_cannot_update_another_users_profile`; `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api`; `e2e:deep_links::test_admin_route_forbidden_for_regular_user` | unit, contract, e2e | exists |
| BE-ACL-006 | MUST | `jobs-api::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`; `wf-c::WorkflowDetailContractTest::test_non_member_user_gets_404_for_private_workflow`; `e2e:findings_security::test_permission_matrix_object_access` | unit, contract, e2e | exists |
| BE-ACL-007 | MUST | `wf-c::WorkflowListContractTest::test_unauthenticated_user_sees_only_public_workflows`, `::test_authenticated_user_sees_accessible_workflows`, `::test_admin_sees_all_enabled_workflows`; `wf-c::WorkflowDetailContractTest::test_unauthenticated_user_gets_404_for_private_workflow`; `wf::WorkflowAPITest::test_workflow_list_unauthenticated`, `::test_workflow_list_authenticated`, `::test_workflow_list_admin`; `e2e:admin_workflows::test_w1_workflow_visibility_per_user`, `::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_groups_and_public_via_settings_page` | unit, contract, e2e | exists |
| BE-ACL-008 | MUST | `wf::WorkflowTest::test_can_access_group_restricted_workflow`, `::test_admin_access`; `wf-c::WorkflowListContractTest::test_private_workflow_without_groups_admin_only` (p) | unit, contract | exists+planned |
| BE-ACL-009 | MUST | `jobs-api::SubmissionTest::test_workflow_access_and_disabled`; `wf::WorkflowTest::test_unauthenticated_access`, `::test_can_access_public_workflow` | unit | exists |
| BE-ACL-010 | MUST | `jobs-api::SubmissionTest::test_maintenance_blocks_users_not_admins`; `e2e:queue::test_maintenance_blocks_users_not_admins` | unit, e2e | exists |
| BE-ACL-011 | MUST | `jobs-api::JobLifecycleApiTest::test_job_visible_after_workflow_access_revoked` (p) | unit | planned |
| BE-ACL-012 | MUST | `jobs-api::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access` | unit | exists |
| BE-ACL-013 | MUST | `jobs-api::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`, `::test_output_traversal_and_foreign_ids`; `e2e:access_jobs::test_other_user_cannot_see_job_outputs_or_log`, `::test_anonymous_cannot_download`, `::test_owner_and_admin_can_download`; `e2e:findings_security::test_foreign_output_id_under_own_job` | unit, e2e | exists |
| BE-ACL-014 | MUST | `jobs-api::JobLifecycleApiTest::test_admin_cancel_of_foreign_job_is_marked_admin` (p) | unit | planned |
| BE-ACL-015 | MUST | `jobs-api::AdminJobsApiTest::test_admin_list_filters_and_permissions`; `e2e:findings_security::test_permission_matrix_admin_endpoints` | unit, e2e | exists |
| BE-ACL-016 | MUST | `acct::PermissionMatrixTest::test_matrix`; `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api` | unit, e2e | exists |

### [workflow-definition.md](workflow-definition.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-WDEF-001 | MUST | `wf-def::LoadDefinitionTest::test_load_from_dir_and_file` | unit | exists |
| BE-WDEF-002 | MUST | `wf-def::LoadDefinitionTest::test_load_from_dir_and_file`, `::test_missing_path_string` | unit | exists |
| BE-WDEF-003 | MUST | `wf-def::LoadDefinitionTest::test_missing_path_string` | unit | exists |
| BE-WDEF-004 | MUST | `wf-def::LoadDefinitionTest::test_invalid_yaml` | unit | exists |
| BE-WDEF-005 | MUST | `wf-def::LoadDefinitionTest::test_load_from_dir_and_file` | unit | exists |
| BE-WDEF-006 | MUST | `wf-def::LoadDefinitionTest::test_required_fields`, `::test_invalid_ids_and_duplicates`, `::test_unknown_input_type` | unit | exists |
| BE-WDEF-007 | MUST | `wf-def::LoadDefinitionTest::test_unsupported_steps_load_with_error` | unit | exists |
| BE-WDEF-008 | MUST | `wf-def::LoadDefinitionTest::test_required_fields`, `::test_boolean_id_must_be_quoted` (p) | unit | exists+planned |
| BE-WDEF-009 | MUST | `wf-def::LoadDefinitionTest::test_required_fields` | unit | exists |
| BE-WDEF-010 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types` | unit | exists |
| BE-WDEF-011 | MUST | `wf-def::LoadDefinitionTest::test_required_fields` | unit | exists |
| BE-WDEF-012 | MUST | `wf-def::CommandStepParsingTest` | unit | exists |
| BE-WDEF-013 | MUST | `wf-def::LoadDefinitionTest::test_unsupported_steps_load_with_error`; `wf-def::CommandStepParsingTest::test_taxodactyl_definition` | unit | exists |
| BE-WDEF-014 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`, `::test_default_script_is_main_nf`; `wf-def::CommandStepParsingTest::test_taxodactyl_definition` | unit | exists |
| BE-WDEF-015 | MUST | `wf-def::CommandStepParsingTest::test_taxodactyl_definition` | unit | exists |
| BE-WDEF-016 | MUST | `wf-def::LoadDefinitionTest::test_invalid_ids_and_duplicates`, `::test_unknown_input_type`; `wf-def::CommandStepParsingTest::test_taxodactyl_definition`; `wf-yref::YamlReferenceExampleTest`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-017 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-018 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`, `::test_list_needs_values_and_number_bounds`, `::test_write_file_must_be_plain_name` (p); `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists+planned |
| BE-WDEF-019 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`, `::test_list_needs_values_and_number_bounds`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-020 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`, `::test_list_needs_values_and_number_bounds`, `::test_bad_default_for_list_is_ignored_with_warning`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-021 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`, `::test_list_needs_values_and_number_bounds`, `::test_checkbox_default_by_mapped_value`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-022 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`, `::test_terms_value_ignored` (p); `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists+planned |
| BE-WDEF-023 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`; `wf-def::CommandStepParsingTest::test_taxodactyl_definition`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-024 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types`; `wf-yref::YamlReferenceExampleTest`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| BE-WDEF-025 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types` | unit | exists |
| BE-WDEF-026 | MUST | `wf-def::LoadDefinitionTest::test_invalid_ids_and_duplicates`, `::test_unknown_input_type` | unit | exists |
| BE-WDEF-027 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types` | unit | exists |
| BE-WDEF-028 | MUST | `wf-def::LoadDefinitionTest::test_parse_is_deterministic` (p) | unit | planned |
| BE-WDEF-031 | MUST | `wf-def::LoadDefinitionTest::test_all_input_types` | unit | exists |
| BE-WDEF-029 | SHOULD (planned) | — | — | none |
| BE-WDEF-030 | SHOULD (planned) | — | — | none |

### [workflow-registry.md](workflow-registry.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-WREG-001 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row` | unit | exists |
| BE-WREG-002 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row`, `::test_install_yaml_file_outside_apps_is_referenced_absolute`; `wf-reg::RegistrySyncTest::test_sync_from_hand_written_settings` | unit | exists |
| BE-WREG-003 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row`, `::test_install_yaml_file_outside_apps_is_referenced_absolute` | unit | exists |
| BE-WREG-004 | MUST | `wf-reg::RegistrySyncTest::test_sync_from_hand_written_settings` | unit | exists |
| BE-WREG-005 | MUST | `wf-reg::RegistrySyncTest::test_sync_from_hand_written_settings` | unit | exists |
| BE-WREG-006 | MUST | `wf-reg::RegistrySyncTest::test_sync_from_hand_written_settings` | unit | exists |
| BE-WREG-007 | MUST | `wf-reg::RegistrySyncTest::test_duplicate_ids_in_settings` | unit | exists |
| BE-WREG-008 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row` | unit | exists |
| BE-WREG-009 | MUST | `wf-reg::RegistrySyncTest::test_sync_from_hand_written_settings`, `::test_app_becoming_invalid_disables_row` | unit | exists |
| BE-WREG-010 | MUST | `wf-reg::RegistrySyncTest::test_manual_rows_untouched_by_sync`, `::test_removed_entry_with_jobs_is_kept_disabled` | unit | exists |
| BE-WREG-011 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row`; `wf-reg::RegistrySyncTest::test_sync_from_hand_written_settings` | unit | exists |
| BE-WREG-012 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row` | unit | exists |
| BE-WREG-013 | MUST | `wf-reg::RegistrySyncTest::test_sync_never_writes_settings` (p) | unit | planned |
| BE-WREG-014 | MUST | `wf-reg::RegistrySyncTest::test_sync_if_changed_detects_settings_edit` | unit | exists |
| BE-WREG-015 | MUST | `wf-reg::RegistrySyncTest::test_middleware_syncs_lazily_on_api_request`, `::test_middleware_sync_failure_does_not_fail_request` (p) | unit | exists+planned |
| BE-WREG-016 | MUST | `wf-reg::RegistrySyncTest::test_list_apps_does_not_write_on_a_plain_read`; `e2e:findings_jobs::test_a03_admin_workflow_list_does_not_write_on_every_read` | unit, e2e | exists |
| BE-WREG-017 | MUST | `wf-reg::RegistrySyncTest::test_sync_if_changed_detects_settings_edit`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_reload_after_yaml_edit` | unit, e2e | exists |
| BE-WREG-018 | MUST | `wf-reg::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row`, `::test_install_with_copy`, `::test_install_invalid_app_rejected_with_errors`, `::test_install_missing_path`, `::test_install_duplicate_id_conflict`, `::test_install_replace_updates_path_only` (p) | unit | exists+planned |
| BE-WREG-019 | MUST | `wf-reg::RegistryInstallTest::test_uninstall_removes_entry_and_row`, `::test_uninstall_unknown` | unit | exists |
| BE-WREG-020 | MUST | `wf-reg::RegistryAccessTest::test_groups_written_to_yaml_and_access_follows`, `::test_enable_disable_public`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_reload_after_yaml_edit` | unit, e2e | exists |
| BE-WREG-021 | MUST | `wf-reg::RegistrySyncTest::test_reload_picks_up_new_input` | unit | exists |
| BE-WREG-022 | MUST | `wf-reg::RegistryAccessTest::test_deleted_group_is_pruned_from_settings` | unit | exists |
| BE-WREG-023 | MUST | `wf-reg::RegistrySyncTest::test_sync_never_writes_settings` (p) | unit | planned |
| BE-WREG-024 | MUST | `wf-reg::RegistryAccessTest::test_nextflow_settings_round_trip` | unit | exists |
| BE-WREG-025 | MUST | `wf-reg::RegistryAccessTest::test_nextflow_settings_round_trip` | unit | exists |
| BE-WREG-026 | MUST | `wf-reg::RegistryAccessTest::test_groups_written_to_yaml_and_access_follows`, `::test_enable_disable_public`; `wf::WorkflowTest::test_can_access_public_workflow`, `::test_can_access_group_restricted_workflow`, `::test_admin_access`, `::test_unauthenticated_access` | unit | exists |
| BE-WREG-027 | MUST | `wf-reg::RegistryInstallTest::test_install_yaml_file_outside_apps_is_referenced_absolute` | unit | exists |
| BE-WREG-028 | MUST | `workflows/test_template_utils.py::test_scopes_and_names` (p) | unit | planned |

### [workflows-api.md](workflows-api.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-WAPI-001 | MUST | `wf::WorkflowAPITest::test_workflow_list_unauthenticated`, `::test_workflow_list_authenticated`, `::test_workflow_list_admin`; `wf-c::WorkflowListContractTest::test_unauthenticated_user_sees_only_public_workflows`, `::test_authenticated_user_sees_accessible_workflows`, `::test_admin_sees_all_enabled_workflows`; `e2e:findings_security::test_permission_matrix_public`; `e2e:admin_workflows::test_w1_workflow_visibility_per_user` | unit, contract, e2e | exists |
| BE-WAPI-002 | MUST | `wf-c::WorkflowDetailContractTest::test_non_member_user_gets_404_for_private_workflow`, `::test_unauthenticated_user_gets_404_for_private_workflow`; `adm::AdminWorkflowsApiTest::test_disabled_hidden_from_public_list_but_shown_to_admin`; `wf::WorkflowAPITest::test_disabled_workflow_detail_404_for_admin` (p) | unit, contract | exists+planned |
| BE-WAPI-003 | MUST | `wf::WorkflowAPITest::test_workflow_list_category_filter` | unit | exists |
| BE-WAPI-004 | MUST | `wf-c::WorkflowListContractTest::test_workflow_list_response_structure`; `wf-c::WorkflowDetailContractTest::test_workflow_detail_response_has_required_fields`, `::test_inputs_contains_only_input_parameters`, `::test_outputs_contains_only_output_parameters`; `wf::WorkflowAPITest::test_workflow_detail`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, contract, e2e | exists |
| BE-WAPI-005 | MUST | `wf-c::WorkflowDetailContractTest::test_no_internal_fields_exposed` (p) | contract | planned |
| BE-WAPI-006 | MUST | `wf-c::WorkflowDetailContractTest::test_unparseable_yaml_reports_definition_errors` (p) | contract | planned |
| BE-WAPI-007 | MUST | `wf::WorkflowAPITest::test_category_list` | unit | exists |
| BE-WAPI-008 | MUST | `adm::PermissionMatrixTest::test_anonymous_gets_401`, `::test_non_admin_gets_403_and_nothing_changes`; `e2e:findings_security::test_permission_matrix_admin_endpoints` | unit, e2e | exists |
| BE-WAPI-009 | MUST | `adm::AdminWorkflowsApiTest::test_install_list_patch_reload_uninstall`; `e2e:findings_jobs::test_a03_admin_workflow_list_does_not_write_on_every_read`; `e2e:admin_workflows::test_d4_invalid_entry_listed_with_errors` | unit, e2e | exists |
| BE-WAPI-010 | MUST | `adm::AdminWorkflowsApiTest::test_install_list_patch_reload_uninstall`, `::test_broken_app_effective_status_is_disabled_even_when_configured_enabled`; `e2e:admin_workflows::test_d4_reload_after_yaml_edit` | unit, e2e | exists |
| BE-WAPI-011 | MUST | `adm::AdminWorkflowsApiTest::test_install_list_patch_reload_uninstall` | unit | exists |
| BE-WAPI-012 | MUST | `adm::AdminWorkflowsApiTest::test_install_errors`; `e2e:admin_workflows::test_d4_install_invalid_then_valid_and_uninstall` | unit, e2e | exists |
| BE-WAPI-013 | MUST | `adm::AdminWorkflowsApiTest::test_install_list_patch_reload_uninstall`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_groups_and_public_via_settings_page` | unit, e2e | exists |
| BE-WAPI-014 | MUST | `adm::AdminWorkflowsApiTest::test_install_list_patch_reload_uninstall` | unit | exists |
| BE-WAPI-015 | MUST | `adm::AdminWorkflowsApiTest::test_broken_app_effective_status_is_disabled_even_when_configured_enabled`; `e2e:admin_workflows::test_d4_reload_after_yaml_edit` | unit, e2e | exists |
| BE-WAPI-016 | MUST | `adm::AdminWorkflowsApiTest::test_sync_returns_all_entries` (p) | unit | planned |
| BE-WAPI-017 | MUST | `adm::AdminWorkflowsApiTest::test_nextflow_per_app`; `e2e:admin_workflows::test_d4_per_app_nextflow_settings_persist` | unit, e2e | exists |
| BE-WAPI-018 | MUST | `adm::AdminWorkflowsApiTest::test_nextflow_per_app`; `e2e:admin_workflows::test_d4_per_app_nextflow_settings_persist` | unit, e2e | exists |
| BE-WAPI-019 | MUST | `adm::AdminWorkflowsApiTest::test_install_errors` | unit | exists |
| BE-WAPI-020 | MUST (planned) | `wf-c::SchemaContractTest` (p) | contract | planned |

### [job-submission.md](job-submission.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-JSUB-001 | MUST | `jobs-api::SubmissionTest::test_workflow_access_and_disabled` | unit | exists |
| BE-JSUB-002 | MUST | `jobs-api::SubmissionTest::test_workflow_access_and_disabled` | unit | exists |
| BE-JSUB-003 | MUST | `jobs-api::SubmissionTest::test_workflow_access_and_disabled` | unit | exists |
| BE-JSUB-004 | MUST | `jobs-api::SubmissionTest::test_maintenance_blocks_users_not_admins`; `e2e:queue::test_maintenance_blocks_users_not_admins` | unit, e2e | exists |
| BE-JSUB-005 | MUST | `jobs-api::SubmissionTest::test_queue_full`; `e2e:queue::test_queue_full_rejects_submission` | unit, e2e | exists |
| BE-JSUB-006 | MUST | `jobs-api::SubmissionTest::test_invalid_definition_gives_409` (p) | unit | planned |
| BE-JSUB-007 | MUST | `jobs-api::SubmissionTest::test_check_order` (p) | unit | planned |
| BE-JSUB-008 | MUST | `jobs-api::SubmissionTest::test_name_too_long_and_control_chars`, `::test_legacy_name_field_and_json_body`, `::test_all_input_types_are_resolved_and_stored`; `e2e:jobs::test_submit_hello_with_unicode_job_name` | unit, e2e | exists |
| BE-JSUB-009 | MUST | `jobs-api::SubmissionTest::test_name_too_long_and_control_chars`, `::test_legacy_name_field_and_json_body`, `::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox`; `e2e:jobs::test_submit_hello_with_unicode_job_name` | unit, e2e | exists |
| BE-JSUB-010 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes`; `jobs-worker::test_job_name_never_in_argv_or_paths` (p) | unit, e2e | exists+planned |
| BE-JSUB-011 | MUST | `jobs-api::SubmissionTest::test_field_errors`; `e2e:run_form::test_server_validation_field_errors` | unit, e2e | exists |
| BE-JSUB-012 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox` | unit | exists |
| BE-JSUB-013 | MUST | `jobs-api::SubmissionTest::test_file_part_for_text_input_is_rejected`; `e2e:findings_jobs::test_a01_file_part_for_text_input_is_rejected` | unit, e2e | exists |
| BE-JSUB-014 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox` | unit | exists |
| BE-JSUB-015 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox` | unit | exists |
| BE-JSUB-016 | MUST | `jobs-api::SubmissionTest::test_number_min_and_nan`, `::test_number_rejects_what_the_run_form_rejects`; `e2e:findings_jobs::test_a05_number_input_rejects_values_the_form_rejects` | unit, e2e | exists |
| BE-JSUB-017 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox` | unit | exists |
| BE-JSUB-018 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`, `::test_defaults_and_unchecked_checkbox` | unit | exists |
| BE-JSUB-019 | MUST | `jobs-api::SubmissionTest::test_field_errors` | unit | exists |
| BE-JSUB-020 | MUST | `jobs-api::SubmissionTest::test_file_accept_and_single_file`, `::test_field_errors` | unit | exists |
| BE-JSUB-021 | MUST | `jobs-api::SafeFilenameTest::test_names`; `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | unit, e2e | exists |
| BE-JSUB-022 | MUST | `jobs-api::SafeFilenameTest::test_names`; `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | unit, e2e | exists |
| BE-JSUB-023 | MUST | `jobs-api::SubmissionTest::test_upload_size_limit`, `::test_many_files_in_folder_input_is_a_client_error_not_500`; `e2e:findings_jobs::test_a02_many_files_in_folder_input_is_a_client_error` | unit, e2e | exists |
| BE-JSUB-024 | MUST | `jobs-api::SafeFilenameTest::test_names`; `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | unit, e2e | exists |
| BE-JSUB-025 | MUST | `jobs-api::SubmissionTest::test_failed_write_removes_workspace` (p) | unit | planned |
| BE-JSUB-026 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored` | unit | exists |
| BE-JSUB-027 | SHOULD | — | — | none |
| BE-JSUB-028 | MUST | `jobs-cmd::SubstitutionTest`; `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes` | unit | exists |
| BE-JSUB-029 | MUST | `jobs-cmd::SubstitutionTest`; `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes` | unit | exists |
| BE-JSUB-030 | MUST | `jobs-cmd::SubstitutionTest`; `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes` | unit | exists |
| BE-JSUB-031 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`; `jobs-cmd::SubstitutionTest::test_params_substitution_is_recursive_and_only_touches_strings` | unit | exists |

### [job-queue-worker.md](job-queue-worker.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-QUEUE-001 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-worker::WorkerFailureTest::test_failed_pipeline`; `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs-cmd::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit | exists |
| BE-QUEUE-002 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-worker::WorkerFailureTest::test_failed_pipeline`; `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs-cmd::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit | exists |
| BE-QUEUE-003 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-worker::WorkerFailureTest::test_failed_pipeline`; `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs-cmd::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit | exists |
| BE-QUEUE-004 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-worker::WorkerFailureTest::test_failed_pipeline`; `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs-cmd::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit | exists |
| BE-QUEUE-005 | MUST | `jobs-api::JobLifecycleApiTest::test_queue_positions` | unit | exists |
| BE-QUEUE-006 | MUST | `jobs-claim::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job`, `::test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once` | unit | exists |
| BE-QUEUE-007 | MUST | `jobs-worker::WorkerQueueTest::test_max_running_and_queue_advances_without_requests`; `e2e:queue::test_queue_limits_and_advances_after_cancel` | unit, e2e | exists |
| BE-QUEUE-008 | MUST | `jobs-worker::WorkerQueueTest::test_paused_queue_claims_nothing`; `e2e:queue::test_pause_and_resume_queue` | unit, e2e | exists |
| BE-QUEUE-009 | MUST | `jobs-worker::WorkerQueueTest::test_max_running_and_queue_advances_without_requests`; `e2e:queue::test_queue_limits_and_advances_after_cancel` | unit, e2e | exists |
| BE-QUEUE-010 | MUST | see BE-JSUB-005 (`jobs-api::SubmissionTest::test_queue_full`, `e2e:queue::test_queue_full_rejects_submission`) | unit, e2e | exists |
| BE-QUEUE-011 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| BE-QUEUE-012 | MUST | `jobs-worker::WorkerQueueTest::test_heartbeat` | unit | exists |
| BE-QUEUE-013 | MUST | `jobs-worker::TickPhaseIsolationTest`; `jobs-worker::RetryOnLockedTest` | unit | exists |
| BE-QUEUE-014 | MUST | `jobs-worker::ShutdownTest::test_shutdown_stops_running_jobs`; `jobs-worker::RunWorkerCommandTest::test_sigterm_stops_gracefully` (p) | unit | exists+planned |
| BE-QUEUE-015 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| BE-QUEUE-016 | MUST | `jobs-worker::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed`, `::test_foreign_process_group_is_not_killed`; `e2e:queue::test_worker_restart_fails_orphans_and_queue_continues` | unit, e2e | exists |
| BE-QUEUE-017 | MUST | `jobs-worker::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed`, `::test_foreign_process_group_is_not_killed`; `e2e:queue::test_worker_restart_fails_orphans_and_queue_continues` | unit, e2e | exists |
| BE-QUEUE-018 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists |
| BE-QUEUE-019 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_running_sets_flag`; `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`, `::test_sigkill_after_grace`; `e2e:jobs::test_cancel_running_job_from_job_page` | unit, e2e | exists |
| BE-QUEUE-020 | MUST | `jobs-worker::WorkerCancelTest::test_waiting_cancel_race_handled_by_worker` | unit | exists |
| BE-QUEUE-021 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists |
| BE-QUEUE-022 | MUST | `jobs-worker::WorkerFailureTest::test_invalid_snapshot`, `::test_poll_error_fails_job` (p) | unit | exists+planned |
| BE-QUEUE-023 | MUST | `jobs-worker::DeletedWhileRunningTest`; `jobs-api::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces` | unit | exists |
| BE-QUEUE-024 | MUST | `jobs-api::AdminJobsApiTest::test_restart`, `::test_restart_needs_enabled_workflow` | unit | exists |
| BE-QUEUE-025 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists |
| BE-QUEUE-026 | MUST | `jobs-api::CleanupCommandTest::test_retention` | unit | exists |
| BE-QUEUE-027 | MUST (planned) | `jobs-api::CleanupCommandTest::test_external_work_dir_removed` (p) | unit | planned |
| BE-QUEUE-028 | MUST (planned) | `jobs-worker::WorkerSuccessTest::test_progress_bumps_updated_at` (p) | unit | planned |

### [job-runner.md](job-runner.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-RUN-001 | MUST | `jobs-worker::WorkerSuccessTest::test_multi_step_and_remote_script`; `jobs-cmd::CommandStepWorkerTest::test_taxodactyl_shaped_job`, `::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit | exists |
| BE-RUN-002 | MUST | `jobs-worker::WorkerFailureTest::test_unsupported_step_fails_with_clear_message` | unit | exists |
| BE-RUN-003 | MUST | `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs-cmd::CommandStepWorkerTest::test_cancel_during_long_command_kills_the_process_group`; `jobs-worker::test_children_killed_after_normal_exit` (p) | unit | exists+planned |
| BE-RUN-004 | MUST | `jobs-worker::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs-cmd::CommandStepWorkerTest::test_cancel_during_long_command_kills_the_process_group`; `jobs-worker::test_children_killed_after_normal_exit` (p) | unit | exists+planned |
| BE-RUN-005 | MUST | `jobs-worker::WorkerFailureTest::test_missing_binary`; `jobs-cmd::CommandStepWorkerTest::test_missing_executable` | unit | exists |
| BE-RUN-006 | MUST | `jobs-worker::WorkerSuccessTest::test_env_files_profile_and_app_config`, `::test_multi_step_and_remote_script`; `jobs-api::JobLifecycleApiTest::test_a04_per_app_work_dir_is_an_allowed_output_root`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root` | unit, e2e | exists |
| BE-RUN-007 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` | unit | exists |
| BE-RUN-008 | MUST | `jobs-worker::WorkerSuccessTest::test_env_files_profile_and_app_config`, `::test_multi_step_and_remote_script`; `jobs-api::JobLifecycleApiTest::test_a04_per_app_work_dir_is_an_allowed_output_root`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root` | unit, e2e | exists |
| BE-RUN-009 | MUST | `jobs-worker::WorkerSuccessTest::test_env_files_profile_and_app_config`, `::test_multi_step_and_remote_script`; `jobs-api::JobLifecycleApiTest::test_a04_per_app_work_dir_is_an_allowed_output_root`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root` | unit, e2e | exists |
| BE-RUN-010 | MUST | `jobs-worker::WorkerSuccessTest::test_env_files_profile_and_app_config`, `::test_multi_step_and_remote_script`; `jobs-api::JobLifecycleApiTest::test_a04_per_app_work_dir_is_an_allowed_output_root`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root` | unit, e2e | exists |
| BE-RUN-011 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-RUN-012 | MUST | `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes`; `jobs-cmd::SubstitutionTest`; `e2e:command_steps::test_command_steps_run_and_show_output` | unit, e2e | exists |
| BE-RUN-013 | MUST | `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes`; `jobs-cmd::SubstitutionTest`; `e2e:command_steps::test_command_steps_run_and_show_output` | unit, e2e | exists |
| BE-RUN-014 | MUST | `jobs-cmd::StreamVisibilityTest::test_hidden_streams_stay_on_disk`, `::test_flagged_streams_are_shown` | unit | exists |
| BE-RUN-015 | MUST | `jobs-cmd::StreamVisibilityTest::test_hidden_streams_stay_on_disk`, `::test_flagged_streams_are_shown` | unit | exists |
| BE-RUN-016 | MUST | `jobs-cmd::CommandStepWorkerTest::test_runaway_output_is_capped` | unit | exists |
| BE-RUN-017 | MUST | `jobs-worker::WorkerSuccessTest::test_env_files_profile_and_app_config`; `jobs-cmd::SubstitutionTest::test_build_variables` | unit | exists |
| BE-RUN-018 | MUST | `jobs-worker::WorkerSuccessTest::test_env_files_profile_and_app_config`; `jobs-cmd::SubstitutionTest::test_build_variables` | unit | exists |
| BE-RUN-019 | MUST (planned) | `jobs-worker::test_server_secrets_not_in_step_env` (p) | unit | planned |
| BE-RUN-020 | MUST | `jobs-cmd::CommandStepWorkerTest::test_injection_is_literal_in_both_modes`; `jobs-cmd::SubstitutionTest`; `e2e:command_steps::test_command_steps_run_and_show_output` | unit, e2e | exists |
| BE-RUN-021 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-RUN-022 | MUST | `jobs-worker::WorkerFailureTest::test_failed_pipeline`; `jobs-cmd::CommandStepWorkerTest::test_nextflow_stdout_flag_adds_output_to_failure_message`; `e2e:jobs::test_failing_workflow` | unit, e2e | exists |
| BE-RUN-023 | MUST | `jobs-cmd::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail`; `e2e:command_steps::test_failing_command_step_fails_the_job` | unit, e2e | exists |
| BE-RUN-024 | MUST | `jobs-worker::WorkerFailureTest::test_missing_binary`; `jobs-cmd::CommandStepWorkerTest::test_missing_executable` | unit | exists |
| BE-RUN-025 | MUST | `jobs-worker::test_only_workspace_files_written` (p) | unit | planned |

### [job-progress-outputs.md](job-progress-outputs.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-PROG-001 | MUST | `jobs-prog::AnnotationParserTest::test_levels`, `::test_value_may_contain_colons`, `::test_unicode_and_invalid` | unit | exists |
| BE-PROG-002 | MUST | `jobs-prog::AnnotationParserTest::test_levels`, `::test_value_may_contain_colons`, `::test_unicode_and_invalid`, `::test_info_and_success_names` (p) | unit | exists+planned |
| BE-PROG-003 | MUST | `jobs-prog::AnnotationParserTest::test_group`, `::test_unterminated_group_flushed_on_close` | unit | exists |
| BE-PROG-004 | MUST | `jobs-prog::AnnotationParserTest::test_message_truncated` (p) | unit | planned |
| BE-PROG-005 | MUST | `jobs-prog::MergerTest::test_dedup_between_sources`, `::test_read_task_annotations`; `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` | unit | exists |
| BE-PROG-006 | MUST | `jobs-prog::MergerTest::test_dedup_between_sources`, `::test_read_task_annotations`; `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` | unit | exists |
| BE-PROG-007 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-PROG-008 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-PROG-009 | MUST | `jobs-prog::LineBufferTest::test_partial_lines` | unit | exists |
| BE-PROG-010 | MUST | `jobs-prog::TaskLineTest::test_formats` | unit | exists |
| BE-PROG-011 | MUST | `jobs-prog::TraceAndTrackerTest::test_incremental_trace_and_counts`, `::test_trace_rewrite_restarts` (p) | unit | exists+planned |
| BE-PROG-012 | MUST | `jobs-prog::TraceAndTrackerTest::test_incremental_trace_and_counts`, `::test_trace_without_process_column`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-PROG-013 | MUST | `jobs-prog::TraceAndTrackerTest::test_incremental_trace_and_counts`, `::test_trace_without_process_column`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-PROG-014 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`, `::test_processes_saved_only_on_change` (p) | unit | exists+planned |
| BE-PROG-015 | MUST | `jobs-prog::TraceAndTrackerTest::test_incremental_trace_and_counts`, `::test_trace_without_process_column`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-PROG-016 | MUST | `jobs-cmd::CommandStepWorkerTest::test_taxodactyl_shaped_job` (p) | unit | planned |
| BE-PROG-017 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-api::JobLifecycleApiTest::test_output_traversal_and_foreign_ids`, `::test_a04_per_app_work_dir_is_an_allowed_output_root`, `::test_a04_global_work_dir_still_allowed_without_an_app_override`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root`; `jobs/tests/test_outputs.py::CollectOutputsTest` (p) | unit, e2e | exists+planned |
| BE-PROG-018 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-api::JobLifecycleApiTest::test_output_traversal_and_foreign_ids`, `::test_a04_per_app_work_dir_is_an_allowed_output_root`, `::test_a04_global_work_dir_still_allowed_without_an_app_override`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root`; `jobs/tests/test_outputs.py::CollectOutputsTest` (p) | unit, e2e | exists+planned |
| BE-PROG-019 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs-api::JobLifecycleApiTest::test_output_traversal_and_foreign_ids`, `::test_a04_per_app_work_dir_is_an_allowed_output_root`, `::test_a04_global_work_dir_still_allowed_without_an_app_override`; `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root`; `jobs/tests/test_outputs.py::CollectOutputsTest` (p) | unit, e2e | exists+planned |
| BE-PROG-020 | MUST | `jobs-api::JobLifecycleApiTest::test_output_traversal_and_foreign_ids` | unit | exists |
| BE-PROG-021 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_failing_workflow`; `jobs/tests/test_outputs.py::ReadJobLogTest` (p) | unit, e2e | exists+planned |
| BE-PROG-022 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_failing_workflow`; `jobs/tests/test_outputs.py::ReadJobLogTest` (p) | unit, e2e | exists+planned |
| BE-PROG-023 | MUST | `jobs-cmd::StreamVisibilityTest::test_hidden_streams_stay_on_disk`, `::test_flagged_streams_are_shown`; `e2e:command_steps::test_command_steps_run_and_show_output` | unit, e2e | exists |
| BE-PROG-024 | MUST | `jobs-cmd::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail`; `e2e:command_steps::test_failing_command_step_fails_the_job` | unit, e2e | exists |
| BE-PROG-025 | MUST | `jobs-cmd::CommandStepWorkerTest::test_runaway_output_is_capped` | unit | exists |
| BE-PROG-026 | MUST | `jobs-worker::WorkerFailureTest::test_failed_pipeline`; `jobs-cmd::CommandStepWorkerTest::test_nextflow_stdout_flag_adds_output_to_failure_message` | unit | exists |
| BE-PROG-027 | MAY | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` | unit | exists |

### [jobs-api.md](jobs-api.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-JAPI-001 | MUST | `jobs-api::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`; `e2e:findings_security::test_permission_matrix_object_access`, `::test_permission_matrix_requires_authentication`; `e2e:access_jobs::test_anonymous_cannot_download` | unit, e2e | exists |
| BE-JAPI-002 | MUST | `jobs-api::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`; `e2e:access_jobs::test_other_user_cannot_see_job_outputs_or_log`, `::test_owner_and_admin_can_download`; `e2e:findings_security::test_permission_matrix_object_access` | unit, e2e | exists |
| BE-JAPI-003 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`, `::test_deleted_job_is_404_for_admin` (p) | unit | exists+planned |
| BE-JAPI-004 | MUST | `jobs-api::JobLifecycleApiTest::test_malformed_job_id_is_404` (p) | unit | planned |
| BE-JAPI-005 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`, `::test_other_users_get_404_admin_gets_access`, `::test_list_order_and_pagination` (p); `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists+planned |
| BE-JAPI-006 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download` | unit | exists |
| BE-JAPI-007 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`, `::test_queue_positions`, `::test_cancel_running_sets_flag` | unit | exists |
| BE-JAPI-008 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_submit_hello_with_unicode_job_name` | unit, e2e | exists |
| BE-JAPI-009 | MUST | `jobs-api::SubmissionTest::test_all_input_types_are_resolved_and_stored`; `jobs-api::JobLifecycleApiTest::test_detail_inputs_hide_paths` (p); `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | unit, e2e | exists+planned |
| BE-JAPI-010 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_live_progress_multi_process` | unit, e2e | exists |
| BE-JAPI-011 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists |
| BE-JAPI-012 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_running_sets_flag`; `e2e:jobs::test_cancel_running_job_from_job_page` | unit, e2e | exists |
| BE-JAPI-013 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` | unit | exists |
| BE-JAPI-014 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists |
| BE-JAPI-015 | MUST | `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` | unit | exists |
| BE-JAPI-016 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:jobs::test_failing_workflow` | unit, e2e | exists |
| BE-JAPI-017 | MUST | `jobs-api::JobLifecycleApiTest::test_output_traversal_and_foreign_ids`; `e2e:findings_security::test_foreign_output_id_under_own_job` | unit, e2e | exists |
| BE-JAPI-018 | MUST | `jobs-api::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e:command_steps::test_command_steps_run_and_show_output` | unit, e2e | exists |
| BE-JAPI-019 | MUST | `jobs-api::OutputDownloadContentTypeTest::test_html_never_served_as_html`, `::test_svg_never_served_inline`, `::test_txt_is_safe_and_can_be_inline`, `::test_png_is_safe_and_can_be_inline`; `e2e:findings_security::test_b04_html_output_not_served_as_active_content` | unit, e2e | exists |
| BE-JAPI-020 | MUST | `jobs-api::OutputDownloadContentTypeTest::test_html_never_served_as_html`, `::test_svg_never_served_inline`, `::test_txt_is_safe_and_can_be_inline`, `::test_png_is_safe_and_can_be_inline`; `e2e:findings_security::test_b04_html_output_not_served_as_active_content` | unit, e2e | exists |
| BE-JAPI-021 | MUST | `jobs-api::OutputDownloadContentTypeTest::test_html_never_served_as_html`, `::test_svg_never_served_inline`, `::test_txt_is_safe_and_can_be_inline`, `::test_png_is_safe_and_can_be_inline`; `e2e:findings_security::test_b04_html_output_not_served_as_active_content` | unit, e2e | exists |
| BE-JAPI-022 | MUST | `jobs-api::SubmissionTest`; `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:queue::test_queue_full_rejects_submission` | unit, e2e | exists |
| BE-JAPI-023 | MUST | `core-api::ErrorEnvelopeHandlerTest`; `jobs-api::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules` | unit | exists |
| BE-JAPI-024 | MUST | `jobs/tests/test_contract.py::JobsContractTest` (p) | contract | planned |
| BE-JAPI-025 | SHOULD | — | — | none |

### [admin-api.md](admin-api.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-ADM-001 | MUST | `adm::PermissionMatrixTest::test_anonymous_gets_401`, `::test_non_admin_gets_403_and_nothing_changes`, `::test_admin_via_admin_group`; `acct::PermissionMatrixTest::test_matrix`, `::test_non_admin_gets_no_data`; `jobs-api::AdminJobsApiTest::test_admin_list_filters_and_permissions`; `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api` | unit, e2e | exists |
| BE-ADM-002 | MUST | `adm::PermissionMatrixTest::test_admin_session_needs_csrf` | unit | exists |
| BE-ADM-003 | MUST | `adm::DashboardQueueTest::test_pause_resume_maintenance_write_settings`; `e2e:admin_dashboard::test_d7_logs_show_admin_actions` | unit, e2e | exists |
| BE-ADM-010 | MUST | `adm::DashboardQueueTest::test_dashboard_shape_and_counts`; `e2e:admin_dashboard::test_d1_dashboard_counts_match_db` | unit, e2e | exists |
| BE-ADM-011 | SHOULD | — | — | none |
| BE-ADM-012 | MUST | `adm::DashboardQueueTest::test_pause_resume_maintenance_write_settings`; `e2e:admin_dashboard::test_d1_pause_resume_queue`, `::test_d1_maintenance_mode_banner` | unit, e2e | exists |
| BE-ADM-013 | MUST | `adm::DashboardQueueTest::test_pause_resume_maintenance_write_settings`; `e2e:admin_dashboard::test_d1_pause_resume_queue`, `::test_d1_maintenance_mode_banner` | unit, e2e | exists |
| BE-ADM-014 | MUST | `adm::DashboardQueueTest::test_queue_actions_idempotent` (p) | unit | planned |
| BE-ADM-020 | MUST | `acct::AdminUsersTest::test_list_shape_and_search` | unit | exists |
| BE-ADM-021 | MUST | `acct::AdminUsersTest::test_privilege_fields_not_writable`, `::test_put_and_post_not_allowed`; `acct-c::UserUpdateContractTest::test_admin_can_update_any_user` | unit, contract | exists |
| BE-ADM-022 | MUST | `acct::AdminUsersTest::test_set_groups_by_name`, `::test_unknown_group`, `::test_admin_group_only_via_is_admin` | unit | exists |
| BE-ADM-023 | MUST | `acct::AdminUsersTest::test_set_groups_by_name`, `::test_unknown_group`, `::test_admin_group_only_via_is_admin` | unit | exists |
| BE-ADM-024 | MUST | `acct::AdminUsersTest::test_self_protection`, `::test_superuser_stays_admin` | unit | exists |
| BE-ADM-025 | MUST | `acct::AdminUsersTest::test_activate_deactivate` | unit | exists |
| BE-ADM-026 | MUST | `acct::AdminUsersTest::test_delete`; `e2e:accounts::test_d3_admin_users`; `e2e:findings_admin::test_c03_deleting_user_removes_the_workspace_of_a_running_job` | unit, e2e | exists |
| BE-ADM-027 | MUST | `acct::AdminUsersTest::test_unknown_user_404` (p) | unit | planned |
| BE-ADM-030 | MUST | `acct::AdminGroupsTest::test_list_with_member_count`, `::test_create`, `::test_create_duplicate_ignoring_case`, `::test_create_invalid`, `::test_delete`, `::test_admin_group_protected`; `acct-c::GroupContractTest` | unit, contract | exists |
| BE-ADM-031 | MUST | `acct::AdminGroupsTest::test_list_with_member_count`, `::test_create`, `::test_create_duplicate_ignoring_case`, `::test_create_invalid`, `::test_delete`, `::test_admin_group_protected`; `acct-c::GroupContractTest` | unit, contract | exists |
| BE-ADM-032 | MUST | `acct::AdminGroupsTest::test_list_with_member_count`, `::test_create`, `::test_create_duplicate_ignoring_case`, `::test_create_invalid`, `::test_delete`, `::test_admin_group_protected`; `acct-c::GroupContractTest` | unit, contract | exists |
| BE-ADM-040 | MUST | `jobs-api::AdminJobsApiTest::test_admin_list_filters_and_permissions`, `::test_restart`, `::test_restart_needs_enabled_workflow`; `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | unit, e2e | exists |
| BE-ADM-041 | MUST | `jobs-api::AdminJobsApiTest::test_admin_list_filters_and_permissions`, `::test_restart`, `::test_restart_needs_enabled_workflow`; `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | unit, e2e | exists |
| BE-ADM-042 | MUST | `jobs-api::AdminJobsApiTest::test_admin_list_filters_and_permissions`, `::test_restart`, `::test_restart_needs_enabled_workflow`; `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | unit, e2e | exists |
| BE-ADM-043 | MUST | `jobs-api::AdminJobsApiTest::test_admin_list_filters_and_permissions`, `::test_restart`, `::test_restart_needs_enabled_workflow`; `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | unit, e2e | exists |
| BE-ADM-050 | MUST | `adm::GeneralSettingsTest::test_round_trip_to_disk`, `::test_partial_update_keeps_other_keys`, `::test_validation_errors_in_envelope_fields`; `e2e:admin_settings::test_d5_general_settings_round_trip`, `::test_d5_general_settings_validation_error` | unit, e2e | exists |
| BE-ADM-051 | MUST | `adm::GeneralSettingsTest::test_round_trip_to_disk`, `::test_partial_update_keeps_other_keys`, `::test_validation_errors_in_envelope_fields`; `e2e:admin_settings::test_d5_general_settings_round_trip`, `::test_d5_general_settings_validation_error` | unit, e2e | exists |
| BE-ADM-052 | MUST | `adm::MailSettingsTest::test_password_write_only`, `::test_invalid_backend`; `e2e:admin_settings::test_d5_mail_password_write_only`; `e2e:findings_admin::test_c01_mail_tls_and_ssl_cannot_both_be_enabled` | unit, e2e | exists |
| BE-ADM-053 | MUST | `adm::MailSettingsTest::test_password_write_only`, `::test_invalid_backend`; `e2e:admin_settings::test_d5_mail_password_write_only`; `e2e:findings_admin::test_c01_mail_tls_and_ssl_cannot_both_be_enabled` | unit, e2e | exists |
| BE-ADM-054 | MUST | `adm::MailSettingsTest::test_send_test_mail_to_admin`, `::test_send_test_mail_requires_address`; `e2e:admin_settings::test_d5_mail_test_lands_in_outbox` | unit, e2e | exists |
| BE-ADM-055 | MUST | `adm::NextflowSettingsTest::test_round_trip`; `e2e:admin_settings::test_d5_nextflow_settings_round_trip` | unit, e2e | exists |
| BE-ADM-056 | MUST | `adm::NextflowSettingsTest::test_round_trip`; `e2e:admin_settings::test_d5_nextflow_settings_round_trip` | unit, e2e | exists |
| BE-ADM-057 | MUST | `adm::NavbarTest::test_round_trip_and_public_filtering`, `::test_missing_title`; `e2e:findings_admin::test_c05_navbar_url_is_validated`; `e2e:admin_settings::test_d6_navbar_editor` | unit, e2e | exists |
| BE-ADM-058 | MUST | `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down`; `core-cfg` | unit, e2e | exists |
| BE-ADM-059 | MUST | `adm::GeneralSettingsTest::test_validation_errors_in_envelope_fields` | unit | exists |
| BE-ADM-060 | MUST | `adm::PagesTest::test_admin_crud`, `::test_home_footer_not_deletable`, `::test_admin_invalid_slug`; `e2e:admin_settings::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` | unit, e2e | exists |
| BE-ADM-061 | MUST | `adm::PagesTest::test_admin_crud`, `::test_home_footer_not_deletable`, `::test_admin_invalid_slug`; `e2e:admin_settings::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` | unit, e2e | exists |
| BE-ADM-062 | MUST | `adm::PagesTest::test_admin_crud`, `::test_home_footer_not_deletable`, `::test_admin_invalid_slug`; `e2e:admin_settings::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` | unit, e2e | exists |
| BE-ADM-063 | MUST | `adm::PagesTest::test_admin_crud`, `::test_home_footer_not_deletable`, `::test_admin_invalid_slug`; `e2e:admin_settings::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` | unit, e2e | exists |
| BE-ADM-064 | MUST | `adm::PagesTest::test_admin_crud`, `::test_home_footer_not_deletable`, `::test_admin_invalid_slug`; `e2e:admin_settings::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` | unit, e2e | exists |
| BE-ADM-065 | MAY | `e2e:admin_settings::test_d6_edit_home_and_footer` | e2e | exists |
| BE-ADM-070 | MUST | `adm::LogsTest::test_handler_and_filters`, `::test_unknown_level_filter_is_a_400_not_silently_empty`; `e2e:admin_dashboard::test_d7_logs_show_admin_actions` | unit, e2e | exists |
| BE-ADM-071 | MUST | `adm::LogsTest::test_handler_and_filters`, `::test_unknown_level_filter_is_a_400_not_silently_empty`; `e2e:admin_dashboard::test_d7_logs_show_admin_actions` | unit, e2e | exists |

### [server-pages-mail.md](server-pages-mail.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-SRV-001 | MUST | `adm::ServerInfoTest::test_public_server_info`; `e2e:smoke::test_footer_renders_footer_template` | unit, e2e | exists |
| BE-SRV-002 | MUST | `adm::NavbarTest::test_round_trip_and_public_filtering`; `e2e:smoke::test_navbar_items_from_yaml_in_order` | unit, e2e | exists |
| BE-SRV-003 | MUST | `adm::ServerInfoTest::test_public_server_info`; `e2e:smoke::test_footer_renders_footer_template` | unit, e2e | exists |
| BE-SRV-004 | MUST | `e2e:admin_settings::test_d5_general_settings_round_trip`, `::test_d6_navbar_editor` | e2e | exists |
| BE-SRV-010 | MUST | `adm::PagesTest::test_public_page`; `e2e:smoke::test_about_page_renders_pages_file` | unit, e2e | exists |
| BE-SRV-011 | MUST | `adm::PagesTest::test_public_page_traversal_rejected`; `e2e:admin_settings::test_d6_traversal_slugs_rejected` | unit, e2e | exists |
| BE-SRV-012 | MUST | `e2e:smoke::test_home_renders_home_template`; `e2e:admin_settings::test_d6_edit_home_and_footer` | e2e | exists |
| BE-SRV-013 | MUST | `e2e:smoke::test_unknown_page_shows_not_found` | e2e | exists |
| BE-SRV-020 | MUST | `jobs-api::SubmissionTest::test_maintenance_blocks_users_not_admins`; `e2e:queue::test_maintenance_blocks_users_not_admins` | unit, e2e | exists |
| BE-SRV-021 | MUST | `jobs-worker` (p) | unit | planned |
| BE-SRV-022 | MUST | `adm::ServerInfoTest::test_public_server_info`; `e2e:smoke::test_footer_renders_footer_template` | unit, e2e | exists |
| BE-SRV-030 | MUST | `core-api::HealthTest::test_health_without_worker`, `::test_health_reports_a_broken_settings_file`, `::test_health_with_fresh_and_stale_heartbeat`, `::test_health_db_down`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e | exists |
| BE-SRV-031 | MUST | `core-api::HealthTest::test_health_without_worker`, `::test_health_reports_a_broken_settings_file`, `::test_health_with_fresh_and_stale_heartbeat`, `::test_health_db_down`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e | exists |
| BE-SRV-032 | MUST | `core-api::HealthTest::test_health_without_worker`, `::test_health_reports_a_broken_settings_file`, `::test_health_with_fresh_and_stale_heartbeat`, `::test_health_db_down`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e | exists |
| BE-SRV-033 | MUST | `core-api::HealthTest::test_health_without_worker`, `::test_health_reports_a_broken_settings_file`, `::test_health_with_fresh_and_stale_heartbeat`, `::test_health_db_down`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e | exists |
| BE-SRV-034 | MUST | `core-api::HealthTest::test_health_without_worker`, `::test_health_reports_a_broken_settings_file`, `::test_health_with_fresh_and_stale_heartbeat`, `::test_health_db_down`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e | exists |
| BE-SRV-035 | MUST | contract test of 503 body vs `Health` (p) | — | planned |
| BE-SRV-040 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`, `::test_spa_missing_build_message`, `::test_unknown_api_path_is_json_404`; `e2e:deep_links::test_user_route_deep_link_and_refresh` | unit, e2e | exists |
| BE-SRV-041 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`, `::test_spa_missing_build_message`, `::test_unknown_api_path_is_json_404`; `e2e:deep_links::test_user_route_deep_link_and_refresh` | unit, e2e | exists |
| BE-SRV-042 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`, `::test_spa_missing_build_message`, `::test_unknown_api_path_is_json_404`; `e2e:deep_links::test_user_route_deep_link_and_refresh` | unit, e2e | exists |
| BE-SRV-043 | MUST | `core-api::AuthSessionTest::test_session_write_without_csrf_rejected` | unit | exists |
| BE-SRV-050 | MUST | `adm::MailSettingsTest::test_send_test_mail_to_admin`; `e2e:admin_settings::test_d5_mail_test_lands_in_outbox` | unit, e2e | exists |
| BE-SRV-051 | MUST | `adm::MailSettingsTest::test_send_test_mail_to_admin`; `e2e:admin_settings::test_d5_mail_test_lands_in_outbox` | unit, e2e | exists |
| BE-SRV-052 | MUST | `adm::MailSettingsTest::test_send_test_mail_to_admin`; `e2e:admin_settings::test_d5_mail_test_lands_in_outbox` | unit, e2e | exists |
| BE-SRV-053 | MUST | `acct::RegistrationTest::test_register_sends_activation_mail_and_stores_hashed_key` | unit | exists |
| BE-SRV-054 | MUST | SMTP failure unit test (mocked) (p) | — | planned |
| BE-SRV-055 | MUST | `adm::MailSettingsTest::test_password_write_only` | unit | exists |

### [logging.md](logging.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-LOG-001 | MUST | `core-dep::LoggingConfigTest::test_handlers_and_levels` (p) | unit | planned |
| BE-LOG-002 | MUST | `adm::LogsTest::test_handler_and_filters`; `adm::LoggingConfigTest::test_cloudgene_does_not_propagate` (p) | unit | exists+planned |
| BE-LOG-003 | MUST | `core-dep::LoggingConfigTest::test_log_format_switch` (p) | unit | planned |
| BE-LOG-004 | MUST | `core-dep::JsonFormatterTest::test_produces_valid_json_with_expected_keys`, `::test_extra_data_is_included` | unit | exists |
| BE-LOG-005 | MUST | `adm::LogsTest::test_handler_and_filters` | unit | exists |
| BE-LOG-006 | MUST | `adm::LogsTest::test_handler_and_filters`, `::test_exception_traceback_in_metadata` (p) | unit | exists+planned |
| BE-LOG-007 | MUST | `adm::LogsTest::test_handler_and_filters` | unit | exists |
| BE-LOG-008 | MUST | `adm::LogsTest::test_handler_swallows_db_errors` (p) | unit | planned |
| BE-LOG-009 | MUST | `adm::LogsTest::test_log_components_follow_the_spec`; `e2e:findings_admin::test_c04_log_components_follow_the_spec` | unit, e2e | exists |
| BE-LOG-010 | MUST | `e2e:admin_dashboard::test_d7_logs_show_admin_actions` | e2e | exists |
| BE-LOG-011 | MUST | `adm::LogsTest::test_actions_record_acting_user` (p) | unit | planned |
| BE-LOG-012 | MUST | `acct::LogSecretsTest::test_no_secret_in_system_log` (p) | unit | planned |
| BE-LOG-013 | MUST | `core-api::ErrorEnvelopeHandlerTest::test_unhandled_exception_becomes_500_envelope` | unit | exists |
| BE-LOG-014 | MUST | `adm::PermissionMatrixTest::test_anonymous_gets_401`, `::test_non_admin_gets_403_and_nothing_changes`; `e2e:findings_security::test_permission_matrix_admin_endpoints` | unit, e2e | exists |
| BE-LOG-015 | MUST | `adm::LogsTest::test_handler_and_filters` | unit | exists |
| BE-LOG-016 | MUST | `adm::LogsTest::test_handler_and_filters` | unit | exists |
| BE-LOG-017 | MUST | `adm::LogsTest::test_unknown_level_filter_is_a_400_not_silently_empty` | unit | exists |
| BE-LOG-018 | MUST | `adm::LogsTest::test_handler_and_filters` | unit | exists |
| BE-LOG-019 | MUST | frontend admin-logs escaping test (p) | — | planned |

### [management-commands.md](management-commands.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-CMD-001 | MUST | traceback-free `create_admin` failure (p) | — | planned |
| BE-CMD-002 | MUST | `wf-reg::TempHomeMixin` | unit | exists |
| BE-CMD-010 | MUST | `core-api::CreateAdminCommandTest::test_create_and_update_idempotent` | unit | exists |
| BE-CMD-011 | MUST | `core-api::CreateAdminCommandTest::test_create_and_update_idempotent` | unit | exists |
| BE-CMD-012 | MUST | `core-api::CreateAdminCommandTest::test_create_and_update_idempotent` | unit | exists |
| BE-CMD-013 | MUST | `core-api::CreateAdminCommandTest::test_create_and_update_idempotent` | unit | exists |
| BE-CMD-014 | MUST | `core-api::CreateAdminCommandTest::test_rejects_weak_password` (p), `::test_email_taken` (p) | unit | planned |
| BE-CMD-015 | MUST | `core-api::CreateAdminCommandTest::test_rejects_weak_password` (p), `::test_email_taken` (p) | unit | planned |
| BE-CMD-020 | MUST | `wf-reg::CommandsTest::test_install_workflow_command` | unit | exists |
| BE-CMD-021 | MUST | `wf-reg::CommandsTest::test_install_workflow_command` | unit | exists |
| BE-CMD-022 | MUST | `wf-reg::CommandsTest::test_install_relative_path_order` (p) | unit | planned |
| BE-CMD-023 | MUST | `wf-reg::CommandsTest::test_install_workflow_command` | unit | exists |
| BE-CMD-024 | MUST | `wf-reg::CommandsTest::test_install_workflow_command_invalid` | unit | exists |
| BE-CMD-025 | MUST | `wf-reg::CommandsTest::test_install_twice_needs_replace` (p) | unit | planned |
| BE-CMD-030 | MUST | `wf-reg::CommandsTest::test_sync_workflows_command`; `e2e:admin_workflows` | unit, e2e | exists |
| BE-CMD-031 | MUST | `wf-reg::CommandsTest::test_sync_workflows_command`; `e2e:admin_workflows` | unit, e2e | exists |
| BE-CMD-032 | MUST | `wf-reg::CommandsTest::test_sync_workflows_command`; `e2e:admin_workflows` | unit, e2e | exists |
| BE-CMD-040 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| BE-CMD-041 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| BE-CMD-042 | MUST | `e2e:queue::test_worker_restart_fails_orphans_and_queue_continues` | e2e | exists |
| BE-CMD-043 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_timeout_exit_code` (p) | unit | planned |
| BE-CMD-050 | MUST | `jobs-api::CleanupCommandTest::test_retention`, `::test_deleting_a_user_removes_job_workspaces` | unit | exists |
| BE-CMD-051 | MUST | `jobs-api::CleanupCommandTest::test_retention`, `::test_deleting_a_user_removes_job_workspaces` | unit | exists |
| BE-CMD-052 | MUST | `jobs-api::CleanupCommandTest::test_retention`, `::test_deleting_a_user_removes_job_workspaces` | unit | exists |
| BE-CMD-053 | MUST | `jobs-api::CleanupCommandTest::test_retention`, `::test_deleting_a_user_removes_job_workspaces` | unit | exists |
| BE-CMD-054 | MUST | `jobs-api::CleanupCommandTest::test_dry_run` (p) | unit | planned |
| BE-CMD-055 | MUST | `jobs-api::CleanupCommandTest::test_dry_run` (p) | unit | planned |
| BE-CMD-060 | MUST | `adm::LogsTest::test_cleanup_logs` | unit | exists |

### [tests.md](tests.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| BE-TEST-001 | MUST | `scripts/test.sh` (inspection); self-test (p) | gate | exists+planned |
| BE-TEST-002 | MUST | `core-schema::SchemaStalenessTest::test_committed_schema_is_up_to_date` | unit | exists |
| BE-TEST-003 | MUST (planned) | `core/tests/test_contract_helper.py::AssertMatchesSchemaTest` (p) | unit | planned |
| BE-TEST-004 | MUST (planned) | `core-schema::ContractCoverageTest::test_every_operation_validated` (p) | unit | planned |
| BE-TEST-005 | MUST | `test.sh` step "Migrations up to date" | gate | exists |
| BE-TEST-006 | MUST (planned) | `core-schema::SchemaLintTest::test_no_untyped_fields_outside_allow_list` (p) | unit | planned |
| BE-TEST-007 | MUST (planned) | `core-schema::ErrorCodeRegistryTest::test_codes_in_table` (p) | unit | planned |
| BE-TEST-008 | MUST (planned) | `e2e:findings_security::test_permission_matrix_admin_endpoints`, `::test_permission_matrix_requires_authentication`, `::test_permission_matrix_object_access` (partial); full matrix (p) | e2e | exists+planned |
| BE-TEST-009 | MUST | `jobs-claim::ClaimConcurrencyTest` (skip reason); `test.sh unit --postgres` | unit, gate | exists |
| BE-TEST-010 | MUST | `jobs-claim::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job`, `::test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once` | unit | exists |
| BE-TEST-011 | MUST | `core/tests/test_runner.py::RunnerIsolationTest::test_home_is_temp_copy` (p) | unit | planned |
| BE-TEST-012 | MUST | `jobs-worker::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` | unit | exists |
| BE-TEST-013 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; isolation assertion (p) | e2e | exists+planned |
| BE-TEST-014 | MUST | `e2e:harness_selftest::test_guards_fail_tests_on_browser_errors` | e2e | exists |
| BE-TEST-015 | MUST | collection-hook marker check (p) | e2e | planned |
| BE-TEST-016 | MUST | `e2e/exploratory/conftest.py` `collect_ignore_glob` (inspection); `core/tests/test_harness_scripts.py::XfailPolicyTest::test_every_e2e_xfail_is_strict` (p) | e2e, config | exists+planned |
| BE-TEST-017 | MUST | `scripts/spec_trace.py` (p); this table | gate | planned |
| BE-TEST-018 | MUST | e2e rows of this table; [frontend tests](../frontend/tests.md) | e2e | exists |
| BE-TEST-019 | MUST (planned) | CI configuration (p) | gate | planned |
| BE-TEST-020 | MUST (planned) | `scripts/spec_trace.py` (p) | gate | planned |
| BE-TEST-021 | MUST | `core/tests/test_harness_scripts.py::RequirementsPinTest::test_e2e_requirements_pinned` (p) | config | planned |

### Summary counts

"Existing test" = at least one cited test exists (it may also have planned ones). Counts are of
requirements, not tests.

| File | Reqs | MUST | Existing test | Planned only | None |
|---|---|---|---|---|---|
| overview.md | 25 | 25 | 19 | 6 | 0 |
| api-contract.md | 31 | 30 | 20 | 10 | 1 |
| data-model.md | 18 | 18 | 17 | 1 | 0 |
| configuration.md | 20 | 20 | 18 | 2 | 0 |
| authentication.md | 27 | 26 | 20 | 7 | 0 |
| accounts.md | 26 | 26 | 26 | 0 | 0 |
| access-control.md | 16 | 16 | 13 | 3 | 0 |
| workflow-definition.md | 31 | 29 | 28 | 1 | 2 |
| workflow-registry.md | 28 | 28 | 25 | 3 | 0 |
| workflows-api.md | 20 | 20 | 16 | 4 | 0 |
| job-submission.md | 31 | 30 | 27 | 3 | 1 |
| job-queue-worker.md | 28 | 28 | 26 | 2 | 0 |
| job-runner.md | 25 | 25 | 23 | 2 | 0 |
| job-progress-outputs.md | 27 | 26 | 25 | 2 | 0 |
| jobs-api.md | 25 | 24 | 22 | 2 | 1 |
| admin-api.md | 41 | 39 | 38 | 2 | 1 |
| server-pages-mail.md | 27 | 27 | 24 | 3 | 0 |
| logging.md | 19 | 19 | 13 | 6 | 0 |
| management-commands.md | 28 | 28 | 20 | 8 | 0 |
| tests.md | 21 | 21 | 11 | 10 | 0 |
| **Total** | **514** | **505** | **431** | **77** | **6** |

MUST requirements: 505, of which 429 have an existing test, 75 have only planned
tests and 1 has none (BE-API-060, a process rule).

## Known gaps

| Req | What the code / suite does today | Where | Severity |
|---|---|---|---|
| BE-TEST-003, BE-TEST-004 | No test validates a response against `schema.yaml`. `*/test_contracts.py` assert status codes and hand-picked fields; nothing loads `schema.yaml` except the staleness test and an exploratory script. No OpenAPI/JSON Schema validator is a dependency. Article 5.1d is unmet. | `accounts/test_contracts.py:28-50`, `workflows/test_contracts.py`, `requirements.txt` | major |
| BE-TEST-019 | No hosted CI: the repository has no CI configuration (no `.github/`, no other CI file). The staleness gate (Article 5.1c "CI fails"), the migrations check, Postgres runs and e2e only run when a developer runs them. | repository root | major |
| BE-TEST-009, BE-TEST-010 | The default run uses SQLite, so `ClaimConcurrencyTest` always skips unless someone runs `--postgres` by hand; BE-QUEUE-006 is unproven in routine runs. | `jobs/tests/test_claim_concurrency.py:26`, `scripts/test.sh:50-57` | major |
| BE-TEST-017 | 75 MUST requirements have only planned tests (see rows with status `planned`); 85 distinct planned test names do not exist yet, including whole planned files `jobs/tests/test_outputs.py`, `jobs/tests/test_contract.py`, `workflows/test_template_utils.py`. Largest clusters: api-contract (10), tests (10), management-commands (8), authentication (7), overview (6), logging (6). | traceability table | major |
| BE-TEST-020 | Traceability is checked by hand. Nothing fails when a spec cites a test that is renamed or deleted. (Today all 962 citations of existing tests resolve.) | — | minor |
| BE-TEST-006, BE-TEST-007, BE-TEST-008 | Schema lint, error-code registry check and full authorisation matrix do not exist; `e2e/exploratory/matrix.py` enumerates `schema.yaml` but only prints. | `e2e/exploratory/matrix.py:1-10` | minor |
| BE-TEST-011 | The runner's isolation (temp home, hasher) has no test of its own. | `core/test_runner.py:18-38` | minor |
| BE-TEST-001 | `scripts/test.sh` forwards extra arguments only to pytest (e2e mode), so a single Django test cannot be run through it; `unit` always runs vitest (and `npm ci` when `node_modules` is missing), so a backend-only gate run needs Node. | `scripts/test.sh:14`, `:58-62` | minor |
| BE-TEST-015 | Nothing enforces the `serial` marker; a test that mutates settings without it breaks under `-n`. | `e2e/pytest.ini:5-7` | minor |
| BE-TEST-021 | `e2e/requirements.txt` uses `>=` ranges and has no `playwright` line (see DEP-HARN-050), so e2e runs are not reproducible. | `e2e/requirements.txt:1-6` | major |
| BE-TEST-016 | `e2e/README.md:132` tells authors to use `xfail(strict=False, reason=...)` and `e2e/pytest.ini:8` sets `xfail_strict = false`, so a non-strict `xfail` that starts passing goes unnoticed. One non-strict `xfail` exists today: `e2e/tests/test_harness_selftest.py:84`. | `e2e/README.md:132`, `e2e/pytest.ini:8` | minor |
| — | No coverage measurement (no `coverage.py` step); coverage of MUST requirements is tracked only through this table. | `scripts/test.sh` | minor |

No test cited as existing in the backend spec files is missing under its cited name. Two cited
tests exist but are marked `(planned)` because the assertion the requirement needs is not in them
yet: `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_taxodactyl_shaped_job`
(BE-PROG-016) and a new test in `jobs/tests/test_worker.py` (BE-SRV-021).

## Open questions

1. Validator choice for BE-TEST-003: `openapi-core` (validates whole responses by operation) or
   `jsonschema` + `referencing` on components (lighter, but needs OpenAPI 3.0 → JSON Schema
   handling of `nullable`). Either goes into a new `requirements-dev.txt`; confirm that file name.
2. Should the e2e suite also validate API responses it observes against `schema.yaml` (in the
   guard), or is backend contract validation enough?
3. Which CI host (BE-TEST-019), and should the Postgres run be required on every pull request or
   only nightly?
