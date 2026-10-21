# Accounts

## Purpose

Self-service account lifecycle: registration, e-mail activation, password recovery, the user's
own profile (`/api/me/`), the personal API token, and deleting one's own account. It also owns
the account field rules (`accounts/validation.py`), which the frontend mirrors and checks
against a shared table of examples, and the case-insensitive identity rules that prevent
duplicate users (`Bob` / `bob`).

## Scope

Covered:

- `accounts/views.py` — `RegisterView`, `ActivateAccountView`, `PasswordResetView`,
  `PasswordResetConfirmView`, `ProfileView`, `ApiTokenView` (lines 150–392).
- `accounts/serializers.py` — self-service serializers (lines 1–210).
- `accounts/models.py` — `User`, `UserManager`, `hash_token`, `new_token`.
- `accounts/validation.py`, `accounts/validation_cases.json`.
- `accounts/migrations/0003_case_insensitive_identity.py` — duplicate check and normalisation.
- `accounts/admin.py` — what the Django admin must not expose (tokens, users).
- Mails sent by these flows (content and triggers; transport is in
  [server-pages-mail.md](server-pages-mail.md)).

Out of scope:

- Login, logout, `auth_me_retrieve`, lockout, CSRF, token authentication: [authentication.md](authentication.md).
- Admin user and group endpoints (`admin_users_*`, `admin_groups_*`), although they live in
  `accounts/views.py`: [admin-api.md](admin-api.md). Admin role semantics: [access-control.md](access-control.md).
- Model fields and constraints in full: [data-model.md](data-model.md).
- `create_admin` management command: [management-commands.md](management-commands.md).
- The frontend mirror `frontend/src/utils/validation.js` and the forms: `spec/frontend/`.

## Dependencies

- [api-contract.md](api-contract.md) — error envelope; components `RegistrationRequest`,
  `RegisterResponse`, `ActivateResponse`, `PasswordResetRequestRequest`,
  `PasswordResetConfirmRequest`, `Profile`, `PatchedProfileUpdateRequest`, `ApiToken`,
  `Message`. (`me_destroy` has no request component; see Known gaps.)
- [authentication.md](authentication.md) — sessions, lockout fields, token authentication.
- [configuration.md](configuration.md) — `security.require_activation`, `server.url`,
  `server.name`.
- [server-pages-mail.md](server-pages-mail.md) — `core.mail.send_mail`.
- [job-queue-worker.md](job-queue-worker.md) — workspace removal when jobs are deleted by cascade.

## Requirements

**Identity and validation**

- **BE-ACCT-001** — Usernames MUST be unique ignoring case and stored stripped with case preserved.
  E-mail addresses MUST be unique ignoring case and stored stripped and lower-cased. The database
  MUST enforce both (`users_username_ci_unique`, `users_email_ci_unique` on `Lower(...)`).
- **BE-ACCT-002** — Field rules MUST be exactly those of `accounts/validation.py`:

  | Field | Rule | 
  |---|---|
  | username | required; 4–150 chars; `^[A-Za-z0-9]+$` (after strip) |
  | email | required; ≤ 254 chars; `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` (after strip + lower) |
  | password | equals `password_confirm` when that is sent; required; 6–128 chars; at least one digit, one lower-case and one upper-case ASCII letter |
  | full_name | required after strip; ≤ 255 chars |
  | group name | `^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$` (after strip) |

  Each rule returns one message from `validation.MESSAGES`; that text is the API message.
- **BE-ACCT-003** — `accounts/validation_cases.json` MUST be the shared example table for these
  rules. The backend suite and the frontend suite (`frontend/src/utils/validation.test.js`, which
  imports the file by relative path) MUST both run every case, and every backend message MUST
  appear verbatim in `frontend/src/utils/validation.js`. A change to a rule or message changes
  `validation.py`, `validation.js` and the JSON file in one commit.
- **BE-ACCT-004** — Migration `accounts.0003` MUST refuse to run while case-duplicate usernames or
  e-mails exist, listing each conflicting account (`id` and value), and MUST change nothing.

