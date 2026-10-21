# Authentication Views

## Purpose

The anonymous account screens of the SPA: sign in, sign out, sign up, e-mail activation, and the
two-step password recovery (request a link, then set a new password from the link). It also
covers the client-side copy of the account field rules (`src/utils/validation.js`), which lets
these forms reject bad input before a request with the same wording the server would use. The
server stays authoritative; these views only collect input, call the auth API module and show
the outcome.

## Scope

Covered:

- `frontend/src/views/public/LoginView.vue` — route `/login`
- `frontend/src/views/public/RegisterView.vue` — route `/register`
- `frontend/src/views/public/ActivateView.vue` — route `/activate/:key`
- `frontend/src/views/public/PasswordResetView.vue` — route `/reset-password` (request a link)
- `frontend/src/views/public/PasswordRecoveryView.vue` — route `/recover/:token` (set new password)
- How these views use `frontend/src/api/auth.js` and the `auth` store actions `login`/`logout`.
- The logout flow triggered from the navbar (`frontend/src/components/layout/AppNavbar.vue:16-19`):
  only the call sequence and the redirect; the menu itself is in
  [layout-navigation.md](layout-navigation.md).
- `frontend/src/utils/validation.js` (all validators and helpers, including `validateGroupName`,
  which only the admin views use).

Out of scope:

- Route table and guards, `next` creation on redirect → [routing.md](routing.md).
- Store internals (`boot`, `refresh`, `_clear`) → [state-stores.md](state-stores.md).
- HTTP client, CSRF, 401 handling, error helpers → [api-client.md](api-client.md).
- `AlertMessage` component → [common-components.md](common-components.md).
- Profile, password change, API token, account deletion → [profile.md](profile.md).
- Server behaviour (lockout, activation keys, reset tokens, mails) →
  [../backend/authentication.md](../backend/authentication.md),
  [../backend/accounts.md](../backend/accounts.md).

## Dependencies

- [../constitution.md](../constitution.md)
- [api-contract.md](api-contract.md) and [../backend/api-contract.md](../backend/api-contract.md)
  (operations below; error envelope).
- [api-client.md](api-client.md): `apiErrorMessage`, `apiFieldErrors`, `apiErrorCode`.
- [routing.md](routing.md), [state-stores.md](state-stores.md),
  [layout-navigation.md](layout-navigation.md), [common-components.md](common-components.md).
- [../backend/authentication.md](../backend/authentication.md) (BE-AUTH-001…016).
- [../backend/accounts.md](../backend/accounts.md) (BE-ACCT-002, -003, -005…-015).
- `accounts/validation.py`, `accounts/validation_cases.json` (shared rule table, BE-ACCT-003).

Operations used: `auth_login_create`, `auth_logout_create`, `auth_register_create`,
`auth_activate_create`, `auth_password_reset_create`, `auth_password_reset_confirm`.
(`auth_me_retrieve` is used by the store, not by these views.)

## Requirements

**General (all views in this file)**

- **FE-AUTHV-001** — All five routes MUST be reachable by anyone (no `requiresAuth`/`requiresAdmin`
  meta). Each view MUST call the backend only through `src/api/auth.js` functions (directly or via
  the `auth` store) and MUST read errors only through `apiErrorMessage`, `apiFieldErrors` and
  `apiErrorCode`.
- **FE-AUTHV-002** — Every message these views show, including server messages that may echo user
  input, MUST be rendered as text (Vue interpolation or `AlertMessage`), never with `v-html`.
- **FE-AUTHV-003** — While a submit request is in flight, the form's submit button MUST be disabled
  and show a spinner, so a form cannot be submitted twice.
- **FE-AUTHV-004** (planned) — A logged-in user who opens `/login` or `/register` SHOULD be sent to
  `/` (or to a same-app `next`) instead of seeing the form.

**Login (`/login`)**

- **FE-AUTHV-010** — Submitting the form MUST call `auth.login(username, password)`, which calls
  `auth_login_create` with `{username, password}` exactly as typed (the server strips the
  username, BE-AUTH-002). Both inputs are `required`.
- **FE-AUTHV-011** — On 200 the store user MUST be set from `LoginResponse.user` and the view MUST
  navigate to `route.query.next` when it is a string that starts with `/` and not with `//`;
  otherwise to `/`. The view MUST NOT navigate to an absolute or protocol-relative URL.
