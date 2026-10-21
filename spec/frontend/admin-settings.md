# Admin settings, pages and logs

## Purpose

The admin "Settings" area edits the server configuration kept in `settings.yaml` and the
files next to it: general server settings and the navigation bar, mail delivery (with a test
mail), global Nextflow settings and config files, and the HTML pages under
`$CLOUDGENE_HOME/pages/`. It also shows the application log stored in the database. The views
load a section, let the admin edit a local copy, send it on Save, and show server field errors
next to the inputs.

## Scope

Covered:

| Route | View |
|-------|------|
| `/admin/settings/general` | `frontend/src/views/admin/settings/GeneralSettingsView.vue` (server settings + navbar editor) |
| `/admin/settings/nextflow` | `frontend/src/views/admin/settings/NextflowSettingsView.vue` |
| `/admin/settings/mail` | `frontend/src/views/admin/settings/MailSettingsView.vue` |
| `/admin/settings/pages` (and redirect from `/admin/settings/templates`) | `frontend/src/views/admin/settings/PagesView.vue` |
| `/admin/settings/logs` | `frontend/src/views/admin/settings/LogsView.vue` |

And the matching functions of `frontend/src/api/admin.js` (settings, navbar, pages, logs).

Out of scope:

- How the navbar, footer, home and `/pages/<slug>` are rendered publicly
  ([layout-navigation.md](layout-navigation.md), [home-static-pages.md](home-static-pages.md)).
- Per-workflow Nextflow settings ([admin-workflows.md](admin-workflows.md)).
- Server validation and file handling ([../backend/admin-api.md](../backend/admin-api.md),
  [../backend/configuration.md](../backend/configuration.md),
  [../backend/server-pages-mail.md](../backend/server-pages-mail.md),
  [../backend/logging.md](../backend/logging.md)).

## Dependencies

- [../backend/admin-api.md](../backend/admin-api.md) — BE-ADM-050…059 (settings, navbar),
  BE-ADM-060…065 (pages), BE-ADM-070…071 (logs).
- [../backend/logging.md](../backend/logging.md) — BE-LOG-015…019 (log listing, escaping).
- [api-client.md](api-client.md) — `apiErrorMessage`, `apiFieldErrors`.
- [state-stores.md](state-stores.md) — `server.load(true)` after changes that affect the
  public shell (service name, maintenance, navbar, footer).
- Contract operations: `admin_settings_general_retrieve`, `admin_settings_general_update`,
  `admin_settings_navbar_retrieve`, `admin_settings_navbar_update`,
  `admin_settings_mail_retrieve`, `admin_settings_mail_update`, `admin_settings_mail_test`,
  `admin_settings_nextflow_retrieve`, `admin_settings_nextflow_update`, `admin_pages_list`,
  `admin_pages_retrieve`, `admin_pages_update`, `admin_pages_destroy`, `admin_logs_list`.

## Requirements

### Common

- **FE-ASET-001** Every route in this file MUST be reachable only by a signed-in admin
  (non-admin → `/`, anonymous → `/login?next=…`). `/admin/settings/templates` MUST redirect to
  `/admin/settings/pages`.