**Registration (`auth_register_create`, anonymous)**

- **BE-ACCT-005** — Registration MUST validate `username`, `email`, `full_name`, `password`
  (+ optional `password_confirm`) and report every failing field at once: 400, code `invalid`,
  `error.fields.<field>`.
- **BE-ACCT-006** — A username or e-mail that differs from an existing one only by case or
  surrounding whitespace MUST be rejected with 400 and `fields.username = ["This username is
  already taken."]` / `fields.email = ["This e-mail address is already registered."]`. A
  concurrent duplicate that slips past validation MUST also give this 400, not 500.
- **BE-ACCT-007** — Fields other than the five above (e.g. `is_staff`, `is_superuser`, `groups`,
  `is_active`) MUST be ignored.
- **BE-ACCT-008** — With `security.require_activation: true` (default) the account MUST be created
  inactive and an activation mail sent with the link `<base>/activate/<key>`; only the sha256 of
  `key` is stored. Response 201 `{user, message, activation_required: true}`.
- **BE-ACCT-009** — If the activation mail cannot be sent, the response MUST be 503, code
  `mail_failed`, and no account MUST remain.
- **BE-ACCT-010** — With `security.require_activation: false` the account MUST be active at once
  (`activated_at` set), no mail is sent, response 201 with `activation_required: false`.

**Activation (`auth_activate_create`, anonymous, POST only)**

- **BE-ACCT-011** — A key whose sha256 matches no user MUST give 400, code
  `invalid_activation_key`. The stored hash itself MUST NOT work as a key. GET MUST give 405.
- **BE-ACCT-012** — The first valid use MUST activate the account: 200 `{status: "activated"}`.
  Any later use MUST give 200 `{status: "already_active"}` and MUST NOT change `is_active`, so
  an account an admin deactivated stays inactive.

**Password recovery (anonymous)**

- **BE-ACCT-013** — `auth_password_reset_create` MUST answer 200 with the same message for a
  registered, unknown or inactive e-mail. A mail MUST be sent only to an active account, and a
  mail failure MUST NOT change the answer. A missing `email` MUST give 400 with
  `fields.email`.
- **BE-ACCT-014** — A reset MUST store only the sha256 of a random token (`secrets.token_urlsafe(32)`),
  expiring 24 h after the request; the mailed link is `<base>/recover/<token>`. A new request
  MUST replace any earlier token.
- **BE-ACCT-015** — `auth_password_reset_confirm` MUST give 400 `invalid_token` for an unknown or
  already used token, 400 `expired_token` after expiry, and 400 with `fields.password` when the
  password rules fail (token kept). On success it MUST set the password, clear the token, clear
  the lockout (`login_attempts = 0`, `locked_until = null`), delete the user's API token, and
  answer 200.

**Profile (`/api/me/`, authenticated user; anonymous → 401)**

- **BE-ACCT-016** — `me_retrieve` MUST return the caller's `Profile`, including
  `api_token: {created}` or `null`. No response other than `me_token_create` may contain a token
  key.
- **BE-ACCT-017** — `me_partial_update` MUST accept only `full_name`, `email`, `password`,
  `password_confirm`, `current_password`; any other key (`username`, `is_staff`, `groups`, …)
  MUST be ignored. PUT MUST give 405.
- **BE-ACCT-018** — Changing the e-mail or the password MUST require `current_password`: missing →
  400 `fields.current_password = ["Please enter your current password."]`; wrong → `["Your
  current password is not correct."]`. A blank `password` means "unchanged". A new e-mail taken
  by another account (ignoring case) MUST give 400 `fields.email`.
- **BE-ACCT-019** — After a password change the current session MUST stay logged in, other
  sessions of the user MUST be invalidated, and the user's API token MUST be deleted.

**API token (`/api/me/token/`, authenticated user; anonymous → 401)**

- **BE-ACCT-020** — `me_token_create` MUST delete any existing token, create a new one and return
  201 `{token, created}`. This is the only response that ever contains the key.