- **FE-AUTHV-012** — On failure the view MUST stay on `/login`, keep the user logged out and show
  the envelope `error.message` in the alert `login-error`, whose `data-code` attribute MUST carry
  `error.code` (`invalid_credentials`, `account_inactive`, `account_locked`, `invalid`,
  `csrf_failed`). Without an envelope message it shows `Invalid username or password.`; a network
  failure shows `Cannot reach the server. Check your connection.` (from `apiErrorMessage`).
- **FE-AUTHV-013** — The page MUST link to `/register` ("Sign up for free") and to `/reset-password`
  ("Reset your password").
- **FE-AUTHV-014** — The login inputs SHOULD carry `autocomplete="username"` and
  `autocomplete="current-password"` so password managers and assistive tools work.

**Logout (navbar)**

- **FE-AUTHV-020** — "Logout" MUST call `auth.logout()`, which calls `auth_logout_create`, and MUST
  clear the store user even when that call fails. The app MUST then navigate to `/`, also when the
  call failed, without an unhandled promise rejection.

**Registration (`/register`)**

- **FE-AUTHV-030** — The form MUST have the inputs `username`, `full_name`, `email`, `password`,
  `password_confirm` (test ids `register-username`, `register-full-name`, `register-email`,
  `register-password`, `register-password-confirm`). Username and password show their rule as help
  text while the field has no error.
- **FE-AUTHV-031** — Before any request the view MUST validate with `validateUsername`,
  `validateFullName`, `validateEmail` and `validatePassword(password, password_confirm)`. If any
  fails, each failing input MUST be marked invalid with its message (`register-<field>-error`),
  and no request MUST be sent.
- **FE-AUTHV-032** — Otherwise it MUST call `register()` → `auth_register_create` with the five
  fields. On 201 the form MUST be replaced by `register-success` showing `RegisterResponse.message`
  and a link to `/login`. The user is not logged in.
- **FE-AUTHV-033** — On an error with `error.fields`, the first message per field MUST be shown
  under the matching input and the alert MUST read `Please correct the marked fields.` Any other
  error (e.g. 503 `mail_failed`) MUST show the envelope message, else
  `Registration failed. Please try again.`

**Activation (`/activate/:key`)**

- **FE-AUTHV-040** — The route path MUST match the mailed link `<base>/activate/<key>`
  (BE-ACCT-008). On mount the view MUST call `activate(key)` → `auth_activate_create` exactly once,
  with the key URL-encoded in the path, and show `Activating your account…` until it answers.
  Activation happens only through this POST (opening the link without JavaScript changes nothing).
- **FE-AUTHV-041** — On 200 it MUST show `ActivateResponse.message` in `activate-success` with
  `data-status` set to `ActivateResponse.status` (`activated` or `already_active`) and a link to
  `/login`. A repeated visit MUST show the success state, not an error (BE-ACCT-012).
- **FE-AUTHV-042** — On error (400 `invalid_activation_key`, network) it MUST show
  `activate-error` with the envelope message, else
  `Activation failed. The link may be invalid.`

**Password reset request (`/reset-password`, `PasswordResetView`)**

- **FE-AUTHV-050** — An e-mail that is empty after trimming MUST show `E-Mail is required.` under
  the input and send no request. No other client-side format check is made.
- **FE-AUTHV-051** — Otherwise the view MUST call `requestPasswordReset(email.trim())` →
  `auth_password_reset_create`. On 200 the form MUST be replaced by `reset-success` showing the
  server's message verbatim. The view MUST NOT show anything that differs between a registered and
  an unknown address (BE-ACCT-013).
- **FE-AUTHV-052** — On error, `fields.email` MUST be shown under the input; any other error shows
  the envelope message, else `Request failed. Please try again.` The page MUST link back to
  `/login`.

**Set new password (`/recover/:token`, `PasswordRecoveryView`)**

- **FE-AUTHV-060** — The route path MUST match the mailed link `<base>/recover/<token>`
  (BE-ACCT-014).
- **FE-AUTHV-061** — Before any request the view MUST run `validatePassword(password, confirm)`;
  a failure MUST be shown under the new-password input (`recover-password-error`) and send no
  request.
- **FE-AUTHV-062** — Otherwise it MUST call `confirmPasswordReset(token, password, confirm)` →
  `auth_password_reset_confirm` with the token URL-encoded in the path and body
  `{password, password_confirm}`. On 200 the form MUST be replaced by `recover-success` showing the
  server message and a link to `/login`. The user is not logged in.
