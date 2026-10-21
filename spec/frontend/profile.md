# Profile

## Purpose

The signed-in user's account page (`/profile`, titled "Account Settings"). It shows who is signed
in, lets the user change their full name and e-mail, change their password, create, regenerate
or revoke their personal API token (the key is shown once), and delete their own account. All
rules are enforced by the server; the view adds client-side checks with the server's wording and
shows the server's answers.

## Scope

Covered:

- `frontend/src/views/public/ProfileView.vue` — route `/profile`.
- The own-profile functions of `frontend/src/api/users.js`: `getProfile`, `updateProfile`,
  `deleteAccount`, `createApiToken`, `revokeApiToken`.

Out of scope:

- The admin functions in `src/api/users.js` (`listUsers`, `getUser`, `updateUser`, `deleteUser`,
  groups) → [admin-users-groups.md](admin-users-groups.md).
- Route guard and 401 redirect → [routing.md](routing.md), [api-client.md](api-client.md).
- Validators (`validateFullName`, `validateEmail`, `validatePassword`, `normalizeEmail`,
  `validateFields`, `firstFieldErrors`) → [auth-views.md](auth-views.md) (FE-AUTHV-070…073).
- Server behaviour (password checks, session/token invalidation, cascade delete, `last_admin`) →
  [../backend/accounts.md](../backend/accounts.md); token authentication →
  [../backend/authentication.md](../backend/authentication.md).
- `AlertMessage`, `LoadingSpinner` → [common-components.md](common-components.md).

## Dependencies

- [../constitution.md](../constitution.md)
- [api-contract.md](api-contract.md), [../backend/api-contract.md](../backend/api-contract.md).
- [api-client.md](api-client.md): `apiErrorMessage`, `apiFieldErrors`; 401 handling.
- [routing.md](routing.md): `requiresAuth`.
- [state-stores.md](state-stores.md): `auth.updateUser`, `auth._clear`.
- [auth-views.md](auth-views.md): client validators.
- [../backend/accounts.md](../backend/accounts.md): BE-ACCT-016…025.

Operations used: `me_retrieve`, `me_partial_update`, `me_destroy`, `me_token_create`,
`me_token_destroy`.

## Requirements

**Access and loading**

