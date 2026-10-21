# Authentication

## Purpose

Establishes who is calling the API. The SPA uses a Django session cookie protected by CSRF;
programmatic clients use one DRF API token per user (`Authorization: Token <key>`). This file
covers login, logout, the "who am I" endpoint, CSRF handling, token authentication, the single
authentication backend with its per-account lockout, password hashing, and the behaviour of
inactive and locked accounts. What an authenticated identity may then do is in
[access-control.md](access-control.md).

## Scope

Covered:

- `accounts/views.py` — `LoginView`, `LogoutView`, `MeView` (lines 59–147).
- `accounts/backends.py` — `LockoutModelBackend` and the `user_login_failed` / `user_logged_in`
  receivers.
- `accounts/models.py` — `UserManager.get_by_natural_key` (case-insensitive lookup).
- `cloudgene_django/settings.py` — `AUTHENTICATION_BACKENDS`, `PASSWORD_HASHERS`, session/CSRF
  cookie settings, `CSRF_TRUSTED_ORIGINS`, `CSRF_FAILURE_VIEW`, `REST_FRAMEWORK` authentication
  classes.
- `core/views.py` — `csrf_failure`, `spa_index` (CSRF cookie only).
- `core/exceptions.py` — mapping of DRF CSRF failures to code `csrf_failed`.
- `core/checks.py` — `core.E001` (insecure hasher guard).
- `security.max_login_attempts`, `security.lockout_duration` in `settings.yaml`.

Out of scope:

- Registration, activation, password reset, profile, API token create/revoke, account deletion:
  [accounts.md](accounts.md).
- Admin role, permission classes, 401/403/404 rules per resource: [access-control.md](access-control.md).
- The error envelope itself and status-code conventions: [api-contract.md](api-contract.md).
- How `settings.yaml` is read and validated: [configuration.md](configuration.md).
- Logging format of auth events: [logging.md](logging.md).
- HTTPS, HSTS, proxy headers in production: `spec/deployment/`.
- The SPA's 401 hook and CSRF header handling: `spec/frontend/api-client.md`.

## Dependencies

- [api-contract.md](api-contract.md) — error envelope, `LoginRequest`, `LoginResponse`, `Me`,
  `Message` components.
- [configuration.md](configuration.md) — `security.*` keys.
- [data-model.md](data-model.md) — `User.login_attempts`, `User.locked_until`, `authtoken_token`.
- [access-control.md](access-control.md) — what 401 vs 403 means downstream.
- [../deployment/api-contract.md](../deployment/api-contract.md) — DEP-API-023 (forwarded headers
  set by nginx); [../deployment/security-hardening.md](../deployment/security-hardening.md) —
  DEP-SEC-026 (nginx rate limit until BE-AUTH-026 lands).
- Operations: `auth_login_create`, `auth_logout_create`, `auth_me_retrieve`.

## Requirements

**Login (`auth_login_create`, anonymous allowed)**

- **BE-AUTH-001** — A POST with the correct `username` and `password` of an active, unlocked account
  MUST return 200 with `{"user": User}`, start a session (`sessionid` cookie), set
  `User.last_login`, cycle the session key and rotate the CSRF token. The response MUST NOT
  contain an API token.
- **BE-AUTH-002** — The username MUST be matched after stripping surrounding whitespace and
  ignoring case (`ALICE` logs in `alice`). Only the username identifies the account; an e-mail
  address in `username` is treated as an unknown username.
- **BE-AUTH-003** — An unknown username and a wrong password MUST produce the identical response:
  400, code `invalid_credentials`, message `Invalid username or password.`. For an unknown
  username the backend MUST still compute a password hash so the two cases are not
  distinguishable by timing.
- **BE-AUTH-004** — A missing `username` or `password` MUST return 400, code `invalid`, with the
  field in `error.fields`.
- **BE-AUTH-005** — An inactive account MUST NOT get a session. With the correct password the
  response is 403, code `account_inactive`; with a wrong password it is the BE-AUTH-003 response.