- **FE-AUTHV-063** — On 400 with `fields.password` the message MUST be shown under the input and the
  form kept, so the user can retry with the same link. Any other error (`invalid_token`,
  `expired_token`, network) MUST show `recover-error` with the envelope message (fallback
  `Password reset failed.`) plus a link `Request a new link` to `/reset-password`.

**Client-side validation (`src/utils/validation.js`)**

- **FE-AUTHV-070** — `validateUsername`, `validateEmail`, `validatePassword`, `validateFullName`
  and `validateGroupName` MUST implement exactly the rules of `accounts/validation.py`
  (BE-ACCT-002): each returns `null` when valid, else the exact message string the server puts in
  `error.fields`. Every case in `accounts/validation_cases.json` MUST pass in the frontend suite.
- **FE-AUTHV-071** — `validatePassword(value, confirm)` MUST compare `confirm` only when it is not
  `null`/`undefined`, and MUST report a mismatch before any other password rule (same order as the
  backend).
- **FE-AUTHV-072** — `normalizeUsername` MUST trim; `normalizeEmail` MUST trim and lower-case, as
  the backend stores them (BE-ACCT-001).
- **FE-AUTHV-073** — `validateFields(spec)` MUST return an object containing only the failing
  fields; `firstFieldErrors(fields)` MUST map envelope `error.fields` (`{field: [msg, …]}`) to
  `{field: firstMsg}` and accept `undefined`.
- **FE-AUTHV-074** — Client validation is advisory only. Every form in this file MUST still show the
  server's field errors (FE-AUTHV-033, -052, -063), because the server can reject input the client
  accepts (e.g. a taken username).

## Interfaces

Routes → views → operations:

| Route | View | API function (`src/api/auth.js`) | operationId | Success shape |
|---|---|---|---|---|
| `/login` | `LoginView` | `login(username, password)` via `auth.login` | `auth_login_create` | `LoginResponse` |
| (navbar) | `AppNavbar` | `logout()` via `auth.logout` | `auth_logout_create` | `Message` |
| `/register` | `RegisterView` | `register(data)` | `auth_register_create` | `RegisterResponse` (201) |
| `/activate/:key` | `ActivateView` | `activate(activationKey)` | `auth_activate_create` | `ActivateResponse` |
| `/reset-password` | `PasswordResetView` | `requestPasswordReset(email)` | `auth_password_reset_create` | `Message` |
| `/recover/:token` | `PasswordRecoveryView` | `confirmPasswordReset(token, password, passwordConfirm)` | `auth_password_reset_confirm` | `Message` |

Request and response fields: see [../backend/api-contract.md](../backend/api-contract.md) and
`schema.yaml`. Error codes per operation are listed there.

Mail links the views must accept (built in `accounts/views.py`):

| Mail | Link | Route |
|---|---|---|
| Activation | `<base>/activate/<key>` (`accounts/views.py:212`) | `/activate/:key` |
| Password reset | `<base>/recover/<token>` (`accounts/views.py:275`) | `/recover/:token` |

`src/utils/validation.js` exports: `MESSAGES`, `normalizeUsername`, `normalizeEmail`,
`validateUsername`, `validateEmail`, `validatePassword(value, confirm = null)`,
`validateFullName`, `validateGroupName`, `validateFields(spec)`, `firstFieldErrors(fields)`.
`MESSAGES` holds the backend `validation.MESSAGES` texts verbatim.

Test ids (used by e2e): `login-username`, `login-password`, `login-submit`, `login-error`
(`data-code`), `login-register-link`, `login-reset-link`; `register-form`, `register-<field>`,
`register-<field>-error`, `register-submit`, `register-success`, `register-error`;
`activate-loading`, `activate-success` (`data-status`), `activate-error`, `activate-login-link`;
`reset-form`, `reset-email`, `reset-email-error`, `reset-submit`, `reset-success`, `reset-error`;
`recover-form`, `recover-password`, `recover-password-confirm`, `recover-password-error`,
`recover-submit`, `recover-success`, `recover-error`, `recover-login-link`.

## Behaviour

**Route naming.** The two password views are named the other way round from the API:

| Step | Route | View file | Operation |
|---|---|---|---|
| 1. ask for a link | `/reset-password` | `PasswordResetView.vue` | `auth_password_reset_create` (`/api/auth/password-reset/`) |
| 2. set new password | `/recover/:token` | `PasswordRecoveryView.vue` | `auth_password_reset_confirm` (`/api/auth/password-reset/{token}/`) |