- **BE-ACCT-021** — `me_token_destroy` MUST delete the token and answer 200 with
  `API token revoked.`, or `No API token.` when there was none.
- **BE-ACCT-022** — The Django admin MUST NOT register `Token`/`TokenProxy` or `accounts.User`, so
  no admin page can show a token key.

**Account deletion (`me_destroy`, authenticated user; anonymous → 401)**

- **BE-ACCT-023** — Deletion MUST require the current `password`: missing or wrong → 400 with
  `fields.password`.
- **BE-ACCT-024** — An administrator MUST NOT delete their own account when no other active
  administrator exists: 400, code `last_admin`.
- **BE-ACCT-025** — On success the session MUST end, the user and their token MUST be deleted,
  their jobs MUST be deleted by cascade (workspaces removed as in
  [job-queue-worker.md](job-queue-worker.md)), and the answer is 200
  `{"message": "Your account has been deleted."}`.

**Mail content**

- **BE-ACCT-026** — Activation and reset mails MUST be plain text with subject `[<server.name>] …`.
  Link base MUST be `server.url` when set, else the request's scheme and host (which Django only
  accepts from `ALLOWED_HOSTS`). User-supplied values (`full_name`, `username`) appear only in
  the plain-text body; no HTML mail is sent.

## Interfaces

| operationId | Method, path | Who | Success | Error codes |
|---|---|---|---|---|
| `auth_register_create` | POST `/api/auth/register/` | anyone | 201 `RegisterResponse` | `invalid`, `mail_failed` (503) |
| `auth_activate_create` | POST `/api/auth/activate/{activation_key}/` | anyone | 200 `ActivateResponse` | `invalid_activation_key` |
| `auth_password_reset_create` | POST `/api/auth/password-reset/` | anyone | 200 `Message` | `invalid` |
| `auth_password_reset_confirm` | POST `/api/auth/password-reset/{token}/` | anyone | 200 `Message` | `invalid_token`, `expired_token`, `invalid` |
| `me_retrieve` | GET `/api/me/` | user | 200 `Profile` | `not_authenticated` (401) |
| `me_partial_update` | PATCH `/api/me/` | user | 200 `Profile` | `invalid`, 401 |
| `me_destroy` | DELETE `/api/me/` | user | 200 `Message` | `invalid`, `last_admin`, 401 |
| `me_token_create` | POST `/api/me/token/` | user | 201 `ApiToken` | 401 |
| `me_token_destroy` | DELETE `/api/me/token/` | user | 200 `Message` | 401 |

Mails (sent with `core.mail.send_mail`):

| Trigger | Subject | Link | Recipient |
|---|---|---|---|
| Registration with activation | `[<name>] Activate your account` | `<base>/activate/<key>` | new user |
| Reset request for an active account | `[<name>] Reset your password` | `<base>/recover/<token>` | that user |

Validation module (`accounts/validation.py`): `normalize_username`, `normalize_email`,
`validate_username`, `validate_email`, `validate_password(value, confirm=None)`,
`validate_full_name`, `validate_group_name`, `MESSAGES`. Each `validate_*` returns `None` or one
message.

Shared table (`accounts/validation_cases.json`): keys `username`, `email`, `full_name`,
`group_name` → `[input, expected message | null]`; `password` → `[password, confirm | null,
expected]`.

## Behaviour

Registration runs in one transaction: create user → (if activation) send mail. A mail exception
raises `MailError` inside the transaction, so the row is rolled back and 503 is returned. An
`IntegrityError` from the case-insensitive constraints is re-checked and reported as field
errors.

Activation keeps the hashed key after use; `activated_at` distinguishes "already active".

Password reset request: always the same 200. For an active account it stores a fresh hashed
token (overwriting any older one) and tries to send the mail; failures are only logged.

Password change via `me_partial_update`: with session authentication the view calls
`update_session_auth_hash`, so this session survives while every other session of the user fails
Django's session-hash check. With token authentication the token used for the request is deleted
by the same call.

Self-deletion: "other administrator" means another active user who is superuser, staff, or in
group `admin` (`accounts/views.py:325`).