- **BE-AUTH-006** — Every failed `authenticate()` call for an existing, not currently locked
  account MUST increment `User.login_attempts` by one, whatever surface made the call. When the
  count reaches `security.max_login_attempts` (> 0) and `security.lockout_duration` > 0, the
  account MUST be locked until now + `lockout_duration` seconds, and that attempt MUST already
  answer 429, code `account_locked`, header `Retry-After: <seconds>`, message
  `Too many failed logins. The account is locked for N minute(s).`.
- **BE-AUTH-007** — While an account is locked, every login attempt MUST be refused with the
  BE-AUTH-006 response, even with the correct password, on both `/api/auth/login/` and
  `/django-admin/login/`. Attempts during a lock MUST NOT extend the lock or change the counter.
- **BE-AUTH-008** — An expired lock MUST be cleared (counter 0, `locked_until` null) before the
  next attempt is evaluated. Any successful login, on any surface, MUST reset the counter and
  clear the lock.
- **BE-AUTH-009** — `security.max_login_attempts: 0` (or `lockout_duration: 0`) MUST disable
  locking; failures are still counted.
- **BE-AUTH-010** — Login MUST be CSRF-checked even though the caller is anonymous (login CSRF).
  A request without a valid `X-CSRFToken` header matching the `csrftoken` cookie MUST get 403,
  code `csrf_failed`.
- **BE-AUTH-011** — Login MUST stay available to every user while `server.maintenance` is on;
  maintenance only blocks job submission ([job-submission.md](job-submission.md)).
- **BE-AUTH-012** — No endpoint may exchange a username and password for an API token
  (`/api/auth/token/` MUST answer 404).

**Logout and current user**

- **BE-AUTH-013** — `auth_logout_create` MUST always return 200 `{"message": "Logged out."}` and
  flush the session. Anonymous callers need no CSRF token; a session-authenticated caller MUST
  send one (BE-AUTH-015). Logout MUST NOT revoke the user's API token.
- **BE-AUTH-014** — `auth_me_retrieve` MUST return 200 for everyone: `{"authenticated": true,
  "user": User}` when authenticated, `{"authenticated": false, "user": null}` otherwise. It MUST
  set the `csrftoken` cookie.

**CSRF and cookies**

- **BE-AUTH-015** — A session-authenticated request with an unsafe method (POST, PUT, PATCH,
  DELETE) MUST carry a valid `X-CSRFToken` header; otherwise 403. On `/api/` paths the body MUST
  be the error envelope with code `csrf_failed`, whether the failure is raised by DRF or by
  Django's `CsrfViewMiddleware`. On other paths the answer is a plain-text 403.
- **BE-AUTH-016** — Every SPA page (`spa_index`) and `auth_me_retrieve` MUST set the `csrftoken`
  cookie. The cookie MUST be readable by JavaScript (not HttpOnly) and `SameSite=Lax`.
- **BE-AUTH-017** — The session cookie MUST be HttpOnly and `SameSite=Lax`. Both cookies MUST be
  `Secure` when `DJANGO_SECURE_COOKIES=1`.
- **BE-AUTH-018** — Cross-origin unsafe requests MUST be accepted only from origins listed in
  `CSRF_TRUSTED_ORIGINS` (default: none in production; the Vite dev origins when `DEBUG`).

**Token authentication**

- **BE-AUTH-019** — A request with `Authorization: Token <key>` for an existing token of an active
  user MUST be authenticated as that user without any CSRF check. Token authentication MUST be
  tried before session authentication.
- **BE-AUTH-020** — A malformed or unknown token MUST give 401, code `authentication_failed`, on
  every `/api/` endpoint, including those open to anonymous callers. The one exception is
  `health`, which performs no authentication.
- **BE-AUTH-021** — An unauthenticated request to an endpoint that requires authentication MUST
  give 401, code `not_authenticated`, with a `WWW-Authenticate` header starting with `Token`;
  never 403.
- **BE-AUTH-022** — A token or session belonging to a user who has since been deactivated MUST NOT
  authenticate: the token gives 401 `authentication_failed`; the session is treated as anonymous.

**Passwords**

- **BE-AUTH-023** — New password hashes MUST use Argon2id. Hashes from PBKDF2, PBKDF2-SHA1 or
  scrypt MUST still verify and MUST be rehashed to Argon2 on the next successful login.
