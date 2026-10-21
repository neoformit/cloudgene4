# Frontend Tests

## Purpose

This file defines how the Vue SPA is tested: the test layers (vitest unit, component and
contract tests; Playwright e2e through the production bundle), the commands that run them, the
rules the frontend test suite itself must meet, and a traceability table that maps every frontend
requirement (`FE-*-NNN`) to the tests that prove it. It is the section-level `tests.md` required
by [Article 7.2](../constitution.md#article-7--tests).

## Scope

In scope:

| Path | What |
|---|---|
| `frontend/vite.config.js` (`test:` block) | vitest config: `happy-dom`, `globals: true`, setup file |
| `frontend/package.json` (`test*` scripts, dev dependencies) | `vitest`, `@vitest/ui`, `@vue/test-utils`, `happy-dom`, `ajv`, `ajv-formats` |
| `frontend/src/test/setup.js` | Global setup and custom matchers |
| `frontend/src/test/*.test.js` | Unit tests: `client.test.js`, `auth-store.test.js` (store + router guards), `server-store.test.js`, `admin-api.test.js` (request shapes) |
| `frontend/src/test/contracts/*.test.js` | Contract tests: `auth`, `jobs`, `users`, `workflows`; plus `dynamic-form.test.js` (form model and `DynamicForm` component) |
| `frontend/src/test/schemas.js`, `frontend/src/test/fixtures/` | Hand-written JSON Schemas and response fixtures |
| `frontend/src/utils/validation.test.js` | Client validation parity with `accounts/validation_cases.json` |
| `e2e/tests/test_*.py`, `e2e/pages/__init__.py` | Playwright tests and page objects, as far as they drive SPA views |
| `scripts/test.sh` (`unit` step "Frontend unit tests (vitest)") | Entry point that runs vitest |

Out of scope: the e2e harness itself (stack, guards, fixtures, markers) and its rules — see
[backend tests](../backend/tests.md) BE-TEST-013 to BE-TEST-016; backend Django tests; deployment
smoke tests ([deployment tests](../deployment/tests.md)). The OpenAPI contract mechanism
(schema loader, fixtures, request validation) is specified in [api-contract.md](api-contract.md)
FE-API-011 to FE-API-015 and only linked here.

## Dependencies

- [api-contract.md](api-contract.md) — FE-API-012 (loader from `schema.yaml`), FE-API-013
  (fixtures and mocked responses validate), FE-API-014 (request bodies validate), FE-API-015
  (every API function has a request-shape test), FE-API-017 (validation parity).
- [overview.md](overview.md) — FE-ARCH-042 (`npm run test:run`, `happy-dom`, setup file) and the
  `package.json` scripts table.
- [routing.md](routing.md) — the route table; the view coverage map below lists every route view.
- [common-components.md](common-components.md) — FE-UI-054 (`data-testid` on interactive elements).
- [../backend/tests.md](../backend/tests.md) — e2e harness (BE-TEST-013 stack, BE-TEST-014
  browser guards, BE-TEST-015 `serial`), BE-TEST-018 (Article 7.3), BE-TEST-019 (CI, planned),
  BE-TEST-020 (traceability script, planned).
- Every other file in this section — their **Acceptance tests** tables are the input for the
  traceability table below.

## Requirements

**Runner**

- **FE-TEST-001** — `npm run test:run` (`vitest run`, run from `frontend/`) MUST run every
  `*.test.js` under `frontend/src/` once, in the `happy-dom` environment, with
  `src/test/setup.js` as setup file, and MUST exit non-zero when any test fails. `npm test` MUST
  run the same suite in watch mode. `scripts/test.sh unit` MUST run the suite after the Django
  steps (BE-TEST-001).
- **FE-TEST-002** — Unit, component and contract tests MUST NOT perform network I/O. HTTP MUST be
  replaced by `vi.mock('@/api/client')`, `vi.mock('@/api/<module>')`, or an axios `adapter` stub.
  (planned) `src/test/setup.js` MUST make any un-stubbed request (axios default adapter or
  `fetch`) fail the test with the method and URL.

**Contract layer**

- **FE-TEST-003** (planned) — Contract tests MUST validate against `schema.yaml` as specified by
  FE-API-012 (loader), FE-API-013 (response fixtures and mocked bodies) and FE-API-014 (request
  bodies). When this is done, `src/test/schemas.js` and the custom matchers in `setup.js` MUST be
  removed, and no test MAY define an API shape by hand (Article 5.1e).
- **FE-TEST-004** — Every exported function of `src/api/*.js` other than `client.js` MUST have a
  contract test that asserts method, path, query parameters and body (FE-API-015). (planned) A
  static test MUST import every API module and fail, listing the functions that no test under
  `src/test/contracts/` or `src/test/admin-api.test.js` calls.

**Views and flows**

- **FE-TEST-005** — Every route view in `src/router/index.js` MUST be rendered by at least one
  test (a component test or an e2e test that opens it and asserts its content), and MUST appear
  in the [view coverage map](#view-coverage-map). A route added without a map entry is a gap.
- **FE-TEST-006** (planned) — Every view with loading, empty or error states, timers (polling) or
  in-progress action state MUST have a component test, `src/test/views/<ViewName>.test.js`, that
  mounts it with `@vue/test-utils`, mocks its API modules with fixtures that validate against
  `schema.yaml` (FE-API-013), and covers each of those states.
- **FE-TEST-007** — Every user-visible flow that reaches the API (Article 7.3) MUST have at least
  one e2e test that performs the action through the UI. `api()` MAY be used only to arrange or to
  assert server state. The [view coverage map](#view-coverage-map) lists the e2e tests per view.
- **FE-TEST-008** — e2e tests MUST locate elements by `data-testid` only
  (`page.get_by_test_id`) and assert state through `data-*` attributes (`data-state`,
  `data-job-id`, …), never through CSS classes or visible text alone. Every `data-testid` an e2e
  test uses MUST exist in `frontend/src`. (planned) A static test MUST fail, listing the ids that
  e2e sources use and no `.vue` file defines.
- **FE-TEST-009** — Interactions repeated across e2e modules SHOULD go through page objects in
  `e2e/pages/` (today `Navbar`, `LoginPage`, `RunPage`, `JobPage`).
- **FE-TEST-010** (planned) — Every requirement that a server value is rendered as text, or that
  restricts `v-html` (Article 8.2), MUST have a test that injects markup (`<script>`,
  `<img src=x onerror=…>`) through a fixture or the API and asserts that the markup is shown as
  text and no element is created.
- **FE-TEST-011** — Tests of polling and timers MUST use fake timers (`vi.useFakeTimers`) and
  MUST NOT wait on real time.

**Coverage and traceability**

- **FE-TEST-012** (planned) — `npm run test:coverage` MUST produce a coverage report (text summary
  and `frontend/coverage/`, git-ignored). `@vitest/coverage-v8`, at the same version as `vitest`,
  MUST be a dev dependency. Thresholds SHOULD be set in `vite.config.js` once FE-TEST-006 tests
  exist.
- **FE-TEST-013** — vitest files MUST follow one layout: unit tests in
  `src/test/<module>.test.js` (`src/utils/<name>.test.js` beside the module is allowed), contract
  tests in `src/test/contracts/`, component tests in `src/test/components/<Component>.test.js`,
  view tests in `src/test/views/<ViewName>.test.js`, fixtures in `src/test/fixtures/`. A rule MUST
  have one test home; spec files MUST cite planned tests under these paths.
- **FE-TEST-014** — Every MUST requirement in `spec/frontend/` MUST map to at least one named test
  in the table below. A test cited as existing MUST exist under that file and describe/it name
  (vitest) or function name (e2e). (planned) The check MUST be automated together with the
  backend one (BE-TEST-020).

## Interfaces

### Commands

```bash
# from frontend/ (needs node_modules: npm ci)
npm run test:run                       # whole vitest suite once (= npx vitest run)
npm test                               # watch mode
npm run test:ui                        # browser UI (@vitest/ui)
npm run test:coverage                  # FAILS today: "MISSING DEPENDENCY @vitest/coverage-v8" (FE-TEST-012)
npx vitest run src/test/client.test.js                 # one file
npx vitest run src/test/contracts                      # one directory
npx vitest run -t "apiErrorMessage"                    # by describe/it name
npx vitest run src/test/auth-store.test.js -t "router guards"

# from the repo root
scripts/test.sh unit                   # Django gates and tests, then vitest (no vitest-only mode)
scripts/test.sh e2e -k deep_links      # e2e subset (args go to pytest)
python -m pytest e2e/tests/test_deep_links.py          # every route, logged out / user / admin
python -m pytest e2e/tests/test_run_form.py e2e/tests/test_jobs.py   # submit form, job pages
python -m pytest e2e -k "admin_settings or admin_workflows" -m serial
python -m pytest e2e/tests/test_auth.py::test_login_follows_next_parameter --headed
```

The e2e stack rebuilds the SPA bundle when `frontend/` is newer than
`static/frontend/index.html`. Do not set `E2E_SKIP_BUILD=1` when testing a frontend change.
Setup, markers and failure artefacts: [backend tests](../backend/tests.md#commands) and
`e2e/README.md`.

### Test layers

| Layer | Where | Runner | Network | What it proves |
|---|---|---|---|---|
| unit | `src/test/client.test.js`, `auth-store.test.js`, `server-store.test.js`, `src/utils/validation.test.js` | vitest, `happy-dom` | stubbed (`vi.mock`, adapter) | Client CSRF/401/error helpers; store boot, login/logout; router guards with a real router; validation parity |
| contract | `src/test/contracts/{auth,jobs,users,workflows}.test.js`, `src/test/admin-api.test.js` | vitest | `vi.mock('@/api/client')` or adapter stub | Method, path, params and body per API function; response fixtures against **hand-written** schemas (`schemas.js`) — target: `schema.yaml` (FE-TEST-003) |
| component | `src/test/contracts/dynamic-form.test.js` (`DynamicForm` mounted with `@vue/test-utils`) | vitest | none | Form model, validation, `FormData`, poller. No view is mounted by any test today (FE-TEST-006) |
| e2e | `e2e/tests/test_*.py` | pytest + Playwright | real stack | Views through the production bundle, real API, worker and Nextflow; browser-error guards |

Size today: 10 vitest files, 144 tests (run 2026-10-21, all pass, about 3 s); 16 e2e modules, 99
test functions, of which 75 are cited by frontend requirements.

### Fixtures and helpers

| Item | Used by | Notes |
|---|---|---|
| `src/test/setup.js` | all vitest files | Sets `global.fetch`/`Request`/`Response` to the real ones; registers `toBeValidApiResponse`, `toHaveApiField` (unused) and `toMatchApiSchema` (uses the `global.ajv` that each contract file creates itself) |
| `src/test/schemas.js` | contract tests | 15 hand-written JSON Schemas; not derived from `schema.yaml` |
| `src/test/fixtures/jobs.js` | `contracts/jobs.test.js`, `dynamic-form.test.js` | `workflowFixture` (`all-inputs`), job list/status/detail fixtures |
| `accounts/validation_cases.json` | `src/utils/validation.test.js`, `accounts/tests.py::ValidationRulesTest` | Shared validation cases (pending amendment P2) |
| `e2e/pages/__init__.py` | 4 e2e modules (`test_jobs`, `test_run_form`, `test_queue`, `test_command_steps`) and login fixture | `Navbar`, `LoginPage`, `RunPage` (`open`, `fill`, `set_files`, `field_error`, `submit`), `JobPage` (`open`, `expect_state`, `open_results`, `open_logs`, `cancel`, `delete`) |

### `data-testid` conventions

- Static kebab-case ids, `<area>-<element>`: `nav-login`, `job-cancel`, `queue-pause`,
  `logs-filter-apply`. About 340 are defined in `frontend/src`; e2e uses about 190.
- Per-item ids keep the same id on every row and carry the key in a `data-*` attribute:
  `workflow-card` + `data-workflow-id`, `admin-job-row` + `data-job-id`, `log-row` +
  `data-level`.
- Dynamic ids only where the key is the id: `input-<param id>`, `error-<param id>`,
  `files-<param id>` (run form), `admin-nav-<item>` (sidebar), `register-<field>` and
  `register-<field>-error`, `workflow-group-<group>`.
- State for assertions is exposed as `data-*` attributes: `data-state` (job state),
  `data-paused`, `data-maintenance`, `data-worker`, `data-valid`, `data-enabled`,
  `data-effective-status`, `data-filename`, `data-output-id`.
- Every id an e2e test uses was found in `frontend/src` on 2026-10-21 (dynamic ids resolved by
  their template). `e2e/README.md` "Current ids" lists only the first ~40 and is out of date.

### View coverage map

e2e tests that open the view and assert its content. vitest coverage of views: none (FE-TEST-006).

| Route | View | e2e tests (module::function) |
|---|---|---|
| `/` | `HomeView` | `smoke::test_home_loads_cleanly_anonymous`, `::test_home_loads_cleanly_logged_in`, `::test_home_renders_home_template`; `admin_workflows::test_w1_workflow_visibility_per_user`; `deep_links::*` |
| `/login` | `LoginView` | `auth::test_login_and_logout_via_ui`, `::test_login_wrong_password_shows_error`, `::test_login_follows_next_parameter`; `accounts::test_a3_lockout`; `login` fixture in every UI test |
| `/register` | `RegisterView` | `accounts::test_a1_register_activate_login`, `::test_a2_client_side_rules_match_server`, `::test_a2_case_variant_duplicates_rejected` |
| `/activate/:key` | `ActivateView` | `accounts::test_a1_register_activate_login` (link from the outbox, re-click) |
| `/reset-password` | `PasswordResetView` | `accounts::test_a4_password_reset` |
| `/recover/:token` | `PasswordRecoveryView` | `accounts::test_a4_password_reset` (rule error, success, used link) |
| `/pages/:slug` | `StaticPageView` | `smoke::test_about_page_renders_pages_file`, `::test_unknown_page_shows_not_found`; `admin_settings::test_d6_create_view_delete_page` |
| `/profile` | `ProfileView` | `accounts::test_a5_profile_name_email_password_token`, `::test_a6_delete_own_account` |
| `/jobs` | `JobListView` | `jobs::test_cancel_waiting_and_delete_finished`; `auth::test_login_follows_next_parameter` |
| `/jobs/:id` | `JobDetailView` | `jobs::*` (6); `command_steps::test_command_steps_run_and_show_output`, `::test_failing_command_step_fails_the_job`, `::test_cancel_during_long_command_step`; `queue::test_queue_limits_and_advances_after_cancel`, `::test_pause_and_resume_queue`; `access_jobs::test_other_user_cannot_see_job_outputs_or_log` |
| `/run/:workflowId` | `WorkflowSubmitView` | `run_form::test_all_input_types_render_with_defaults`, `::test_client_validation_blocks_submit`, `::test_server_field_errors_are_shown_in_the_form`; `command_steps::test_run_form_shows_details_help_and_accept`; `jobs::test_submit_hello_with_unicode_job_name`; `queue::test_queue_full_rejects_submission`, `::test_maintenance_blocks_users_not_admins` |
| `/admin` | `AdminDashboardView` | `admin_dashboard::test_d1_dashboard_counts_match_db`, `::test_d1_pause_resume_queue`, `::test_d1_maintenance_mode_banner` |
| `/admin/jobs` | `AdminJobsView` | `admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` |
| `/admin/users` | `AdminUsersView` (+ group modals) | `accounts::test_d3_admin_users`, `::test_a7_non_admin_blocked_from_admin_ui_and_api` |
| `/admin/workflows` | `AdminWorkflowsView` | `admin_workflows::test_d4_install_invalid_then_valid_and_uninstall`, `::test_d4_invalid_entry_listed_with_errors`, `::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_reload_after_yaml_edit` |
| `/admin/workflows/:id` | `AdminWorkflowSettingsView` | `admin_workflows::test_d4_groups_and_public_via_settings_page`, `::test_d4_per_app_nextflow_settings_persist` |
| `/admin/settings/general` | `GeneralSettingsView` | `admin_settings::test_d5_general_settings_round_trip`, `::test_d5_general_settings_validation_error`, `::test_d6_navbar_editor` |
| `/admin/settings/nextflow` | `NextflowSettingsView` | `admin_settings::test_d5_nextflow_settings_round_trip` |
| `/admin/settings/mail` | `MailSettingsView` | `admin_settings::test_d5_mail_password_write_only`, `::test_d5_mail_test_lands_in_outbox` |
| `/admin/settings/pages` | `PagesView` | `admin_settings::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page`, `::test_d6_traversal_slugs_rejected` |
| `/admin/settings/logs` | `LogsView` | `admin_dashboard::test_d7_logs_show_admin_actions` |
| shell | `AppNavbar`, `AppFooter`, `MaintenanceBanner`, `AdminSidebar` | `smoke::test_navbar_items_from_yaml_in_order`, `::test_footer_renders_footer_template`; `auth::test_admin_sees_admin_link_regular_user_does_not`; `admin_dashboard::test_d1_maintenance_mode_banner`; `deep_links::test_admin_route_deep_link_and_refresh` |

`deep_links::test_public_route_logged_out`, `::test_protected_route_logged_out_redirects_to_login_with_next`,
`::test_user_route_deep_link_and_refresh`, `::test_admin_route_forbidden_for_regular_user` and
`::test_admin_route_deep_link_and_refresh` open every route except `/activate/:key` and
`/recover/:token` under the browser guards. `/admin/settings/templates` (redirect) has no test.

Components with vitest tests: `DynamicForm`/`ParamInput` (`contracts/dynamic-form.test.js`).
`AlertMessage`, `ConfirmDialog`, `LoadingSpinner`, `Pagination`, `JobStatusBadge`, `JobProgress`,
`JobResultsTab`, `JobLogTab`, `GroupManagementModal`, `GroupMembersModal` and the layout
components are covered only through e2e.

e2e tests that cite no frontend requirement (API-only or harness): `access_jobs::test_anonymous_cannot_download`;
`findings_admin::test_c02…`, `::test_c03…`, `::test_c04…`; `findings_jobs::test_a01…` to
`::test_a04…`; `findings_security::test_permission_matrix_object_access`, `::…_requires_authentication`,
`::…_public`, `::test_foreign_output_id_under_own_job`, `::test_b01…`, `::test_b03…`, `::test_b04…`,
`::test_b05…`; `queue::test_worker_restart_fails_orphans_and_queue_continues`; the
`harness_selftest` cases other than the three cited by FE-API-018. vitest tests that no
frontend requirement cites: `contracts/auth.test.js` › "logout() posts to /auth/logout/",
› "bad credentials are a non-field error message", › "an old token-style login response no
longer matches the contract"; `contracts/jobs.test.js` › "admin endpoints", › "job response
fixtures match the contract" (3 tests); `contracts/workflows.test.js` › "rejects the legacy
parameter shape (W2)", › "rejects unknown input types"; `contracts/users.test.js` › "there is no
getToken() any more".

### Traceability legend

`fe:` = `frontend/src/test/` (`fe:src/…` = `frontend/src/…` outside `src/test/`), `e2e:x` =
`e2e/tests/test_x.py`. `(p)` = planned test (file or name does not exist yet). `†` = the test
exists but the spec cites it under a paraphrased name (see Known gaps). Layer: `unit`, `contract`,
`e2e`, `gate` (`scripts/test.sh`, the e2e stack build, `scripts/smoke_gunicorn.sh`), `unit
(backend)`. `contracts/dynamic-form.test.js` is counted as `unit`. **Lvl** is the strongest RFC
2119 keyword in the requirement, plus `(planned)` when the requirement is marked so. **Status**:
`exists` = at least one cited test exists; `exists+planned` = exists, with further planned tests;
`planned` = only planned tests; `none` = no test cited.

## Behaviour

**vitest run.** `vitest run` collects `**/*.test.js` under `frontend/`, loads `setup.js`, and
runs each file in its own `happy-dom` environment with `describe`/`it`/`expect`/`vi` as globals.
`@/` resolves to `frontend/src` (FE-ARCH-004). Tests isolate HTTP in one of three ways:
`vi.mock('@/api/client', …)` with `vi.fn()` methods (contract files), a per-request or default
axios `adapter` stub (`client.test.js`, `admin-api.test.js`), or `vi.mock('@/api/<module>')`
(store tests). `auth-store.test.js` builds the real router from `src/router/index.js` with
`HomeView` mocked, so the guards run as in the app.

**Contract tests today.** A contract test calls an API-module function, asserts the mocked
client was called with the expected method, path, params and body, and validates the mocked
response with Ajv against a schema from `schemas.js`. Both the mocked body and the schema are
hand-written, so these tests prove request shapes but not response conformance to `schema.yaml`.
The target flow (FE-TEST-003) is in [api-contract.md](api-contract.md#target-contract-test-loader-fe-api-012-planned).

**Component tests (target).** A view test mounts the view with `@vue/test-utils` `mount`, a
memory-history router, a fresh Pinia, and `vi.mock` of each `@/api/<module>` it imports,
returning fixtures from `src/test/fixtures/` that FE-API-013 validates. It asserts on
`data-testid` elements (the same ids e2e uses), uses `flushPromises` for API settling and fake
timers for polling, and covers loading, empty, error (envelope message via `apiErrorMessage`)
and in-progress states.

**e2e.** Each e2e test drives one flow through the browser against the per-worker stack; the
browser guards fail a test on any unexpected console error or API response ≥ 400
(BE-TEST-014), so an e2e run also catches frontend↔API drift on every request a view makes.

**Traceability build.** The table below was built on 2026-10-21 by a one-off script: it parsed
the **Requirements** bullets of the 17 other files in this section (379 IDs; every one has an RFC
2119 keyword), parsed each **Acceptance tests** row (expanding `FE-X-010, 011`, `-031`,
`030–032` and bare `NNN` forms), and resolved each cited test: e2e functions by `def <name>(` in
the cited module, vitest names against the describe/it titles in the cited file (source and
`vitest --reporter=json` output), backend classes by `class <Name>`. 588 citations were
resolved: 407 to existing tests, 181 to planned ones. Two rows (`(contract)` in
admin-dashboard-jobs.md, `contract` in home-static-pages.md) carry no requirement ID and are not
in the table.

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| FE-TEST-001 | `scripts/test.sh` step "Frontend unit tests (vitest)"; `npm run test:run` (144 tests pass) | gate |
| FE-TEST-002 | by inspection: every vitest file stubs HTTP; `fe:setup.test.js › an un-stubbed request fails the test` (planned) | unit |
| FE-TEST-003 | the FE-API-012, FE-API-013, FE-API-014 tests (planned) | contract |
| FE-TEST-004 | `fe:admin-api.test.js › admin api › %#: request shape`; `fe:contracts/*.test.js`; `fe:contracts/operations.test.js › every exported api function has a contract test` (planned) | contract |
| FE-TEST-005 | `e2e/tests/test_deep_links.py` (all five functions); [view coverage map](#view-coverage-map) | e2e |
| FE-TEST-006 | `fe:views/<ViewName>.test.js` for each view (planned; named per view in the view spec files) | unit |
| FE-TEST-007 | e2e column of the [view coverage map](#view-coverage-map); missing flows in Known gaps | e2e |
| FE-TEST-008 | by inspection 2026-10-21 (all e2e ids resolve); `fe:testids.test.js › every data-testid used by e2e exists in src` (planned) | unit |
| FE-TEST-009 | `e2e/pages/__init__.py` used by `e2e:jobs`, `e2e:run_form`, `e2e:queue`, `e2e:command_steps` (inspection) | e2e |
| FE-TEST-010 | `fe:views/no-v-html.test.js` (planned, one file for all views); `e2e/tests/test_findings_security.py::test_user_values_never_rendered_as_html` (planned) | unit, e2e |
| FE-TEST-011 | `fe:contracts/dynamic-form.test.js › helpers › poller backs off without changes and stops when inactive` | unit |
| FE-TEST-012 | `npm run test:coverage` exits 0 (planned) | gate |
| FE-TEST-013 | `scripts/spec_trace.py` path check (planned) | gate |
| FE-TEST-014 | `scripts/spec_trace.py` (planned, BE-TEST-020); this table (built 2026-10-21) | gate |

### Traceability table

Built on 2026-10-21 by script (see Behaviour). All 379 requirement IDs defined in the other
frontend files appear below, followed by this file's own. Legend: see Traceability legend above.

### [overview.md](overview.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-ARCH-001 | MUST | `e2e/stack.py`; `scripts/smoke_gunicorn.sh`; `fe:build.test.js › built index.html references only /static/frontend/ assets` (p) | gate, unit | exists+planned |
| FE-ARCH-002 | MUST | `e2e/stack.py`; `scripts/smoke_gunicorn.sh`; `fe:build.test.js › built index.html references only /static/frontend/ assets` (p) | gate, unit | exists+planned |
| FE-ARCH-003 | MUST | `fe:vite-config.test.js › dev server proxies /api to :8000 only` (p) | unit | planned |
| FE-ARCH-004 | MUST | `fe:client.test.js` | unit | exists |
| FE-ARCH-005 | MUST | `e2e:smoke::test_favicon_served` (p) | e2e | planned |
| FE-ARCH-010 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e | exists |
| FE-ARCH-011 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e | exists |
| FE-ARCH-012 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e | exists |
| FE-ARCH-013 | MUST | `e2e:smoke::test_navbar_items_from_yaml_in_order`; `e2e:auth::test_admin_sees_admin_link_regular_user_does_not`; `fe:app.test.js › reloads server info when the user id changes` (p) | e2e, unit | exists+planned |
| FE-ARCH-020 | MUST | `fe:layering.test.js › only src/api imports the client default export or axios` (p) | unit | planned |
| FE-ARCH-021 | MUST | `fe:layering.test.js › no view reads err.response.data` (p) | unit | planned |
| FE-ARCH-022 | MAY | `fe:layering.test.js › only src/api imports the client default export or axios` (p) | unit | planned |
| FE-ARCH-023 | MUST | `fe:layering.test.js › only src/api imports the client default export or axios` (p) | unit | planned |
| FE-ARCH-024 | SHOULD | — | — | none |
| FE-ARCH-030 | MUST | `e2e:jobs::test_state_badge_classes` (p) | e2e | planned |
| FE-ARCH-031 | MUST | `e2e:jobs::test_state_badge_classes` (p) | e2e | planned |
| FE-ARCH-032 | MUST | `e2e:smoke::test_no_third_party_requests` (p) | e2e | planned |
| FE-ARCH-040 | MUST | `scripts/test.sh`; `fe:layering.test.js › runtime dependencies match the spec list` (p) | gate, unit | exists+planned |
| FE-ARCH-041 | MUST | `scripts/test.sh`; `fe:layering.test.js › runtime dependencies match the spec list` (p) | gate, unit | exists+planned |
| FE-ARCH-042 | MUST | `scripts/test.sh` | gate | exists |
| FE-ARCH-043 | SHOULD | — | — | none |
| FE-ARCH-044 | SHOULD | — | — | none |

### [api-contract.md](api-contract.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-API-001 | MUST | `fe:contracts/boundary.test.js › only api modules call the client` (p) | contract | planned |
| FE-API-002 | MUST | `fe:admin-api.test.js › admin api › %#: request shape`; `fe:contracts/jobs.test.js › jobs api endpoints › uses the SPEC paths for detail, status, cancel…`; `fe:contracts/users.test.js › users API › *`; `fe:contracts/auth.test.js › Authentication API Contracts › *`; `fe:contracts/operations.test.js › every api function uses a schema.yaml path and method` (p) | contract | exists+planned |
| FE-API-003 | MUST | `fe:admin-api.test.js › admin api › %#: request shape (getPage('../x'))`; `fe:contracts/users.test.js › account flows (auth.js) › activate POSTs the (url-encoded) key` | contract | exists |
| FE-API-004 | MUST | `fe:admin-api.test.js › admin api › %#: request shape (bodies)`; `fe:contracts/dynamic-form.test.js › buildFormData › sends SPEC field names, typed text, explicit checkb…` | contract, unit | exists |
| FE-API-005 | MUST | `fe:admin-api.test.js › admin api › sends only non-empty admin job filters (C6), › sends lo…`; `fe:contracts/jobs.test.js › lists own jobs with params or a page number` | contract | exists |
| FE-API-006 | MUST | `fe:contracts/fields-read.test.js › views read only schema fields` (p) | contract | planned |
| FE-API-007 | MUST | `e2e:jobs::test_cancel_waiting_and_delete_finished`; `e2e:smoke::test_home_lists_all_workflows` (p) | e2e | exists+planned |
| FE-API-008 | MUST | `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | e2e | exists |
| FE-API-009 | MUST | `e2e:access_jobs::test_owner_and_admin_can_download`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | e2e | exists |
| FE-API-010 | MUST | `fe:client.test.js › apiErrorMessage › *` | unit | exists |
| FE-API-011 | MUST | `fe:contracts/operations.test.js › mapping table lists every schema.yaml operationId` (p) | contract | planned |
| FE-API-012 | MUST | `fe:contracts/openapi-loader.test.js › loads components from schema.yaml` (p) | contract | planned |
| FE-API-013 | MUST | `fe:contracts/fixtures.test.js › every fixture validates against its schema.yaml component` (p) | contract | planned |
| FE-API-014 | MUST | `fe:contracts/requests.test.js › request bodies validate against *Request components` (p) | contract | planned |
| FE-API-015 | MUST | `fe:admin-api.test.js`; `fe:contracts/*.test.js` | contract | exists |
| FE-API-016 | MUST | `fe:operations.test.js › every exported function is used or listed unused` (p) | unit | planned |
| FE-API-017 | MUST | `fe:src/utils/validation.test.js › validation mirrors accounts/validation.py › username/email/password…`; `accounts/tests.py::ValidationRulesTest`; `e2e:accounts::test_a2_client_side_rules_match_server` | unit, unit (backend), e2e | exists |
| FE-API-018 | MUST | `e2e:harness_selftest::test_api_500_fails`; `e2e:harness_selftest::test_declared_api_error_passes`; `e2e:harness_selftest::test_declared_wrong_status_still_fails` | e2e | exists |

### [api-client.md](api-client.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-CLIENT-001 | MUST | `fe:client.test.js › api client › uses cookies and the /api base URL`; `fe:contracts/jobs.test.js › uses the SPEC paths for detail, status, cancel, delete, log`; `fe:contracts/auth.test.js › Session › me() calls GET /auth/me/ …`; `fe:client.test.js › encodes string path segments` (p) | unit, contract | exists+planned |
| FE-CLIENT-002 | MUST | `fe:client.test.js › uses cookies and the /api base URL` | unit | exists |
| FE-CLIENT-003 | MUST | `fe:client.test.js › never sends an Authorization token from localStorage`; `fe:auth-store.test.js › auth store › boots from /auth/me exactly once …` | unit | exists |
| FE-CLIENT-010 | MUST | `fe:client.test.js › sends X-CSRFToken from the csrftoken cookie on unsafe requests only`; `e2e:auth::test_login_and_logout_via_ui` | unit, e2e | exists |
| FE-CLIENT-011 | MUST | `fe:client.test.js › sends X-CSRFToken from the csrftoken cookie on unsafe requests only`; `e2e:auth::test_login_and_logout_via_ui` | unit, e2e | exists |
| FE-CLIENT-012 | MUST | `fe:client.test.js › sends unsafe requests without X-CSRFToken when no cookie exists` (p) | unit | planned |
| FE-CLIENT-013 | MUST | `fe:client.test.js › sends X-CSRFToken from the csrftoken cookie on unsafe requests only` | unit | exists |
| FE-CLIENT-020 | MUST | `fe:client.test.js › never forces a JSON content type on FormData …`; `fe:contracts/jobs.test.js › submits multipart FormData unchanged`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | unit, contract, e2e | exists |
| FE-CLIENT-021 | MUST | `fe:client.test.js › sends plain objects as application/json` (p) | unit | planned |
| FE-CLIENT-022 | MUST | `fe:contracts/jobs.test.js › uses the SPEC paths for detail, status, cancel, delete, log` | contract | exists |
| FE-CLIENT-030 | MUST | `fe:client.test.js › calls the 401 handler but does not redirect by itself` | unit | exists |
| FE-CLIENT-031 | MUST | `fe:client.test.js › apiErrorMessage › reads the SPEC §3.5 envelope › falls back for leg…`; `e2e:auth::test_login_wrong_password_shows_error` | unit, e2e | exists |
| FE-CLIENT-032 | MUST | `fe:client.test.js › apiErrorMessage › exposes field errors`; `fe:contracts/auth.test.js › Session › login field errors arrive in error.fields` | unit, contract | exists |
| FE-CLIENT-033 | MUST | `fe:client.test.js › apiErrorMessage › reads the SPEC §3.5 envelope`; `e2e:accounts::test_a3_lockout` | unit, e2e | exists |
| FE-CLIENT-034 | MUST | `fe:layering.test.js › no view reads err.response.data` (p) | unit | planned |
| FE-CLIENT-035 | MUST | `fe:client.test.js › mirrors the envelope message to data.message for legacy views` | unit | exists |
| FE-CLIENT-040 | MUST | `fe:client.test.js › calls the 401 handler but does not redirect by itself` | unit | exists |
| FE-CLIENT-041 | MUST | `fe:client.test.js › calls the 401 handler but does not redirect by itself` | unit | exists |
| FE-CLIENT-042 | MUST | `fe:client.test.js › calls the 401 handler but does not redirect by itself` | unit | exists |
| FE-CLIENT-050 | MUST | `fe:contracts/jobs.test.js › submitJob sets no short timeout` (p) | contract | planned |

### [routing.md](routing.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-ROUTE-001 | MUST | `e2e:deep_links::test_public_route_logged_out`; `e2e:deep_links::test_user_route_deep_link_and_refresh`; `e2e:deep_links::test_admin_route_deep_link_and_refresh` | e2e | exists |
| FE-ROUTE-002 | MUST | `e2e:deep_links`; `fe:router.test.js › route table matches the spec` (p) | e2e, unit | exists+planned |
| FE-ROUTE-003 | MUST | `fe:router.test.js › every route component is a lazy import` (p) | unit | planned |
| FE-ROUTE-004 | MUST | `fe:router.test.js › /admin/settings/templates redirects to /admin/settings/pages` (p) | unit | planned |
| FE-ROUTE-005 | MUST | `e2e:deep_links::test_unknown_route_redirects_home` | e2e | exists |
| FE-ROUTE-006 | MUST | `e2e:accounts::test_a1_register_activate_login`; `e2e:accounts::test_a4_password_reset` | e2e | exists |
| FE-ROUTE-010 | MUST | `fe:auth-store.test.js › router guards › waits for boot and redirects anonymous users to /lo…`; `fe:auth-store.test.js › auth store › boots from /auth/me exactly once, even with concurrent…` | unit | exists |
| FE-ROUTE-011 | MUST | `fe:auth-store.test.js › router guards › waits for boot and redirects anonymous users to /lo…`; `e2e:deep_links::test_protected_route_logged_out_redirects_to_login_with_next` | unit, e2e | exists |
| FE-ROUTE-012 | MUST | `fe:auth-store.test.js › router guards › sends non-admins away from admin routes › admins ca…`; `e2e:deep_links::test_admin_route_forbidden_for_regular_user`; `e2e:deep_links::test_protected_route_logged_out_redirects_to_login_with_next`; `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api` | unit, e2e | exists |
| FE-ROUTE-013 | MUST | `e2e:deep_links::test_public_route_logged_out` | e2e | exists |
| FE-ROUTE-014 | MUST | `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api`; `e2e:findings_security::test_permission_matrix_admin_endpoints` | e2e | exists |
| FE-ROUTE-020 | MUST | `e2e:auth::test_login_follows_next_parameter`; `fe:login-view.test.js › falls back to / for a missing or foreign next` (p) | e2e, unit | exists+planned |
| FE-ROUTE-021 | MUST | `fe:login-view.test.js › rejects //host, /\\host and absolute next values` (p) | unit | planned |
| FE-ROUTE-030 | MUST | `fe:auth-store.test.js › router guards › 401 on a protected page clears the user and goes to…` (p); `e2e:auth::test_session_expiry_returns_to_login` (p) | unit, e2e | planned |
| FE-ROUTE-031 | MUST | `fe:auth-store.test.js › router guards › 401 while anonymous is ignored` (p) | unit | planned |
| FE-ROUTE-040 | MUST | `e2e:deep_links::test_public_route_logged_out`; `e2e:deep_links::test_user_route_deep_link_and_refresh`; `e2e:deep_links::test_admin_route_deep_link_and_refresh` | e2e | exists |
| FE-ROUTE-041 | MUST | `e2e:deep_links::test_route_params_are_not_rendered_as_html` (p) | e2e | planned |
| FE-ROUTE-050 | SHOULD (planned) | — | — | none |
| FE-ROUTE-051 | SHOULD (planned) | — | — | none |
| FE-ROUTE-052 | MUST (planned) | `fe:router.test.js › chunk load failure falls back to a full page load` (p) | unit | planned |

### [state-stores.md](state-stores.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-STORE-001 | MUST | `fe:auth-store.test.js › auth store › boots from /auth/me exactly once, even with concurrent…`; `fe:layering.test.js › stores import only API modules` (p) | unit | exists+planned |
| FE-STORE-002 | MUST | `fe:auth-store.test.js › auth store › boots from /auth/me exactly once, even with concurrent…` | unit | exists |
| FE-STORE-003 | MUST | `fe:auth-store.test.js › auth store › anonymous and failing /me both mean logged out`; `fe:contracts/auth.test.js › Session › me() calls GET /auth/me/ and accepts both anonymous and a…` | unit, contract | exists |
| FE-STORE-004 | MUST | `fe:auth-store.test.js › auth store › anonymous and failing /me both mean logged out`; `fe:contracts/auth.test.js › Session › me() calls GET /auth/me/ and accepts both anonymous and a…` | unit, contract | exists |
| FE-STORE-005 | MUST | `fe:auth-store.test.js › auth store`; `fe:auth-store.test.js › router guards › sends non-admins away from admin routes` | unit | exists |
| FE-STORE-006 | MUST | `fe:auth-store.test.js › auth store`; `e2e:auth::test_login_and_logout_via_ui`; `e2e:auth::test_login_wrong_password_shows_error`; `fe:auth-store.test.js › failed login rejects and keeps user unchanged` (p) | unit, e2e | exists+planned |
| FE-STORE-007 | MUST | `fe:auth-store.test.js › auth store`; `e2e:auth::test_login_and_logout_via_ui` | unit, e2e | exists |
| FE-STORE-008 | MUST | `e2e:accounts::test_a6_delete_own_account`; `fe:auth-store.test.js › _clear resets the user without a request` (p) | e2e, unit | exists+planned |
| FE-STORE-009 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token`; `fe:auth-store.test.js › updateUser replaces the user` (p) | e2e, unit | exists+planned |
| FE-STORE-010 | MUST | `e2e:auth::test_admin_sees_admin_link_regular_user_does_not`; `e2e:smoke::test_navbar_items_from_yaml_in_order`; `fe:app.test.js › reloads server info when the user id changes` (p) | e2e, unit | exists+planned |
| FE-STORE-020 | MUST | `fe:server-store.test.js › server store › keeps defaults and records the error when the reques…` | unit | exists |
| FE-STORE-021 | MUST | `fe:server-store.test.js › server store › loads name, maintenance, navbar and footer`; `e2e:smoke::test_footer_renders_footer_template` | unit, e2e | exists |
| FE-STORE-022 | MUST | `fe:server-store.test.js › server store › loads once unless forced (navbar depends on the viewer)` | unit | exists |
| FE-STORE-023 | MUST | `e2e:auth::test_admin_sees_admin_link_regular_user_does_not`; `e2e:smoke::test_navbar_items_from_yaml_in_order`; `fe:app.test.js › reloads server info when the user id changes` (p) | e2e, unit | exists+planned |
| FE-STORE-024 | MUST | `fe:server-store.test.js › server store › keeps defaults and records the error when the reques…` | unit | exists |
| FE-STORE-025 | MUST | `fe:server-store.test.js › server store › loads name, maintenance, navbar and footer` | unit | exists |
| FE-STORE-030 | MUST | `fe:jobs-store.test.js › fetchJobs maps the paginated response › refreshJob replaces the cac…` (p) | unit | planned |
| FE-STORE-031 | MUST | `fe:jobs-store.test.js › fetchJobs maps the paginated response › refreshJob replaces the cac…` (p) | unit | planned |
| FE-STORE-032 | MUST | `fe:layering.test.js › every store is used` (p) | unit | planned |

### [layout-navigation.md](layout-navigation.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-NAV-001 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; `e2e:smoke::test_home_loads_cleanly_logged_in` | e2e | exists |
| FE-NAV-002 | MUST | `fe:server-store.test.js › server store › loads once unless forced (navbar depends on the viewer)`; `e2e:admin_settings::test_d6_navbar_editor` | unit, e2e | exists |
| FE-NAV-003 | MUST | `fe:server-store.test.js › server store › keeps defaults and records the error when the reques…`; `fe:layout.test.js › AppNavbar › renders defaults without server info` (p) | unit | exists+planned |
| FE-NAV-010 | MUST | `fe:layout.test.js › AppNavbar › brand is server name text` (p) | unit | planned |
| FE-NAV-011 | MUST | `e2e:smoke::test_navbar_items_from_yaml_in_order` | e2e | exists |
| FE-NAV-012 | MUST | `fe:layout.test.js › AppNavbar › renders links only for internal paths and http(s)` (p) | unit | planned |
| FE-NAV-013 | MUST | `fe:layout.test.js › AppNavbar › renders links only for internal paths and http(s)` (p) | unit | planned |
| FE-NAV-014 | MUST | `fe:layout.test.js › AppNavbar › renders links only for internal paths and http(s)` (p) | unit | planned |
| FE-NAV-015 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous` | e2e | exists |
| FE-NAV-016 | MUST | `e2e:auth::test_admin_sees_admin_link_regular_user_does_not` | e2e | exists |
| FE-NAV-017 | MUST | `e2e:auth::test_login_and_logout_via_ui`; `fe:layout.test.js › AppNavbar › logout navigates home when the request fails` (p) | e2e, unit | exists+planned |
| FE-NAV-020 | MUST | `e2e:admin_dashboard::test_d1_maintenance_mode_banner` | e2e | exists |
| FE-NAV-021 | MUST | `e2e:admin_dashboard::test_d1_maintenance_mode_banner` | e2e | exists |
| FE-NAV-030 | MUST | `e2e:smoke::test_footer_renders_footer_template`; `e2e:admin_settings::test_d6_edit_home_and_footer` | e2e | exists |
| FE-NAV-031 | MUST | `fe:layout.test.js › AppFooter › default text` (p) | unit | planned |
| FE-NAV-032 | MUST | `fe:layout.test.js › AppFooter › default text` (p) | unit | planned |
| FE-NAV-040 | MUST | `e2e:deep_links::test_admin_route_deep_link_and_refresh`; `fe:layout.test.js › AdminSidebar › every link resolves` (p) | e2e, unit | exists+planned |
| FE-NAV-041 | MUST | `e2e:deep_links::test_admin_route_deep_link_and_refresh`; `fe:layout.test.js › AdminSidebar › every link resolves` (p) | e2e, unit | exists+planned |
| FE-NAV-042 | MUST | `fe:layout.test.js › AdminSidebar › dashboard exact, others prefix` (p) | unit | planned |
| FE-NAV-043 | MUST | `e2e:deep_links::test_admin_route_forbidden_for_regular_user` | e2e | exists |
| FE-NAV-050 | MUST | `e2e:smoke::test_navbar_collapses_on_mobile` (p) | e2e | planned |
| FE-NAV-051 | MUST | `e2e:smoke::test_navbar_collapses_on_mobile` (p) | e2e | planned |
| FE-NAV-052 | SHOULD (planned) | — | — | none |
| FE-NAV-053 | SHOULD (planned) | — | — | none |

### [common-components.md](common-components.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-UI-001 | MUST | `fe:client.test.js › apiErrorMessage › reads the SPEC §3.5 envelope, › falls back for le…` | unit | exists |
| FE-UI-002 | MUST | `fe:common-components.test.js › AlertMessage` (p) | unit | planned |
| FE-UI-003 | MUST | `e2e:smoke::test_unknown_page_shows_not_found` | e2e | exists |
| FE-UI-010 | MUST | `fe:common-components.test.js › LoadingSpinner › has role status` (p) | unit | planned |
| FE-UI-011 | MUST | `e2e:smoke::test_unknown_page_shows_not_found` | e2e | exists |
| FE-UI-020 | MUST | `e2e:jobs::test_cancel_waiting_and_delete_finished`; `e2e:admin_settings::test_d6_create_view_delete_page`; `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart`; `e2e:accounts::test_d3_admin_users` | e2e | exists |
| FE-UI-021 | MUST | `fe:common-components.test.js › ConfirmDialog › emits confirm/cancel, disables while loading` (p) | unit | planned |
| FE-UI-022 | MUST | `fe:common-components.test.js › ConfirmDialog › emits confirm/cancel, disables while loading` (p) | unit | planned |
| FE-UI-023 | MUST | `e2e:findings_security::test_confirm_dialog_escapes_job_name` (p); `e2e/exploratory/probes_xss.py` (exploratory) | e2e | planned |
| FE-UI-024 | MUST (planned) | — | — | none |
| FE-UI-030 | MUST | `fe:common-components.test.js › Pagination › hidden for one page, no out-of-range emits` (p) | unit | planned |
| FE-UI-031 | MUST | `fe:common-components.test.js › Pagination › hidden for one page, no out-of-range emits` (p) | unit | planned |
| FE-UI-032 | MUST | `fe:common-components.test.js › Pagination › hidden for one page, no out-of-range emits` (p) | unit | planned |
| FE-UI-033 | SHOULD (planned) | — | — | none |
| FE-UI-034 | MUST | `fe:contracts/users.test.js › users API › admin users › listUsers → GET /admin/users/ with params…` | contract | exists |
| FE-UI-040 | MUST | `fe:contracts/users.test.js › initials avatar (no external requests) › uses the full name, else t…` | contract | exists |
| FE-UI-041 | MUST | `fe:contracts/users.test.js › initials avatar (no external requests) › uses the full name, else t…` | contract | exists |
| FE-UI-042 | MUST | `fe:contracts/users.test.js › initials avatar (no external requests) › uses the full name, else t…` | contract | exists |
| FE-UI-050 | MUST | `e2e:a11y::test_main_routes_have_no_critical_violations` (p) | e2e | planned |
| FE-UI-051 | MUST | `e2e:a11y::test_main_routes_have_no_critical_violations` (p) | e2e | planned |
| FE-UI-052 | MUST | — | — | none |
| FE-UI-053 | MUST | — | — | none |
| FE-UI-054 | MUST | — | — | none |

### [auth-views.md](auth-views.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-AUTHV-001 | MUST | `e2e:deep_links::test_public_route_logged_out`; `fe:src/views/public/__tests__/auth-views.test.js › views call only api/auth.js` (p) | e2e, unit | exists+planned |
| FE-AUTHV-002 | MUST | `fe:no-v-html.test.js › auth views render messages as text` (p) | unit | planned |
| FE-AUTHV-003 | MUST | `fe:src/views/public/__tests__/auth-views.test.js › submit button disabled while pending` (p) | unit | planned |
| FE-AUTHV-004 | SHOULD (planned) | `e2e:auth::test_logged_in_user_redirected_from_login` (p) | e2e | planned |
| FE-AUTHV-010 | MUST | `e2e:auth::test_login_and_logout_via_ui`; `fe:contracts/auth.test.js › login() posts credentials and receives {user} (no token)`; `fe:auth-store.test.js › "login stores the returned user` | e2e, contract, unit | exists |
| FE-AUTHV-011 | MUST | `e2e:auth::test_login_follows_next_parameter`; `fe:src/views/public/__tests__/LoginView.test.js › ignores //host and absolute next` (p) | e2e, unit | exists+planned |
| FE-AUTHV-012 | MUST | `e2e:auth::test_login_wrong_password_shows_error`; `e2e:accounts::test_a3_lockout`; `e2e:accounts::test_a1_register_activate_login` | e2e | exists |
| FE-AUTHV-013 | MUST | `fe:src/views/public/__tests__/LoginView.test.js › links to register and reset` (p) | unit | planned |
| FE-AUTHV-014 | SHOULD | — | — | none |
| FE-AUTHV-020 | MUST | `e2e:auth::test_login_and_logout_via_ui`; `fe:auth-store.test.js › "login stores the returned user`; `fe:src/components/layout/__tests__/AppNavbar.test.js › navigates home when logout fails` (p) | e2e, unit | exists+planned |
| FE-AUTHV-030 | MUST | `e2e:accounts::test_a2_client_side_rules_match_server` | e2e | exists |
| FE-AUTHV-031 | MUST | `e2e:accounts::test_a2_client_side_rules_match_server` | e2e | exists |
| FE-AUTHV-032 | MUST | `e2e:accounts::test_a1_register_activate_login`; `fe:contracts/auth.test.js › register() posts the form and receives {user, message}` | e2e, contract | exists |
| FE-AUTHV-033 | MUST | `e2e:accounts::test_a2_case_variant_duplicates_rejected`; `fe:contracts/auth.test.js › registration validation errors arrive in error.fields`; `e2e:accounts::test_register_mail_failed_shows_message` (p) | e2e, contract | exists+planned |
| FE-AUTHV-040 | MUST | `e2e:accounts::test_a1_register_activate_login`; `fe:contracts/users.test.js › activate POSTs the (url-encoded) key` | e2e, contract | exists |
| FE-AUTHV-041 | MUST | `e2e:accounts::test_a1_register_activate_login`; `fe:contracts/users.test.js › activate POSTs the (url-encoded) key` | e2e, contract | exists |
| FE-AUTHV-042 | MUST | `e2e:accounts::test_activate_invalid_key_shows_error` (p) | e2e | planned |
| FE-AUTHV-050 | MUST | `fe:src/views/public/__tests__/PasswordResetView.test.js › empty e-mail sends no request` (p) | unit | planned |
| FE-AUTHV-051 | MUST | `e2e:accounts::test_a4_password_reset`; `fe:contracts/auth.test.js › requestPasswordReset() posts the e-mail` | e2e, contract | exists |
| FE-AUTHV-052 | MUST | `fe:src/views/public/__tests__/PasswordResetView.test.js › shows fields.email` (p) | unit | planned |
| FE-AUTHV-060 | MUST | `e2e:accounts::test_a4_password_reset`; `fe:contracts/users.test.js › confirmPasswordReset posts password (+ confirm) to /auth/password-r…`; `e2e:accounts::test_recover_expired_token_offers_new_link` (p) | e2e, contract | exists+planned |
| FE-AUTHV-061 | MUST | `e2e:accounts::test_a4_password_reset`; `fe:contracts/users.test.js › confirmPasswordReset posts password (+ confirm) to /auth/password-r…`; `e2e:accounts::test_recover_expired_token_offers_new_link` (p) | e2e, contract | exists+planned |
| FE-AUTHV-062 | MUST | `e2e:accounts::test_a4_password_reset`; `fe:contracts/users.test.js › confirmPasswordReset posts password (+ confirm) to /auth/password-r…`; `e2e:accounts::test_recover_expired_token_offers_new_link` (p) | e2e, contract | exists+planned |
| FE-AUTHV-063 | MUST | `e2e:accounts::test_a4_password_reset`; `fe:contracts/users.test.js › confirmPasswordReset posts password (+ confirm) to /auth/password-r…`; `e2e:accounts::test_recover_expired_token_offers_new_link` (p) | e2e, contract | exists+planned |
| FE-AUTHV-070 | MUST | `fe:src/utils/validation.test.js › validation mirrors accounts/validation.py`; `accounts/tests.py::ValidationRulesTest` | unit, unit (backend) | exists |
| FE-AUTHV-071 | MUST | `fe:src/utils/validation.test.js › validation mirrors accounts/validation.py`; `accounts/tests.py::ValidationRulesTest` | unit, unit (backend) | exists |
| FE-AUTHV-072 | MUST | `fe:src/utils/validation.test.js › helpers › normalises like the backend model › validateFields collec…` | unit | exists |
| FE-AUTHV-073 | MUST | `fe:src/utils/validation.test.js › helpers › normalises like the backend model › validateFields collec…` | unit | exists |
| FE-AUTHV-074 | MUST | `e2e:accounts::test_a2_case_variant_duplicates_rejected`; `e2e:accounts::test_a4_password_reset` | e2e | exists |

### [profile.md](profile.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-PROF-001 | MUST | `e2e:deep_links::test_protected_route_logged_out_redirects_to_login_with_next`; `e2e:deep_links::test_user_route_deep_link_and_refresh`; `e2e:auth::test_login_follows_next_parameter`; `e2e:accounts::test_profile_session_expired_redirects_to_login` (p) | e2e | exists+planned |
| FE-PROF-002 | MUST | `fe:contracts/users.test.js › getProfile → GET /me/ with token metadata only › updateProfile → PA…` | contract | exists |
| FE-PROF-003 | MUST | `fe:src/views/public/__tests__/ProfileView.test.js › shows load error and no forms` (p) | unit | planned |
| FE-PROF-004 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token`; `fe:src/views/public/__tests__/ProfileView.test.js › shows username and groups` (p) | e2e, unit | exists+planned |
| FE-PROF-005 | MUST | `fe:no-v-html.test.js › profile renders server values as text` (p) | unit | planned |
| FE-PROF-010 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-011 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-012 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-013 | MUST | `e2e:accounts::test_profile_email_taken_shows_field_error` (p) | e2e | planned |
| FE-PROF-020 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-021 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-022 | MUST | `e2e:findings_security::test_b02_password_change_revokes_api_token`; `fe:src/views/public/__tests__/ProfileView.test.js › password change hides shown token` (p) | e2e, unit | exists+planned |
| FE-PROF-023 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-030 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-031 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-032 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token`; `fe:src/views/public/__tests__/ProfileView.test.js › token key not stored outside the view` (p) | e2e, unit | exists+planned |
| FE-PROF-033 | MUST | `fe:src/views/public/__tests__/ProfileView.test.js › copy falls back when clipboard is unavailable` (p) | unit | planned |
| FE-PROF-034 | MUST | `e2e:accounts::test_a5_profile_name_email_password_token` | e2e | exists |
| FE-PROF-035 | MUST | `fe:src/views/public/__tests__/ProfileView.test.js › token error message` (p) | unit | planned |
| FE-PROF-036 | SHOULD (planned) | — | — | none |
| FE-PROF-040 | MUST | `e2e:accounts::test_a6_delete_own_account`; `e2e:accounts::test_last_admin_cannot_delete_self_ui` (p) | e2e | exists+planned |
| FE-PROF-041 | MUST | `e2e:accounts::test_a6_delete_own_account`; `e2e:accounts::test_last_admin_cannot_delete_self_ui` (p) | e2e | exists+planned |
| FE-PROF-042 | MUST | `e2e:accounts::test_a6_delete_own_account`; `e2e:accounts::test_last_admin_cannot_delete_self_ui` (p) | e2e | exists+planned |
| FE-PROF-043 | MUST | `e2e:accounts::test_a6_delete_own_account`; `e2e:accounts::test_last_admin_cannot_delete_self_ui` (p) | e2e | exists+planned |
| FE-PROF-050 | MUST | `fe:src/views/public/__tests__/ProfileView.test.js › buttons disabled while saving` (p) | unit | planned |

### [home-static-pages.md](home-static-pages.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-PAGE-001 | MUST | `e2e:smoke::test_home_loads_cleanly_anonymous`; `e2e:deep_links::test_public_route_logged_out` | e2e | exists |
| FE-PAGE-002 | MUST | `e2e:smoke::test_home_renders_home_template`; `fe:home-view.test.js › HomeView › renders without home page on 404` (p) | e2e, unit | exists+planned |
| FE-PAGE-003 | MUST | `e2e:smoke::test_home_renders_home_template`; `fe:home-view.test.js › HomeView › renders without home page on 404` (p) | e2e, unit | exists+planned |
| FE-PAGE-004 | MUST | `e2e:admin_workflows::test_w1_workflow_visibility_per_user`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e | exists |
| FE-PAGE-005 | MUST | `fe:home-view.test.js › HomeView › follows pagination` (p) | unit | planned |
| FE-PAGE-006 | MUST | `e2e:smoke::test_home_loads_cleanly_logged_in`; `fe:home-view.test.js › HomeView › login link carries next` (p) | e2e, unit | exists+planned |
| FE-PAGE-007 | MUST | `fe:home-view.test.js › HomeView › error alert / empty text` (p) | unit | planned |
| FE-PAGE-008 | MUST | `fe:home-view.test.js › HomeView › error alert / empty text` (p) | unit | planned |
| FE-PAGE-009 | SHOULD (planned) | — | — | none |
| FE-PAGE-020 | MUST | `e2e:smoke::test_about_page_renders_pages_file`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-PAGE-021 | MUST | `e2e:smoke::test_about_page_renders_pages_file`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-PAGE-022 | MUST | `e2e:smoke::test_unknown_page_shows_not_found`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-PAGE-023 | MUST | `fe:static-page-view.test.js › StaticPageView › shows error alert` (p) | unit | planned |
| FE-PAGE-024 | MUST | `e2e:admin_settings::test_d6_traversal_slugs_rejected` | e2e | exists |
| FE-PAGE-030 | MUST | `e2e:admin_settings::test_d6_edit_home_and_footer` | e2e | exists |
| FE-PAGE-031 | MUST | `fe:home-view.test.js › HomeView › renders description HTML` (p) | unit | planned |
| FE-PAGE-032 | MUST | `e2e/exploratory/probes_xss.py` (exploratory); `e2e:findings_security::test_user_values_never_rendered_as_html` (p) | e2e | planned |
| FE-PAGE-033 | SHOULD (planned) | — | — | none |
| FE-PAGE-040 | MUST | `e2e:deep_links::test_unknown_route_redirects_home` | e2e | exists |

### [workflow-submit-form.md](workflow-submit-form.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-FORM-001 | MUST | `e2e:deep_links::test_protected_route_logged_out_redirects_to_login_with_next` | e2e | exists |
| FE-FORM-002 | MUST | `e2e:run_form::test_all_input_types_render_with_defaults`; `fe:contracts/workflows.test.js › workflows api › lists and gets workflows (call shape)` | e2e, contract | exists |
| FE-FORM-003 | MUST | `fe:views/workflow-submit.test.js › Workflow not found.` (p); `e2e:run_form::test_private_workflow_shows_not_found` (p) | unit, e2e | planned |
| FE-FORM-004 | MUST | `e2e:run_form::test_all_input_types_render_with_defaults`; `fe:contracts/workflows.test.js › workflows api › lists and gets workflows (call shape)` | e2e, contract | exists |
| FE-FORM-005 | MUST | `fe:views/workflow-submit.test.js › shows definition errors` (p) | unit | planned |
| FE-FORM-006 | SHOULD (planned) | — | — | none |
| FE-FORM-007 | MUST | `fe:contracts/dynamic-form.test.js › DynamicForm component › renders a wrapper per input with defaults a…`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-008 | MUST | `fe:contracts/dynamic-form.test.js › DynamicForm component › renders a wrapper per input with defaults a…`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-009 | MUST | `fe:contracts/dynamic-form.test.js › DynamicForm component › renders a wrapper per input with defaults a…`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-010 | MUST | `fe:contracts/dynamic-form.test.js › DynamicForm component › renders a wrapper per input with defaults a…`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-011 | MUST | `fe:contracts/dynamic-form.test.js › DynamicForm component › renders a wrapper per input with defaults a…`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-012 | MUST | `fe:contracts/dynamic-form.test.js › DynamicForm component › renders a wrapper per input with defaults a…`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-013 | MUST | `e2e:command_steps::test_run_form_shows_details_help_and_accept`; `fe:contracts/dynamic-form.test.js` | e2e, unit | exists |
| FE-FORM-014 | MUST | `fe:contracts/dynamic-form.test.js › helpers › formatBytes`; `fe:contracts/dynamic-form.test.js › lists selected files with size and removes one` (p) | unit | exists+planned |
| FE-FORM-015 | MUST | `e2e:run_form::test_all_input_types_render_with_defaults`; `fe:contracts/dynamic-form.test.js › renders help, details and option labels as text` (p) | e2e, unit | exists+planned |
| FE-FORM-016 | MUST | `fe:contracts/dynamic-form.test.js › non-http help is not a link` (p) | unit | planned |
| FE-FORM-017 | SHOULD (planned) | — | — | none |
| FE-FORM-018 | MUST | `fe:contracts/dynamic-form.test.js › buildFormData › sends SPEC field names…`; `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-019 | MUST | `fe:contracts/dynamic-form.test.js › buildFormData › sends SPEC field names…`; `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:run_form::test_all_input_types_render_with_defaults` | unit, e2e | exists |
| FE-FORM-020 | MUST | `fe:contracts/dynamic-form.test.js › validate › optional agb checkbox may stay unchecked` | unit | exists |
| FE-FORM-021 | MUST | `fe:contracts/dynamic-form.test.js › validate › reports required, range, choice, terms and file errors l…`; `e2e:run_form::test_client_validation_blocks_submit` | unit, e2e | exists |
| FE-FORM-022 | MUST | `fe:contracts/dynamic-form.test.js › validate › reports required, range, choice, terms and file errors l…`; `e2e:run_form::test_client_validation_blocks_submit`; `e2e:run_form::test_server_validation_field_errors`; `e2e:findings_jobs::test_a05_number_input_rejects_values_the_form_rejects` | unit, e2e | exists |
| FE-FORM-023 | MUST | `fe:contracts/dynamic-form.test.js › validate › reports required, range, choice, terms and file errors l…`; `e2e:run_form::test_client_validation_blocks_submit` | unit, e2e | exists |
| FE-FORM-024 | MUST | `fe:contracts/dynamic-form.test.js › validate › checks accept, single file and total upload size` | unit | exists |
| FE-FORM-025 | MUST | `fe:contracts/jobs.test.js › submits multipart FormData unchanged`; `fe:client.test.js › never forces a JSON content type on FormData` | contract, unit | exists |
| FE-FORM-026 | MUST | `fe:contracts/dynamic-form.test.js › buildFormData › sends SPEC field names, typed text, explicit checkb…`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | unit, e2e | exists |
| FE-FORM-027 | MUST | `fe:views/workflow-submit.test.js › disables submit while submitting` (p) | unit | planned |
| FE-FORM-028 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file` | e2e | exists |
| FE-FORM-029 | MUST | `e2e:run_form::test_server_field_errors_are_shown_in_the_form`; `fe:contracts/dynamic-form.test.js › DynamicForm component › shows field errors` | e2e, unit | exists |
| FE-FORM-030 | MUST | `e2e:queue::test_queue_full_rejects_submission`; `e2e:queue::test_maintenance_blocks_users_not_admins`; `fe:views/workflow-submit.test.js › maps 413/404/409 envelopes` (p) | e2e, unit | exists+planned |
| FE-FORM-031 | MUST | `e2e:queue::test_maintenance_blocks_users_not_admins` | e2e | exists |

### [job-list.md](job-list.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-JLIST-001 | MUST | `e2e:deep_links::test_protected_route_logged_out_redirects_to_login_with_next`; `e2e:deep_links::test_user_route_deep_link_and_refresh` | e2e | exists |
| FE-JLIST-002 | MUST | `e2e:access_jobs::test_other_user_cannot_see_job_outputs_or_log`; `fe:views/job-list.test.js › lists only returned jobs` (p) | e2e, unit | exists+planned |
| FE-JLIST-003 | MUST | `fe:contracts/jobs.test.js › jobs api endpoints › lists own jobs with params or a page number`; `fe:views/job-list.test.js › loads page 1 of 20 on mount` (p) | contract, unit | exists+planned |
| FE-JLIST-004 | MUST | `fe:views/job-list.test.js › shows the envelope message on load error` (p) | unit | planned |
| FE-JLIST-005 | MUST | `e2e:jobs::test_cancel_waiting_and_delete_finished`; `fe:views/job-list.test.js › formats duration` (p) | e2e, unit | exists+planned |
| FE-JLIST-006 | MUST | `fe:views/job-list.test.js › shows queue position and cancelling` (p) | unit | planned |
| FE-JLIST-007 | MUST | `e2e:jobs_list::test_html_in_job_name_is_text` (p) | e2e | planned |
| FE-JLIST-008 | MUST | `e2e:jobs_list::test_state_filter` (p) | e2e | planned |
| FE-JLIST-009 | MUST | `e2e:jobs_list::test_pagination` (p) | e2e | planned |
| FE-JLIST-010 | MUST | `fe:views/job-list.test.js › empty state with and without filter` (p) | unit | planned |
| FE-JLIST-011 | MUST | `fe:contracts/dynamic-form.test.js › helpers › poller backs off without changes and stops when inactive`; `e2e:jobs::test_cancel_waiting_and_delete_finished`; `fe:views/job-list.test.js › polls only while a job is active` (p) | unit, e2e | exists+planned |
| FE-JLIST-012 | MUST | `fe:contracts/dynamic-form.test.js › helpers › poller backs off without changes and stops when inactive`; `e2e:jobs::test_cancel_waiting_and_delete_finished`; `fe:views/job-list.test.js › polls only while a job is active` (p) | unit, e2e | exists+planned |
| FE-JLIST-013 | SHOULD (planned) | — | — | none |
| FE-JLIST-014 | MUST | `fe:views/job-list.test.js › buttons follow can_cancel/can_delete` (p); `e2e:jobs::test_cancel_waiting_and_delete_finished` | unit, e2e | exists+planned |
| FE-JLIST-015 | MUST | `e2e:jobs::test_cancel_waiting_and_delete_finished`; `fe:views/job-list.test.js › confirm dialog escapes the job name` (p) | e2e, unit | exists+planned |
| FE-JLIST-016 | MUST | `e2e:jobs::test_cancel_waiting_and_delete_finished`; `e2e:jobs_list::test_delete_from_list_and_conflict_message` (p) | e2e | exists+planned |
| FE-JLIST-018 | SHOULD (planned) | — | — | none |
| FE-JLIST-017 | MUST | `fe:components/job-status-badge.test.js › maps every state` (p); `fe:contracts/jobs.test.js › jobs api endpoints › state helpers` | unit, contract | exists+planned |
| FE-JLIST-019 | SHOULD (planned) | — | — | none |
| FE-JLIST-020 | MUST | `fe:architecture.test.js › views do not import the HTTP client` (p) | unit | planned |

### [job-detail.md](job-detail.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-JDET-001 | MUST | `e2e:deep_links::test_protected_route_logged_out_redirects_to_login_with_next`; `e2e:deep_links::test_job_page_deep_link` (p) | e2e | exists+planned |
| FE-JDET-002 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `fe:contracts/jobs.test.js › jobs api endpoints › uses the SPEC paths for detail, status, cancel…` | e2e, contract | exists |
| FE-JDET-003 | MUST | `e2e:access_jobs::test_other_user_cannot_see_job_outputs_or_log`; `fe:views/job-detail.test.js › shows envelope message on non-404 error` (p) | e2e, unit | exists+planned |
| FE-JDET-004 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:job_detail::test_html_in_job_name_is_text` (p) | e2e | exists+planned |
| FE-JDET-005 | MUST | `fe:views/job-detail.test.js › elapsed time` (p) | unit | planned |
| FE-JDET-006 | MUST | `e2e:queue::test_queue_limits_and_advances_after_cancel`; `e2e:queue::test_pause_and_resume_queue`; `fe:views/job-detail.test.js › shows cancelling` (p) | e2e, unit | exists+planned |
| FE-JDET-007 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_live_progress_multi_process`; `e2e:queue::test_pause_and_resume_queue`; `fe:views/job-detail.test.js › stops polling on final state and unmount` (p) | e2e, unit | exists+planned |
| FE-JDET-008 | MUST | `fe:contracts/dynamic-form.test.js › helpers › poller backs off without changes and stops when inactive` | unit | exists |
| FE-JDET-009 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_live_progress_multi_process`; `e2e:queue::test_pause_and_resume_queue`; `fe:views/job-detail.test.js › stops polling on final state and unmount` (p) | e2e, unit | exists+planned |
| FE-JDET-010 | MUST | `fe:views/job-detail.test.js › progress change resets the poll delay` (p) | unit | planned |
| FE-JDET-011 | MUST | `e2e:jobs::test_live_progress_multi_process` | e2e | exists |
| FE-JDET-012 | SHOULD (planned) | — | — | none |
| FE-JDET-013 | SHOULD (planned) | — | — | none |
| FE-JDET-014 | MUST | `e2e:jobs::test_failing_workflow`; `fe:views/job-detail.test.js › results badge` (p) | e2e, unit | exists+planned |
| FE-JDET-015 | MUST | `e2e:jobs::test_failing_workflow` | e2e | exists |
| FE-JDET-016 | MUST | `e2e:command_steps::test_command_steps_run_and_show_output` | e2e | exists |
| FE-JDET-017 | MUST | `e2e:jobs::test_live_progress_multi_process` | e2e | exists |
| FE-JDET-018 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_failing_workflow`; `e2e:command_steps::test_command_steps_run_and_show_output`; `e2e:command_steps::test_failing_command_step_fails_the_job`; `e2e:job_detail::test_message_html_is_text` (p) | e2e | exists+planned |
| FE-JDET-019 | MUST | `fe:views/job-detail.test.js › inputs table` (p) | unit | planned |
| FE-JDET-020 | MUST | `fe:components/job-results-tab.test.js › states: active, purged, empty` (p) | unit | planned |
| FE-JDET-021 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file`; `e2e:jobs::test_live_progress_multi_process`; `e2e:command_steps::test_command_steps_run_and_show_output` | e2e | exists |
| FE-JDET-022 | MUST | `e2e:jobs::test_submit_hello_with_unicode_job_name`; `e2e:jobs::test_all_inputs_uploads_folder_and_write_file`; `e2e:jobs::test_live_progress_multi_process`; `e2e:command_steps::test_command_steps_run_and_show_output` | e2e | exists |
| FE-JDET-023 | MUST | `fe:components/job-results-tab.test.js › expiry line` (p) | unit | planned |
| FE-JDET-024 | MUST | `e2e:jobs::test_failing_workflow`; `e2e:command_steps::test_command_steps_run_and_show_output` | e2e | exists |
| FE-JDET-025 | MUST | `fe:components/job-log-tab.test.js › error and refresh` (p) | unit | planned |
| FE-JDET-026 | MUST | `e2e:jobs::test_cancel_running_job_from_job_page`; `fe:views/job-detail.test.js › restart only for admins` (p) | e2e, unit | exists+planned |
| FE-JDET-027 | MUST | `e2e:jobs::test_cancel_running_job_from_job_page`; `e2e:jobs::test_cancel_waiting_and_delete_finished`; `fe:views/job-detail.test.js › confirm dialog escapes the job name` (p) | e2e, unit | exists+planned |
| FE-JDET-028 | MUST | `e2e:jobs::test_cancel_running_job_from_job_page`; `e2e:jobs::test_cancel_waiting_and_delete_finished`; `e2e:command_steps::test_cancel_during_long_command_step`; `e2e:job_detail::test_admin_restart_from_job_page` (p) | e2e | exists+planned |
| FE-JDET-029 | MUST | `e2e:job_detail::test_cancel_conflict_shows_message` (p) | e2e | planned |
| FE-JDET-030 | SHOULD (planned) | — | — | none |
| FE-JDET-031 | MUST | `fe:architecture.test.js › views do not import the HTTP client` (p) | unit | planned |

### [admin-dashboard-jobs.md](admin-dashboard-jobs.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-ADASH-001 | MUST | `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api`; `fe:router.test.js` (p) | e2e, unit | exists+planned |
| FE-ADASH-010 | MUST | `fe:views/AdminDashboardView.test.js › polls every 10 s, stops on unmount, keeps data on error` (p) | unit | planned |
| FE-ADASH-011 | MUST | `fe:views/AdminDashboardView.test.js › polls every 10 s, stops on unmount, keeps data on error` (p) | unit | planned |
| FE-ADASH-012 | MUST | `e2e:admin_dashboard::test_d1_dashboard_counts_match_db` | e2e | exists |
| FE-ADASH-013 | MUST | `e2e:admin_dashboard::test_d1_pause_resume_queue`; `e2e:admin_dashboard::test_d7_logs_show_admin_actions` | e2e | exists |
| FE-ADASH-014 | MUST | `e2e:admin_dashboard::test_d1_maintenance_mode_banner`; `fe:admin-api.test.js › admin api request shape (enterMaintenance)` † | e2e, contract | exists |
| FE-ADASH-015 | MUST | `e2e:admin_dashboard::test_d1_pause_resume_queue`; `e2e:admin_dashboard::test_d7_logs_show_admin_actions`; `e2e:admin_dashboard::test_d1_maintenance_mode_banner`; `fe:admin-api.test.js › admin api request shape (enterMaintenance)` † | e2e, contract | exists |
| FE-ADASH-016 | MUST | `e2e:admin_dashboard::test_d1_dashboard_counts_match_db` | e2e | exists |
| FE-ADASH-017 | MUST | `e2e:admin_dashboard::test_d1_dashboard_counts_match_db` | e2e | exists |
| FE-ADASH-018 | MUST (planned) | `fe:views/AdminDashboardView.test.js › shows config errors` (p) | unit | planned |
| FE-ADASH-019 | MUST | `fe:views/admin-no-vhtml.test.js › admin dashboard/jobs render <script> names as text` (p) | unit | planned |
| FE-ADASH-030 | MUST | `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart`; `fe:admin-api.test.js › sends only non-empty admin job filters (C6)` | e2e, contract | exists |
| FE-ADASH-031 | MUST | `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart`; `fe:admin-api.test.js › sends only non-empty admin job filters (C6)` | e2e, contract | exists |
| FE-ADASH-032 | MUST | `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart`; `fe:admin-api.test.js › sends only non-empty admin job filters (C6)` | e2e, contract | exists |
| FE-ADASH-033 | MUST | `fe:views/AdminJobsView.test.js › page count from count/page_size, filters kept` (p) | unit | planned |
| FE-ADASH-034 | MUST | `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | e2e | exists |
| FE-ADASH-035 | MUST | `e2e:admin_dashboard::test_d2_admin_jobs_filter_cancel_restart` | e2e | exists |
| FE-ADASH-036 | MUST | `fe:views/admin-no-vhtml.test.js › admin dashboard/jobs render <script> names as text` (p) | unit | planned |

### [admin-users-groups.md](admin-users-groups.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-AUSER-001 | MUST | `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api` | e2e | exists |
| FE-AUSER-010 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › admin users › listUsers → GET /admin/users/ with params (paginated)` | e2e, contract | exists |
| FE-AUSER-011 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › admin users › listUsers → GET /admin/users/ with params (paginated)` | e2e, contract | exists |
| FE-AUSER-012 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:views/AdminUsersView.test.js › page change replaces rows, no duplicates` (p) | e2e, unit | exists+planned |
| FE-AUSER-013 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › admin users › listUsers → GET /admin/users/ with params (paginated)` | e2e, contract | exists |
| FE-AUSER-014 | MUST | `fe:views/AdminUsersView.test.js › shows envelope message and keeps row on PATCH failure` (p) | unit | planned |
| FE-AUSER-020 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › groups are names, not objects` | e2e, contract | exists |
| FE-AUSER-021 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › groups are names, not objects` | e2e, contract | exists |
| FE-AUSER-022 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › groups are names, not objects` | e2e, contract | exists |
| FE-AUSER-023 | MUST | `fe:views/AdminUsersView.test.js › shows envelope message and keeps row on PATCH failure` (p) | unit | planned |
| FE-AUSER-024 | MUST | `fe:views/AdminUsersView.test.js › own row and superuser buttons disabled` (p) | unit | planned |
| FE-AUSER-025 | MUST | `e2e:accounts::test_d3_admin_users` | e2e | exists |
| FE-AUSER-030 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › admin groups › listGroups / createGroup / deleteGroup` †; `fe:src/utils/validation.test.js` | e2e, contract, unit | exists |
| FE-AUSER-031 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › admin groups › listGroups / createGroup / deleteGroup` †; `fe:src/utils/validation.test.js` | e2e, contract, unit | exists |
| FE-AUSER-032 | MUST | `e2e:accounts::test_d3_admin_users`; `fe:contracts/users.test.js › admin groups › listGroups / createGroup / deleteGroup` †; `fe:src/utils/validation.test.js` | e2e, contract, unit | exists |
| FE-AUSER-033 | MUST | `e2e:admin_users::test_group_members_modal_remove_member` (p) | e2e | planned |
| FE-AUSER-034 | MUST | `e2e:admin_users::test_group_members_modal_remove_member` (p) | e2e | planned |
| FE-AUSER-035 | MUST | `fe:components/GroupModals.test.js › backdrop closes only top modal` (p) | unit | planned |
| FE-AUSER-040 | MUST | `fe:views/admin-no-vhtml.test.js › user and group names render as text` (p) | unit | planned |

### [admin-workflows.md](admin-workflows.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-AWF-001 | MUST | `fe:router.test.js` (p); `e2e:accounts::test_a7_non_admin_blocked_from_admin_ui_and_api` | unit, e2e | exists+planned |
| FE-AWF-010 | MUST | `e2e:admin_workflows::test_d4_invalid_entry_listed_with_errors`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e | exists |
| FE-AWF-011 | MUST | `e2e:admin_workflows::test_d4_invalid_entry_listed_with_errors`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e | exists |
| FE-AWF-012 | MUST | `e2e:admin_workflows::test_d4_invalid_entry_listed_with_errors`; `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e | exists |
| FE-AWF-013 | MUST | `e2e:admin_workflows::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e | exists |
| FE-AWF-014 | MUST | `e2e:admin_workflows::test_admin_list_reload_and_sync` (p); `fe:admin-api.test.js › admin api request shape (reloadWorkflow, syncWorkflows)` † | e2e, contract | exists+planned |
| FE-AWF-015 | MUST | `e2e:admin_workflows::test_admin_list_reload_and_sync` (p); `fe:admin-api.test.js › admin api request shape (reloadWorkflow, syncWorkflows)` † | e2e, contract | exists+planned |
| FE-AWF-016 | MUST | `e2e:admin_workflows::test_d4_install_invalid_then_valid_and_uninstall` | e2e | exists |
| FE-AWF-017 | MUST | `e2e:admin_workflows::test_d4_install_invalid_then_valid_and_uninstall` | e2e | exists |
| FE-AWF-018 | MUST | `fe:views/AdminWorkflowsView.test.js › buttons disabled while busy` (p) | unit | planned |
| FE-AWF-030 | MUST | `fe:views/AdminWorkflowSettingsView.test.js › 404 shows not-found` (p) | unit | planned |
| FE-AWF-031 | MUST | `e2e:admin_workflows::test_d4_reload_after_yaml_edit` | e2e | exists |
| FE-AWF-032 | MUST | `e2e:admin_workflows::test_d4_groups_and_public_via_settings_page` | e2e | exists |
| FE-AWF-033 | MUST | `e2e:admin_workflows::test_d4_per_app_nextflow_settings_persist` | e2e | exists |
| FE-AWF-034 | MUST | `e2e:admin_workflows::test_d4_reload_after_yaml_edit` | e2e | exists |
| FE-AWF-035 | MUST | `fe:views/AdminWorkflowsView.test.js › buttons disabled while busy` (p) | unit | planned |
| FE-AWF-040 | MUST | `fe:views/admin-no-vhtml.test.js › workflow errors/YAML render as text` (p) | unit | planned |

### [admin-settings.md](admin-settings.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-ASET-001 | MUST | `fe:router.test.js` (p) | unit | planned |
| FE-ASET-002 | MUST | `fe:views/AdminSettingsViews.test.js › load failure hides form` (p) | unit | planned |
| FE-ASET-003 | MUST | `e2e:admin_settings::test_d5_general_settings_round_trip`; `e2e:admin_settings::test_d5_general_settings_validation_error` | e2e | exists |
| FE-ASET-010 | MUST | `e2e:admin_settings::test_d5_general_settings_round_trip`; `e2e:admin_settings::test_d5_general_settings_validation_error` | e2e | exists |
| FE-ASET-011 | MUST | `e2e:admin_settings::test_d5_general_settings_round_trip`; `e2e:admin_settings::test_d5_general_settings_validation_error` | e2e | exists |
| FE-ASET-012 | MUST | `e2e:admin_settings::test_d6_navbar_editor`; `e2e:findings_admin::test_c05_navbar_url_is_validated`; `fe:admin-api.test.js › request shape (updateNavbar)` | e2e, contract | exists |
| FE-ASET-013 | MUST | `e2e:admin_settings::test_d6_navbar_editor`; `e2e:findings_admin::test_c05_navbar_url_is_validated`; `fe:admin-api.test.js › request shape (updateNavbar)` | e2e, contract | exists |
| FE-ASET-020 | MUST | `e2e:admin_settings::test_d5_nextflow_settings_round_trip` | e2e | exists |
| FE-ASET-021 | MUST | `e2e:admin_settings::test_d5_nextflow_settings_round_trip` | e2e | exists |
| FE-ASET-030 | MUST | `e2e:admin_settings::test_d5_mail_password_write_only` | e2e | exists |
| FE-ASET-031 | MUST | `e2e:admin_settings::test_d5_mail_password_write_only` | e2e | exists |
| FE-ASET-032 | MUST | `e2e:findings_admin::test_c01_mail_tls_and_ssl_cannot_both_be_enabled`; `e2e:admin_settings::test_d5_mail_tls_ssl_field_error` (p) | e2e | exists+planned |
| FE-ASET-033 | MUST | `e2e:admin_settings::test_d5_mail_test_lands_in_outbox`; `fe:admin-api.test.js › request shape (sendTestMail with/without to)` | e2e, contract | exists |
| FE-ASET-040 | MUST | `e2e:admin_settings::test_d6_edit_home_and_footer`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-ASET-041 | MUST | `fe:views/PagesView.test.js › late getPage response is dropped` (p) | unit | planned |
| FE-ASET-042 | MUST | `e2e:admin_settings::test_d6_traversal_slugs_rejected`; `fe:admin-api.test.js › request shape (getPage('../x') encoded)` | e2e, contract | exists |
| FE-ASET-043 | MUST | `e2e:admin_settings::test_d6_edit_home_and_footer`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-ASET-044 | MUST | `e2e:admin_settings::test_d6_edit_home_and_footer`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-ASET-045 | MUST | `e2e:admin_settings::test_d6_edit_home_and_footer`; `e2e:admin_settings::test_d6_create_view_delete_page` | e2e | exists |
| FE-ASET-046 | MUST | `e2e:admin_settings::test_d6_edit_home_and_footer` | e2e | exists |
| FE-ASET-050 | MUST | `e2e:admin_dashboard::test_d7_logs_show_admin_actions`; `fe:admin-api.test.js › sends log filters` | e2e, contract | exists |
| FE-ASET-051 | MUST | `e2e:admin_dashboard::test_d7_logs_show_admin_actions`; `fe:admin-api.test.js › sends log filters` | e2e, contract | exists |
| FE-ASET-052 | MUST | `fe:views/LogsView.test.js › row click toggles metadata` (p) | unit | planned |
| FE-ASET-053 | MUST | `fe:views/LogsView.test.js › HTML in message is shown as text` (p) | unit | planned |

### [tests.md](tests.md)

| ID | Lvl | Tests | Layer | Status |
|---|---|---|---|---|
| FE-TEST-001 | MUST | `scripts/test.sh` (vitest step) | gate | exists |
| FE-TEST-002 | MUST | inspection; `fe:setup.test.js › an un-stubbed request fails the test` (p) | unit | planned |
| FE-TEST-003 | MUST (planned) | FE-API-012/013/014 tests (p) | contract | planned |
| FE-TEST-004 | MUST | `fe:admin-api.test.js › admin api › %#: request shape`; `fe:contracts/*.test.js`; `fe:contracts/operations.test.js › every exported api function has a contract test` (p) | contract | exists+planned |
| FE-TEST-005 | MUST | `e2e:deep_links` (5 functions) | e2e | exists |
| FE-TEST-006 | MUST (planned) | `fe:views/<ViewName>.test.js` (p) | unit | planned |
| FE-TEST-007 | MUST | e2e tests of the view coverage map | e2e | exists |
| FE-TEST-008 | MUST | inspection; `fe:testids.test.js › every data-testid used by e2e exists in src` (p) | unit | exists+planned |
| FE-TEST-009 | SHOULD | `e2e/pages/__init__.py` (inspection) | e2e | exists |
| FE-TEST-010 | MUST (planned) | `fe:views/no-v-html.test.js` (p); `e2e:findings_security::test_user_values_never_rendered_as_html` (p) | unit, e2e | planned |
| FE-TEST-011 | MUST | `fe:contracts/dynamic-form.test.js › helpers › poller backs off without changes and stops when inactive` | unit | exists |
| FE-TEST-012 | MUST (planned) | `npm run test:coverage` (p) | gate | planned |
| FE-TEST-013 | MUST | `scripts/spec_trace.py` (p) | gate | planned |
| FE-TEST-014 | MUST | `scripts/spec_trace.py` (p); this table | gate | planned |

### Summary counts

"Existing test" = at least one cited test exists (it may also have planned ones). Counts are of
requirements, not tests.

| File | Reqs | MUST | Existing test | Planned only | None |
|---|---|---|---|---|---|
| overview.md | 22 | 18 | 10 | 9 | 3 |
| api-contract.md | 18 | 18 | 11 | 7 | 0 |
| api-client.md | 20 | 20 | 16 | 4 | 0 |
| routing.md | 20 | 18 | 11 | 7 | 2 |
| state-stores.md | 19 | 19 | 16 | 3 | 0 |
| layout-navigation.md | 24 | 22 | 13 | 9 | 2 |
| common-components.md | 23 | 22 | 8 | 10 | 5 |
| auth-views.md | 29 | 27 | 21 | 7 | 1 |
| profile.md | 25 | 24 | 18 | 6 | 1 |
| home-static-pages.md | 19 | 17 | 11 | 6 | 2 |
| workflow-submit-form.md | 31 | 29 | 25 | 4 | 2 |
| job-list.md | 20 | 17 | 10 | 7 | 3 |
| job-detail.md | 31 | 28 | 20 | 8 | 3 |
| admin-dashboard-jobs.md | 18 | 18 | 12 | 6 | 0 |
| admin-users-groups.md | 19 | 19 | 12 | 7 | 0 |
| admin-workflows.md | 17 | 17 | 13 | 4 | 0 |
| admin-settings.md | 24 | 24 | 19 | 5 | 0 |
| tests.md | 14 | 13 | 7 | 7 | 0 |
| **Total** | **393** | **370** | **253** | **116** | **24** |

MUST requirements: 370, of which 252 have an existing test, 114 have only planned tests and 4
have none (FE-UI-024 (planned), FE-UI-052, FE-UI-053, FE-UI-054). The 20 requirements with no
test that are not MUST are SHOULD/MAY requirements, 16 of them `(planned)`.

Cited tests: 76 distinct existing e2e functions, 30 planned e2e functions (10 of them in modules that do
not exist yet: `test_a11y.py`, `test_admin_users.py`, `test_job_detail.py`, `test_jobs_list.py`);
78 distinct existing vitest tests or files, 112 planned vitest tests in 41 planned files.

## Known gaps

| Req | What the code / suite does today | Where | Severity |
|---|---|---|---|
| FE-TEST-003 | Contract tests validate mocked responses and fixtures against hand-written JSON Schemas in `src/test/schemas.js`; nothing loads `schema.yaml`. A response-shape drift between backend and SPA passes vitest and is caught only by e2e. Details and home of this gap: [api-contract.md](api-contract.md) FE-API-012/013. | `frontend/src/test/schemas.js`, `frontend/src/test/contracts/*.test.js` | major |
| FE-TEST-006 | No view has a component test: 0 of 21 route views are mounted in vitest; only `DynamicForm` is. Loading, empty, error, polling and in-progress states are therefore untested except where e2e happens to reach them. 107 MUST requirements in other files have only planned tests; about 60 of them are view or component tests. | `frontend/src/test/` | major |
| FE-TEST-007 | User flows that reach the API with only planned e2e tests: job list state filter, pagination, delete from list and 409 message (FE-JLIST-008, 009, 016); group members modal (FE-AUSER-033, 034); admin workflows reload/sync buttons (FE-AWF-014, 015); activation with an invalid key (FE-AUTHV-042); e-mail already taken on the profile (FE-PROF-013); session expiry on a protected page (FE-ROUTE-030); restart from the job page and cancel conflict (FE-JDET-028, 029); `/admin/settings/templates` redirect. | `e2e/tests/` | major |
| FE-TEST-010 | No test in the suite injects markup into a user-controlled value (job name, username, group name, log message, workflow error) and asserts it renders as text. Only the exploratory probe `e2e/exploratory/probes_xss.py` does, outside the suite. Planned tests are spread over `no-v-html.test.js`, `views/admin-no-vhtml.test.js`, `job-detail.test.js`, `job-list.test.js`, `test_job_detail.py`, `test_jobs_list.py`. | `e2e/exploratory/probes_xss.py` | major |
| FE-TEST-012 | `npm run test:coverage` fails with "MISSING DEPENDENCY Cannot find dependency '@vitest/coverage-v8'"; no coverage is measured. | `frontend/package.json` | minor |
| FE-TEST-002 | Unit tests stub HTTP by convention only. `setup.js` sets `global.fetch = fetch` (the real one) and leaves the axios default adapter in place, so a test that forgets a mock would hit the network (or fail with a connection error) instead of failing clearly. | `frontend/src/test/setup.js:6-8` | minor |
| FE-TEST-003 | `setup.js` registers `toBeValidApiResponse` and `toHaveApiField`, which no test uses, and `toMatchApiSchema`, which reads `global.ajv`; each contract file creates its own Ajv with different options (`auth`, `users`: default strict; `jobs`, `workflows`: `strict: false, allowUnionTypes`). [overview.md](overview.md) Known gaps says `global.ajv` is "never set"; that is wrong — it is set per file. | `frontend/src/test/setup.js:11-70`, `frontend/src/test/contracts/*.test.js:15-24` | minor |
| FE-TEST-013 | Planned vitest tests cited by the view spec files use 41 new files in 5 locations (`src/test/`, `src/test/views/`, `src/test/components/`, `src/views/public/__tests__/`, `src/components/layout/__tests__/`) and kebab- and Pascal-case names. Several rules have more than one planned home: layering (`layering.test.js`, `architecture.test.js`, `contracts/boundary.test.js`); no-`v-html` (`no-v-html.test.js`, `views/admin-no-vhtml.test.js`); router (`router.test.js`, `auth-store.test.js` › "router guards"); login view (`login-view.test.js`, `views/public/__tests__/LoginView.test.js`); operations (`operations.test.js`, `contracts/operations.test.js`). The existing `contracts/dynamic-form.test.js` is a unit/component test in the contracts folder. | spec/frontend Acceptance tests | minor |
| FE-TEST-014 | 7 citations name existing tests by a paraphrase (marked `†`): FE-ADASH-014, 015 cite `admin-api.test.js` › "admin api request shape (`enterMaintenance`)" — actual name `admin api › %#: request shape` (case `enterMaintenance`); FE-AWF-014, 015 likewise for `reloadWorkflow`, `syncWorkflows`; FE-AUSER-030, 031, 032 cite `contracts/users.test.js` › "admin groups › listGroups / createGroup / deleteGroup" — actual tests `admin groups › listGroups → plain array with member_count` and `› createGroup / deleteGroup`. No test cited as existing is missing. | admin-dashboard-jobs.md, admin-workflows.md, admin-users-groups.md Acceptance tests | minor |
| FE-TEST-014 | Traceability is checked by hand; nothing fails when a cited test is renamed. Acceptance tables use four formats (`FE-X-010, 011`, `-031`, `030–032`, bare `NNN` in workflow-submit-form.md) and two column layouts (with and without a Layer column), which a checker has to normalise. | spec/frontend | minor |
| FE-TEST-008 | `e2e/README.md` "Current ids" lists about 40 ids; the SPA defines about 340 and e2e uses about 190. Nothing checks that an id used by e2e exists (all do today). | `e2e/README.md` (Writing a test, step 3) | minor |
| FE-TEST-001 | `scripts/test.sh` has no vitest-only mode: `unit` always runs the Django gates first. [overview.md](overview.md) FE-ARCH-042's test cell says the script runs `npm run test:run`; it runs `npx vitest run` (same effect). | `scripts/test.sh:58-62` | minor |
| — | FE-UI-052, FE-UI-053, FE-UI-054 (MUST) and FE-UI-024 (MUST, planned) have no test cited. FE-UI-054 (`data-testid` on interactive elements) would be covered by the FE-TEST-008 check; FE-UI-053 by FE-TEST-010. | [common-components.md](common-components.md) | minor |
| — | No hosted CI runs vitest or e2e ([BE-TEST-019](../backend/tests.md)). | repository root | major (owned by backend tests) |

## Open questions

1. Confirm the vitest layout in FE-TEST-013 (`src/test/views/<ViewName>.test.js`, PascalCase), and
   that the view spec files' planned test paths are then renamed to it.
2. Should e2e also validate every `/api/` response it observes against `schema.yaml` (in the
   browser guard)? That would cover response drift without waiting for FE-API-013 (same question
   as backend tests, Open question 2).
3. Accessibility (FE-UI-050, 051): accept `axe-core` (via `axe-playwright-python` or an injected
   script) as an e2e test dependency?
4. Coverage thresholds (FE-TEST-012): per-file or global, and from which value?
