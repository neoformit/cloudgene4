# Workflows API

## Purpose

These endpoints expose installed workflows over HTTP. The public endpoints list the workflows a
caller may run and return each one's run-form schema (inputs, outputs) parsed from its
`cloudgene.yaml`. The admin endpoints manage the registry: install, uninstall, enable/disable,
public flag, groups, reload, sync and per-app Nextflow settings. All admin writes go through
[workflow-registry.md](workflow-registry.md); the views add no rules of their own beyond
access control and request validation.

## Scope

- `workflows/views.py` — `WorkflowViewSet`, `WorkflowCategoryViewSet`.
- `workflows/admin_views.py` — admin workflow views and their serializers.
- `workflows/serializers.py` — public workflow / category serializers.
- `workflows/urls.py` — routes (included at `/` by `cloudgene_django/urls.py`).

Out of scope: request/response field shapes, pagination and the error envelope
([api-contract.md](api-contract.md), quoted from `schema.yaml`); job submission against a
workflow ([job-submission.md](job-submission.md)); the admin dashboard's workflow summary
([admin-api.md](admin-api.md)); how the SPA renders the run form (frontend spec).

## Dependencies

- [api-contract.md](api-contract.md): envelope, pagination, auth schemes, operation catalogue.
- [authentication.md](authentication.md): session/token auth; anonymous → 401 on protected ops.
- [access-control.md](access-control.md): `IsAdmin` / `is_admin`, group membership.
- [workflow-registry.md](workflow-registry.md): `list_apps`, `get_status`, `install`,
  `uninstall`, `update_access`, `reload`, `sync_all`, `get/set_nextflow_settings`,
  `template_utils.VARIABLES`, `RegistryError`.
- [workflow-definition.md](workflow-definition.md): `InputParam.to_dict`, `OutputParam.to_dict`.
- `jobs/workflow_bridge.py`: `get_definition(row)` (parse of `yaml_config`, memoised by content).
- [configuration.md](configuration.md): `server.max_upload_mb`.

Operations covered (from `schema.yaml`): `workflows_list`, `workflows_retrieve`,
`categories_list`, `categories_retrieve`, `admin_workflows_list`, `admin_workflows_install`,
`admin_workflows_sync`, `admin_workflows_retrieve`, `admin_workflows_update`,
`admin_workflows_uninstall`, `admin_workflows_reload`, `admin_workflows_nextflow_retrieve`,
`admin_workflows_nextflow_update`.

## Requirements

Public workflows

- **BE-WAPI-001** `workflows_list` and `workflows_retrieve` MUST be available to anyone
  (anonymous allowed). They MUST include only rows with `status == 'enabled'`, and of those:
  anonymous → `public` rows; authenticated non-admin → `public` rows plus rows whose
  `allowed_groups` include one of the user's groups (no duplicates); admin → every enabled row.
- **BE-WAPI-002** `workflows_retrieve` for an id that is not in the caller's visible set
  (unknown, disabled, uninstalled, invalid, or private to other groups) MUST return 404 with the
  error envelope, for every caller including admins. It MUST NOT reveal whether the id exists.
- **BE-WAPI-003** `workflows_list` MUST be ordered by `name` and paginated as defined in
  [api-contract.md](api-contract.md). The query parameter `category=<name>` MUST restrict the
  list to that category name (exact match).
- **BE-WAPI-004** Each workflow MUST expose exactly the fields of the `Workflow` component:
  `id, name, description, version, website, author, logo, category_name, status, public, inputs,
  outputs, definition_errors, max_upload_mb`. `inputs`/`outputs` MUST be the definition's
  `InputParam.to_dict()` / `OutputParam.to_dict()` lists in YAML order; display inputs are
  included. `author` and `logo` come from the parsed definition. `max_upload_mb` is
  `server.max_upload_mb` (default 1024).
- **BE-WAPI-005** The public API MUST NOT expose `app_path`, `yaml_config`, steps, step
  commands, Nextflow params, `allowed_groups`, per-app Nextflow settings or registry errors.
- **BE-WAPI-006** If a row's stored YAML fails to parse, the workflow MUST still be returned
  with `inputs: []`, `outputs: []`, `author: ''`, `logo: ''` and the parser messages in
  `definition_errors`; for a valid row `definition_errors` MUST be `[]`.
