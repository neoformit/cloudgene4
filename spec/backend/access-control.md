# Access control

## Purpose

Decides what an identified caller may do. Cloudgene has three roles — anonymous, user and
administrator — plus Django groups that grant access to workflows. This file defines the single
admin rule, the DRF permission classes, workflow visibility by `public` flag and group, owner-only
job access, and exactly what a caller without access receives (401, 403 or 404). How the caller
is identified is in [authentication.md](authentication.md).

## Scope

Covered:

- `core/permissions.py` — `ADMIN_GROUP`, `is_admin`, `IsAdmin`, `IsAdminOrReadOnly`.
- `accounts/models.py` — `User.is_admin_user`, `User.make_admin`, `User.has_group`.
- `cloudgene_django/settings.py` — `DEFAULT_PERMISSION_CLASSES`.
- `workflows/views.py` — `WorkflowViewSet.get_queryset` (visibility).
- `workflows/models.py` — `Workflow.public`, `Workflow.allowed_groups`, `Workflow.can_access`.
- `jobs/views.py` — `JobViewSet.get_queryset` (owner-or-admin), `AdminJobViewSet`.
- `jobs/submission.py:291-313` — `resolve_workflow` access check, maintenance bypass for admins.
- `jobs/workflow_bridge.py` — `can_access`.
- The permission class of every `/api/` view (inventory below).

Out of scope:

- Admin user/group endpoints' request and response rules (`admin_users_*`, `admin_groups_*`):
  [admin-api.md](admin-api.md). This file only defines what "admin" means and who may call them.
- How `settings.yaml` `apps[].public` / `apps[].groups` are stored and synced to the
  `Workflow` rows, and pruning of deleted groups: [workflow-registry.md](workflow-registry.md).
- Navbar item filtering (`admin_only`, `auth_only`): [server-pages-mail.md](server-pages-mail.md).
- Who may log in to `/django-admin/`: Django's own rule (`is_staff`, active), lockout in
  [authentication.md](authentication.md).
- Frontend route guards: `spec/frontend/`.

## Dependencies

- [authentication.md](authentication.md) — 401 for unauthenticated callers, token vs session.
- [api-contract.md](api-contract.md) — error envelope and codes `not_authenticated`,
  `permission_denied`, `not_found`.
- [workflow-registry.md](workflow-registry.md) — source of `public`, `allowed_groups`, `status`.
- [jobs-api.md](jobs-api.md), [workflows-api.md](workflows-api.md), [admin-api.md](admin-api.md) —
  the endpoints whose access is defined here.

## Requirements

**Roles**

- **BE-ACL-001** — A user MUST be treated as an administrator if and only if they are
  authenticated and at least one holds: `is_superuser`, `is_staff`, or membership of the group
  named `admin`. `core.permissions.is_admin` MUST be the only implementation; other code
  (`User.is_admin_user`, `UserSerializer.is_admin`, workflow access, dashboard counts) MUST give
  the same answer.
- **BE-ACL-002** — Granting admin through the API (`is_admin: true`) MUST add the user to group
  `admin` and set `is_staff`; revoking MUST remove both. A superuser MUST stay an administrator
  (revoking → 400 `fields.is_admin`). An administrator MUST NOT revoke their own admin rights or
  deactivate themselves (400). The `admin` group MUST NOT be changed through a user's `groups`
  list and MUST NOT be deletable (400 `protected_group`).
- **BE-ACL-003** — Every `/api/` view MUST declare its permission explicitly; the default when one
  does not is `IsAuthenticated`.

**What non-authorised callers receive**

- **BE-ACL-004** — An anonymous caller on an endpoint that needs a user or admin MUST receive 401,
  code `not_authenticated` (never 403).
- **BE-ACL-005** — An authenticated non-admin on an admin endpoint (`/api/admin/**`) MUST receive
  403, code `permission_denied`, message `Administrator privileges are required.`, and a body
  with no data other than `error`.
- **BE-ACL-006** — A caller who may not see a specific object (another user's job, a workflow
  outside their access) MUST receive 404, code `not_found` — never 403 — so object existence is
  not disclosed.

**Workflows**

- **BE-ACL-007** — `workflows_list` and `workflows_retrieve` MUST only show workflows with
  `status = enabled`, and among those: anonymous callers see `public` workflows; users see
  `public` workflows plus those whose `allowed_groups` include one of their groups; admins see
  all enabled workflows. Anything else MUST be absent from the list and 404 on retrieve, for
  every role.
- **BE-ACL-008** — A non-public workflow with no `allowed_groups` MUST be visible to admins only.
- **BE-ACL-009** — Job submission (`jobs_create`) MUST require an authenticated user (401
  otherwise) and MUST give 404 `not_found` with `fields.workflow` when the workflow does not exist
  or is not accessible under BE-ACL-007. An accessible but disabled workflow MUST give 409
  `workflow_disabled`.
- **BE-ACL-010** — While `server.maintenance` is on, submission by a non-admin MUST give 503, code
  `maintenance`; admins MUST still be able to submit.
- **BE-ACL-011** — Access is checked when a job is submitted only. Losing access to a workflow
  later MUST NOT hide or affect jobs already submitted with it.