Duplicate-user fix (K1): before migration 0003, usernames and e-mails were unique only exactly,
so `Bob` and `bob` could both register. Now normalisation (`User.save`), serializer checks
(`username_taken` / `email_taken`, `__iexact`), DB constraints and case-insensitive login
(`UserManager.get_by_natural_key`) all use the same rule.

## Acceptance tests

| Requirement | Tests |
|---|---|
| BE-ACCT-001 | unit `accounts/tests.py::UserModelTest::test_email_normalised_and_username_stripped`, `::test_db_rejects_case_variant_username`, `::test_db_rejects_case_variant_email`, `::test_natural_key_lookup_ignores_case` |
| BE-ACCT-002 | unit `accounts/tests.py::ValidationRulesTest` (all `test_*_cases`); unit `accounts/tests.py::UserModelTest::test_clean_uses_shared_rules` |
| BE-ACCT-003 | unit `accounts/tests.py::ValidationRulesTest::test_frontend_module_mirrors_messages`; unit (vitest) `frontend/src/utils/validation.test.js` › `validation mirrors accounts/validation.py`; e2e `e2e/tests/test_accounts.py::test_a2_client_side_rules_match_server` |
| BE-ACCT-004 | unit `accounts/tests.py::DuplicateDetectionTest::test_find_case_duplicates`, `::test_check_raises_with_list` |
| BE-ACCT-005 | unit `accounts/tests.py::RegistrationTest::test_all_field_errors_reported`, `::test_password_mismatch`; contract `accounts/test_contracts.py::RegistrationContractTest` (missing/invalid field tests) |
| BE-ACCT-006 | unit `accounts/tests.py::RegistrationTest::test_case_variants_rejected`; unit `accounts/tests.py::K1RegressionTest::test_no_duplicate_users`; contract `accounts/test_contracts.py::RegistrationContractTest::test_duplicate_username_returns_400_with_username_error`; e2e `e2e/tests/test_accounts.py::test_a2_case_variant_duplicates_rejected`; race path (planned) `accounts/tests.py::RegistrationTest::test_integrity_error_is_field_error` |
| BE-ACCT-007 | unit `accounts/tests.py::RegistrationTest::test_privilege_fields_ignored` |
| BE-ACCT-008 | unit `accounts/tests.py::RegistrationTest::test_register_sends_activation_mail_and_stores_hashed_key`, `::test_link_uses_server_url`; contract `accounts/test_contracts.py::RegistrationContractTest::test_valid_registration_returns_201_with_user`; e2e `e2e/tests/test_accounts.py::test_a1_register_activate_login` |
| BE-ACCT-009 | unit `accounts/tests.py::RegistrationTest::test_mail_failure_rolls_back` |
| BE-ACCT-010 | unit `accounts/tests.py::RegistrationTest::test_without_activation_account_is_active` |
| BE-ACCT-011 | unit `accounts/tests.py::ActivationTest::test_invalid_key`, `::test_raw_hash_is_not_a_key`, `::test_get_not_allowed` |
| BE-ACCT-012 | unit `accounts/tests.py::ActivationTest::test_activate_is_idempotent`, `::test_deactivated_user_cannot_reactivate_with_old_link`; e2e `e2e/tests/test_accounts.py::test_a1_register_activate_login` |
| BE-ACCT-013 | unit `accounts/tests.py::PasswordResetTest::test_same_answer_for_known_unknown_and_inactive`, `::test_missing_email_is_field_error`; contract `accounts/test_contracts.py::PasswordResetContractTest` (all) |
| BE-ACCT-014 | unit `accounts/tests.py::PasswordResetTest::test_token_hashed_single_use`, `::test_expires_after_24h`; new request replaces old (planned) `accounts/tests.py::PasswordResetTest::test_new_request_invalidates_previous_link` |
| BE-ACCT-015 | unit `accounts/tests.py::PasswordResetTest::test_token_hashed_single_use`, `::test_expired`, `::test_password_rules`, `::test_reset_clears_lockout`, `::test_reset_revokes_api_token`; e2e `e2e/tests/test_accounts.py::test_a4_password_reset` |
| BE-ACCT-016 | unit `accounts/tests.py::ProfileTest::test_get`; unit `accounts/tests.py::ApiTokenTest::test_create_use_regenerate_revoke` |
| BE-ACCT-017 | unit `accounts/tests.py::ProfileTest::test_no_mass_assignment`, `::test_put_not_allowed`, `::test_update_full_name`; e2e `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` |
| BE-ACCT-018 | unit `accounts/tests.py::ProfileTest::test_email_change_requires_current_password`, `::test_email_unique_ignoring_case`, `::test_blank_password_means_unchanged`, `::test_password_change` |
| BE-ACCT-019 | unit `accounts/tests.py::ProfileTest::test_password_change`, `::test_password_change_revokes_api_token`; e2e `e2e/tests/test_findings_security.py::test_b02_password_change_revokes_api_token`; other sessions invalidated (planned) `accounts/tests.py::ProfileTest::test_password_change_ends_other_sessions` |
| BE-ACCT-020 | unit `accounts/tests.py::ApiTokenTest::test_create_use_regenerate_revoke`; e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token` |
| BE-ACCT-021 | unit `accounts/tests.py::ApiTokenTest::test_create_use_regenerate_revoke`; "No API token." path (planned) `accounts/tests.py::ApiTokenTest::test_revoke_without_token` |
| BE-ACCT-022 | unit `accounts/tests.py::DjangoAdminTokenExposureTest` (all three); e2e `e2e/tests/test_findings_security.py::test_b03_token_keys_not_readable_in_django_admin` |
| BE-ACCT-023 | unit `accounts/tests.py::SelfDeleteTest::test_requires_password` |
| BE-ACCT-024 | unit `accounts/tests.py::SelfDeleteTest::test_last_admin_cannot_delete_self` |
| BE-ACCT-025 | unit `accounts/tests.py::SelfDeleteTest::test_delete_logs_out`; unit `jobs/tests/test_api.py::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces`; e2e `e2e/tests/test_accounts.py::test_a6_delete_own_account` |
| BE-ACCT-026 | unit `accounts/tests.py::RegistrationTest::test_link_uses_server_url`; request-host fallback (planned) `accounts/tests.py::RegistrationTest::test_link_falls_back_to_request_host` |

## Known gaps

| Req | What the code does | Where | Severity |
|---|---|---|---|
| BE-ACCT-002 | `AUTH_PASSWORD_VALIDATORS` (Django's similarity/common/numeric validators) is configured but no API flow uses it; only Django's own `changepassword`/`createsuperuser` apply it, so two different password policies exist. | `cloudgene_django/settings.py:193-198` | minor |
| BE-ACCT-002 | `create_admin` sets any `--password` / `$CLOUDGENE_ADMIN_PASSWORD` without `validate_password`, and stores `--email` lower-cased but without `validate_email`. | `core/management/commands/create_admin.py:38-45` | minor |
| BE-ACCT-015 | Confirm does not check `is_active`: a reset link issued before an admin deactivated the account still changes its password (login stays blocked by BE-AUTH-005). | `accounts/views.py:300-316` | minor |
| BE-ACCT-023 | `schema.yaml` documents no request body for `me_destroy` (drf-spectacular drops bodies on DELETE), although the view requires `{"password"}` (`PasswordSerializer`). The API shape therefore exists outside `schema.yaml`, contrary to constitution Article 5.1. | `accounts/views.py:357`; `schema.yaml:1815-1838` | major |
| BE-ACCT-013 | No rate limit on reset requests or registrations; one address can be mailed repeatedly (see BE-AUTH-026). | `accounts/views.py:258-291` | major |

## Open questions

- Activation keys never expire. Should unactivated accounts or keys expire after a set time?
- Changing the e-mail in `me_partial_update` takes effect immediately, with no confirmation sent
  to the new address and no notice to the old one. Is that intended?
- Should account deletion be refused, or ask for confirmation, while the user has running jobs
  (they are deleted by cascade today)?