- **BE-WAPI-007** `categories_list` / `categories_retrieve` MUST be available to anyone and
  return `id, name, description, created_at`; unknown id → 404.

Admin workflows

- **BE-WAPI-008** Every `admin_workflows_*` operation MUST require an admin: anonymous → 401,
  authenticated non-admin → 403 with code `permission_denied`, and nothing is changed.
- **BE-WAPI-009** `admin_workflows_list` MUST return one row per `settings.yaml` `apps[]` entry,
  in `apps[]` order, including disabled and invalid entries, without pagination. It MUST NOT
  write the DB or `settings.yaml` when nothing changed on disk (BE-WREG-016).
- **BE-WAPI-010** Each admin row MUST contain `id, name, version, description, category, path,
  yaml_path, index, enabled, effective_status, public, groups, valid, errors, warnings,
  job_count`. `enabled` is the configured `apps[].enabled`; `effective_status` MUST be
  `enabled` only when configured enabled AND valid, else `disabled`. For an invalid entry,
  `name`/`version` fall back to the last cached row (else id / `''`) and
  `description`/`category` are `''`. `job_count` counts all jobs of that workflow id.
- **BE-WAPI-011** `admin_workflows_retrieve`, `admin_workflows_update`,
  `admin_workflows_reload` and `admin_workflows_install` MUST return the detail row
  (BE-WAPI-010 plus `yaml`, the current raw text of the resolved `cloudgene.yaml`, `''` when
  unresolved). Unknown id → 404 `not_found`.
- **BE-WAPI-012** `admin_workflows_install` takes `{path, enabled=true, public=false,
  groups=[], copy=false}` and MUST return 201 with the detail row on success. A missing path is
  400 with `fields.path`. A path that does not resolve or an invalid definition MUST be 400 with
  the registry/definition messages in `fields.path` and nothing written. An id that is already
  installed, or an existing copy target, MUST be 409 `conflict`.
- **BE-WAPI-013** `admin_workflows_update` (PATCH) accepts any subset of `{enabled, public,
  groups}` and MUST change only those keys (BE-WREG-020). Group names longer than 150
  characters MUST be rejected with 400.
- **BE-WAPI-014** `admin_workflows_uninstall` MUST remove the entry and return 204 with no
  body; the app files stay on disk. A subsequent `admin_workflows_retrieve` of that id → 404.
- **BE-WAPI-015** `admin_workflows_reload` MUST re-read the app and return its detail row; an
  app that became invalid MUST come back with `valid: false`, its `errors`, and
  `effective_status: disabled` (status 200, not an error).
- **BE-WAPI-016** `admin_workflows_sync` MUST run a full sync unconditionally and return the
  list rows (as `admin_workflows_list`).
- **BE-WAPI-017** `admin_workflows_nextflow_retrieve` MUST return `{profile, work_dir, config,
  env, config_path, env_path, variables}` where `variables` is
  `template_utils.VARIABLES` as `{name, scope, description}`. Unknown id → 404.
- **BE-WAPI-018** `admin_workflows_nextflow_update` (PUT) MUST treat every field as optional
  and update only the fields sent; `profile` max 255 characters; `config` and `env` are stored
  without trimming whitespace. It returns the same shape as the retrieve. Unknown id → 404 and
  nothing written.
- **BE-WAPI-019** Every error from these operations MUST use the error envelope; registry errors
  map to `{message, code, status}` of the `RegistryError` (`invalid` 400, `not_found` 404 or
  400, `conflict` 409), with `fields.path` only for 400s that carry messages.
- **BE-WAPI-020** (planned) Every operation in this file MUST have a contract test validating
  real success and error responses against its `schema.yaml` component (Article 5.1d).

## Interfaces

