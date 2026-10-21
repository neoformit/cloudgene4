# Admin workflows

## Purpose

Lets administrators manage the workflow registry kept in `settings.yaml` `apps[]`: see every
installed entry (including disabled and invalid ones with their errors), install a new one from
a path, re-read one or all from disk, enable or disable, uninstall, and on a per-workflow page
set who may run it (public / groups) and its Nextflow profile, work directory, `nextflow.config`
and `nextflow.env`.

## Scope

Covered:

- `frontend/src/views/admin/AdminWorkflowsView.vue` (route `/admin/workflows`)
- `frontend/src/views/admin/AdminWorkflowSettingsView.vue` (route `/admin/workflows/:id`)
- Workflow functions of `frontend/src/api/admin.js`: `listAdminWorkflows`, `getAdminWorkflow`,
  `updateAdminWorkflow`, `uninstallWorkflow`, `reloadWorkflow`, `installWorkflow`,
  `syncWorkflows`, `getWorkflowNextflow`, `updateWorkflowNextflow`; and `listGroups` from
  `src/api/users.js` for the group choices.

Out of scope:

- Public workflow list and submit form ([home-static-pages.md](home-static-pages.md),
  [workflow-submit-form.md](workflow-submit-form.md)).
- Global Nextflow settings ([admin-settings.md](admin-settings.md)).
- Registry, validation and access rules on the server
  ([../backend/workflows-api.md](../backend/workflows-api.md),
  [../backend/workflow-registry.md](../backend/workflow-registry.md),
  [../backend/access-control.md](../backend/access-control.md)).

## Dependencies

- [../backend/workflows-api.md](../backend/workflows-api.md) — BE-WAPI-008…019.
- [../backend/workflow-definition.md](../backend/workflow-definition.md) — what makes an entry invalid.
- [api-client.md](api-client.md) — `apiErrorMessage`, `apiFieldErrors`.
- Contract operations: `admin_workflows_list`, `admin_workflows_retrieve`,
  `admin_workflows_update`, `admin_workflows_uninstall`, `admin_workflows_reload`,
  `admin_workflows_install`, `admin_workflows_sync`, `admin_workflows_nextflow_retrieve`,
  `admin_workflows_nextflow_update`, `admin_groups_list`.

## Requirements

### Access

- **FE-AWF-001** `/admin/workflows` and `/admin/workflows/:id` MUST be reachable only by a
  signed-in admin (non-admin → `/`, anonymous → `/login?next=…`).

### Workflow list

- **FE-AWF-010** On mount the list MUST call `listAdminWorkflows` and show one row per entry in
  response order (`admin-workflow-row`, `data-workflow-id`, `data-enabled`, `data-valid`,
  `data-effective-status`) with id, name, version, status, access, job count and actions. An
  empty list MUST show "No workflows installed."; a load failure the envelope message (fallback
  "Could not load workflows.").
- **FE-AWF-011** The status badge (`workflow-status`) MUST read "invalid" when `valid` is false
  (and list every `errors` entry under it, `workflow-errors`), otherwise "enabled" or "disabled"
  following `enabled`. So a broken entry is never shown as enabled.
- **FE-AWF-012** The access cell (`workflow-access`) MUST show a "public" badge when `public`,
  one badge per group name, and "admins only" when neither applies.
- **FE-AWF-013** Enable/Disable (`workflow-toggle`) MUST call `updateAdminWorkflow(id,
  {enabled: !enabled})`, then re-load the list and show "`<name>` enabled." / "disabled."
  (`workflows-success`).
- **FE-AWF-014** The per-row reload button (`workflow-reload`) MUST call `reloadWorkflow(id)`
  and re-load the list. If the returned row is valid it MUST show "`<name>` reloaded."; if not,
  it MUST show "`<id>`: `<errors joined by '; '>`" as an error.
- **FE-AWF-015** Reload all (`workflows-sync`) MUST call `syncWorkflows` and show the returned
  rows, then "All workflows re-read from settings.yaml.".