The mailed link (`/recover/<token>`) matches step 2, so the flow works; only the names are
confusing. See Open questions.

**Login flow.** The guard sends an anonymous user from a protected route to
`/login?next=<fullPath>` ([routing.md](routing.md)). After a successful login the view pushes
`next` (filtered by FE-AUTHV-011) through the router, so only in-app routes are reached; unknown
paths fall to the catch-all redirect to `/`. `App.vue` watches the store user id and reloads the
server config (viewer-filtered navbar) when it changes ([layout-navigation.md](layout-navigation.md)).
A locked account (429 `account_locked`) shows the server message, which states how long the lock
lasts; the view has no countdown.

**Logout flow.** `AppNavbar.logout()` awaits `auth.logout()` and then pushes `/`. The store clears
the user in a `finally`, then rethrows any error.

**Register flow.** Client validation → request → either success panel or field errors. Server
field errors replace the client ones. The success text comes from the server (it differs for
`activation_required: true`/`false`); the view does not read `activation_required`.

**Activation flow.** States: `loading` → `activated` | `already_active` | `error`. Any non-error
status from the server is shown as success. There is no resend-activation feature.

**Recovery flow.** The token is checked only on submit (there is no "check token" operation), so an
expired or used link shows the form first and the error after submit. A password-rule error keeps
the token usable (BE-ACCT-015).

**Validation table.** `validation.test.js` imports `../../../accounts/validation_cases.json`,
a file outside `frontend/`. The production bundle does not include it (only the test imports it),
but the frontend test suite needs the full repository checkout.

## Acceptance tests

| Requirement | Tests |
|---|---|
| FE-AUTHV-001 | e2e `e2e/tests/test_deep_links.py::test_public_route_logged_out` (`/login`, `/register`, `/reset-password`); unit (planned) `frontend/src/views/public/__tests__/auth-views.test.js` › "views call only api/auth.js" |
| FE-AUTHV-002 | (planned) unit `frontend/src/test/no-v-html.test.js` › "auth views render messages as text" |
| FE-AUTHV-003 | (planned) unit `frontend/src/views/public/__tests__/auth-views.test.js` › "submit button disabled while pending" |
| FE-AUTHV-004 | (planned) e2e `e2e/tests/test_auth.py::test_logged_in_user_redirected_from_login` |
| FE-AUTHV-010 | e2e `e2e/tests/test_auth.py::test_login_and_logout_via_ui`; contract `frontend/src/test/contracts/auth.test.js` › "login() posts credentials and receives {user} (no token)"; unit `frontend/src/test/auth-store.test.js` › "login stores the returned user; logout clears it even if the call fails" |
| FE-AUTHV-011 | e2e `e2e/tests/test_auth.py::test_login_follows_next_parameter`; (planned) unit `frontend/src/views/public/__tests__/LoginView.test.js` › "ignores //host and absolute next" |
| FE-AUTHV-012 | e2e `e2e/tests/test_auth.py::test_login_wrong_password_shows_error`, `e2e/tests/test_accounts.py::test_a3_lockout`, `e2e/tests/test_accounts.py::test_a1_register_activate_login` (`account_inactive`) |
| FE-AUTHV-013 | (planned) unit `frontend/src/views/public/__tests__/LoginView.test.js` › "links to register and reset" |
| FE-AUTHV-020 | e2e `e2e/tests/test_auth.py::test_login_and_logout_via_ui`; unit `frontend/src/test/auth-store.test.js` › "login stores the returned user; logout clears it even if the call fails"; (planned) unit `frontend/src/components/layout/__tests__/AppNavbar.test.js` › "navigates home when logout fails" |
| FE-AUTHV-030, -031 | e2e `e2e/tests/test_accounts.py::test_a2_client_side_rules_match_server` |
| FE-AUTHV-032 | e2e `e2e/tests/test_accounts.py::test_a1_register_activate_login`; contract `frontend/src/test/contracts/auth.test.js` › "register() posts the form and receives {user, message}" |
| FE-AUTHV-033 | e2e `e2e/tests/test_accounts.py::test_a2_case_variant_duplicates_rejected`; contract `frontend/src/test/contracts/auth.test.js` › "registration validation errors arrive in error.fields"; (planned) e2e `e2e/tests/test_accounts.py::test_register_mail_failed_shows_message` |
| FE-AUTHV-040, -041 | e2e `e2e/tests/test_accounts.py::test_a1_register_activate_login`; contract `frontend/src/test/contracts/users.test.js` › "activate POSTs the (url-encoded) key" |
| FE-AUTHV-042 | (planned) e2e `e2e/tests/test_accounts.py::test_activate_invalid_key_shows_error` |
| FE-AUTHV-050 | (planned) unit `frontend/src/views/public/__tests__/PasswordResetView.test.js` › "empty e-mail sends no request" |
| FE-AUTHV-051 | e2e `e2e/tests/test_accounts.py::test_a4_password_reset` (same text for unknown and known address); contract `frontend/src/test/contracts/auth.test.js` › "requestPasswordReset() posts the e-mail" |
| FE-AUTHV-052 | (planned) unit `frontend/src/views/public/__tests__/PasswordResetView.test.js` › "shows fields.email" |
| FE-AUTHV-060, -061, -062, -063 | e2e `e2e/tests/test_accounts.py::test_a4_password_reset` (mailed link, rule error, success, used link); contract `frontend/src/test/contracts/users.test.js` › "confirmPasswordReset posts password (+ confirm) to /auth/password-reset/<token>/"; (planned) e2e `e2e/tests/test_accounts.py::test_recover_expired_token_offers_new_link` |
| FE-AUTHV-070, -071 | unit `frontend/src/utils/validation.test.js` › "validation mirrors accounts/validation.py" (all `it.each` cases); backend twin `accounts/tests.py::ValidationRulesTest` |
| FE-AUTHV-072, -073 | unit `frontend/src/utils/validation.test.js` › "helpers" › "normalises like the backend model", "validateFields collects only failures", "firstFieldErrors takes the first server message per field" |
| FE-AUTHV-074 | e2e `e2e/tests/test_accounts.py::test_a2_case_variant_duplicates_rejected`, `::test_a4_password_reset` |

