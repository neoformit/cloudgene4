# Deployment Tests

## Purpose

This file defines how the deployment is verified: the test layers (`config` static checks of the
files in `deploy/` and the deployment-relevant settings, `smoke` scripts that boot or install the
production stack, `unit` and `e2e` tests owned by the other sections, the `check --deploy` gate
and operator-run host obligations), the commands that run them, the rules the deployment
verification suite itself must meet, and a traceability table that maps every deployment
requirement (`DEP-*-NNN`) to the tests that prove it. It is the section-level `tests.md` required
by [Article 7.2](../constitution.md#article-7--tests).

## Scope

In scope:

| Path | What |
|---|---|
| `core/tests/test_deploy.py` | Existing: deploy system checks (`core.W001`–`W006`, `core.E001`), `cloudgene.env.example` check, HSTS, hasher, JSON log formatter, JSON body limit middleware |
| `core/tests/test_deploy_files.py` | Planned: static checks of every file in `deploy/` and cross-file consistency (DEP-TEST-002, DEP-TEST-003) |
| `core/tests/test_settings_env.py` | Planned: parsing of environment variables in `cloudgene_django/settings.py` |
| `core/tests/test_harness_scripts.py` | Planned: static checks of `scripts/`, `e2e/pytest.ini`, `e2e/requirements.txt` and the CI file |
| `scripts/smoke_gunicorn.sh` | Existing smoke script: SPA build, migrate, collectstatic, `check --deploy`, gunicorn boot, three HTTP probes |
| `scripts/smoke_install.sh`, `scripts/smoke_upgrade.sh`, `scripts/smoke_backup_restore.sh`, `scripts/smoke_runtime.sh` | Planned procedure-level smoke scripts (DEP-TEST-007) |
| `manage.py check --deploy` | Deploy gate, run by `DeployEnvExampleTest` and by the smoke script |
| Acceptance tests tables of every other file in `spec/deployment/` | Input for the traceability table |

Out of scope: the e2e harness itself and `scripts/test.sh` (owned by
[test-harness.md](test-harness.md)); backend and frontend test strategy
([backend tests](../backend/tests.md), [frontend tests](../frontend/tests.md)). Unit and e2e tests
that deployment files cite are listed in the traceability table but specified by their owners.

## Dependencies

- [test-harness.md](test-harness.md) — `scripts/test.sh` (DEP-HARN-001..005), the gunicorn smoke
  script (DEP-HARN-010..017), the e2e stack, CI (DEP-HARN-070..075).
- [security-hardening.md](security-hardening.md) — `check --deploy` checks and DEP-SEC-009 (the
  smoke script fails on a deploy-check Error).
- [install-upgrade.md](install-upgrade.md) — install, upgrade and rollback procedures that the
  planned procedure smoke scripts exercise.
- [../backend/tests.md](../backend/tests.md) — `CloudgeneTestRunner`, BE-TEST-019 (CI) and
  BE-TEST-020 (`scripts/spec_trace.py`, planned).
- Every other file in this section — their **Acceptance tests** tables are the input for the
  traceability table below.

## Requirements

**Config layer**

- **DEP-TEST-001** — Config tests MUST be Django tests under `core/tests/`, so `manage.py test`
  and therefore `scripts/test.sh unit` run them. They MUST NOT need network access, root, a
  running nginx, PostgreSQL or systemd. They MUST read deploy files from the checkout: Python
  files (`deploy/gunicorn.conf.py`) evaluated with `runpy.run_path` under a controlled
  environment, all other files parsed as text. A config test that finds a violation MUST fail
  and name the file, the line or key, and the requirement ID.
- **DEP-TEST-002** — Each kind of check MUST have one home: static checks of files in `deploy/`
  and cross-file consistency in `core/tests/test_deploy_files.py` (classes `GunicornConfigTest`,
  `NginxExampleTest`, `SystemdUnitsTest`, `EnvContractTest`, `DeployFilesConsistencyTest`, …);
  deploy system checks, security settings and middleware in `core/tests/test_deploy.py`;
  environment-variable parsing in `core/tests/test_settings_env.py`; checks of `scripts/`, e2e
  configuration and CI in `core/tests/test_harness_scripts.py`. A test class name MUST exist in
  one module only. Spec files MUST cite planned config tests under these paths.
- **DEP-TEST-003** (planned) — Every file under `deploy/` MUST be read by at least one config
  test. `core/tests/test_deploy_files.py::DeployInventoryTest` MUST list `deploy/**` and fail,
  naming the files, when a file is not in the module's covered-files map.
- **DEP-TEST-004** (planned) — `GunicornConfigTest` MUST evaluate `deploy/gunicorn.conf.py` once
  with every `GUNICORN_*` variable removed (asserting the defaults table of
  [web-server.md](web-server.md#interfaces)) and once with each variable set (asserting it is
  honoured, DEP-WEB-001).

**Smoke layer**

- **DEP-TEST-005** — Every smoke script in `scripts/` MUST run with `set -euo pipefail`, MUST exit
  non-zero on the first failed assertion or failed command with a `FAIL: <what>` line, MUST print
  its final `OK` line only when every assertion passed, and MUST remove its temporary directory
  and stop every process it started on any exit. No assertion MAY be followed by `|| true`.
- **DEP-TEST-006** (planned) — The smoke run of `scripts/smoke_gunicorn.sh` MUST check the exit
  status and output of `manage.py check --deploy`: an Error MUST fail the script
  ([DEP-SEC-009](security-hardening.md#requirements)), and a Warning MUST fail it unless its ID is
  in an expected-warnings list in the script with a reason. To keep that list short, the script
  MUST set the TLS variables of `deploy/cloudgene.env.example` (`DJANGO_SECURE_COOKIES`,
  `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_BEHIND_TLS_PROXY`, `DJANGO_HSTS_SECONDS`) and send
  `X-Forwarded-Proto: https` on its probes, as nginx does; the list MAY then contain only
  `core.W001` (SQLite with DEBUG off).
- **DEP-TEST-007** (planned) — Requirements on an operator procedure MUST be covered by
  procedure-level smoke scripts: `scripts/smoke_install.sh` (first install, DEP-INST-002..008),
  `scripts/smoke_upgrade.sh` (upgrade and rollback, DEP-INST-021..031, DEP-DB-021),
  `scripts/smoke_backup_restore.sh` (DEP-DB-040..042) and `scripts/smoke_runtime.sh` (Nextflow
  under the worker unit's user and sandbox, DEP-RT-*). These scripts change the host (users,
  units, `/etc`), so each MUST exit 2 with a message, before changing anything, unless
  `CLOUDGENE_SMOKE_DISPOSABLE_HOST=1` is set. They MUST meet DEP-TEST-005.
- **DEP-TEST-008** — A planned smoke citation MUST name the step title the script will print
  (`step "<title>"`), so the step can be resolved once it exists (DEP-TEST-011).

**e2e layer**

- **DEP-TEST-009** (planned) — Behaviour that depends on the production web stack and is visible
  in the browser (CSRF and Secure cookies behind the TLS proxy, CSP, HSTS) SHOULD have an e2e test
  against a stack served by nginx and gunicorn with the shipped config
  (`e2e/tests/test_deploy_tls.py`, `e2e/tests/test_csp.py`). See test-harness.md Open question 6.

**Host obligations**

- **DEP-TEST-010** — A requirement that binds the operator's host or procedure MAY be covered by a
  host obligation (Article 7.1). Its Acceptance tests row MUST cite `—`, the words "host
  obligation" and a manual verification step whose expected result is stated. A requirement on
  repository content (files in `deploy/`, `scripts/`, settings or code) MUST NOT be a host
  obligation. This file MUST count host obligations separately from gaps.

**CI and traceability**

- **DEP-TEST-011** — Every MUST requirement in `spec/deployment/` MUST map, in the table below, to
  at least one named test or a host obligation. A test cited as existing MUST exist: a Python test
  under its `path::Class::method`, an e2e test under its function name, a script step under the
  exact title that the script passes to `step`. (planned) The check MUST be automated by extending
  `scripts/spec_trace.py` ([BE-TEST-020](../backend/tests.md#requirements)) to `spec/deployment/`,
  including script step titles.
- **DEP-TEST-012** (planned) — CI ([DEP-HARN-070..075](test-harness.md#requirements)) MUST run the
  config layer on every push and pull request (through `scripts/test.sh unit`) and
  `scripts/smoke_gunicorn.sh` as a required job. The procedure smoke scripts of DEP-TEST-007
  SHOULD run on a disposable host before every release.

## Interfaces

### Commands

```bash
# config layer (part of the Django suite)
python manage.py test core.tests.test_deploy                 # existing deploy checks and settings tests
python manage.py test core.tests.test_deploy_files           # (planned) static checks of deploy/
python manage.py test core.tests.test_settings_env           # (planned) env parsing
python manage.py test core.tests.test_harness_scripts        # (planned) scripts/, e2e config, CI
python manage.py test core.tests.test_deploy.DeployEnvExampleTest   # check --deploy with the example env
scripts/test.sh unit                                         # runs all of the above with the rest of the suite

# smoke layer
scripts/smoke_gunicorn.sh                  # build SPA, migrate, collectstatic, check --deploy, boot gunicorn, probe
scripts/smoke_gunicorn.sh --skip-build     # reuse static/frontend/
PYTHON=/path/to/python scripts/smoke_gunicorn.sh
CLOUDGENE_SMOKE_DISPOSABLE_HOST=1 scripts/smoke_install.sh   # (planned) disposable host only
CLOUDGENE_SMOKE_DISPOSABLE_HOST=1 scripts/smoke_upgrade.sh   # (planned)
CLOUDGENE_SMOKE_DISPOSABLE_HOST=1 scripts/smoke_backup_restore.sh   # (planned)
CLOUDGENE_SMOKE_DISPOSABLE_HOST=1 scripts/smoke_runtime.sh   # (planned)

# deploy gate on a real host (operator; with the unit environment loaded, see DEP-API-005)
sudo -u cloudgene env $(sudo cat /etc/cloudgene/cloudgene.env | xargs) \
  /opt/cloudgene/venv/bin/python /opt/cloudgene/manage.py check --deploy
sudo nginx -t
systemd-analyze verify /etc/systemd/system/cloudgene-*.service /etc/systemd/system/cloudgene-cleanup.timer
```

The smoke script needs Node.js and npm (unless `--skip-build`), `curl`, and gunicorn in the venv
or on `PATH`. It writes `static/frontend/` and (today, DEP-HARN-017) the checkout's `staticfiles/`.

### Test layers

| Layer | Where | Runner | Needs | What it proves |
|---|---|---|---|---|
| config | `core/tests/test_deploy*.py`, `test_settings_env.py`, `test_harness_scripts.py` | `manage.py test` | nothing outside the checkout | Shipped files and settings say what the spec requires; files agree with each other |
| unit | backend test modules cited by deployment files | `manage.py test` | as backend | App behaviour a deployment requirement relies on (health, worker lock, limits) |
| smoke | `scripts/smoke_gunicorn.sh` | bash | Node/npm, gunicorn, curl | The production server boots from `deploy/gunicorn.conf.py` with `DEBUG=False` and serves the SPA, a hashed asset and health |
| smoke (procedure, planned) | `scripts/smoke_{install,upgrade,backup_restore,runtime}.sh` | bash as root | disposable host with systemd, PostgreSQL, nginx, Java, Nextflow | Install, upgrade/rollback, backup/restore and the worker sandbox work as written |
| e2e | `e2e/tests/` | pytest + Playwright | e2e stack (`runserver`, not gunicorn) | Browser-visible behaviour; deployment cites it where the stack reproduces production |
| gate | `manage.py check --deploy` | Django | env file | Deploy checks clean (DEP-SEC-001..009) |
| host obligation | owner file's Acceptance tests row | operator | the production host | Host configuration, monitoring, backups, file modes outside the repository |

### Deploy file coverage map

| File | Existing config test | Other existing coverage | Planned config test |
|---|---|---|---|
| `deploy/cloudgene.env.example` | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | — | `dep-files::EnvContractTest` |
| `deploy/gunicorn.conf.py` | none | `smoke` › "Starting gunicorn" (boots it) | `dep-files::GunicornConfigTest` |
| `deploy/nginx.conf.example` | none | none | `dep-files::NginxExampleTest` |
| `deploy/systemd/cloudgene-web.service` | none | none | `dep-files::SystemdUnitsTest` |
| `deploy/systemd/cloudgene-worker.service` | none | none | `dep-files::SystemdUnitsTest` |
| `deploy/systemd/cloudgene-cleanup.service` | none | none | `dep-files::SystemdUnitsTest` |
| `deploy/systemd/cloudgene-cleanup.timer` | none | none | `dep-files::SystemdUnitsTest` |

### Planned procedure smoke scripts

| Script | Requirements citing it |
|---|---|
| `scripts/smoke_install.sh` | DEP-INST-002, DEP-INST-003, DEP-INST-004, DEP-INST-007, DEP-INST-042 |
| `scripts/smoke_upgrade.sh` | DEP-DB-021, DEP-INST-021, DEP-INST-022, DEP-INST-030, DEP-INST-031 |
| `scripts/smoke_backup_restore.sh` | DEP-DB-040, DEP-DB-042 |
| `scripts/smoke_runtime.sh` | DEP-RT-001, DEP-RT-002, DEP-RT-003, DEP-RT-006, DEP-RT-014, DEP-RT-018, DEP-RT-019 |
| `scripts/manage_prod.sh` (a wrapper, not a test; its config test is `dep-files::ManageWrapperTest`) | DEP-API-005 |

### Traceability legend

Path aliases: `dep` = `core/tests/test_deploy.py`, `dep-files` = `core/tests/test_deploy_files.py`,
`senv` = `core/tests/test_settings_env.py`, `harn` = `core/tests/test_harness_scripts.py`,
`core-api` / `core-cfg` / `core-plat` = `core/tests/test_{api,config,platform}.py`, `jobs-api` /
`jobs-worker` / `jobs-claim` / `jobs-cmd` = `jobs/tests/test_{api,worker,claim_concurrency,command_steps}.py`,
`smoke` = `scripts/smoke_gunicorn.sh`, `e2e:x` = `e2e/tests/test_x.py`. `X › "title"` is a script
step. `::name` continues the previous `file::Class`. `(p)` = planned. **Status**: `exists` = at
least one cited test exists; `exists+planned` = exists, with further planned tests; `planned` =
only planned tests (a gap); `host obligation` = accepted untested item with a manual
verification step in the owner file; `none` = no test cited (a gap for MUST, accepted for
SHOULD/MAY); `withdrawn` = retired ID, with the requirement that replaces it.

## Behaviour

**Config run.** `scripts/test.sh unit` runs the Django suite, which includes the config tests.
`DeployEnvExampleTest` loads `deploy/cloudgene.env.example` into the environment of a
`manage.py check --deploy` subprocess and asserts it is clean; it is today the only test that
reads a file in `deploy/`. Planned `test_deploy_files.py` classes read each file as text (or with
`runpy` for gunicorn) and assert the values required by the owner files, then the cross-file
rules: nginx `proxy_pass` equals the default gunicorn bind (DEP-API-011), `proxy_read_timeout` ≥
`GUNICORN_TIMEOUT` (DEP-WEB-011), `client_max_body_size` ≥ `max_upload_mb` plus headroom
(DEP-WEB-031), unit paths and user match DEP-INST-001, every variable the code reads appears in
the example env file (DEP-API-001).

**Smoke run.** `scripts/smoke_gunicorn.sh` builds the SPA, creates a throw-away home and SQLite
database, migrates, collects static files, runs `check --deploy` (output printed, status
ignored today), boots gunicorn on a free loopback port with the shipped config, waits for
health, and probes `/`, one hashed asset and `/api/health`. Any probe miss exits 1. Details:
DEP-HARN-010..017.

**Procedure smoke (planned).** Each script runs on a disposable VM or container with systemd. It
follows the owner file's procedure step by step, as root, and asserts each observable outcome
(unit active, health 200, data present after restore, rollback serves the previous release).

**Host obligations.** The operator runs the manual verification step in the owner file's
Acceptance tests row at go-live and after any change to the host. Nothing in the repository
records the result.

**Building this table.** The table below was built on 2026-10-22 by a script that parses the
Requirements section (bulleted `**DEP-…**` IDs, RFC 2119 keywords, `(planned)`, `(withdrawn …)`)
and the Acceptance tests table of each deployment file, then resolves every citation not marked
planned or host obligation: Python and e2e names with `ast` (class and method names), scripts by
path, and step titles against the `step "…"` calls in `scripts/smoke_gunicorn.sh` and
`scripts/test.sh`.

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| DEP-TEST-001 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` (runs in `manage.py test`) | config |
| DEP-TEST-002 | `scripts/spec_trace.py` (planned, DEP-TEST-011) | config |
| DEP-TEST-003 | `core/tests/test_deploy_files.py::DeployInventoryTest::test_every_deploy_file_has_a_config_test` (planned) | config |
| DEP-TEST-004 | `core/tests/test_deploy_files.py::GunicornConfigTest::test_defaults_without_env` (planned) | config |
| DEP-TEST-004 | `core/tests/test_deploy_files.py::GunicornConfigTest::test_every_variable_overrides` (planned) | config |
| DEP-TEST-005 | `core/tests/test_harness_scripts.py::SmokeScriptTest::test_strict_mode_and_no_unchecked_steps` (planned) | config |
| DEP-TEST-006 | `scripts/smoke_gunicorn.sh` › "manage.py check --deploy" asserting the expected-warnings list (planned) | smoke |
| DEP-TEST-007 | `core/tests/test_harness_scripts.py::SmokeScriptTest::test_procedure_scripts_refuse_without_disposable_flag` (planned) | config |
| DEP-TEST-008 | `scripts/spec_trace.py` (planned, DEP-TEST-011) | config |
| DEP-TEST-009 | `e2e/tests/test_deploy_tls.py::test_spa_login_behind_tls_proxy_passes_csrf` (planned) | e2e |
| DEP-TEST-010 | `scripts/spec_trace.py` (planned, DEP-TEST-011); this table (built by script) | config |
| DEP-TEST-011 | `scripts/spec_trace.py` (planned); this table (built by script, 0 unresolved citations) | config |
| DEP-TEST-012 | `core/tests/test_harness_scripts.py::CiConfigTest::test_required_jobs_present` (planned) | config |

### Traceability table

All 348 requirement IDs defined in the other deployment files appear below: 332 active and 16
withdrawn. Of the parsed citations, 150 resolve to existing tests or script steps (79 distinct),
205 are planned (159 distinct) and 26 are host obligations. No test cited as existing is
missing.

### [overview.md](overview.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-ARCH-001 | MUST | `dep-files::SystemdUnitsTest::test_units_and_exec_lines` (p) | config | planned |
| DEP-ARCH-002 | MUST | `dep-files::GunicornConfigTest::test_default_bind_is_loopback` (p) | config | planned |
| DEP-ARCH-003 | MUST | `core-plat::SubmissionWithoutWorkerTest::test_submitted_job_waits_until_the_worker_claims_it` | unit | exists |
| DEP-ARCH-004 | MUST | `dep-files::SystemdUnitsTest::test_web_and_worker_share_environment_file` (p) | config | planned |
| DEP-ARCH-005 | MUST | `smoke` › "GET a hashed static asset" | smoke | exists |
| DEP-ARCH-006 | MUST | `core-plat::NoCeleryChannelsTest::test_django_boots_without_celery_channels_redis` | unit | exists |
| DEP-ARCH-010 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| DEP-ARCH-011 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-ARCH-012 | — | withdrawn → DEP-HOME-005 | — | withdrawn |
| DEP-ARCH-020 | MUST | `dep-files::SystemdUnitsTest::test_paths_and_user` (p) | config | planned |
| DEP-ARCH-021 | MUST | `dep-files::SystemdUnitsTest::test_paths_and_user` (p) | config | planned |
| DEP-ARCH-022 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-ARCH-030 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-ARCH-031 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |

### [api-contract.md](api-contract.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-API-001 | MUST | `dep-files::EnvContractTest::test_every_env_read_is_in_env_example` (p) | config | planned |
| DEP-API-002 | MUST | `dep-files::DeployFilesConsistencyTest::test_bind_paths_and_user_agree` (p) | config | planned |
| DEP-API-003 | MUST | `dep-files::EnvContractTest::test_every_env_read_is_in_env_example` (p) | config | planned |
| DEP-API-004 | MUST | `dep::DeployChecksTest::test_sqlite_warning_only_when_debug_off`; `dep::DeployChecksTest::test_allowed_hosts_wildcard_warning`; `dep::DeployChecksTest::test_secret_key_weak_warning`; `dep::DeployChecksTest::test_secure_transport_warnings`; `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config, unit | exists |
| DEP-API-005 | MUST | `scripts/manage_prod.sh`, `dep-files::ManageWrapperTest::test_loads_env_file` (p) | config | planned |
| DEP-API-006 | MUST | `dep::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e`; `dep::InsecureHashingCheckTest::test_clean_when_e2e_flag_set`; `dep::InsecureHashingCheckTest::test_clean_when_debug`; `dep::InsecureHashingCheckTest::test_clean_when_flag_unset` | unit | exists |
| DEP-API-010 | — | withdrawn → DEP-WEB-002 | — | withdrawn |
| DEP-API-011 | MUST | `dep-files::DeployFilesConsistencyTest::test_bind_paths_and_user_agree` (p) | config | planned |
| DEP-API-012 | MUST | `dep-files::ListenSocketTest::test_only_web_process_binds_a_socket` (p) | config | planned |
| DEP-API-020 | MUST | `core/tests/test_proxy.py::ProxyHeaderTest::test_unknown_host_is_400` (p) | unit | planned |
| DEP-API-021 | MUST | `core/tests/test_proxy.py::ProxyHeaderTest::test_forwarded_proto_marks_request_secure` (p) | unit | planned |
| DEP-API-022 | MUST | `dep-files::GunicornConfigTest::test_forwarded_allow_ips_default` (p) | config | planned |
| DEP-API-023 | MUST (planned) | `core/tests/test_proxy.py::ProxyHeaderTest::test_no_code_reads_forwarded_for_or_real_ip` (p) | config | planned |
| DEP-API-030 | MUST | `core-api::HealthTest::test_health_without_worker`; `core-api::HealthTest::test_health_with_fresh_and_stale_heartbeat`; `core-api::HealthTest::test_health_reports_a_broken_settings_file`; `core-api::HealthTest::test_health_db_down`; `smoke` › "GET /api/health" | smoke, unit | exists |
| DEP-API-031 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-API-032 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-API-033 | MUST | `smoke` (p) | smoke | planned |
| DEP-API-040 | MUST | `smoke` › "GET a hashed static asset" | smoke | exists |
| DEP-API-041 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`; `core-api::MiscRoutingTest::test_spa_missing_build_message`; `core-api::MiscRoutingTest::test_unknown_api_path_is_json_404`; `smoke` › "GET / (SPA shell)" | smoke, unit | exists |
| DEP-API-050 | MUST | `senv::SecretKeyTest::test_unwritable_home_fails_start` (p) | unit | planned |
| DEP-API-051 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-API-052 | — | withdrawn → DEP-ENV-030 | — | withdrawn |
| DEP-API-053 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-API-060 | MUST | `dep-files::SystemdUnitsTest::test_web_reload_sends_hup` (p) | config | planned |
| DEP-API-061 | MUST | `jobs-worker::ShutdownTest::test_shutdown_stops_running_jobs`; `jobs-worker::RunWorkerCommandTest::test_sigterm_exits_zero_and_releases_lock` (p) | unit | exists+planned |
| DEP-API-062 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| DEP-API-063 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |

### [environment-config.md](environment-config.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-ENV-001 | MUST | `senv::DotenvTest::test_process_env_wins_over_dotenv` (p) | unit | planned |
| DEP-ENV-002 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-ENV-003 | MUST | `dep-files::GunicornConfigTest::test_reads_only_process_env` (p) | config | planned |
| DEP-ENV-004 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-ENV-010 | MUST | `senv::ParsingTest::test_env_bool_values` (p) | unit | planned |
| DEP-ENV-011 | MUST | `senv::ParsingTest::test_env_list_values` (p) | unit | planned |
| DEP-ENV-012 | MUST | `senv::ParsingTest::test_bad_integer_names_variable` (p) | unit | planned |
| DEP-ENV-013 | MUST (planned) | `dep-files::GunicornConfigTest::test_bad_integer_fails` (p) | config | planned |
| DEP-ENV-014 | MUST | `dep::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e`; `dep::InsecureHashingCheckTest::test_clean_when_e2e_flag_set`; `dep::InsecureHashingCheckTest::test_clean_when_debug`; `dep::InsecureHashingCheckTest::test_clean_when_flag_unset` | unit | exists |
| DEP-ENV-020 | MUST | `dep::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit | exists |
| DEP-ENV-021 | MUST | `senv::ParsingTest::test_cloudgene_home_resolution` (p) | unit | planned |
| DEP-ENV-022 | MUST | `senv::ParsingTest::test_database_url_and_conn_max_age` (p) | unit | planned |
| DEP-ENV-023 | — | withdrawn → DEP-SEC-012, DEP-SEC-008 | — | withdrawn |
| DEP-ENV-024 | MUST | `senv::ParsingTest::test_behind_tls_proxy_sets_header` (p) | unit | planned |
| DEP-ENV-025 | MUST | `dep::DeployChecksTest::test_secure_transport_warnings` | unit | exists |
| DEP-ENV-026 | MUST | `dep::JsonFormatterTest::test_produces_valid_json_with_expected_keys` | unit | exists |
| DEP-ENV-027 | MUST | `dep::JsonBodySizeLimitMiddlewareTest::test_rejects_oversized_json_body_by_content_length_alone`; `dep::JsonBodySizeLimitMiddlewareTest::test_exempts_multipart_regardless_of_content_length` | unit | exists |
| DEP-ENV-028 | MUST | `senv::MailSettingsTest::test_email_backend_env_does_not_change_app_mail` (p) | unit | planned |
| DEP-ENV-029 | MUST | `core/tests/test_commands.py::CreateAdminTest::test_password_from_env` (p) | unit | planned |
| DEP-ENV-030 | MUST | `senv::SecretKeyTest::test_generated_key_file_mode_0600` (p) | unit | planned |
| DEP-ENV-031 | MUST | `senv::SecretKeyTest::test_concurrent_start_shares_key` (p) | unit | planned |
| DEP-ENV-032 | MUST (planned) | `senv::SecretKeyTest::test_empty_key_file_is_replaced_or_named_in_error` (p) | unit | planned |
| DEP-ENV-033 | MUST | `senv::SecretKeyTest::test_unwritable_home_fails_start` (p) | unit | planned |
| DEP-ENV-034 | MUST | `dep::DeployChecksTest::test_secret_key_weak_warning`; `dep::DeployChecksTest::test_example_placeholder_key_warns` (p) | unit | exists+planned |
| DEP-ENV-040 | MUST | `dep::DeployChecksTest::test_sqlite_warning_only_when_debug_off`; `dep::DeployChecksTest::test_allowed_hosts_wildcard_warning`; `dep::DeployChecksTest::test_secure_transport_warnings` | unit | exists |
| DEP-ENV-041 | SHOULD (planned) |  | — | none |
| DEP-ENV-050 | MUST | `dep-files::EnvContractTest::test_every_env_read_is_in_env_example` (p) | config | planned |
| DEP-ENV-051 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |

### [web-server.md](web-server.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-WEB-001 | MUST | `smoke` › "Starting gunicorn" | smoke | exists |
| DEP-WEB-002 | MUST | `dep-files::GunicornConfigTest::test_default_bind_is_loopback` (p) | config | planned |
| DEP-WEB-003 | — | withdrawn → DEP-ENV-013 | — | withdrawn |
| DEP-WEB-004 | MUST | `dep-files::GunicornConfigTest::test_default_workers_formula` (p) | config | planned |
| DEP-WEB-005 | — | withdrawn → DEP-API-022 | — | withdrawn |
| DEP-WEB-010 | MUST | `dep-files::GunicornConfigTest::test_timeout_default_300` (p) | config | planned |
| DEP-WEB-011 | MUST | `dep-files::DeployFilesConsistencyTest::test_proxy_read_timeout_covers_gunicorn_timeout` (p) | config | planned |
| DEP-WEB-012 | MUST | `dep-files::GunicornConfigTest::test_graceful_timeout_default` (p) | config | planned |
| DEP-WEB-013 | — | withdrawn → DEP-PROC-013 | — | withdrawn |
| DEP-WEB-014 | MUST | `dep-files::GunicornConfigTest::test_max_requests_defaults` (p) | config | planned |
| DEP-WEB-015 | MUST (planned) | `smoke` › "slow download of a large output survives GUNICORN_TIMEOUT" (p) | smoke | planned |
| DEP-WEB-016 | MUST | `dep-files::DeployFilesConsistencyTest::test_web_unit_has_no_misleading_reload` (p) | config | planned |
| DEP-WEB-020 | — | withdrawn → DEP-OBS-002 | — | withdrawn |
| DEP-WEB-021 | — | withdrawn → DEP-OBS-006 | — | withdrawn |
| DEP-WEB-030 | MUST | `jobs-api::SubmissionTest::test_upload_size_limit` | unit | exists |
| DEP-WEB-031 | MUST | `dep-files::DeployFilesConsistencyTest::test_client_max_body_size_covers_default_max_upload_mb` (p) | config | planned |
| DEP-WEB-032 | MUST | `dep-files::GunicornConfigTest::test_no_request_limits_lowered` (p) | config | planned |
| DEP-WEB-033 | MUST | `core-api::ErrorEnvelopeHandlerTest::test_upload_suspicious_operations_are_4xx_not_500` | unit | exists |
| DEP-WEB-034 | MUST | `dep::UploadSettingsTest::test_file_upload_spool_threshold` (p) | config | planned |
| DEP-WEB-035 | MUST | `jobs-api::SubmissionTest::test_many_files_in_folder_input_is_a_client_error_not_500`; `core-api::ErrorEnvelopeHandlerTest::test_upload_suspicious_operations_are_4xx_not_500` | unit | exists |
| DEP-WEB-036 | MUST | `dep::JsonBodySizeLimitMiddlewareTest::test_rejects_oversized_json_body_by_content_length_alone`; `dep::JsonBodySizeLimitMiddlewareTest::test_exempts_multipart_regardless_of_content_length` | unit | exists |
| DEP-WEB-037 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-WEB-038 | SHOULD (planned) |  | — | none |

### [reverse-proxy.md](reverse-proxy.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-PROXY-001 | MUST | `dep-files::NginxExampleTest::test_port_80_redirects_except_acme` (p) | config | planned |
| DEP-PROXY-002 | MUST | `dep-files::NginxExampleTest::test_tls_protocols` (p) | config | planned |
| DEP-PROXY-003 | SHOULD |  | — | none |
| DEP-PROXY-004 | MUST | `dep-files::NginxExampleTest::test_proxy_pass_targets_loopback` (p) | config | planned |
| DEP-PROXY-005 | MUST | `dep-files::NginxExampleTest::test_no_hsts_or_csp_add_header` (p) | config | planned |
| DEP-PROXY-006 | — | withdrawn → DEP-SEC-012 | — | withdrawn |
| DEP-PROXY-007 | — | withdrawn → DEP-SEC-012 | — | withdrawn |
| DEP-PROXY-008 | — | withdrawn → DEP-SEC-008 | — | withdrawn |
| DEP-PROXY-010 | MUST | `dep-files::NginxExampleTest::test_forwarding_headers_present` (p) | config | planned |
| DEP-PROXY-011 | MUST | `dep::ProxySslHeaderTest::test_forwarded_https_is_secure_and_not_redirected` (p) | unit | planned |
| DEP-PROXY-012 | MUST | `dep-files::DeployFilesConsistencyTest::test_client_max_body_size_covers_default_max_upload_mb` (p) | config | planned |
| DEP-PROXY-013 | MUST (planned) | `dep-files::NginxExampleTest::test_api_413_returns_json_envelope` (p) | config | planned |
| DEP-PROXY-014 | SHOULD (planned) |  | — | none |
| DEP-PROXY-015 | MUST | `dep-files::DeployFilesConsistencyTest::test_proxy_read_timeout_covers_gunicorn_timeout` (p) | config | planned |
| DEP-PROXY-016 | MUST | `dep-files::NginxExampleTest::test_static_location_cache_policy` (p) | config | planned |
| DEP-PROXY-017 | SHOULD (planned) |  | — | none |
| DEP-PROXY-020 | MUST | `dep::SecurityHeadersTest::test_spa_shell_security_headers` (p) | unit | planned |
| DEP-PROXY-021 | MUST (planned) | `dep::SecurityHeadersTest::test_spa_shell_has_csp` (p); `e2e:csp::test_v_html_event_handler_does_not_execute` (p) | e2e, unit | planned |
| DEP-PROXY-022 | MUST (planned) | `dep-files::NginxExampleTest::test_no_hsts_or_csp_add_header` (p) | config | planned |
| DEP-PROXY-023 | MUST (planned) | `jobs-api::DownloadHeadersTest::test_sandbox_csp_survives_global_policy` (p) | unit | planned |
| DEP-PROXY-024 | MUST (planned) | `dep::SecurityHeadersTest::test_swagger_ui_policy_scoped_to_its_path` (p) | unit | planned |
| DEP-PROXY-025 | SHOULD |  | — | none |

### [process-management.md](process-management.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-PROC-001 | MUST | `dep-files::SystemdUnitsTest::test_units_run_as_cloudgene_user` (p) | config | planned |
| DEP-PROC-002 | MUST | `dep-files::SystemdUnitsTest::test_units_share_environment_file_and_workdir` (p) | config | planned |
| DEP-PROC-003 | MUST | `dep-files::SystemdUnitsTest::test_units_use_venv_binaries` (p) | config | planned |
| DEP-PROC-004 | MUST | `dep-files::SystemdUnitsTest::test_units_sandboxed` (p) | config | planned |
| DEP-PROC-005 | MUST | `dep-files::SystemdUnitsTest::test_read_write_paths_cover_cloudgene_home` (p) | config | planned |
| DEP-PROC-006 | MUST | `dep-files::SystemdUnitsTest::test_worker_read_write_paths_cover_nextflow_home` (p) | config | planned |
| DEP-PROC-007 | SHOULD |  | — | none |
| DEP-PROC-008 | MUST | `dep-files::SystemdUnitsTest::test_units_ordered_after_postgresql` (p) | config | planned |
| DEP-PROC-009 | MUST | `dep-files::SystemdUnitsTest::test_read_write_paths_exclude_code_checkout` (p) | config | planned |
| DEP-PROC-010 | MUST | `dep-files::SystemdUnitsTest::test_web_execstart` (p); `smoke` | config, smoke | exists+planned |
| DEP-PROC-011 | MUST | `dep-files::SystemdUnitsTest::test_web_and_worker_restart_always` (p) | config | planned |
| DEP-PROC-012 | MUST | `dep-files::SystemdUnitsTest::test_web_reload_sends_hup` (p) | config | planned |
| DEP-PROC-013 | MUST | `dep-files::SystemdUnitsTest::test_web_stop_timeout_exceeds_graceful_timeout` (p) | config | planned |
| DEP-PROC-014 | MUST | `dep-files::SystemdUnitsTest::test_install_targets` (p) | config | planned |
| DEP-PROC-020 | MUST | `dep-files::SystemdUnitsTest::test_worker_execstart` (p) | config | planned |
| DEP-PROC-021 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| DEP-PROC-022 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock`; `dep-files::SystemdUnitsTest::test_web_and_worker_restart_always` (p) | config, unit | exists+planned |
| DEP-PROC-023 | MUST | `jobs-worker::ShutdownTest::test_shutdown_stops_running_jobs`; `jobs-worker::RunWorkerCommandTest::test_sigterm_stops_gracefully` (p) | unit | exists+planned |
| DEP-PROC-024 | MUST | `dep-files::SystemdUnitsTest::test_worker_stop_timeout_covers_max_running_jobs` (p) | config | planned |
| DEP-PROC-025 | MUST | `jobs-worker::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed` (recovery side only; systemd behaviour not tested) | unit | exists |
| DEP-PROC-026 | MUST | `dep-files::SystemdUnitsTest::test_install_targets` (p) | config | planned |
| DEP-PROC-030 | MUST | `dep-files::SystemdUnitsTest::test_cleanup_runs_both_commands` (p) | config | planned |
| DEP-PROC-031 | MUST | `dep-files::SystemdUnitsTest::test_install_targets` (p) | config | planned |
| DEP-PROC-032 | MUST | `dep-files::SystemdUnitsTest::test_cleanup_timer_schedule` (p) | config | planned |
| DEP-PROC-033 | MUST | `jobs-api::CleanupCommandTest::test_retention` | unit | exists |
| DEP-PROC-034 | SHOULD (planned) |  | — | none |
| DEP-PROC-040 | MUST | `dep-files::SystemdUnitsTest::test_unit_command_map` (p) | config | planned |

### [database.md](database.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-DB-001 | MUST | `senv::DatabaseSettingsTest::test_database_url_selects_engine_and_defaults_to_sqlite` (p) | unit | planned |
| DEP-DB-002 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-DB-003 | MUST | `dep::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit | exists |
| DEP-DB-004 | MUST | `senv::DatabaseSettingsTest::test_conn_max_age_from_env` (p) | unit | planned |
| DEP-DB-005 | MUST | `senv::DatabaseSettingsTest::test_conn_health_checks_enabled` (p) | unit | planned |
| DEP-DB-006 | MUST | `jobs-worker::WorkerTickConnectionTest::test_tick_closes_old_connections` (p) | unit | planned |
| DEP-DB-007 | MUST | `scripts/test.sh unit --postgres` | unit | exists |
| DEP-DB-010 | MUST | `senv::DatabaseSettingsTest::test_sqlite_options_defaults` (p) | unit | planned |
| DEP-DB-011 | MUST | `senv::DatabaseSettingsTest::test_postgres_has_no_sqlite_options` (p) | unit | planned |
| DEP-DB-012 | MUST | `e2e:findings_jobs::test_a03_admin_workflow_list_does_not_write_on_every_read` | e2e | exists |
| DEP-DB-020 | MUST | `smoke` › "Migrating a throw-away DB" | smoke | exists |
| DEP-DB-021 | MUST | `scripts/smoke_upgrade.sh` (p) | smoke | planned |
| DEP-DB-022 | MUST | `scripts/test.sh unit` › "Migrations up to date" | unit | exists |
| DEP-DB-023 | MUST | `dep-files::SystemdUnitsTest::test_unit_command_map` (p) | config | planned |
| DEP-DB-030 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit | exists |
| DEP-DB-031 | MUST | `jobs-claim::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job`, `jobs-claim::ClaimConcurrencyTest::test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once` | unit | exists |
| DEP-DB-040 | MUST | `scripts/smoke_backup_restore.sh` (p) | smoke | planned |
| DEP-DB-041 | SHOULD |  | — | none |
| DEP-DB-042 | MUST | `scripts/smoke_backup_restore.sh` (p) | smoke | planned |
| DEP-DB-043 | MUST | `jobs-worker::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed` | unit | exists |
| DEP-DB-044 | MUST | `senv::SecretKeyRotationTest::test_sessions_invalid_after_key_change` (p) | unit | planned |
| DEP-DB-050 | MUST | `jobs-claim::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job` | unit | exists |
| DEP-DB-051 | MUST | `scripts/test.sh unit --postgres` | unit | exists |
| DEP-DB-052 | MUST | `e2e:stack::test_postgres_stack_creates_and_drops_its_database` (p) | e2e | planned |
| DEP-DB-053 | SHOULD |  | — | none |
| DEP-DB-060 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-DB-061 | MUST | host obligation (manual step in file) | — | host obligation |

### [static-assets.md](static-assets.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-STATIC-001 | MUST | `smoke` › "Building the SPA (npm run build)" | smoke | exists |
| DEP-STATIC-002 | MUST | `smoke` › "GET a hashed static asset" | smoke | exists |
| DEP-STATIC-003 | MUST | `smoke` › "GET a hashed static asset" | smoke | exists |
| DEP-STATIC-004 | MUST | `dep::StaticConfigTest::test_build_output_is_gitignored` (p) | config | planned |
| DEP-STATIC-005 | SHOULD (planned) |  | — | none |
| DEP-STATIC-010 | MUST | `smoke` › "GET a hashed static asset" | smoke | exists |
| DEP-STATIC-011 | MUST (planned) | `dep::StaticConfigTest::test_finders_off_when_debug_off` (p); `smoke` › "asset missing from staticfiles/ is 404 even if present in static/" (p) | config, smoke | planned |
| DEP-STATIC-012 | MUST (planned) | `core-api::MiscRoutingTest::test_spa_missing_build_message`; `core-api::MiscRoutingTest::test_spa_shell_read_once_per_process` (p) | unit | exists+planned |
| DEP-STATIC-013 | MUST | `core-api::MiscRoutingTest::test_missing_static_file_is_404_not_spa` (p) | unit | planned |
| DEP-STATIC-014 | MUST | `dep::StaticConfigTest::test_whitenoise_follows_security_middleware` (p) | config | planned |
| DEP-STATIC-020 | MUST (planned) | `smoke` › "hashed asset is immutable" (p) | smoke | planned |
| DEP-STATIC-021 | MUST | `core-api::MiscRoutingTest::test_spa_shell_is_no_cache` (p) | unit | planned |
| DEP-STATIC-022 | MUST | `smoke` › "unhashed asset has short max-age" (p) | smoke | planned |
| DEP-STATIC-023 | MUST | `smoke` › "unhashed asset has Last-Modified" (p) | smoke | planned |
| DEP-STATIC-024 | SHOULD (planned) |  | — | none |
| DEP-STATIC-030 | MUST (planned) | `smoke` › "previous release chunk still served after rebuild + restart" (p) | smoke | planned |
| DEP-STATIC-031 | MUST (planned) | `smoke` › "shell and assets consistent after rebuild" (p) | smoke | planned |
| DEP-STATIC-032 | MUST (planned) | `dep::StaticPruneTest::test_prunes_assets_older_than_retention` (p) | unit | planned |
| DEP-STATIC-033 | MUST | `dep::StaticConfigTest::test_upgrade_procedure_has_no_collectstatic_clear` (p) | config | planned |
| DEP-STATIC-034 | — | withdrawn → DEP-HARN-017 | — | withdrawn |

### [cloudgene-home.md](cloudgene-home.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-HOME-001 | MUST | `dep-files::SystemdUnitsTest::test_units_share_environment_file` (p); `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists+planned |
| DEP-HOME-002 | MUST | `dep-files::SystemdUnitsTest::test_units_run_as_cloudgene` (p) | config | planned |
| DEP-HOME-003 | MUST | `dep-files::SystemdUnitsTest::test_units_set_restrictive_umask` (p) | config | planned |
| DEP-HOME-004 | MUST | `dep-files::SystemdUnitsTest::test_read_write_paths_include_cloudgene_home` (p) | config | planned |
| DEP-HOME-005 | MUST | `jobs-worker::RunWorkerCommandTest::test_once_and_single_instance_lock`; `core-cfg::ConfigWriteTest::test_concurrent_writers_from_processes_do_not_lose_updates` | unit | exists |
| DEP-HOME-006 | MUST | `core-cfg::ConfigLoadTest::test_missing_file_yields_defaults`; `smoke` | smoke, unit | exists |
| DEP-HOME-007 | MUST | `smoke` (p) | smoke | planned |
| DEP-HOME-008 | MUST | `core-cfg::ConfigWriteTest::test_existing_file_mode_is_preserved` (p); `core-cfg::ConfigWriteTest::test_new_settings_file_is_owner_only` (p) | unit | planned |
| DEP-HOME-009 | SHOULD |  | — | none |
| DEP-HOME-010 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-011 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-012 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-013 | MUST | `dep-files::SystemdUnitsTest::test_cleanup_timer_runs_both_commands_daily` (p); `jobs-api::CleanupCommandTest::test_retention`; `admin_panel/tests/test_api.py::LogsTest::test_cleanup_logs` | config, unit | exists+planned |
| DEP-HOME-014 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-015 | MUST | `jobs-api::CleanupCommandTest::test_external_work_dir_removed` (p) | unit | planned |
| DEP-HOME-016 | SHOULD |  | — | none |
| DEP-HOME-017 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-018 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-019 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-HOME-020 | MUST | `e2e:queue::test_worker_restart_fails_orphans_and_queue_continues`; `jobs-api::CleanupCommandTest::test_retention` | e2e, unit | exists |
| DEP-HOME-021 | MUST | `core-cfg::CommittedHomeTest::test_committed_layout`; `core-cfg::CommittedHomeTest::test_committed_settings_yaml_is_valid_and_complete` | unit | exists |
| DEP-HOME-022 | MUST | `dep::GitignoreTest::test_runtime_home_files_are_ignored` (p) | config | planned |

### [workflow-runtime.md](workflow-runtime.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-RT-001 | MUST | `jobs-worker::WorkerFailureTest::test_missing_binary`; `e2e:jobs::test_submit_hello_with_unicode_job_name`; `scripts/smoke_runtime.sh` (p) | e2e, smoke, unit | exists+planned |
| DEP-RT-002 | MUST | `scripts/smoke_runtime.sh` (p) | smoke | planned |
| DEP-RT-003 | MUST | `scripts/smoke_runtime.sh` (p) | smoke | planned |
| DEP-RT-004 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_live_progress_multi_process` | e2e | exists |
| DEP-RT-005 | MUST | `jobs-cmd::CommandStepWorkerTest::test_missing_executable`; `e2e:command_steps::test_command_steps_run_and_show_output` | e2e, unit | exists |
| DEP-RT-006 | MUST | `scripts/smoke_runtime.sh` (p) | smoke | planned |
| DEP-RT-007 | SHOULD |  | — | none |
| DEP-RT-008 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-RT-009 | MUST | `dep-files::SystemdUnitsTest::test_worker_read_write_paths_exclude_code_checkout` (p); `e2e:findings_jobs::test_a04_per_app_work_dir_is_an_allowed_output_root` | config, e2e | exists+planned |
| DEP-RT-010 | SHOULD |  | — | none |
| DEP-RT-011 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-RT-012 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-RT-013 | MUST | `jobs-worker::WorkerSuccessTest::test_global_env_file_blanks_inherited_variables` (p); `dep::NextflowEnvTest::test_shipped_nextflow_env_blanks_server_secrets` (p); `jobs-worker::test_server_secrets_not_in_step_env` (p) | config, unit | planned |
| DEP-RT-014 | MUST | `scripts/smoke_runtime.sh` (p) | smoke | planned |
| DEP-RT-015 | MUST | `dep-files::SystemdUnitsTest::test_worker_read_write_paths_exclude_code_checkout` (p) | config | planned |
| DEP-RT-016 | MUST | `dep-files::SystemdUnitsTest::test_web_and_worker_are_separate_units` (p) | config | planned |
| DEP-RT-017 | SHOULD |  | — | none |
| DEP-RT-018 | MUST (planned) | `scripts/smoke_runtime.sh` (p) | smoke | planned |
| DEP-RT-019 | MUST | `scripts/smoke_runtime.sh` (p) | smoke | planned |
| DEP-RT-020 | SHOULD |  | — | none |

### [security-hardening.md](security-hardening.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-SEC-001 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-SEC-002 | MUST | `dep::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e`; `dep::InsecureHashingCheckTest::test_clean_when_e2e_flag_set`; `dep::InsecureHashingCheckTest::test_clean_when_debug`; `dep::InsecureHashingCheckTest::test_clean_when_flag_unset` | unit | exists |
| DEP-SEC-003 | MUST | `dep::DeployChecksTest::test_secret_key_weak_warning` | unit | exists |
| DEP-SEC-004 | MUST | `dep::DeployChecksTest::test_allowed_hosts_wildcard_warning` | unit | exists |
| DEP-SEC-005 | MUST | `dep::DeployChecksTest::test_secure_transport_warnings` | unit | exists |
| DEP-SEC-006 | MUST | `dep::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit | exists |
| DEP-SEC-007 | MUST | `dep::DeployChecksTest::test_sqlite_warning_only_when_debug_off`; `dep::DeployChecksTest::test_all_deploy_checks_silent_in_debug` (p) | unit | exists+planned |
| DEP-SEC-008 | MUST | `dep::SilencedChecksTest::test_w021_silenced_only_without_preload` (p); `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env`; `dep::HstsPreloadDefaultTest::test_w021_not_silenced_when_preload_on` (p) | config, unit | exists+planned |
| DEP-SEC-009 | MUST | `smoke` › "manage.py check --deploy" (p) | smoke | planned |
| DEP-SEC-010 | MUST | `dep::DebugDefaultTest::test_debug_off_unless_truthy` (p) | config | planned |
| DEP-SEC-011 | MUST | `dep::AllowedHostsTest::test_unknown_host_is_400` (p) | unit | planned |
| DEP-SEC-012 | MUST | `dep::HstsPreloadDefaultTest::test_preload_off_by_default_even_with_hsts_seconds_set`; `dep::HstsPreloadDefaultTest::test_preload_on_only_with_explicit_env_var`; `dep::HstsPreloadDefaultTest::test_include_subdomains_follows_hsts_seconds` (p) | config, unit | exists+planned |
| DEP-SEC-013 | MUST | `dep::ProxySslHeaderTest::test_header_trusted_only_with_env_flag` (p) | config | planned |
| DEP-SEC-014 | MUST | `dep::SecurityHeadersTest::test_default_security_headers` (p) | unit | planned |
| DEP-SEC-015 | MUST | `dep::CookieFlagsTest::test_session_cookie_flags` (p) | unit | planned |
| DEP-SEC-016 | MUST | `core-api::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`; `dep::CookieFlagsTest::test_csrf_cookie_flags` (p) | unit | exists+planned |
| DEP-SEC-017 | MUST | `e2e:deploy_tls::test_spa_login_behind_tls_proxy_passes_csrf` (p) | e2e | planned |
| DEP-SEC-018 | MUST | `dep::PasswordHasherTest::test_argon2_is_the_default_hasher`; `dep::PasswordHasherTest::test_pbkdf2_hash_is_upgraded_to_argon2_on_login` | unit | exists |
| DEP-SEC-019 | MUST | `dep::InsecureHasherSettingTest::test_md5_ignored_without_debug_or_e2e` (p) | config | planned |
| DEP-SEC-020 | MUST | `dep::GitignoreTest::test_secret_key_ignored` (p) | config | planned |
| DEP-SEC-021 | MUST | host obligation (manual step in file); (planned) covered by DEP-SEC-022's check once it also inspects `EnvironmentFile` (p) | — | planned |
| DEP-SEC-022 | MUST (planned) | `dep::DeployChecksTest::test_secret_files_permission_warning` (p) | unit | planned |
| DEP-SEC-023 | MUST | `dep-files::SystemdUnitsTest::test_units_run_unprivileged_and_sandboxed` (p) | config | planned |
| DEP-SEC-024 | MUST | `accounts/tests.py::DjangoAdminLockoutTest::test_locked_account_rejected_with_correct_password`; `e2e:findings_security::test_b01_django_admin_login_bypasses_lockout` | e2e, unit | exists |
| DEP-SEC-025 | MUST | `e2e:findings_security::test_permission_matrix_public` | e2e | exists |
| DEP-SEC-026 | MUST (planned) | `dep-files::NginxExampleTest::test_auth_endpoints_rate_limited` (p) | config | planned |
| DEP-SEC-027 | MUST | `harn::RequirementsPinTest::test_all_requirements_pinned` (p) | config | planned |
| DEP-SEC-028 | MUST | `harn::RequirementsPinTest::test_package_lock_committed` (p) | config | planned |
| DEP-SEC-029 | SHOULD (planned) |  | — | none |

### [observability.md](observability.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-OBS-001 | MUST | `dep-files::SystemdUnitsTest::test_units_log_to_journal` (p) | config | planned |
| DEP-OBS-002 | MUST | `dep-files::GunicornConfigTest::test_log_targets_default_to_stdio` (p) | config | planned |
| DEP-OBS-003 | MUST | `dep::JsonFormatterTest::test_produces_valid_json_with_expected_keys`; `dep::JsonFormatterTest::test_extra_data_is_included`; `dep::JsonFormatterTest::test_traceback_stays_on_one_line` (p) | unit | exists+planned |
| DEP-OBS-004 | MUST | `dep::DeployEnvExampleTest::test_example_uses_json_logging` (p) | config | planned |
| DEP-OBS-005 | MUST | `dep::LogLevelTest::test_unknown_log_level_fails_startup` (p) | config | planned |
| DEP-OBS-006 | SHOULD (planned) | `dep-files::GunicornConfigTest::test_access_log_uses_forwarded_client_ip` (p) | config | planned |
| DEP-OBS-007 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-OBS-008 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-OBS-009 | MUST | `dep-files::SystemdUnitsTest::test_cleanup_service_runs_cleanup_logs` (p) | config | planned |
| DEP-OBS-010 | MUST | `dep-files::SystemdUnitsTest::test_cleanup_service_runs_cleanup_jobs` (p) | config | planned |
| DEP-OBS-011 | MUST | `core-api::HealthTest::test_health_db_down`; `core-api::HealthTest::test_health_without_worker` | unit | exists |
| DEP-OBS-012 | MUST | `core-api::HealthTest::test_health_with_fresh_and_stale_heartbeat` | unit | exists |
| DEP-OBS-013 | MUST | `core-api::HealthTest::test_health_reports_a_broken_settings_file`; `e2e:findings_admin::test_c02_invalid_settings_value_does_not_take_the_site_down` | e2e, unit | exists |
| DEP-OBS-014 | MUST | host obligation (manual step in file) | — | host obligation |
| DEP-OBS-015 | SHOULD | host obligation (manual step in file) | — | host obligation |
| DEP-OBS-016 | MUST (planned) | `core-api::HealthTest::test_health_reports_queue_state` (p) | unit | planned |
| DEP-OBS-017 | MUST | `smoke` › "GET /api/health" | smoke | exists |
| DEP-OBS-018 | MUST | host obligation (manual step in file) | — | host obligation |

### [install-upgrade.md](install-upgrade.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-INST-001 | MUST | `dep-files::SystemdUnitsTest::test_units_share_environment_file_and_workdir` (p) | config | planned |
| DEP-INST-002 | MUST | `scripts/smoke_install.sh` (p) | smoke | planned |
| DEP-INST-003 | MUST | `scripts/smoke_install.sh` (p) | smoke | planned |
| DEP-INST-004 | MUST | `scripts/smoke_install.sh` (p) | smoke | planned |
| DEP-INST-005 | MUST | `smoke` › "Building the SPA" | smoke | exists |
| DEP-INST-006 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-INST-007 | MUST | `scripts/smoke_install.sh` (p) | smoke | planned |
| DEP-INST-008 | MUST | `smoke`; `core-api::CreateAdminCommandTest::test_create_and_update_idempotent`; `workflows/test_registry.py::CommandsTest::test_install_workflow_command` | smoke, unit | exists |
| DEP-INST-009 | MUST | `dep-files::SystemdUnitsTest::test_install_targets` (p) | config | planned |
| DEP-INST-010 | MUST | `dep-files::NginxExampleTest::test_nginx_t_accepts_example` (p) | config | planned |
| DEP-INST-011 | SHOULD |  | — | none |
| DEP-INST-020 | SHOULD |  | — | none |
| DEP-INST-021 | MUST | `scripts/smoke_upgrade.sh` (p) | smoke | planned |
| DEP-INST-022 | MUST | `scripts/smoke_upgrade.sh` (p) | smoke | planned |
| DEP-INST-023 | MUST | `dep-files::SystemdUnitsTest::test_web_reload_sends_hup` (p) | config | planned |
| DEP-INST-024 | MUST | `jobs-worker::ShutdownTest::test_shutdown_stops_running_jobs` | unit | exists |
| DEP-INST-025 | — | withdrawn → DEP-STATIC-031 | — | withdrawn |
| DEP-INST-026 | — | withdrawn → DEP-STATIC-030, DEP-STATIC-033 | — | withdrawn |
| DEP-INST-027 | MUST | `workflows/test_registry.py::CommandsTest::test_sync_workflows_command` | unit | exists |
| DEP-INST-030 | MUST | `scripts/smoke_upgrade.sh` (p) | smoke | planned |
| DEP-INST-031 | MUST | `scripts/smoke_upgrade.sh` (p) | smoke | planned |
| DEP-INST-040 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-INST-041 | MUST | `core-api::HealthTest::test_health_with_fresh_and_stale_heartbeat`; `smoke` › "GET /api/health" | smoke, unit | exists |
| DEP-INST-042 | MUST | `scripts/smoke_install.sh` (p) | smoke | planned |
| DEP-INST-043 | — | withdrawn → DEP-HARN-010, DEP-HARN-011, DEP-HARN-012, DEP-HARN-013, DEP-HARN-014, DEP-HARN-017 | — | withdrawn |

### [test-harness.md](test-harness.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-HARN-001 | MUST | `harn::TestShTest::test_runs_from_repo_root_with_python_override` (p) | config | planned |
| DEP-HARN-002 | MUST | `harn::TestShTest::test_postgres_flag_sets_database_url_for_django_tests_only` (p) | config | planned |
| DEP-HARN-003 | MUST | `harn::TestShTest::test_failing_step_exits_non_zero_without_ok` (p) | config | planned |
| DEP-HARN-004 | MUST (planned) | `harn::TestShTest::test_postgres_flag_in_e2e_mode_is_not_ignored` (p) | config | planned |
| DEP-HARN-005 | MUST | `scripts/test.sh unit` › "Frontend unit tests (vitest)" | smoke | exists |
| DEP-HARN-010 | MUST | `smoke` › "Building the SPA" | smoke | exists |
| DEP-HARN-011 | MUST | `smoke` | smoke | exists |
| DEP-HARN-012 | MUST | `smoke` › "collectstatic" | smoke | exists |
| DEP-HARN-013 | MUST | `smoke` › "Starting gunicorn" | smoke | exists |
| DEP-HARN-014 | MUST | `smoke` › "GET / (SPA shell)", "GET a hashed static asset", "GET /api/health" | smoke | exists |
| DEP-HARN-015 | MUST (planned) | `harn::SmokeScriptTest::test_readiness_timeout_fails` (p) | config | planned |
| DEP-HARN-016 | MUST (planned) | `smoke` (p) | smoke | planned |
| DEP-HARN-017 | MUST (planned) | `dep::StaticConfigTest::test_smoke_script_uses_throwaway_static_root` (p) | config | planned |
| DEP-HARN-020 | MUST | `e2e:harness_selftest::test_stack_root_and_stack_json` (p) | e2e | planned |
| DEP-HARN-021 | MUST | `e2e:harness_selftest::test_bundle_rebuilt_only_when_sources_newer` (p) | e2e | planned |
| DEP-HARN-022 | MUST | `e2e:smoke::test_home_renders_home_template`; `e2e:smoke::test_footer_renders_footer_template`; `e2e:smoke::test_about_page_renders_pages_file`; `e2e:smoke::test_navbar_items_from_yaml_in_order` | e2e | exists |
| DEP-HARN-023 | MUST | `e2e:harness_selftest::test_postgres_database_per_worker_created_and_dropped` (p) | e2e | planned |
| DEP-HARN-024 | MUST | `dep::InsecureHashingCheckTest::test_clean_when_e2e_flag_set`; `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e, unit | exists |
| DEP-HARN-025 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; `e2e:jobs::test_failing_workflow` | e2e | exists |
| DEP-HARN-026 | MUST | `e2e:harness_selftest::test_stop_kills_process_groups` (p) | e2e | planned |
| DEP-HARN-027 | MUST (planned) | `e2e:harness_selftest::test_missing_nextflow_fails_stack_start` (p) | e2e | planned |
| DEP-HARN-028 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous` | e2e | exists |
| DEP-HARN-030 | MUST | `e2e:harness_selftest::test_guards_fail_tests_on_browser_errors` | e2e | exists |
| DEP-HARN-031 | MUST | `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e | exists |
| DEP-HARN-032 | MUST | `e2e:harness_selftest::test_server_settings_restored` (p) | e2e | planned |
| DEP-HARN-033 | MUST | `e2e:harness_selftest::test_summary_written` (p) | e2e | planned |
| DEP-HARN-034 | MUST (planned) | `e2e:harness_selftest::test_serial_rejected_under_xdist` (p) | e2e | planned |
| DEP-HARN-035 | MUST (planned) | `harn::PytestIniTest::test_xfail_strict_true` (p) | config | planned |
| DEP-HARN-036 | MUST | `e2e:harness_selftest::test_guards_fail_tests_on_browser_errors` | e2e | exists |
| DEP-HARN-040 | MUST | `e2e:accounts::test_a2_case_variant_duplicates_rejected` | e2e | exists |
| DEP-HARN-041 | MUST (planned) | `e2e:harness_selftest::test_helpers_use_schema_paths_only` (p) | e2e | planned |
| DEP-HARN-042 | MUST | `e2e:accounts::test_a1_register_activate_login` | e2e | exists |
| DEP-HARN-043 | MUST | `e2e:harness_selftest::test_no_django_import_in_pytest_process` (p) | e2e | planned |
| DEP-HARN-044 | MUST | `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e | exists |
| DEP-HARN-045 | MUST | `e2e:harness_selftest::test_no_django_import_in_pytest_process` (p) | e2e | planned |
| DEP-HARN-050 | MUST (planned) | `harn::RequirementsPinTest::test_e2e_requirements_pinned` (p) | config | planned |
| DEP-HARN-051 | MUST | `e2e:harness_selftest::test_guards_fail_tests_on_browser_errors` | e2e | exists |
| DEP-HARN-055 | MUST | `e2e/fixtures/verify_apps.py`; `harn::FixtureAppsTest::test_every_fixture_app_listed_in_constants` (p) | config, smoke | exists+planned |
| DEP-HARN-056 | MUST | — (manual: `python -m e2e.exploratory.serve`) (planned) (p) | smoke | planned |
| DEP-HARN-057 | MUST | — (manual: `python -m e2e.exploratory.matrix`) (planned) (p) | smoke | planned |
| DEP-HARN-070 | MUST (planned) | `harn::CiConfigTest::test_required_jobs_present` (p) | config | planned |
| DEP-HARN-071 | MUST (planned) | `harn::CiConfigTest::test_required_jobs_present` (p) | config | planned |
| DEP-HARN-072 | MUST (planned) | `harn::CiConfigTest::test_postgres_job_fails_on_concurrency_skip` (p) | config | planned |
| DEP-HARN-073 | MUST (planned) | `harn::CiConfigTest::test_e2e_jobs_scheduled` (p) | config | planned |
| DEP-HARN-074 | MUST (planned) | `harn::CiConfigTest::test_toolchain_pinned_and_artifacts_uploaded` (p) | config | planned |
| DEP-HARN-075 | MUST (planned) | `harn::CiConfigTest::test_no_secrets_referenced` (p) | config | planned |

### [tests.md](tests.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| DEP-TEST-001 | MUST | `dep::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config | exists |
| DEP-TEST-002 | MUST | `scripts/spec_trace.py` (p) | config | planned |
| DEP-TEST-003 | MUST (planned) | `dep-files::DeployInventoryTest::test_every_deploy_file_has_a_config_test` (p) | config | planned |
| DEP-TEST-004 | MUST (planned) | `dep-files::GunicornConfigTest::test_defaults_without_env`, `::test_every_variable_overrides` (p) | config | planned |
| DEP-TEST-005 | MUST | `harn::SmokeScriptTest::test_strict_mode_and_no_unchecked_steps` (p) | config | planned |
| DEP-TEST-006 | MUST (planned) | `smoke` › "manage.py check --deploy" (p) | smoke | planned |
| DEP-TEST-007 | MUST (planned) | `harn::SmokeScriptTest::test_procedure_scripts_refuse_without_disposable_flag` (p) | config | planned |
| DEP-TEST-008 | MUST | `scripts/spec_trace.py` (p) | config | planned |
| DEP-TEST-009 | SHOULD (planned) | `e2e:deploy_tls::test_spa_login_behind_tls_proxy_passes_csrf` (p) | e2e | planned |
| DEP-TEST-010 | MUST | `scripts/spec_trace.py` (p); this table | config | planned |
| DEP-TEST-011 | MUST | `scripts/spec_trace.py` (p); this table | config | planned |
| DEP-TEST-012 | MUST (planned) | `harn::CiConfigTest::test_required_jobs_present` (p) | config | planned |

### Summary counts

Counts are of active requirements (withdrawn IDs excluded from Reqs). "Existing test" = at least
one cited test exists (it may also have planned ones). Host obligations are accepted untested
items (Article 7.1), not gaps. "None" are all SHOULD/MAY requirements.

| File | Reqs | MUST | Existing test | Planned only | Host obligation | None | Withdrawn |
|---|---|---|---|---|---|---|---|
| overview.md | 13 | 13 | 6 | 5 | 2 | 0 | 1 |
| api-contract.md | 25 | 25 | 8 | 13 | 4 | 0 | 2 |
| environment-config.md | 27 | 26 | 9 | 16 | 1 | 1 | 1 |
| web-server.md | 18 | 17 | 5 | 11 | 1 | 1 | 5 |
| reverse-proxy.md | 19 | 15 | 0 | 15 | 0 | 4 | 3 |
| process-management.md | 27 | 25 | 6 | 19 | 0 | 2 | 0 |
| database.md | 27 | 25 | 11 | 12 | 2 | 2 | 0 |
| static-assets.md | 19 | 17 | 5 | 12 | 0 | 2 | 1 |
| cloudgene-home.md | 22 | 20 | 6 | 7 | 7 | 2 | 0 |
| workflow-runtime.md | 20 | 16 | 4 | 9 | 3 | 4 | 0 |
| security-hardening.md | 29 | 28 | 13 | 15 | 0 | 1 | 0 |
| observability.md | 18 | 16 | 5 | 8 | 5 | 0 | 0 |
| install-upgrade.md | 22 | 20 | 7 | 13 | 0 | 2 | 3 |
| test-harness.md | 46 | 46 | 18 | 28 | 0 | 0 | 0 |
| tests.md | 12 | 11 | 1 | 11 | 0 | 0 | 0 |
| **Total** | **344** | **320** | **104** | **194** | **25** | **21** | **16** |

MUST requirements: 320. 104 have an existing test, 192 have only planned tests (gaps), 24 are
host obligations, and none has no test at all. The 25th host obligation (DEP-HOME-012) is a
SHOULD. The 21 requirements with no test are SHOULD requirements: DEP-ENV-041, DEP-WEB-038,
DEP-PROXY-003, DEP-PROXY-014, DEP-PROXY-017, DEP-PROXY-025, DEP-PROC-007, DEP-PROC-034,
DEP-DB-041, DEP-DB-053, DEP-STATIC-005, DEP-STATIC-024, DEP-HOME-009, DEP-HOME-016, DEP-RT-007,
DEP-RT-010, DEP-RT-017, DEP-RT-020, DEP-SEC-029, DEP-INST-011, DEP-INST-020.

By layer, existing citations: 90 unit, 26 smoke, 25 e2e, 16 config. Planned citations: 108
config, 50 unit, 33 smoke, 14 e2e.

## Known gaps

| Req | What the code / suite does today | Where | Severity |
|---|---|---|---|
| DEP-TEST-003 | Only 1 of the 7 files in `deploy/` is read by any test (`cloudgene.env.example`, by `DeployEnvExampleTest`). `gunicorn.conf.py` is exercised only by being booted in the smoke script; `nginx.conf.example` and the four systemd files have no test. 76 requirements cite planned `dep-files::` classes. | `core/tests/test_deploy.py:140`, `deploy/` | major |
| DEP-TEST-006 | The smoke script runs `check --deploy` with `|| true` and only prints the output; it sets none of the TLS variables, so the Warnings it would report are not those of a production run. DEP-SEC-009 is unmet (gap owned by [test-harness.md](test-harness.md) DEP-HARN-016). | `scripts/smoke_gunicorn.sh:50-52` | major |
| DEP-TEST-012 | No CI configuration exists; neither the config layer nor the smoke script runs automatically, and `scripts/test.sh` does not run the smoke script in any mode. Owned by DEP-HARN-070..075. | repository root, `scripts/test.sh:74-79` | major |
| DEP-TEST-011 | 192 MUST requirements have only planned tests. Largest clusters: test-harness.md 28, process-management.md 19, environment-config.md 16, reverse-proxy.md 15 (no existing test at all), security-hardening.md 15, api-contract.md 13, install-upgrade.md 13. | traceability table | major |
| DEP-TEST-007 | None of the planned procedure scripts exists (`smoke_install.sh`, `smoke_upgrade.sh`, `smoke_backup_restore.sh`, `smoke_runtime.sh`); 19 requirements on install, upgrade, rollback, backup and the worker sandbox depend on them. | `scripts/` | major |
| DEP-TEST-005 | `smoke_gunicorn.sh` readiness loop falls through after 10 s instead of failing (DEP-HARN-015), and `check --deploy` is unchecked (above). | `scripts/smoke_gunicorn.sh:74-79`, `:51` | minor |
| DEP-TEST-011 | Traceability is checked by a one-off script, not in the suite; renaming a cited test or a smoke step title fails nothing. | — | minor |
| DEP-TEST-001 | The same existing test is cited with different layers in different files (for example `HstsPreloadDefaultTest` as `config` in security-hardening.md and `unit` for DEP-SEC-008; `DeployChecksTest` as `unit`). Layer names for `test_deploy.py` are therefore not consistent. | Acceptance tests tables | minor |
| DEP-TEST-008 | 3 planned citations of `smoke_gunicorn.sh` name no step title (DEP-API-033, DEP-HOME-007, DEP-HARN-016), and none of the 20 citations of the planned procedure scripts names a step. | Acceptance tests tables | minor |
| — | The smoke script uses SQLite only; the PostgreSQL path of a deployment (driver, `DATABASE_URL`, `DB_CONN_MAX_AGE`) is exercised only by `scripts/test.sh unit --postgres`, never with gunicorn. | `scripts/smoke_gunicorn.sh:35` | minor |

## Open questions

1. Disposable host for the procedure smoke scripts (DEP-TEST-007): a VM image, a
   systemd-enabled container, or `systemd-nspawn`? The choice decides whether CI can run them.
2. Should config tests call `nginx -t` and `systemd-analyze verify` when the binaries exist, and
   skip otherwise? That adds environment-dependent skips to a layer that is otherwise hermetic.
3. DEP-TEST-006 accepts `core.W001` in the smoke run because it uses SQLite. Should the smoke
   script instead run against PostgreSQL when `TEST_DATABASE_URL` is set, so `check --deploy` is
   fully clean in CI?