**Jobs**

- **BE-ACL-012** — `jobs_list` MUST return only the caller's own, not-deleted jobs — for
  admins too.
- **BE-ACL-013** — `jobs_retrieve`, `jobs_status_retrieve`, `jobs_log_retrieve`,
  `jobs_outputs_retrieve`, `jobs_cancel_create` and `jobs_destroy` MUST be allowed to the job's
  owner and to admins. Any other user MUST get 404 `not_found`; anonymous callers 401. An
  output id that does not belong to the job in the URL MUST give 404.
- **BE-ACL-014** — A cancel by someone other than the owner (an admin) MUST be recorded as an
  admin cancellation ([job-queue-worker.md](job-queue-worker.md)).
- **BE-ACL-015** — `admin_jobs_list`, `admin_jobs_cancel_create`, `admin_jobs_restart_create`
  MUST be admin-only (BE-ACL-004/005).

**Accounts**

- **BE-ACL-016** — Self-service account endpoints (`me_*`) MUST act only on the caller; no
  endpoint outside `/api/admin/` may read or change another user. Unscoped paths `/api/users/`
  and `/api/groups/` MUST answer 404.

## Interfaces

Permission classes (`core/permissions.py`):

| Name | Allows | Denied caller gets |
|---|---|---|
| `IsAdmin` | `is_admin(user)` | 401 anonymous, 403 user |
| `IsAdminOrReadOnly` | safe methods: anyone; others: admins | as above (currently unused) |
| DRF `IsAuthenticated` (default) | any authenticated user | 401 |
| DRF `AllowAny` | everyone | — |

Endpoint inventory by required role (operationIds from `schema.yaml`):

| Role | Operations |
|---|---|
| anyone | `auth_login_create`, `auth_logout_create`, `auth_me_retrieve`, `auth_register_create`, `auth_activate_create`, `auth_password_reset_create`, `auth_password_reset_confirm`, `workflows_list`, `workflows_retrieve`, `categories_list`, `categories_retrieve`, `server_info`, `pages_retrieve`, `health` |
| user | `me_retrieve`, `me_partial_update`, `me_destroy`, `me_token_create`, `me_token_destroy`, `jobs_list`, `jobs_create` |
| owner or admin | `jobs_retrieve`, `jobs_status_retrieve`, `jobs_log_retrieve`, `jobs_outputs_retrieve`, `jobs_cancel_create`, `jobs_destroy` |
| admin | every operation under `/api/admin/` (`admin_*`) |

Workflow access fields (`Workflow`): `status` (`enabled` / `disabled` / …), `public` (bool),
`allowed_groups` (M2M to `auth.Group`). Their source of truth is `settings.yaml` `apps[]`
([workflow-registry.md](workflow-registry.md)).

Groups are plain Django `auth.Group` rows. Names are unique ignoring case at creation
([accounts.md](accounts.md) BE-ACCT-002 for the name rule); they carry no Django model
permissions in Cloudgene — membership is the only thing that matters.

## Behaviour

Access decision order for an `/api/` request:

1. Authentication ([authentication.md](authentication.md)); a bad token is 401 before any
   permission check.
2. View permission class: `AllowAny`, `IsAuthenticated` or `IsAdmin` → 401/403.
3. Object scoping in the queryset: jobs filtered to `user = caller` unless the caller is admin
   (detail actions) — list always filtered; workflows filtered by BE-ACL-007. Objects outside the
   queryset raise `Http404` → 404 `not_found`.
4. Action rules (e.g. submission maintenance, disabled workflow, cancel/delete state rules in
   [jobs-api.md](jobs-api.md)).

Workflow visibility has two implementations that MUST agree: the queryset filter in
`WorkflowViewSet.get_queryset` (lists and retrieve) and `Workflow.can_access` (submission). The
latter returns `False` for anonymous callers, which is consistent because submission needs a
user anyway.

Admin through Django admin: `create_admin` creates a superuser with `is_staff` in group `admin`.
A user who is admin only through group membership (no `is_staff`) is a Cloudgene admin but cannot
enter `/django-admin/`; the API's `is_admin: true` sets `is_staff`, so this only happens when
membership is changed some other way.

Deleting a group removes it from every workflow's `groups` list (signal in `workflows/apps.py`,
see [workflow-registry.md](workflow-registry.md)); its members lose access to workflows that only
that group granted.

## Acceptance tests

