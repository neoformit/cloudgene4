# Common components and UI conventions

## Purpose

A small set of shared components gives every view the same way to show errors, loading,
confirmations for destructive actions and page navigation. This file specifies those components,
the initials avatar helper, and the conventions every view follows: how API errors are shown, when
a confirmation is required, how HTML may reach a dialog, and the accessibility baseline.

## Scope

| Source | What |
|--------|------|
| `frontend/src/components/common/AlertMessage.vue` | Inline alert for one message |
| `frontend/src/components/common/ConfirmDialog.vue` | Modal confirmation dialog |
| `frontend/src/components/common/LoadingSpinner.vue` | Centred loading indicator |
| `frontend/src/components/common/Pagination.vue` | Page-number pagination control |
| `frontend/src/utils/avatar.js` | `initials(user)`, `avatarHue(user)` |
| `frontend/src/main.js` (CSS/JS imports only) | Bootstrap 5 CSS + bundle JS, Font Awesome |

Out of scope (linked instead):

- `apiErrorMessage()` / `apiFieldErrors()` and the error envelope parsing: [api-client.md](api-client.md).
- Per-view use of these components (which actions, which messages): the view's own spec file.
- Client-side form validation rules: [auth-views.md](auth-views.md), [workflow-submit-form.md](workflow-submit-form.md).
- Build, styling files and dependency list: [overview.md](overview.md).

## Dependencies

- [api-client.md](api-client.md): error helpers (Article 5.2).
- [../backend/api-contract.md](../backend/api-contract.md): error envelope; pagination shape (`count`, `next`, `previous`, `results`; `page`, `page_size` ≤ 200).

## Requirements

### Error display

- **FE-UI-001** A view MUST turn an API error into user text only through `apiErrorMessage()` (or `apiFieldErrors()` for per-field messages) from `src/api/client.js`, never by reading `err.response.data` directly.
- **FE-UI-002** `AlertMessage` MUST render nothing when `message` is empty, and otherwise a Bootstrap `alert alert-<type>` (default `danger`) with `role="alert"` containing the message as text (interpolated, never HTML).
- **FE-UI-003** A view-level load failure MUST show an error alert instead of the content and MUST NOT leave the spinner running.

### Loading

- **FE-UI-010** `LoadingSpinner` MUST render a centred Bootstrap spinner with `role="status"` and the visually-hidden text `Loading...`.
- **FE-UI-011** A view MUST show `LoadingSpinner` (or a disabled button with an inline spinner, for an action) while a request it depends on is pending.

### Confirmations for destructive actions

- **FE-UI-020** Every action that deletes data, cancels or restarts a job, uninstalls a workflow or deletes a page MUST ask for confirmation first, naming the object and, for deletions, stating that the action cannot be undone. The request MUST be sent only after the user confirms. Cancelling the dialog MUST send nothing.
- **FE-UI-021** `ConfirmDialog` MUST show `title`, `message`, a `Cancel` button and a confirm button (`confirmText`, class `confirmClass`, default `btn-danger`), and emit `confirm` or `cancel`. The header close button MUST emit `cancel`.
- **FE-UI-022** While `loading` is true, both buttons MUST be disabled and the confirm button MUST show a spinner and `Please wait...`, so a second click cannot send a second request.
- **FE-UI-023** `ConfirmDialog.message` is rendered as HTML. A caller that includes any server- or user-supplied value (job name, username, workflow name) in `message` MUST HTML-escape it first; a caller that cannot escape MUST render its own dialog with text interpolation instead.
- **FE-UI-024** (planned) `ConfirmDialog` SHOULD behave as an accessible modal: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at the title, focus moved into the dialog on open, `Escape` emitting `cancel`, and focus returned to the triggering control on close. The close button MUST have an accessible name (`aria-label="Close"`).

### Pagination

- **FE-UI-030** `Pagination` MUST render nothing when `totalPages ≤ 1`.
- **FE-UI-031** Otherwise it MUST render `← Previous`, one button per page, and `Next →` inside `<nav aria-label="Pagination">`, marking the current page active, and emit `change(page)` with the chosen page number.
- **FE-UI-032** `Previous` MUST NOT emit on page 1 and `Next` MUST NOT emit on the last page, whether activated by mouse or keyboard. Emitted pages MUST be within `1…totalPages`.
- **FE-UI-033** (planned) The current page button SHOULD carry `aria-current="page"`. With many pages the control SHOULD show a window of pages (e.g. first, last, ±2 around current) rather than every number.
- **FE-UI-034** Callers MUST derive `totalPages` from the API's `count` and the page size they requested, and MUST request the page passed in `change`.