| operationId | Method and path | Who | Success |
|---|---|---|---|
| `workflows_list` | GET `/api/workflows/` (`?category=`, `?page=`, `?page_size=`) | anyone | 200 `PaginatedWorkflowList` |
| `workflows_retrieve` | GET `/api/workflows/{id}/` | anyone (visibility filtered) | 200 `Workflow` |
| `categories_list` | GET `/api/categories/` | anyone | 200 `PaginatedWorkflowCategoryList` |
| `categories_retrieve` | GET `/api/categories/{id}/` | anyone | 200 `WorkflowCategory` |
| `admin_workflows_list` | GET `/api/admin/workflows/` | admin | 200 `AdminWorkflow[]` |
| `admin_workflows_install` | POST `/api/admin/workflows/install/` | admin | 201 `AdminWorkflowDetail` |
| `admin_workflows_sync` | POST `/api/admin/workflows/sync/` | admin | 200 `AdminWorkflow[]` |
| `admin_workflows_retrieve` | GET `/api/admin/workflows/{workflow_id}/` | admin | 200 `AdminWorkflowDetail` |
| `admin_workflows_update` | PATCH `/api/admin/workflows/{workflow_id}/` | admin | 200 `AdminWorkflowDetail` |
| `admin_workflows_uninstall` | DELETE `/api/admin/workflows/{workflow_id}/` | admin | 204 |
| `admin_workflows_reload` | POST `/api/admin/workflows/{workflow_id}/reload/` | admin | 200 `AdminWorkflowDetail` |
| `admin_workflows_nextflow_retrieve` | GET `/api/admin/workflows/{workflow_id}/nextflow/` | admin | 200 `AppNextflow` |
| `admin_workflows_nextflow_update` | PUT `/api/admin/workflows/{workflow_id}/nextflow/` | admin | 200 `AppNextflow` |

Component names are as generated in `schema.yaml`; field types and nullability are defined
there and indexed in [api-contract.md](api-contract.md). Note the route order: `install/` and
`sync/` are matched before `{workflow_id}/`, so no app can be addressed by the id `install` or
`sync` through the detail routes.

## Behaviour

- Every `/api/` request first passes `WorkflowSyncMiddleware` (BE-WREG-015), so a hand edit of
  `settings.yaml` or an app's YAML is reflected by the response to the same request.
- Public serialisation parses `yaml_config` once per row per request (memoised by content
  across requests); a valid registry row always parses, so `definition_errors` is non-empty
  only for rows created outside the registry.
- Disabling an app (`admin_workflows_update {enabled:false}`) or breaking its YAML removes it
  from `workflows_list` and makes `workflows_retrieve` 404 for everyone at once; existing jobs
  are not affected.
- `admin_workflows_list` reads statuses from the registry's last sync in this process; it does
  not resync unless something changed on disk. `admin_workflows_sync` always resyncs.
- Admin PATCH on an invalid entry is allowed (access rules can be prepared before the YAML is
  fixed).

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| 001 | `workflows/tests.py::WorkflowAPITest::test_workflow_list_unauthenticated`, `::test_workflow_list_authenticated`, `::test_workflow_list_admin`; `workflows/test_contracts.py::WorkflowListContractTest::test_unauthenticated_user_sees_only_public_workflows`, `::test_authenticated_user_sees_accessible_workflows`, `::test_admin_sees_all_enabled_workflows` | unit |
| 001 | `e2e/tests/test_findings_security.py::test_permission_matrix_public`; `e2e/tests/test_admin_workflows.py::test_w1_workflow_visibility_per_user` | e2e |
| 002 | `workflows/test_contracts.py::WorkflowDetailContractTest::test_non_member_user_gets_404_for_private_workflow`, `::test_unauthenticated_user_gets_404_for_private_workflow`; `admin_panel/tests/test_api.py::AdminWorkflowsApiTest::test_disabled_hidden_from_public_list_but_shown_to_admin` | unit |
| 002 (admin, disabled) | (planned) `WorkflowAPITest::test_disabled_workflow_detail_404_for_admin` | unit |
| 003 | `workflows/tests.py::WorkflowAPITest::test_workflow_list_category_filter` | unit |
| 004 | `workflows/test_contracts.py::WorkflowListContractTest::test_workflow_list_response_structure`; `WorkflowDetailContractTest::test_workflow_detail_response_has_required_fields`, `::test_inputs_contains_only_input_parameters`, `::test_outputs_contains_only_output_parameters`; `workflows/tests.py::WorkflowAPITest::test_workflow_detail` | unit |
| 004 (form) | `e2e/tests/test_run_form.py::test_all_input_types_render_with_defaults` | e2e |
| 005 | (planned) `WorkflowDetailContractTest::test_no_internal_fields_exposed` | unit |
| 006 | (planned) `WorkflowDetailContractTest::test_unparseable_yaml_reports_definition_errors` | unit |
| 007 | `workflows/tests.py::WorkflowAPITest::test_category_list` | unit |
| 008 | `admin_panel/tests/test_api.py::PermissionMatrixTest::test_anonymous_gets_401`, `::test_non_admin_gets_403_and_nothing_changes`; `e2e/tests/test_findings_security.py::test_permission_matrix_admin_endpoints` | unit, e2e |
| 009, 010, 011, 013, 014 | `admin_panel/tests/test_api.py::AdminWorkflowsApiTest::test_install_list_patch_reload_uninstall` | unit |
| 009 | `e2e/tests/test_findings_jobs.py::test_a03_admin_workflow_list_does_not_write_on_every_read`; `e2e/tests/test_admin_workflows.py::test_d4_invalid_entry_listed_with_errors` | e2e |
| 010, 015 | `admin_panel/tests/test_api.py::AdminWorkflowsApiTest::test_broken_app_effective_status_is_disabled_even_when_configured_enabled`; `e2e/tests/test_admin_workflows.py::test_d4_reload_after_yaml_edit` | unit, e2e |
| 012 | `admin_panel/tests/test_api.py::AdminWorkflowsApiTest::test_install_errors`; `e2e/tests/test_admin_workflows.py::test_d4_install_invalid_then_valid_and_uninstall` | unit, e2e |
| 013 | `e2e/tests/test_admin_workflows.py::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_groups_and_public_via_settings_page` | e2e |
| 016 | (planned) `AdminWorkflowsApiTest::test_sync_returns_all_entries` | unit |
| 017, 018 | `admin_panel/tests/test_api.py::AdminWorkflowsApiTest::test_nextflow_per_app`; `e2e/tests/test_admin_workflows.py::test_d4_per_app_nextflow_settings_persist` | unit, e2e |
| 019 | `admin_panel/tests/test_api.py::AdminWorkflowsApiTest::test_install_errors` | unit |
| 020 | (planned) `workflows/test_contracts.py::SchemaContractTest::*` (validate against `schema.yaml`) | contract |