- **FE-AWF-016** Uninstall (`workflow-uninstall`) MUST ask for confirmation ("Remove this
  workflow from settings.yaml? Its files stay on disk and existing jobs are kept.") before
  calling `uninstallWorkflow(id)`, then re-load and show "`<name>` uninstalled.".
- **FE-AWF-017** Install (`workflow-install-open`) MUST show a form with path (required),
  comma-separated groups, Public and Copy checkboxes. Submit MUST call `installWorkflow({path,
  public, groups, copy})` with groups split on `,`, trimmed, empties dropped. On success the
  form MUST reset and close, the list reload, and "`<name> <version>` installed." show. On
  failure the envelope message MUST show and every `fields.path` message MUST be listed under
  the path input (`workflow-install-errors`); the form MUST stay open with its values.
- **FE-AWF-018** While any list action runs, the toggle, reload, uninstall and Reload-all
  buttons MUST be disabled, so two registry writes are never sent at once from this view.

### Workflow settings page

- **FE-AWF-030** On mount the page MUST call `getAdminWorkflow(id)` and
  `getWorkflowNextflow(id)` together, then `listGroups`. A 404 from either MUST show "Workflow
  not found." (`workflow-not-found`); any other failure the envelope message (fallback "Could
  not load the workflow."). A failure of `listGroups` MUST leave only the workflow's own
  groups as choices, without an error.
- **FE-AWF-031** The header MUST show name (`workflow-admin-title`), id, version and the
  resolved `yaml_path`. An invalid workflow MUST show "This workflow is invalid and cannot be
  run:" with every error (`workflow-errors`); warnings, when present, MUST be listed in a
  warning alert. The raw `cloudgene.yaml` MUST be shown as preformatted text
  (`workflow-yaml`).
- **FE-AWF-032** The Access form MUST offer Enabled and Public switches and one checkbox per
  group (`workflow-group-<name>`), the union of all existing groups and the workflow's current
  groups, sorted. A free-text input (`workflow-group-new`, Enter or Add) MUST add a not-yet
  listed name as checked. Save access (`workflow-access-save`) MUST send
  `updateAdminWorkflow(id, {enabled, public, groups})` and re-render from the returned detail
  ("Access settings saved.").
- **FE-AWF-033** The Nextflow form MUST show profile and work directory (empty = global
  default), `nextflow.config` and `nextflow.env` text areas labelled with their file paths, and
  a collapsible table of available `${variables}` (name, scope, description). Save
  (`workflow-nf-save`) MUST send `updateWorkflowNextflow(id, {profile, work_dir, config, env})`
  with the text unchanged (no trimming) and re-render from the response ("Nextflow settings
  saved."). A field error on `profile` MUST show under that input.
- **FE-AWF-034** Reload YAML (`workflow-reload`) MUST call `reloadWorkflow(id)` and re-render
  header, errors, access and YAML from the response; "cloudgene.yaml re-read." MUST show only
  when the result is valid.
- **FE-AWF-035** While any save or reload on the page runs, all three action buttons MUST be
  disabled.

### Rendering safety

- **FE-AWF-040** Workflow names, descriptions, errors, warnings, group names, file paths and
  YAML/config text MUST be rendered as text; neither view MAY use `v-html`. (The YAML may come
  from an app directory not written by the admin.)

## Interfaces

| UI action | API function | operationId | Body |
|-----------|--------------|-------------|------|
| List | `listAdminWorkflows()` | `admin_workflows_list` | — |
| Reload all | `syncWorkflows()` | `admin_workflows_sync` | — |
| Install | `installWorkflow(data)` | `admin_workflows_install` | `InstallRequest` `{path, public, groups, copy}` (`enabled` left to default `true`) |
| Enable/disable, access | `updateAdminWorkflow(id, data)` | `admin_workflows_update` | `PatchedAdminWorkflowPatchRequest` |
| Reload one | `reloadWorkflow(id)` | `admin_workflows_reload` | — |
| Uninstall | `uninstallWorkflow(id)` | `admin_workflows_uninstall` | — |
| Detail | `getAdminWorkflow(id)` | `admin_workflows_retrieve` | — |
| Per-workflow Nextflow | `getWorkflowNextflow(id)` / `updateWorkflowNextflow(id, data)` | `admin_workflows_nextflow_retrieve` / `_update` | `AppNextflowRequest` |
| Group choices | `listGroups()` (`users.js`) | `admin_groups_list` | — |

Shapes `AdminWorkflow`, `AdminWorkflowDetail`, `AppNextflow`: see [api-contract.md](api-contract.md).

## Behaviour

- List actions go through `run(key, fn, msg)`: set `busy = key`, clear alerts, call, re-load
  the list, show the message; `busy` cleared in `finally`.
- The settings page keeps two local copies (`access`, `nf`) seeded from the responses; edits are
  not sent until the matching Save. Saving one form does not save the other.
- A group added by name on the settings page that does not exist yet is created by the server
  on save (BE-WAPI-013 "created if missing").

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-AWF-001 | `frontend/src/test/router.test.js` admin guard (planned); `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` (same guard, users route) | unit, e2e |
| FE-AWF-010, 011, 012 | `e2e/tests/test_admin_workflows.py::test_d4_invalid_entry_listed_with_errors`, `::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e |
| FE-AWF-013 | `e2e/tests/test_admin_workflows.py::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e |
| FE-AWF-014, 015 | `e2e/tests/test_admin_workflows.py::test_admin_list_reload_and_sync` (planned); `frontend/src/test/admin-api.test.js` › admin api request shape (`reloadWorkflow`, `syncWorkflows`) | e2e, unit |
| FE-AWF-016, 017 | `e2e/tests/test_admin_workflows.py::test_d4_install_invalid_then_valid_and_uninstall` | e2e |
| FE-AWF-018, 035 | `frontend/src/test/views/AdminWorkflowsView.test.js` › buttons disabled while busy (planned) | unit |
| FE-AWF-030 | `frontend/src/test/views/AdminWorkflowSettingsView.test.js` › 404 shows not-found (planned) | unit |
| FE-AWF-031, 034 | `e2e/tests/test_admin_workflows.py::test_d4_reload_after_yaml_edit` | e2e |
| FE-AWF-032 | `e2e/tests/test_admin_workflows.py::test_d4_groups_and_public_via_settings_page` | e2e |
| FE-AWF-033 | `e2e/tests/test_admin_workflows.py::test_d4_per_app_nextflow_settings_persist` | e2e |
| FE-AWF-040 | `frontend/src/test/views/admin-no-vhtml.test.js` › workflow errors/YAML render as text (planned) | unit |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| FE-AWF-030 | The route param is read once (`const id = route.params.id`); navigating from one `/admin/workflows/:id` to another reuses the component and keeps showing the first workflow. | `frontend/src/views/admin/AdminWorkflowSettingsView.vue:15` | minor |
| FE-AWF-030 | `getAdminWorkflow` and `getWorkflowNextflow` are awaited with `Promise.all`; if only the Nextflow call fails (non-404), the whole page shows an error and the access form is unavailable. | `frontend/src/views/admin/AdminWorkflowSettingsView.vue:48-57` | minor |
| FE-AWF-032 | The free-text group input is not checked with `validateGroupName`, and the server accepts any name ≤ 150 chars and creates it, so groups that the Groups modal would reject (e.g. with spaces) can be created here. | `frontend/src/views/admin/AdminWorkflowSettingsView.vue:66-70` | minor |
| FE-AWF-033 | Only a `profile` field error is displayed; errors for `work_dir`, `config` or `env` show only in the top alert. | `frontend/src/views/admin/AdminWorkflowSettingsView.vue:178-184` | minor |
| — | `listGroups` result read as `data.results ?? data` although `admin_groups_list` is a plain array (schema drift tolerance). | `frontend/src/views/admin/AdminWorkflowSettingsView.vue:60` | minor |
| FE-AWF-018 | The install button is not disabled by other busy actions, and list actions are not disabled during install (only the install submit checks `busy === 'install'`). | `frontend/src/views/admin/AdminWorkflowsView.vue:115`, `:151` | minor |
| — | No view-level vitest tests for either view. | `frontend/src/test/` | minor |

## Open questions

- Should group names typed on the workflow settings page follow the same rule as group
  creation (frontend and BE-WAPI-013)?
- Install form does not offer `enabled: false`; is installing disabled needed?