FE-AUTHV-014 is a SHOULD and has no test.

## Known gaps

| Requirement | Current behaviour | Location | Severity |
|---|---|---|---|
| FE-AUTHV-020 | `auth.logout()` rethrows a failed `auth_logout_create` after clearing the user; `AppNavbar.logout()` does not catch it, so the push to `/` is skipped (the user may stay on a protected page) and the rejection is unhandled. | `frontend/src/components/layout/AppNavbar.vue:16-19`; `frontend/src/stores/auth.js:52-58` | minor |
| FE-AUTHV-014 | Login form and both inputs set `autocomplete="off"`, which blocks password-manager fill and the WCAG 1.3.5 input-purpose hint. | `frontend/src/views/public/LoginView.vue:47,56,69` | minor |
| FE-AUTHV-004 | `/login` and `/register` have no guard for logged-in users; a signed-in user can fill in the login form again or register a second account in the same session. | `frontend/src/router/index.js:10-11` | minor |
| FE-AUTHV-001, -002, -003, -013, -050, -052 | No component tests exist for any of the five views; they are covered only by e2e or not at all. | `frontend/src/views/public/` | minor |
| — | Contract tests for `src/api/auth.js` validate against hand-written JSON Schemas in `frontend/src/test/schemas.js`, not components loaded from `schema.yaml` (constitution 5.1e). Owned by [api-contract.md](api-contract.md). | `frontend/src/test/schemas.js:1-30`; `frontend/src/test/contracts/auth.test.js` | major |
| — | Route/view names are inverted relative to the API (`PasswordResetView` requests the link; `PasswordRecoveryView` confirms the reset at `/api/auth/password-reset/{token}/`). Behaviour is correct; maintenance risk only. | `frontend/src/router/index.js:13-14` | minor |
| FE-AUTHV-063 | The `Request a new link` hint appears for every non-field error, including a network failure where the link may still be valid. | `frontend/src/views/public/PasswordRecoveryView.vue:47` | minor |

## Open questions

- Should the password views be renamed to match the API (`PasswordResetRequestView` at
  `/reset-password`, `PasswordResetConfirmView` at `/recover/:token`)? Renaming the route would
  break links already mailed (valid 24 h), so only the file names are cheap to change.
- Should `/activate/:key` require a click ("Activate my account") instead of activating on mount?
  Activation on mount is idempotent and POST-only, so link scanners that do not run JavaScript do
  not trigger it; a click would also stop scanners that do.
- Constitution pending amendment P2: `validation.js` shares rules with the backend through
  `accounts/validation_cases.json`, outside `schema.yaml`. This file treats that table as the
  contract for FE-AUTHV-070.