- **FE-ASET-002** Each view MUST show a spinner while its initial data loads, and on a load
  failure MUST show the envelope message with a view-specific fallback ("Could not load
  settings.", "Could not load Nextflow settings.", "Could not load mail settings.", "Could not
  load pages.", "Could not load logs.") and MUST NOT render the edit form.
- **FE-ASET-003** On a 400 with `fields`, every settings form MUST show the envelope message in
  the top alert and mark each input whose key is in `fields` invalid, with the first message
  under it. A save MUST clear previous success, error and field messages first, and the Save
  button MUST be disabled while the request runs.

### General settings and navbar

- **FE-ASET-010** The General view MUST load `getGeneralSettings` and `getNavbar` together and
  offer: service name, public URL, max running jobs, max queue size, job retention days, max
  upload MB (numeric inputs), maintenance switch and maintenance message.
- **FE-ASET-011** Save (`settings-save`) MUST send the edited object with `updateGeneralSettings`
  (`admin_settings_general_update`), replace the form with the response, show "Settings saved."
  (`settings-success`) and call `server.load(true)` so the brand name and maintenance banner
  update without a reload.
- **FE-ASET-012** The navbar editor MUST list stored items in order (`navbar-row`) with title,
  URL, icon, "Logged-in only", "Admins only", and up/down/remove buttons; Add item MUST append
  an empty item. Save navigation (`navbar-save`) MUST send the full list with `updateNavbar`
  (`{navbar: [...]}`), replace it with the response, show "Navigation saved." and call
  `server.load(true)`.
- **FE-ASET-013** Navbar field errors keyed `navbar[i].title` / `navbar[i].url` MUST be shown
  under the input of row `i`. URL safety (no `javascript:`, `data:`, `//host`) is enforced by
  the server (BE-ADM-057); the editor MUST NOT be the only check.

### Nextflow settings

- **FE-ASET-020** The Nextflow view MUST load `getNextflowSettings` and offer executable
  (`nextflow-binary`), default profile, work directory, and the global `nextflow.config` and
  `nextflow.env` as monospace text areas, plus a collapsible list of global `${variables}`.
- **FE-ASET-021** Save MUST send every field except the read-only `variables` with
  `updateNextflowSettings`, with text-area contents unchanged, replace the form with the
  response and show "Nextflow settings saved." (`nextflow-success`).

### Mail settings

- **FE-ASET-030** The Mail view MUST load `getMailSettings` and offer delivery backend (`smtp`,
  `file`, `console`), the outbox directory only for `file`, host/port/user/password/STARTTLS/SSL
  only for `smtp`, and the sender address for all.
- **FE-ASET-031** The password input MUST start empty and MUST NOT be filled from the server
  (the API never returns it). Its placeholder MUST say "(unchanged)" when `password_set` is true
  and "not set" otherwise. Save MUST include `password` only when the input is non-empty, and
  `clear_password: true` only when "Remove stored password" (`mail-clear-password`, shown only
  when `password_set`) is checked. `password_set` MUST NOT be sent. After a successful save both
  inputs MUST reset and "Mail settings saved." MUST show.
- **FE-ASET-032** A rejected STARTTLS + SSL combination (`fields.use_ssl`) MUST be shown under
  the SSL checkbox.
- **FE-ASET-033** "Send test e-mail" (`mail-test-send`) MUST call `sendTestMail(to)` with the
  optional recipient (omitted when empty, so the server uses the admin's address) and show the
  server `message` on success (`mail-success`). A failure (400 `fields.to`, 502 `mail_failed`)
  MUST show the envelope message. The form MUST state that the saved settings are used.

### Pages

- **FE-ASET-040** The Pages view MUST list `listPages` results by slug (`page-item`,
  `data-slug`), marking non-deletable pages "required", and show "Select a page to edit." until
  one is opened.
- **FE-ASET-041** Opening a page MUST call `getPage(slug)` and hide the editor until that
  response arrives. A response for a page that is no longer the latest one opened MUST be
  dropped, so Save always targets the page whose text is shown.
- **FE-ASET-042** "New page" MUST lower-case and trim the slug and check it against
  `^[a-z0-9][a-z0-9_-]{0,63}$` before any request; an invalid slug MUST show 'Use lower-case
  letters, digits, "-" and "_" (max 64).' and open no editor. An existing slug MUST open that
  page; a new one MUST open an unsaved editor (badge "new") pre-filled with a heading.
- **FE-ASET-043** Save (`page-save`) MUST send `savePage(slug, html)` with the text unchanged,
  show `Page "<slug>" saved.`, reload the list, and call `server.load(true)` when the slug is
  `footer`. A `fields.slug` error MUST be shown under the new-slug input.
- **FE-ASET-044** Delete (`page-delete`) MUST be offered only for saved pages with
  `deletable: true` and MUST ask for confirmation before `deletePage(slug)`; success MUST close
  the editor, show `Page "<slug>" deleted.` and reload the list.
- **FE-ASET-045** "View" MUST link to `/` for `home`, `/pages/<slug>` for other saved pages,
  and be absent for `footer` and unsaved pages. Slugs in API URLs MUST be URL-encoded by the API
  module.
- **FE-ASET-046** The Preview tab MAY render the page HTML with `v-html`, because page HTML is
  trusted admin-authored content that the public site renders the same way (BE-ADM-065). This
  MUST be the only `v-html` in the settings views; slugs, messages and all other strings MUST be
  rendered as text.

### Logs

- **FE-ASET-050** The Logs view MUST call `listLogs({min_level, component, search, page,
  page_size: 50})` (`admin_logs_list`), omitting empty filters, and show rows newest first as
  returned: local time, level (coloured by severity), component, username (blank when null) and
  message (`log-row`, `data-level`, `data-component`, `log-message`). An empty result MUST show
  "No log entries found.".
- **FE-ASET-051** Changing the level filter ("`<level>` and above") MUST re-fetch page 1 at
  once; component and search MUST apply on the filter button or Enter. Paging MUST keep the
  filters. A 400 for a bad filter MUST show the envelope message.
- **FE-ASET-052** Clicking a row with non-empty `metadata` MUST toggle a pretty-printed JSON
  block for it below the row.
- **FE-ASET-053** Log `message`, `component`, `username` and `metadata` MUST be rendered only by
  text interpolation (escaped), never with `v-html`, because they can contain user-supplied text
  (BE-LOG-019). A message such as `<img src=x onerror=alert(1)>` MUST appear literally.

## Interfaces

| UI action | API function (`src/api/admin.js`) | operationId |
|-----------|-----------------------------------|-------------|
| Load / save general | `getGeneralSettings()` / `updateGeneralSettings(data)` | `admin_settings_general_retrieve` / `_update` |
| Load / save navbar | `getNavbar()` / `updateNavbar(navbar)` | `admin_settings_navbar_retrieve` / `_update` |
| Load / save Nextflow | `getNextflowSettings()` / `updateNextflowSettings(data)` | `admin_settings_nextflow_retrieve` / `_update` |
| Load / save mail | `getMailSettings()` / `updateMailSettings(data)` | `admin_settings_mail_retrieve` / `_update` |
| Test mail | `sendTestMail(to?)` | `admin_settings_mail_test` |
| Pages | `listPages()`, `getPage(slug)`, `savePage(slug, html)`, `deletePage(slug)` | `admin_pages_list`, `_retrieve`, `_update`, `_destroy` |
| Logs | `listLogs(params)` | `admin_logs_list` |

All settings updates use PUT with a partial or full object; shapes (`GeneralSettings`,
`MailSettings`, `NextflowSettings`, `Navbar`, `Page`, `PageSummary`, `SystemLog`) are in
[api-contract.md](api-contract.md).

## Behaviour

- Pages open-race guard: `openToken` is incremented by every `open()` and `startNew()`; a
  `getPage` response whose token is not current is ignored, and `current` is cleared before the
  request so no edit or Save can apply to the outgoing page (`PagesView.vue:26`, `:40-59`).
- Mail form fields for other backends stay in the object and are sent unchanged; switching the
  backend does not clear them.
- Navbar rows are keyed by index; moving swaps objects in the array, and field errors refer to
  the order last saved.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-ASET-001 | `frontend/src/test/router.test.js` admin guard and templates redirect (planned) | unit |
| FE-ASET-002 | `frontend/src/test/views/AdminSettingsViews.test.js` › load failure hides form (planned) | unit |
| FE-ASET-003, 010, 011 | `e2e/tests/test_admin_settings.py::test_d5_general_settings_round_trip`, `::test_d5_general_settings_validation_error` | e2e |
| FE-ASET-012, 013 | `e2e/tests/test_admin_settings.py::test_d6_navbar_editor`; `e2e/tests/test_findings_admin.py::test_c05_navbar_url_is_validated` (API); `frontend/src/test/admin-api.test.js` › request shape (`updateNavbar`) | e2e, unit |
| FE-ASET-020, 021 | `e2e/tests/test_admin_settings.py::test_d5_nextflow_settings_round_trip` | e2e |
| FE-ASET-030, 031 | `e2e/tests/test_admin_settings.py::test_d5_mail_password_write_only` | e2e |
| FE-ASET-032 | `e2e/tests/test_findings_admin.py::test_c01_mail_tls_and_ssl_cannot_both_be_enabled` (API only); UI field error (planned, `e2e/tests/test_admin_settings.py::test_d5_mail_tls_ssl_field_error`) | e2e |
| FE-ASET-033 | `e2e/tests/test_admin_settings.py::test_d5_mail_test_lands_in_outbox`; `frontend/src/test/admin-api.test.js` › request shape (`sendTestMail` with/without `to`) | e2e, unit |
| FE-ASET-040, 043, 044, 045 | `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer`, `::test_d6_create_view_delete_page` | e2e |
| FE-ASET-041 | `frontend/src/test/views/PagesView.test.js` › late getPage response is dropped (planned) | unit |
| FE-ASET-042 | `e2e/tests/test_admin_settings.py::test_d6_traversal_slugs_rejected`; `frontend/src/test/admin-api.test.js` › request shape (`getPage('../x')` encoded) | e2e, unit |
| FE-ASET-046 | `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer` (preview renders HTML) | e2e |
| FE-ASET-050, 051 | `e2e/tests/test_admin_dashboard.py::test_d7_logs_show_admin_actions`; `frontend/src/test/admin-api.test.js` › sends log filters | e2e, unit |
| FE-ASET-052 | `frontend/src/test/views/LogsView.test.js` › row click toggles metadata (planned) | unit |
| FE-ASET-053 | `frontend/src/test/views/LogsView.test.js` › HTML in message is shown as text (planned; also covers BE-LOG-019) | unit |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| FE-ASET-003 | Field errors are shown only for some inputs: General has none for `maintenance_message`; Nextflow only for `binary` (not `profile`, `work_dir`, `config`, `env`); Mail none for `user`, `file_path`, `backend`, and the test-mail `to` input gets `is-invalid` with no message element. | `GeneralSettingsView.vue:129-132`; `NextflowSettingsView.vue:56-66`; `MailSettingsView.vue:84-87`, `:149` | minor |
| FE-ASET-011 | General Save PUTs the whole object loaded at mount, including `maintenance`/`maintenance_message`; a maintenance change made meanwhile on the dashboard (or by another admin) is silently reverted. | `frontend/src/views/admin/settings/GeneralSettingsView.vue:38` | minor |
| FE-ASET-050 | The component filter is a free-text input, but the server matches `component` exactly; partial input finds nothing. There is no choice list of known components. The exact `level` filter is not offered. | `frontend/src/views/admin/settings/LogsView.vue:54` | minor |
| FE-ASET-052 | `Object.keys(log.metadata || {})` treats a non-object `metadata` (string/array, allowed by the untyped schema field) as having keys and prints it; harmless but untyped. | `frontend/src/views/admin/settings/LogsView.vue:79` | minor |
| FE-ASET-053 | Escaping is correct today (interpolation only) but has no test (BE-LOG-019 handoff). | `frontend/src/views/admin/settings/LogsView.vue:73-80` | minor |
| FE-ASET-041 | Opening another page, or the same page again, discards unsaved edits without a prompt. | `frontend/src/views/admin/settings/PagesView.vue:40-46` | minor |
| FE-ASET-043 | Saving `home` does not refresh anything shared; acceptable only because the home view fetches on navigation. `slugError` is not cleared when an existing page is opened. | `frontend/src/views/admin/settings/PagesView.vue:88`, `:72-73` | minor |
| — | No view-level vitest tests for any settings view. | `frontend/src/test/` | minor |

## Open questions

- Maintenance can be toggled in two places (dashboard and General settings). Keep both, or make
  the dashboard the only control and drop the fields from the General form?
- Should the Logs view offer a fixed component list (from the backend's component table in
  [../backend/logging.md](../backend/logging.md)) instead of free text?