- **BE-AUTH-024** — The MD5 hasher MAY be enabled only with `INSECURE_FAST_PASSWORD_HASHING=1`
  together with `DEBUG` or `CLOUDGENE_E2E=1`. If the variable is set without either, the system
  check `core.E001` MUST report an error.
- **BE-AUTH-025** — Passwords MUST never be written to logs or returned by any endpoint.

**Throttling**

- **BE-AUTH-026** (planned) — The anonymous auth endpoints (`auth_login_create`,
  `auth_register_create`, `auth_password_reset_create`, `auth_activate_create`,
  `auth_password_reset_confirm`) SHOULD be rate-limited per client address, answering 429, code
  `throttled`, with `Retry-After`.
- **BE-AUTH-027** (planned) — The client address that BE-AUTH-026 throttles on MUST be the real
  client's address, not the reverse proxy's. Behind the reference nginx (one proxy, which appends
  `$remote_addr` to `X-Forwarded-For`), the throttle MUST use the right-most `X-Forwarded-For`
  entry (DRF `NUM_PROXIES = 1`), so a client-supplied `X-Forwarded-For` value cannot change its
  key. Without a proxy (development) it MUST use `REMOTE_ADDR`. This is the only permitted use of
  `X-Forwarded-For` ([../deployment/api-contract.md](../deployment/api-contract.md#proxy-headers)
  DEP-API-023).

## Interfaces

Operations (shapes in [api-contract.md](api-contract.md)):

| operationId | Method, path | Who | Success |
|---|---|---|---|
| `auth_login_create` | POST `/api/auth/login/` | anonymous (CSRF required) | 200 `LoginResponse` |
| `auth_logout_create` | POST `/api/auth/logout/` | anyone | 200 `Message` |
| `auth_me_retrieve` | GET `/api/auth/me/` | anyone | 200 `Me` |

Login error outcomes:

| Situation | Status | `error.code` | Extra |
|---|---|---|---|
| Missing field | 400 | `invalid` | `fields.username` / `fields.password` |
| Unknown user or wrong password | 400 | `invalid_credentials` | — |
| Correct password, inactive account | 403 | `account_inactive` | — |
| Locked (incl. the attempt that locks) | 429 | `account_locked` | `Retry-After` |
| CSRF missing/invalid | 403 | `csrf_failed` | — |
| Bad `Authorization: Token` header | 401 | `authentication_failed` | — |

Authentication classes (`REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES`), in order:
`TokenAuthentication`, `SessionAuthentication`. `HealthView` disables authentication.

Backend: `AUTHENTICATION_BACKENDS = ['accounts.backends.LockoutModelBackend']` — the only backend,
used by the SPA login and the Django admin login.

Configuration (`settings.yaml`, see [configuration.md](configuration.md)):

| Key | Default | Effect |
|---|---|---|
| `security.max_login_attempts` | 5 | Failures before lock; 0 = no lock |
| `security.lockout_duration` | 300 | Lock length in seconds; 0 = no lock |

Environment (`cloudgene_django/settings.py`): `DJANGO_SECURE_COOKIES`, `CSRF_TRUSTED_ORIGINS`,
`INSECURE_FAST_PASSWORD_HASHING`, `CLOUDGENE_E2E`.

## Behaviour

Login flow (`LoginView.post`):

1. Enforce CSRF explicitly (`SessionAuthentication().enforce_csrf`), because DRF skips CSRF for
   anonymous callers.
2. Validate `LoginSerializer`; strip the username.
3. Call `django.contrib.auth.authenticate()`. `LockoutModelBackend.authenticate`:
   - looks the user up with `username__iexact`; unknown → hash the password once, return `None`;
   - `locked_until` in the future → return `None` without checking the password;
   - `locked_until` in the past → clear counter and lock, continue;
   - return the user if the password matches. The backend does **not** check `is_active`.
4. If `authenticate()` returned `None`, Django fires `user_login_failed`; `count_failed_login`
   increments the counter (atomic `F()` update) and sets the lock when the threshold is reached.
   The view then re-reads the account: locked → 429, else 400 `invalid_credentials`.
5. User returned but inactive → 403 `account_inactive`; no session, counter untouched.
6. `login()` creates the session, rotates the CSRF token, updates `last_login`, and fires
   `user_logged_in`, whose receiver clears the counter.

The Django admin login (`/django-admin/login/`) calls the same `authenticate()`, so it shares the
counter and lock; Django's `AuthenticationForm` then rejects inactive and non-staff users itself.

CSRF: DRF views are exempt from `CsrfViewMiddleware`; `SessionAuthentication` enforces CSRF for
authenticated session requests and raises `PermissionDenied('CSRF Failed: …')`, which
`core/exceptions.py:128` maps to code `csrf_failed`. Non-DRF views use
`CSRF_FAILURE_VIEW = core.views.csrf_failure`. Login rotates the token, so clients must re-read
the `csrftoken` cookie after logging in.

Sessions use Django defaults (database sessions, two-week cookie age). Changing a password
invalidates other sessions of that user through Django's session auth hash
([accounts.md](accounts.md)).

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| BE-AUTH-001 | `accounts/tests.py::LoginTest::test_success_updates_last_login_and_session`; `core/tests/test_api.py::AuthSessionTest::test_login_me_logout_flow_without_trailing_slash` (CSRF rotation); `accounts/test_contracts.py::AuthContractTest::test_valid_login_returns_user_and_session`; `e2e/tests/test_auth.py::test_login_and_logout_via_ui` | unit, contract, e2e |
| BE-AUTH-002 | `accounts/tests.py::LoginTest::test_username_case_insensitive`; `accounts/tests.py::LoginTest::test_email_is_not_a_login_name` (planned; e-mail as username) | unit |
| BE-AUTH-003 | `accounts/tests.py::LoginTest::test_unknown_user_and_wrong_password_same_answer`; `core/tests/test_api.py::AuthSessionTest::test_login_errors_use_envelope`; `accounts/test_contracts.py::AuthContractTest::test_wrong_credentials_returns_400`; `e2e/tests/test_auth.py::test_login_wrong_password_shows_error` | unit, contract, e2e |
| BE-AUTH-004 | `accounts/test_contracts.py::AuthContractTest::test_missing_username_returns_400_with_username_error`, `::test_missing_password_returns_400_with_password_error` | contract |
| BE-AUTH-005 | `core/tests/test_api.py::AuthSessionTest::test_inactive_user_cannot_login`; `accounts/tests.py::ActivationTest::test_login_blocked_before_activation`, `::test_inactive_with_wrong_password_gets_generic_message` | unit |
| BE-AUTH-006 | `accounts/tests.py::LoginTest::test_lockout_after_max_attempts`; `e2e/tests/test_accounts.py::test_a3_lockout` | unit, e2e |
| BE-AUTH-007 | `accounts/tests.py::DjangoAdminLockoutTest::test_locked_account_rejected_with_correct_password`, `::test_wrong_passwords_count_towards_lockout_case_insensitive`; `e2e/tests/test_findings_security.py::test_b01_django_admin_login_bypasses_lockout`; `accounts/tests.py::LoginTest::test_attempts_during_lock_do_not_extend_it` (planned; no extension during lock) | unit, e2e |
| BE-AUTH-008 | `accounts/tests.py::LoginTest::test_success_resets_counter`, `::test_lockout_after_max_attempts` (expiry); `accounts/tests.py::DjangoAdminLockoutTest::test_successful_login_resets_counter` | unit |
| BE-AUTH-009 | `accounts/tests.py::LoginTest::test_lockout_disabled_with_zero` | unit |
| BE-AUTH-010 | `core/tests/test_api.py::AuthSessionTest::test_login_requires_csrf` | unit |
| BE-AUTH-011 | `accounts/tests.py::LoginTest::test_login_allowed_in_maintenance_mode` (planned) | unit |
| BE-AUTH-012 | `accounts/tests.py::LoginTest::test_obtain_token_endpoint_removed` | unit |
| BE-AUTH-013 | `accounts/tests.py::PermissionMatrixTest::test_matrix`; `accounts/test_contracts.py::AuthContractTest::test_logout_returns_200`; `core/tests/test_api.py::AuthSessionTest::test_session_write_without_csrf_rejected` | unit, contract |
| BE-AUTH-014 | `core/tests/test_api.py::AuthSessionTest::test_me_anonymous`; `e2e/tests/test_findings_security.py::test_permission_matrix_public` | unit, e2e |
| BE-AUTH-015 | `core/tests/test_api.py::AuthSessionTest::test_session_write_without_csrf_rejected`; `core/tests/test_api.py::ErrorEnvelopeHandlerTest::test_other_api_exceptions`; `core/tests/test_api.py::MiscRoutingTest::test_csrf_failure_view_api_and_non_api` (planned; non-DRF path) | unit |
| BE-AUTH-016 | `core/tests/test_api.py::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`; `core/tests/test_api.py::AuthSessionTest::test_login_requires_csrf` (cookie from `/api/auth/me/`) | unit |
| BE-AUTH-017 | `core/tests/test_deploy.py::CookieFlagsTest::test_session_and_csrf_cookie_flags` (planned) | unit |
| BE-AUTH-018 | `core/tests/test_deploy.py::CookieFlagsTest::test_csrf_trusted_origins_default` (planned) | unit |
| BE-AUTH-019 | `core/tests/test_api.py::TokenAuthTest::test_token_auth_without_csrf`; `accounts/tests.py::ApiTokenTest::test_token_client_needs_no_csrf` | unit |
| BE-AUTH-020 | `core/tests/test_api.py::TokenAuthTest::test_bad_token_is_401_envelope` | unit |
| BE-AUTH-021 | `core/tests/test_api.py::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope`; `e2e/tests/test_findings_security.py::test_permission_matrix_requires_authentication` | unit, e2e |
| BE-AUTH-022 | `core/tests/test_api.py::TokenAuthTest::test_deactivated_user_token_and_session_rejected` (planned) | unit |
| BE-AUTH-023 | `core/tests/test_deploy.py::PasswordHasherTest::test_argon2_is_the_default_hasher`, `::test_pbkdf2_hash_is_upgraded_to_argon2_on_login` | unit |
| BE-AUTH-024 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e`, `::test_clean_when_e2e_flag_set`, `::test_clean_when_debug`, `::test_clean_when_flag_unset` | unit |
| BE-AUTH-025 | `accounts/tests.py::LoginTest::test_password_not_logged` (planned) | unit |
| BE-AUTH-026 | `accounts/tests.py::ThrottleTest::test_login_throttled_per_address` (planned) | unit |
| BE-AUTH-027 | `accounts/tests.py::ThrottleTest::test_throttle_keys_on_rightmost_forwarded_address` (planned) | unit |

## Known gaps

| Req | What the code does | Where | Severity |
|---|---|---|---|
| BE-AUTH-026 | No throttling is configured: `REST_FRAMEWORK` has no `DEFAULT_THROTTLE_CLASSES` and no view sets `throttle_classes`. The lockout is per account only, so password spraying across many usernames, and repeated register / password-reset requests (mail flooding), are unlimited. | `cloudgene_django/settings.py:260-273`; `accounts/views.py:61-320` | major |
| BE-AUTH-027 | `NUM_PROXIES` is not set and nothing reads `X-Forwarded-For`; behind nginx every request comes from `127.0.0.1`, so a per-address throttle added without this would throttle all clients together. | `cloudgene_django/settings.py:260-273` | major |
| BE-AUTH-003 | A locked account returns before `check_password`, so a refused attempt on a locked account is measurably faster than one on an unlocked account; the 429 response also confirms the username exists. This is the intended `account_locked` contract, but it lets a caller enumerate usernames by locking them. | `accounts/backends.py:55-57`; `accounts/views.py:92-97` | minor |
| BE-AUTH-022 | Behaviour is correct (DRF `TokenAuthentication` rejects inactive users; `ModelBackend.get_user` drops inactive sessions) but nothing tests it, and deactivation does not delete the user's token. | `accounts/serializers.py:261-265` | minor |

## Open questions

- Should login accept the e-mail address as well as the username? The code accepts only the
  username (`accounts/backends.py:49`).
- API tokens never expire and DRF stores the key in plain text (`authtoken_token.key`). Should
  tokens be hashed at rest or have a lifetime?
- The per-account lockout lets anyone lock out a known username for `lockout_duration` seconds.
  Is that acceptable, or should the lock be keyed on account + client address?
- Should `auth_logout_create` with token authentication revoke the token, or is token revocation
  only via `me_token_destroy` (current behaviour)?