## Known gaps

| Requirement | What the code does | Where | Severity |
|---|---|---|---|
| BE-WAPI-020 | No test validates workflow responses against `schema.yaml`; `workflows/test_contracts.py` checks fields by hand. | `workflows/test_contracts.py` | major |
| BE-WAPI-003 | The `category` query parameter is not declared, so it is missing from `schema.yaml` (`workflows_list` lists only `page`, `page_size`). | `workflows/views.py:42-44`, `schema.yaml` `workflows_list` | minor |
| BE-WAPI-007 | Categories are public and never pruned, so the names of categories used only by private or uninstalled workflows are visible to anonymous callers. | `workflows/views.py:49-52`, `workflows/registry.py:281-282` | minor |
| BE-WAPI-017, -018 | For a duplicate entry (id `<id>~<n>`) both Nextflow operations return 500 (see BE-WREG-024 gap). | `workflows/admin_views.py:136-139`, `workflows/registry.py:510-512` | minor |
| BE-WAPI-019 | A path that does not resolve on install returns code `not_found` with status 400. | `workflows/registry.py:156-157` | minor |
| BE-WAPI-018 | `PUT` behaves as a partial update (all fields optional); the method does not match the semantics. | `workflows/admin_views.py:79-90`, `:237-253` | minor |

## Open questions

- Should `workflows_list` return `inputs`/`outputs` for every item, or only on retrieve? The
  list payload grows with the number and size of run forms.
- `install` accepts any absolute server path from an admin. Should it be restricted to
  directories under `$CLOUDGENE_HOME` (or an allow-list)?
- `status` is always `enabled` in public responses; keep the field or drop it from the public
  serializer?
- `admin_workflows_update` and `admin_workflows_install` accept any group name of at most 150
  characters and create missing groups with `Group.objects.get_or_create`, bypassing the shared
  group-name rule (`^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$`) and the case-insensitive duplicate check
  that `admin_groups_create` applies (BE-ADM-031). Should BE-WAPI-013 require the same rule (400
  `invalid`, `fields.groups`), or should these operations only accept existing groups?
  (`workflows/admin_views.py:59`, `:68`; `workflows/registry.py:395-398`;
  [../frontend/admin-workflows.md](../frontend/admin-workflows.md) FE-AWF-032.)