### Avatar

- **FE-UI-040** User avatars MUST be generated locally from initials; the SPA MUST NOT request any third-party avatar service (no e-mail or hash leaves the browser).
- **FE-UI-041** `initials(user)` MUST return the upper-cased first letters of the first and last words of `full_name` when it has two or more words, the first two letters of a one-word `full_name`, else the first two letters of `username`, else `?`.
- **FE-UI-042** `avatarHue(user)` MUST return an integer in `0…359` that depends only on `username` (same user → same hue). The avatar text MUST be rendered by interpolation.

### Accessibility and Bootstrap conventions

- **FE-UI-050** Every form control MUST have an associated `<label>` or an `aria-label`. Icon-only buttons MUST have an `aria-label` (and MAY have a `title`).
- **FE-UI-051** Status that appears without user action (banners, async progress) MUST use `role="status"`; errors MUST use `role="alert"` (via `AlertMessage` or equivalent).
- **FE-UI-052** UI MUST use Bootstrap 5 classes and components (grid, cards, alerts, badges, modals, dropdowns, collapse) with Bootstrap's bundled JS for dropdown/collapse; no other UI framework is used. Icons MUST be Font Awesome (`fas fa-*`) and decorative icons SHOULD carry `aria-hidden="true"`.
- **FE-UI-053** Values from the API MUST be rendered with text interpolation. `v-html` is allowed only for the trusted admin/workflow-author HTML surfaces listed in [home-static-pages.md](home-static-pages.md), [layout-navigation.md](layout-navigation.md) FE-NAV-030, [workflow-submit-form.md](workflow-submit-form.md), and `ConfirmDialog.message` under FE-UI-023.
- **FE-UI-054** Interactive elements MUST carry stable `data-testid` attributes used by the e2e suite; renaming one is a test-visible change.

## Interfaces

| Component | Props | Events | Test ids |
|-----------|-------|--------|----------|
| `AlertMessage` | `type` (`'danger'`), `message` (`''`) | — | caller supplies `data-testid` (falls through to the root) |
| `ConfirmDialog` | `title` (`'Confirm'`), `message` (required, HTML), `confirmText` (`'Confirm'`), `confirmClass` (`'btn-danger'`), `loading` (`false`) | `confirm`, `cancel` | `confirm-dialog`, `confirm-ok`, `confirm-cancel` |
| `LoadingSpinner` | — | — | caller supplies |
| `Pagination` | `currentPage` (required), `totalPages` (required) | `change(page)` | — |

```js
// src/utils/avatar.js
initials({ full_name, username }) -> string   // 1–2 upper-case chars, or '?'
avatarHue({ username }) -> number             // 0–359, stable per username
```

Current users of the components:

| Component | Used by |
|-----------|---------|
| `ConfirmDialog` | `JobListView`, `JobDetailView`, `AdminJobsView`, `AdminWorkflowsView`, `PagesView` |
| Own inline confirmation (text-interpolated) | `AdminUsersView` (delete user), `GroupManagementModal` (delete group) |
| `Pagination` | `JobListView`, `AdminJobsView`, `AdminUsersView`, `LogsView` |
| `initials` / `avatarHue` | `AdminUsersView`, `GroupMembersModal` |

## Behaviour

**Error flow.** View catches the rejected API call → `error = apiErrorMessage(err, '<fallback>')`
→ `<AlertMessage :message="error" />`. Network failures yield `Cannot reach the server. Check your
connection.` ([api-client.md](api-client.md)).

**Confirmation flow.** User clicks a destructive control → view stores the pending action and
shows the dialog → `confirm` sets `loading`, calls the API, closes the dialog on success or shows
the error via `AlertMessage` → `cancel` clears the pending action.

**Escaping in dialog messages.** `JobListView.vue:26` and `JobDetailView.vue:33` each define a
local `escapeHtml` and wrap the job name in `<b>…</b>`. Fixed-text messages
(`AdminWorkflowsView.vue:227`, `PagesView.vue:200`, `AdminJobsView.vue:174`) contain no
interpolated data.