- **FE-PROF-001** — `/profile` MUST require authentication (`meta.requiresAuth`). An anonymous
  visitor MUST be redirected to `/login?next=/profile`. If any call on this page answers 401, the
  store MUST be cleared and the user sent to `/login?next=/profile` (via the client's 401 handler).
- **FE-PROF-002** — The view MUST call the backend only through `src/api/users.js` and read errors
  only through `apiErrorMessage`/`apiFieldErrors`.
- **FE-PROF-003** — On mount the view MUST call `getProfile()` → `me_retrieve` and show a spinner
  until it answers. On error it MUST show `profile-load-error` with the envelope message, else
  `Could not load your profile.`, and render none of the forms.
- **FE-PROF-004** — On success it MUST show `Signed in as <username>` and, when the user has groups,
  `· groups: <names joined by ", ">` (`profile-username`), prefill the personal-information form,
  set the token status from `Profile.api_token`, and replace the store user with the returned
  profile (`auth.updateUser`).
- **FE-PROF-005** — All values from the server (username, groups, names, messages, token key, dates)
  MUST be rendered as text or input values, never with `v-html`.

**Personal information**

- **FE-PROF-010** — The form MUST have `Full Name` and `E-Mail` inputs. While
  `normalizeEmail(email)` differs from the loaded `Profile.email`, an extra
  `Current password (required to change your e-mail)` input MUST be shown
  (`profile-email-current-password`); otherwise it MUST be hidden.
- **FE-PROF-011** — On submit the view MUST validate `full_name` and `email` with the shared
  validators, and require the current password when the e-mail changed
  (`Please enter your current password.`). Any failure MUST mark the field and send no request.
- **FE-PROF-012** — Otherwise it MUST call `updateProfile()` → `me_partial_update` with
  `{full_name, email}`, plus `current_password` only when the e-mail changed. On 200 it MUST apply
  the returned `Profile` (refill the form, clear and hide the current-password input, update the
  store) and show `Your profile has been updated.` (`profile-success`).
- **FE-PROF-013** — On an error with `error.fields`, the first message per field MUST be shown under
  the matching input (e.g. `email`: taken; `current_password`: missing or not correct) and the
  alert `profile-error` MUST read `Please correct the marked fields.` Other errors show the
  envelope message, else `Saving failed.`

**Password change**

- **FE-PROF-020** — The password form MUST have `Current Password`, `New Password` and
  `New Password (again)` inputs. On submit the view MUST run
  `validatePassword(password, password_confirm)` and require `current_password`
  (`Please enter your current password.`); any failure marks the field and sends no request.
- **FE-PROF-021** — Otherwise it MUST call `me_partial_update` with
  `{current_password, password, password_confirm}`. On 200 it MUST clear the three inputs, apply the
  returned `Profile`, and show `password-success`: `Your password has been changed.`, followed by
  `Your API token was revoked; create a new one below if you need it.` when a token existed before
  the change. The user MUST stay signed in (BE-ACCT-019).
- **FE-PROF-022** — After a successful password change the token status MUST show "no token" (the
  server deleted it) and any token key still displayed from earlier on the page MUST be removed.
- **FE-PROF-023** — Errors MUST be shown as in FE-PROF-013 (`password-current-error`,
  `password-new-error`, alert `password-error`).

**API token**

- **FE-PROF-030** — The section MUST explain the header `Authorization: Token <your token>` and show
  `You have an API token (created <local date-time>).` (`token-status`, `data-state="active"`) or
  `You have no API token.` (`data-state="none"`).
- **FE-PROF-031** — The create button (labelled `Create API token`, or `Regenerate token` when one
  exists) MUST call `createApiToken()` → `me_token_create`. On 201 it MUST show `ApiToken.token` in a
  read-only input (`token-value`) under the warning
  `Copy your new token now — it will not be shown again.` and set the status from
  `ApiToken.created`.
- **FE-PROF-032** — The token key MUST live only in the view's local state: it MUST NOT be written to
  the store, `localStorage`, `sessionStorage`, the URL or logs, and MUST NOT be shown again after a
  reload (the server never returns it again, BE-ACCT-016).
- **FE-PROF-033** — `Copy` MUST copy the key with the Clipboard API and change its label to
  `Copied`. If the clipboard is unavailable the key MUST stay visible and selectable, with no error.
- **FE-PROF-034** — `Revoke token` (shown only when a token exists) MUST call `revokeApiToken()` →
  `me_token_destroy`; on 200 it MUST hide any shown key and set the status to "no token".
- **FE-PROF-035** — Token errors MUST show `token-error` with the envelope message, else
  `Could not create a token.` / `Could not revoke the token.` Both buttons MUST be disabled while a
  token request is in flight.
- **FE-PROF-036** (planned) — Regenerate and revoke SHOULD ask for confirmation, because both
  immediately break scripts that use the current token.

**Account deletion**

- **FE-PROF-040** — `Delete account…` MUST reveal an inline form asking for the password; `Cancel`
  MUST hide it again. Nothing is deleted until the form is submitted.
- **FE-PROF-041** — An empty password MUST show `Please enter your password.` and send no request.
- **FE-PROF-042** — Otherwise the view MUST call `deleteAccount(password)` → `me_destroy` with the
  JSON body `{"password": <password>}`. On 200 it MUST clear the store user and navigate to `/`,
  where the navbar shows the logged-out state.
- **FE-PROF-043** — On error it MUST show `fields.password` (wrong or missing password) or, for any
  other error such as 400 `last_admin`, the envelope message (fallback `Deleting failed.`) in
  `delete-error`, and stay on the page signed in.

**General**

- **FE-PROF-050** — Each form's submit button MUST be disabled and show a spinner while its request
  is in flight.

## Interfaces

| UI action | API function (`src/api/users.js`) | operationId | Request | Success |
|---|---|---|---|---|
| Load page | `getProfile()` | `me_retrieve` | — | 200 `Profile` |
| Save personal info | `updateProfile(data)` | `me_partial_update` | `PatchedProfileUpdateRequest` (`full_name`, `email`, `current_password?`) | 200 `Profile` |
| Change password | `updateProfile(data)` | `me_partial_update` | `PatchedProfileUpdateRequest` (`current_password`, `password`, `password_confirm`) | 200 `Profile` |
| Create / regenerate token | `createApiToken()` | `me_token_create` | — | 201 `ApiToken` |
| Revoke token | `revokeApiToken()` | `me_token_destroy` | — | 200 `Message` |
| Delete account | `deleteAccount(password)` | `me_destroy` | body `{"password"}` (not in `schema.yaml`; see Known gaps) | 200 `Message` |

Field shapes and error codes: [../backend/api-contract.md](../backend/api-contract.md),
`schema.yaml`. `deleteAccount` sends the body with `client.delete('/me/', {data: {password}})`;
the client interceptor sets `Content-Type: application/json` ([api-client.md](api-client.md)).

Test ids (used by e2e): `profile-load-error`, `profile-username`, `profile-form`,
`profile-full-name`, `profile-email`, `profile-email-error`, `profile-email-current-password`,
`profile-save`, `profile-success`, `profile-error`; `password-form`, `password-current`,
`password-current-error`, `password-new`, `password-new-error`, `password-confirm`,
`password-save`, `password-success`, `password-error`; `token-section`, `token-error`, `token-new`,
`token-value`, `token-copy`, `token-status` (`data-state`), `token-create`, `token-revoke`;
`delete-section`, `delete-account`, `delete-password`, `delete-error`, `delete-confirm`,
`delete-cancel`.

## Behaviour

**Page states.** `loading` (spinner) → `loaded` (four sections) | `error` (alert only). There is
no retry button; reloading the page retries.

**E-mail change detection.** The view compares the normalised input with the stored (already
normalised) address, so changing only case or surrounding spaces does not ask for the current
password; the server applies the same rule (BE-ACCT-018). The view always sends `email` in the
personal-information PATCH, even when unchanged.

**Password change and token.** The view remembers whether a token existed before the request to
choose the success text. The server deletes the token and keeps the current session
(BE-ACCT-019); other sessions of the user are logged out by the server.

**Token lifecycle.** States: `none` → (create) `active + key shown` → (reload) `active` →
(regenerate) `active + new key shown` → (revoke) `none`. The created date is formatted with
`toLocaleString()` in the browser's locale and time zone.

**Deletion.** After `me_destroy` succeeds the server has already ended the session. The view clears
the store locally (no logout call) and pushes `/`; `App.vue` reloads the viewer-filtered server
config because the store user id changed ([layout-navigation.md](layout-navigation.md)). An admin
who is the only active administrator gets 400 `last_admin` and stays signed in (BE-ACCT-024).

## Acceptance tests

| Requirement | Tests |
|---|---|
| FE-PROF-001 | e2e `e2e/tests/test_deep_links.py::test_protected_route_logged_out_redirects_to_login_with_next` (`/profile`), `::test_user_route_deep_link_and_refresh`; e2e `e2e/tests/test_auth.py::test_login_follows_next_parameter`; (planned) e2e `e2e/tests/test_accounts.py::test_profile_session_expired_redirects_to_login` |
| FE-PROF-002 | contract `frontend/src/test/contracts/users.test.js` › "getProfile → GET /me/ with token metadata only", "updateProfile → PATCH /me/", "deleteAccount sends the password as the DELETE body", "createApiToken / revokeApiToken" |
| FE-PROF-003 | (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "shows load error and no forms" |
| FE-PROF-004 | e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token`; (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "shows username and groups" |
| FE-PROF-005 | (planned) unit `frontend/src/test/no-v-html.test.js` › "profile renders server values as text" |
| FE-PROF-010, -011, -012 | e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token` (name change, e-mail change with current password, field hidden after save) |
| FE-PROF-013 | (planned) e2e `e2e/tests/test_accounts.py::test_profile_email_taken_shows_field_error` |
| FE-PROF-020, -021, -023 | e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token` (wrong current password → field error; success; still signed in after reload) |
| FE-PROF-022 | e2e `e2e/tests/test_findings_security.py::test_b02_password_change_revokes_api_token` (server side); (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "password change hides shown token" |
| FE-PROF-030, -031, -034 | e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token` (create, status, works as `Authorization: Token`, revoke → 401) |
| FE-PROF-032 | e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token` (key not shown after reload, not echoed by `/api/me/`); (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "token key not stored outside the view" |
| FE-PROF-033 | (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "copy falls back when clipboard is unavailable" |
| FE-PROF-035 | (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "token error message" |
| FE-PROF-040, -041, -042, -043 | e2e `e2e/tests/test_accounts.py::test_a6_delete_own_account` (wrong password → field error; success → `/`, logged out, login fails); (planned) e2e `e2e/tests/test_accounts.py::test_last_admin_cannot_delete_self_ui` |
| FE-PROF-050 | (planned) unit `frontend/src/views/public/__tests__/ProfileView.test.js` › "buttons disabled while saving" |

FE-PROF-036 is a SHOULD and has no test. No component (vitest) test of `ProfileView.vue` exists
today.

## Known gaps

| Requirement | Current behaviour | Location | Severity |
|---|---|---|---|
| FE-PROF-042 | `me_destroy` has no request body in `schema.yaml` (drf-spectacular drops DELETE bodies), yet the view must send `{"password"}`. The frontend request shape therefore rests on a hand-written contract, against constitution 5.1; a contract test cannot validate it against the schema. Fix belongs to the backend (BE-ACCT-023, BE-API-004). | `frontend/src/api/users.js:13-15`; `schema.yaml:1815-1838`; `accounts/views.py:357` | major |
| — | Contract tests for `src/api/users.js` validate against hand-written schemas (`profileSchema`, `apiTokenSchema`) in `frontend/src/test/schemas.js`, not `schema.yaml` components (constitution 5.1e). Owned by [api-contract.md](api-contract.md). | `frontend/src/test/contracts/users.test.js:11-16`; `frontend/src/test/schemas.js` | major |
| FE-PROF-022 | `savePassword()` does not clear `newToken`, so a key created earlier on the same page stays on screen (with its warning) after the password change revoked it, while the status says "no token". | `frontend/src/views/public/ProfileView.vue:117-125` | minor |
| FE-PROF-036 | `Regenerate token` and `Revoke token` act on the first click with no confirmation. | `frontend/src/views/public/ProfileView.vue:331-343` | minor |
| FE-PROF-043 | A non-field error such as `last_admin` is put in the same `deleteError` that marks the password input invalid, so a correct password is shown as wrong. | `frontend/src/views/public/ProfileView.vue:183,365-368` | minor |
| FE-PROF-040 | `Cancel` hides the delete form but keeps the typed password and error; reopening shows them again. | `frontend/src/views/public/ProfileView.vue:373` | minor |
| FE-PROF-004 | `auth.updateUser(data)` stores the `Profile` shape (with `api_token`) where the store otherwise holds `User`; harmless today but the store user's shape depends on which page set it. | `frontend/src/views/public/ProfileView.vue:64`; `frontend/src/stores/auth.js:65-67` | minor |
| FE-PROF-003…050 | No component tests for `ProfileView.vue`; loading, error and token-copy states are untested. | `frontend/src/views/public/ProfileView.vue` | minor |

## Open questions

- Should the e-mail change require re-confirmation of the new address (a mail to the new address)
  before it takes effect? Today the change is immediate on the backend; the view only asks for the
  current password.
- Should account deletion use the shared confirm dialog ([common-components.md](common-components.md))
  instead of the inline form, for consistency with job and admin deletions?