| Requirement | Tests |
|---|---|
| BE-ACL-001 | unit `core/tests/test_api.py::IsAdminTest::test_admin_definition`; unit `core/tests/test_api.py::AdminPermissionTest::test_admin_endpoints_use_is_admin`; unit `accounts/tests.py::PermissionMatrixTest::test_admin_via_group_only`; unit `accounts/tests.py::UserModelTest::test_admin_helpers` |
| BE-ACL-002 | unit `accounts/tests.py::AdminUsersTest::test_admin_group_only_via_is_admin`, `::test_self_protection`, `::test_superuser_stays_admin`; unit `accounts/tests.py::AdminGroupsTest::test_admin_group_protected`; e2e `e2e/tests/test_accounts.py::test_d3_admin_users` |
| BE-ACL-003 | (planned) unit `core/tests/test_schema.py::PermissionInventoryTest::test_every_api_view_declares_permission_classes` |
| BE-ACL-004 | unit `accounts/tests.py::PermissionMatrixTest::test_matrix`; unit `core/tests/test_api.py::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope`; e2e `e2e/tests/test_findings_security.py::test_permission_matrix_admin_endpoints`, `::test_permission_matrix_requires_authentication` |
| BE-ACL-005 | unit `accounts/tests.py::PermissionMatrixTest::test_non_admin_gets_no_data`; contract `accounts/test_contracts.py::GroupContractTest::test_non_admin_cannot_create_group`, `UserUpdateContractTest::test_user_cannot_update_another_users_profile`; e2e `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api`; e2e `e2e/tests/test_deep_links.py::test_admin_route_forbidden_for_regular_user` |
| BE-ACL-006 | unit `jobs/tests/test_api.py::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`; contract `workflows/test_contracts.py::WorkflowDetailContractTest::test_non_member_user_gets_404_for_private_workflow`; e2e `e2e/tests/test_findings_security.py::test_permission_matrix_object_access` |
| BE-ACL-007 | contract `workflows/test_contracts.py::WorkflowListContractTest::test_unauthenticated_user_sees_only_public_workflows`, `::test_authenticated_user_sees_accessible_workflows`, `::test_admin_sees_all_enabled_workflows`; contract `workflows/test_contracts.py::WorkflowDetailContractTest::test_unauthenticated_user_gets_404_for_private_workflow`; unit `workflows/tests.py::WorkflowAPITest::test_workflow_list_unauthenticated`, `::test_workflow_list_authenticated`, `::test_workflow_list_admin`; e2e `e2e/tests/test_admin_workflows.py::test_w1_workflow_visibility_per_user`, `::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_groups_and_public_via_settings_page` |
| BE-ACL-008 | unit `workflows/tests.py::WorkflowTest::test_can_access_group_restricted_workflow`, `::test_admin_access`; list case (planned) `workflows/test_contracts.py::WorkflowListContractTest::test_private_workflow_without_groups_admin_only` |
| BE-ACL-009 | unit `jobs/tests/test_api.py::SubmissionTest::test_workflow_access_and_disabled`; unit `workflows/tests.py::WorkflowTest::test_unauthenticated_access`, `::test_can_access_public_workflow` |
| BE-ACL-010 | unit `jobs/tests/test_api.py::SubmissionTest::test_maintenance_blocks_users_not_admins`; e2e `e2e/tests/test_queue.py::test_maintenance_blocks_users_not_admins` |
| BE-ACL-011 | (planned) unit `jobs/tests/test_api.py::JobLifecycleApiTest::test_job_visible_after_workflow_access_revoked` |
| BE-ACL-012 | unit `jobs/tests/test_api.py::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access` (admin list = own jobs) |
| BE-ACL-013 | unit `jobs/tests/test_api.py::JobLifecycleApiTest::test_other_users_get_404_admin_gets_access`, `::test_output_traversal_and_foreign_ids`; e2e `e2e/tests/test_access_jobs.py::test_other_user_cannot_see_job_outputs_or_log`, `::test_anonymous_cannot_download`, `::test_owner_and_admin_can_download`; e2e `e2e/tests/test_findings_security.py::test_foreign_output_id_under_own_job` |
| BE-ACL-014 | (planned) unit `jobs/tests/test_api.py::JobLifecycleApiTest::test_admin_cancel_of_foreign_job_is_marked_admin` |
| BE-ACL-015 | unit `jobs/tests/test_api.py::AdminJobsApiTest::test_admin_list_filters_and_permissions`; e2e `e2e/tests/test_findings_security.py::test_permission_matrix_admin_endpoints` |
| BE-ACL-016 | unit `accounts/tests.py::PermissionMatrixTest::test_matrix` (`/api/users/`, `/api/groups/` → 404); e2e `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` |

## Known gaps

| Req | What the code does | Where | Severity |
|---|---|---|---|
| BE-ACL-001 | `Workflow.can_access` checks `user.is_superuser` and then `user.is_admin_user()`; the result is right but the rule is restated, and the workflow list filter in `WorkflowViewSet` is a third implementation of the same visibility rule. Drift between them would make a workflow listed but not submittable, or the reverse. | `workflows/models.py:137-150`; `workflows/views.py:30-46` | minor |
| BE-ACL-003 | `IsAdminOrReadOnly` exists but no view uses it. | `core/permissions.py:27-35` | minor |

## Open questions

- Admins can delete any user's job through `jobs_destroy` on `/api/jobs/{id}/` (owner-or-admin
  scoping), but there is no `admin_jobs_destroy`. Is admin deletion through the user endpoint
  intended, or should it be owner-only?
- Should an admin's own `jobs_list` offer a way to include other users' jobs, or is
  `admin_jobs_list` the only cross-user view (current behaviour)?
- `is_staff` alone makes a user a Cloudgene admin. Should staff status and the `admin` group stay
  equivalent, or should one of them be dropped?