**Pagination events.** `Pagination` delegates disabling of Previous/Next to Bootstrap's
`.page-item.disabled` style (which blocks pointer events only).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-UI-001 | `frontend/src/test/client.test.js` › apiErrorMessage › reads the SPEC §3.5 envelope, › falls back for legacy shapes, server errors and network errors; lint/grep rule that views do not read `response.data` (planned) | unit |
| FE-UI-002 | `AlertMessage` renders nothing for empty message, text for HTML input (planned, `frontend/src/test/common-components.test.js` › AlertMessage) | unit |
| FE-UI-003, 011 | `e2e/tests/test_smoke.py::test_unknown_page_shows_not_found` (error replaces spinner); per-view load-failure tests (planned) | e2e |
| FE-UI-010 | `common-components.test.js` › LoadingSpinner › has role status (planned) | unit |
| FE-UI-020 | `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished`, `e2e/tests/test_admin_settings.py::test_d6_create_view_delete_page`, `e2e/tests/test_admin_dashboard.py::test_d2_admin_jobs_filter_cancel_restart`, `e2e/tests/test_accounts.py::test_d3_admin_users` | e2e |
| FE-UI-021, 022 | `common-components.test.js` › ConfirmDialog › emits confirm/cancel, disables while loading (planned) | unit |
| FE-UI-023 | job name with markup shown escaped in the cancel/delete dialog (planned, `e2e/tests/test_findings_security.py::test_confirm_dialog_escapes_job_name`); currently covered only by `e2e/exploratory/probes_xss.py` (exploratory, not in the suite) | e2e |
| FE-UI-030–032 | `common-components.test.js` › Pagination › hidden for one page, no out-of-range emits (planned) | unit |
| FE-UI-034 | `frontend/src/test/contracts/users.test.js` › users API › admin users › listUsers → GET /admin/users/ with params (paginated) | contract |
| FE-UI-040, 041, 042 | `frontend/src/test/contracts/users.test.js` › initials avatar (no external requests) › uses the full name, else the username; › hue is stable per user | unit |
| FE-UI-050, 051 | automated accessibility scan of main routes (planned, `e2e/tests/test_a11y.py::test_main_routes_have_no_critical_violations`) | e2e |
| FE-UI-053 | covered per surface in [home-static-pages.md](home-static-pages.md) and [workflow-submit-form.md](workflow-submit-form.md) | e2e |

## Known gaps

| ID | What the code does | Where | Severity |
|----|--------------------|-------|----------|
| FE-UI-023 | `ConfirmDialog` renders `message` with `v-html`; safety depends on every caller escaping. Escaping is a copy-pasted local `escapeHtml` in two views, not a shared util, and nothing prevents a new caller passing raw data. A text `message` plus an optional bold `subject` prop would remove the HTML surface. | `frontend/src/components/common/ConfirmDialog.vue:21`, `frontend/src/views/public/JobListView.vue:26`, `frontend/src/views/public/JobDetailView.vue:33` | major |
| FE-UI-024 | `ConfirmDialog` has no `role="dialog"`/`aria-modal`/`aria-labelledby`, no focus management, no `Escape` handling, and the close button has no `aria-label`. | `frontend/src/components/common/ConfirmDialog.vue:14-19` | minor |
| FE-UI-032 | Previous/Next buttons are only styled disabled; they stay focusable and keyboard activation emits `change(0)` or `change(totalPages + 1)`. | `frontend/src/components/common/Pagination.vue:18-31` | minor |
| FE-UI-033 | All page numbers are rendered (no window) and the active page has no `aria-current`. | `frontend/src/components/common/Pagination.vue:8-12`, `:21-28` | minor |
| FE-UI-020 | Destructive confirmations are implemented three ways (`ConfirmDialog`, an inline modal in `AdminUsersView`, an inline alert in `GroupManagementModal`); behaviour and accessibility differ between them. | `frontend/src/views/admin/AdminUsersView.vue:272-300`, `frontend/src/components/admin/GroupManagementModal.vue:164-170` | minor |
| FE-UI-052 | Decorative Font Awesome icons across the app lack `aria-hidden="true"`. | e.g. `frontend/src/components/layout/AdminSidebar.vue:40` | minor |
| FE-UI-010–033 | No component unit tests exist for `AlertMessage`, `ConfirmDialog`, `LoadingSpinner` or `Pagination`. | `frontend/src/test/` | minor |

## Open questions

1. Should `ConfirmDialog` drop HTML messages entirely (text `message` + `subject` prop), retiring FE-UI-023's escaping rule?
2. Should the two inline confirmations (`AdminUsersView`, `GroupManagementModal`) be migrated to `ConfirmDialog` once it is accessible?
