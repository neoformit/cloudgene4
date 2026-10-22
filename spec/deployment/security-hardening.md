# Security hardening

## Purpose

Defines the security posture a production Cloudgene deployment must have and how it is checked:
the project's Django system checks (`core/checks.py`) and `manage.py check --deploy`, the
security-relevant Django settings (DEBUG, hosts, HTTPS, HSTS, cookies, CSRF origins), password
hashing, how secrets on disk are protected, rate limiting, and the exposure of the Django admin
and API documentation routes. The goal is that an operator who follows the example configuration
gets a deployment where `check --deploy` is clean and no setting is left at a development default.

## Scope

Covered:

| Source | What |
|--------|------|
| `core/checks.py` | Always-on check `core.E001`; deploy checks `core.W001`–`core.W006` |
| `cloudgene_django/settings.py:61-97` | `DEBUG`, `SECRET_KEY` loading, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` |
| `cloudgene_django/settings.py:173-198` | `PASSWORD_HASHERS`, test-only hasher switch, password validators |
| `cloudgene_django/settings.py:228-255` | Cookie flags, `SECURE_*`, `X_FRAME_OPTIONS`, `SILENCED_SYSTEM_CHECKS` |
| `cloudgene_django/urls.py` | Exposure of `/django-admin/`, `/api/schema/`, `/api/schema/swagger-ui/` |
| `deploy/cloudgene.env.example` | Security-relevant variable values (lines 10-19, 33-45, 65-67) |
| `requirements.txt`, `frontend/package.json`, `frontend/package-lock.json` | Dependency pinning |
| `.gitignore` | Secrets kept out of the repository |
| `core/tests/test_deploy.py` | Tests for the above |

Out of scope (linked, not restated):

- Meaning, defaults and parsing of each environment variable, including secret key resolution
  order → [environment-config.md](environment-config.md).
- TLS, HSTS/CSP headers at the proxy, proxy headers → [reverse-proxy.md](reverse-proxy.md).
- systemd sandboxing directives → [process-management.md](process-management.md).
- gunicorn bind address and `forwarded_allow_ips`; JSON body size limit
  (`JsonBodySizeLimitMiddleware`) → [web-server.md](web-server.md).
- `$CLOUDGENE_HOME` ownership and directory modes → [cloudgene-home.md](cloudgene-home.md).
- Login lockout, session/token authentication, CSRF enforcement per request →
  [../backend/authentication.md](../backend/authentication.md).
- Who may use `/django-admin/` → [../backend/access-control.md](../backend/access-control.md).
- `settings.yaml` file mode on write → [../backend/configuration.md](../backend/configuration.md)
  (BE-CONF-015).

## Dependencies

- [environment-config.md](environment-config.md) — `DEBUG`, `DJANGO_SECRET_KEY`,
  `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DJANGO_SECURE_*`, `DJANGO_HSTS_*`,
  `DJANGO_BEHIND_TLS_PROXY`, `INSECURE_FAST_PASSWORD_HASHING`, `CLOUDGENE_E2E`.
- [reverse-proxy.md](reverse-proxy.md) — TLS termination, `X-Forwarded-Proto`, CSP.
- [process-management.md](process-management.md) — service user and sandboxing.
- [database.md](database.md) — why SQLite is warned about in production.
- [../backend/authentication.md](../backend/authentication.md) — BE-AUTH-026 (throttling, planned),
  BE-AUTH-027 (client address behind the proxy, planned).
- [api-contract.md](api-contract.md) — DEP-API-023 (forwarded headers), DEP-API-051 (env file mode).
- [../backend/overview.md](../backend/overview.md) — BE-ARCH-008/009 (schema and admin routes).
- Contract operations: none directly. Rate limiting (DEP-SEC-026) applies to `auth_login_create`,
  `auth_register_create`, `auth_password_reset_create`, `auth_password_reset_confirm`, `auth_activate_create`
  (operationIds from `schema.yaml`, see [../backend/api-contract.md](../backend/api-contract.md)).

## Requirements

System checks

- **DEP-SEC-001** `manage.py check --deploy`, run with the variables of
  `deploy/cloudgene.env.example` and DEBUG off, MUST exit 0 and report "no issues". A change to
  the example file or to the settings MUST keep this true.
- **DEP-SEC-002** Check `core.E001` MUST be an always-on check (not gated by `--deploy`), so it
  blocks every `manage.py` command (including `migrate`, `run_worker`, `collectstatic`). It MUST
  report an Error when `INSECURE_FAST_PASSWORD_HASHING=1` while DEBUG is off and `CLOUDGENE_E2E`
  is not true, and MUST report nothing otherwise.
- **DEP-SEC-003** Deploy check `core.W002` MUST warn when DEBUG is off and `SECRET_KEY` is
  shorter than 50 characters or (case-insensitively) one of `changeme`, `change-me`, `secret`,
  `insecure`, `dev`, `development`, or empty.
- **DEP-SEC-004** Deploy check `core.W003` MUST warn when DEBUG is off and `ALLOWED_HOSTS`
  contains `*`.
- **DEP-SEC-005** Deploy check `core.W004` MUST warn when DEBUG is off and either session or CSRF
  cookie is not Secure; `core.W005` when `SECURE_SSL_REDIRECT` is off; `core.W006` when
  `SECURE_HSTS_SECONDS` is 0. Each hint MUST name the environment variable that fixes it.
- **DEP-SEC-006** Deploy check `core.W001` MUST warn when DEBUG is off and the default database
  engine is SQLite.
- **DEP-SEC-007** Every deploy check (`core.W001`–`core.W006`) MUST report nothing when DEBUG is
  on.
- **DEP-SEC-008** `security.W021` (HSTS preload not set) MUST be silenced only while
  `SECURE_HSTS_PRELOAD` is off (so `check --deploy` is clean with `deploy/cloudgene.env.example`),
  MUST NOT be silenced when `DJANGO_HSTS_PRELOAD` is true, and no other system check MUST be
  silenced. Rationale: preload
  is a deliberate opt-in (DEP-SEC-012), so the check must not push operators to enable it.
- **DEP-SEC-009** The gunicorn smoke test (`scripts/smoke_gunicorn.sh`) MUST fail when
  `check --deploy` reports an Error, and SHOULD fail when it reports any Warning.

Core settings

- **DEP-SEC-010** `DEBUG` MUST default to off and MUST be on only for the values `1`, `true`,
  `yes`, `on` (case-insensitive). A production environment file MUST set it off.
- **DEP-SEC-011** `ALLOWED_HOSTS` MUST default to `localhost,127.0.0.1,[::1]` when unset. A
  production environment MUST list exactly the public host name(s). A request with any other
  `Host` header MUST get 400 (Django `DisallowedHost`) and MUST NOT reach a view.
- **DEP-SEC-012** HSTS MUST be sent by Django only when `DJANGO_HSTS_SECONDS` > 0 (sets
  `SECURE_HSTS_SECONDS`, default `0`), and only on HTTPS responses. This file owns the HSTS
  policy; nginx's part is [DEP-PROXY-005](reverse-proxy.md#hsts).
  `includeSubDomains` MUST default to on when HSTS is on (opt-out via
  `DJANGO_HSTS_INCLUDE_SUBDOMAINS=0`). `preload` MUST be off unless `DJANGO_HSTS_PRELOAD` is
  true, whatever `DJANGO_HSTS_SECONDS` is.
- **DEP-SEC-013** `SECURE_PROXY_SSL_HEADER` MUST be set (to `X-Forwarded-Proto: https`) only when
  `DJANGO_BEHIND_TLS_PROXY` is true. Reachability of the gunicorn port when it is set is governed
  by [DEP-WEB-002](web-server.md#process-and-binding).
- **DEP-SEC-014** Every response MUST carry `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and
  `Cross-Origin-Opener-Policy: same-origin` (Django `SecurityMiddleware` and clickjacking
  middleware defaults; neither may be removed from `MIDDLEWARE`).
- **DEP-SEC-015** The session cookie (`sessionid`) MUST be `HttpOnly` and `SameSite=Lax`, and
  MUST be `Secure` exactly when `DJANGO_SECURE_COOKIES` is true.
- **DEP-SEC-016** The CSRF cookie (`csrftoken`) MUST NOT be `HttpOnly` (the SPA reads it to send
  `X-CSRFToken`), MUST be `SameSite=Lax`, and MUST be `Secure` exactly when
  `DJANGO_SECURE_COOKIES` is true.
- **DEP-SEC-017** `CSRF_TRUSTED_ORIGINS` MUST default to empty when DEBUG is off and to the Vite
  dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`) only when DEBUG is on. Behind a
  TLS proxy, a same-origin unsafe request from the SPA MUST pass the CSRF origin check; this
  requires `DJANGO_BEHIND_TLS_PROXY=1` or the `https://` origin in `CSRF_TRUSTED_ORIGINS`. The
  production example MUST set both.

Passwords and secrets

- **DEP-SEC-018** `PASSWORD_HASHERS` MUST list Argon2 first, then PBKDF2, PBKDF2-SHA1, scrypt.
  A stored PBKDF2 hash MUST be re-hashed with Argon2 on the next successful login.
- **DEP-SEC-019** The MD5 test hasher MUST be used only when `INSECURE_FAST_PASSWORD_HASHING=1`
  and (DEBUG is on or `CLOUDGENE_E2E` is true). In every other case the production list
  (DEP-SEC-018) MUST be in effect, even if the variable is set.
- **DEP-SEC-020** `config/secret_key` MUST be excluded from version control (`.gitignore`). How the
  file is generated (exclusive create, mode `0600`) is owned by
  [DEP-ENV-030](environment-config.md#secret-key).
- **DEP-SEC-021** The production environment file (`/etc/cloudgene/cloudgene.env`) holds the
  secret key and database password; its owner and mode are
  [DEP-API-051](api-contract.md#filesystem) (root, `0600`, not readable by `cloudgene`). A
  deployment that runs more than one web host MUST set `DJANGO_SECRET_KEY` explicitly so all
  hosts share one key.
- **DEP-SEC-022** (planned) A deploy check MUST warn when `$CLOUDGENE_HOME/config/secret_key` or
  `$CLOUDGENE_HOME/config/settings.yaml` (which holds `mail.password` in plain text) is readable
  by group or others.

Defence in depth

- **DEP-SEC-023** The web, worker and cleanup processes MUST run as the unprivileged `cloudgene`
  user under the systemd sandbox of [DEP-PROC-001](process-management.md#common-to-all-units),
  DEP-PROC-004 and DEP-PROC-005. The application code MUST NOT be writable by them
  ([DEP-PROC-009](process-management.md#common-to-all-units)).
- **DEP-SEC-024** The Django admin at `/django-admin/` MUST accept only active staff users and
  MUST apply the same login lockout as the API
  ([../backend/authentication.md](../backend/authentication.md), BE-AUTH-007). Deployments SHOULD
  restrict `/django-admin/` at the reverse proxy to administrator networks, since the SPA admin
  area covers normal administration.
- **DEP-SEC-025** `/api/schema/` and `/api/schema/swagger-ui/` are public (BE-ARCH-008). They
  MUST NOT disclose data beyond the API description. Swagger UI loads its JavaScript from a
  third-party CDN by default (drf-spectacular `SWAGGER_UI_DIST`); how the CSP treats this route is
  [DEP-PROXY-024](reverse-proxy.md#requirements).
- **DEP-SEC-026** (planned) Until BE-AUTH-026 is implemented, the reference nginx configuration
  MUST rate-limit the anonymous auth endpoints (`/api/auth/login/`, `/api/auth/register/`,
  `/api/auth/password-reset/`, `/api/auth/password-reset/<token>/`, `/api/auth/activate/<key>/`, and
  `/django-admin/login/`) per client IP with `limit_req`, answering excess requests with 429.
  After BE-AUTH-026 lands, nginx SHOULD keep this as an outer limit. The exact directives belong
  in [reverse-proxy.md](reverse-proxy.md).

Dependencies

- **DEP-SEC-027** `requirements.txt` MUST pin every direct Python dependency to an exact version
  (`==`), including `argon2-cffi` (required by DEP-SEC-018).
- **DEP-SEC-028** The frontend MUST be built from the committed `frontend/package-lock.json`
  (`npm ci`), so the `^` ranges in `package.json` do not float in production builds.
- **DEP-SEC-029** (planned) `scripts/test.sh unit` SHOULD run a dependency vulnerability audit
  (`pip-audit -r requirements.txt` and `npm audit --omit=dev`) and report findings.

## Interfaces

### Project system checks (`core/checks.py`)

| ID | Kind | Runs | Condition (DEBUG off unless stated) | Fix named in hint |
|----|------|------|--------------------------------------|-------------------|
| `core.E001` | Error | every command | `INSECURE_FAST_PASSWORD_HASHING=1`, DEBUG off, `CLOUDGENE_E2E` not true | unset the variable |
| `core.W001` | Warning | `--deploy` | DB engine is SQLite | `DATABASE_URL=postgres://…` |
| `core.W002` | Warning | `--deploy` | `SECRET_KEY` < 50 chars or a known weak value | `DJANGO_SECRET_KEY` or generated file |
| `core.W003` | Warning | `--deploy` | `*` in `ALLOWED_HOSTS` | `ALLOWED_HOSTS` |
| `core.W004` | Warning | `--deploy` | session or CSRF cookie not Secure | `DJANGO_SECURE_COOKIES=1` |
| `core.W005` | Warning | `--deploy` | no SSL redirect | `DJANGO_SECURE_SSL_REDIRECT=1`, `DJANGO_BEHIND_TLS_PROXY=1` |
| `core.W006` | Warning | `--deploy` | `SECURE_HSTS_SECONDS` = 0 | `DJANGO_HSTS_SECONDS` |

Django's own `security.W0xx` deploy checks also run; `core.W002`–`W006` overlap them on purpose
(same thresholds, project-specific hints). Silenced: `security.W021` only, only while preload is
off (`settings.py:250-255`).

### Effective security settings

| Setting | Value | Source |
|---------|-------|--------|
| `SESSION_COOKIE_HTTPONLY` | `True` | fixed |
| `SESSION_COOKIE_SAMESITE`, `CSRF_COOKIE_SAMESITE` | `'Lax'` | fixed |
| `CSRF_COOKIE_HTTPONLY` | `False` | fixed (SPA reads `csrftoken`) |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | env | `DJANGO_SECURE_COOKIES` |
| `SECURE_SSL_REDIRECT` | env | `DJANGO_SECURE_SSL_REDIRECT` |
| `SECURE_HSTS_SECONDS` | env, default 0 | `DJANGO_HSTS_SECONDS` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | env, default = HSTS on | `DJANGO_HSTS_INCLUDE_SUBDOMAINS` |
| `SECURE_HSTS_PRELOAD` | env, default off | `DJANGO_HSTS_PRELOAD` |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` or unset | `DJANGO_BEHIND_TLS_PROXY` |
| `X_FRAME_OPTIONS` | `'DENY'` | fixed |
| `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`, `SECURE_CROSS_ORIGIN_OPENER_POLICY` | Django defaults (`True`, `'same-origin'`, `'same-origin'`) | not set |
| `CSRF_FAILURE_VIEW` | `core.views.csrf_failure` | fixed |
| `PASSWORD_HASHERS` | Argon2, PBKDF2, PBKDF2-SHA1, scrypt | fixed |
| `AUTH_PASSWORD_VALIDATORS` | Django's four default validators | fixed |

### Production checklist (values in `deploy/cloudgene.env.example`)

```
DEBUG=False
DJANGO_SECRET_KEY=<≥50 random chars>
ALLOWED_HOSTS=<public host>
CSRF_TRUSTED_ORIGINS=https://<public host>
DJANGO_SECURE_COOKIES=1
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_BEHIND_TLS_PROXY=1
DJANGO_HSTS_SECONDS=31536000
DJANGO_HSTS_PRELOAD=0
# never: INSECURE_FAST_PASSWORD_HASHING, CLOUDGENE_E2E
```

### Secrets on disk

| File | Holds | Required mode | Enforced by |
|------|-------|---------------|-------------|
| `/etc/cloudgene/cloudgene.env` | secret key, DB password | root, `0600` (DEP-API-051) | operator only |
| `$CLOUDGENE_HOME/config/secret_key` | generated secret key | `0600` | `settings.py:81` on create |
| `$CLOUDGENE_HOME/config/settings.yaml` | `mail.password` | `0600` | not enforced (BE-CONF-015) |
| `/etc/letsencrypt/live/<host>/privkey.pem` | TLS key | certbot default | certbot |

## Behaviour

Deploy flow. After editing the environment file the operator runs
`manage.py check --deploy` as the service user. `core.E001` fires on any command, so a leaked
test switch stops `migrate` before gunicorn starts. Deploy warnings do not stop anything; they
are the operator's checklist.

HTTPS behind nginx. nginx terminates TLS and sends `X-Forwarded-Proto: $scheme`. With
`DJANGO_BEHIND_TLS_PROXY=1`, `request.is_secure()` is true, so `SECURE_SSL_REDIRECT` does not
loop, HSTS is emitted, and Django's CSRF origin check compares `Origin: https://host` with an
`https` request. Without it, the origin check passes only if the origin is in
`CSRF_TRUSTED_ORIGINS`, and `SECURE_SSL_REDIRECT=1` would redirect forever.

Secret key. Resolution order is in [environment-config.md](environment-config.md). Rotating
`DJANGO_SECRET_KEY` logs out every session and invalidates outstanding password-reset links;
there is no `SECRET_KEY_FALLBACKS` support.

Rate limiting. The application has per-account lockout only and sees every client as the
proxy's address, so a per-IP limit can only be applied at nginx today (DEP-SEC-026). How the
planned DRF throttle must find the real client address is
[BE-AUTH-027](../backend/authentication.md#requirements). nginx's 429 body is not the API error
envelope; the SPA shows its generic error for it.

CSP. Requirements and the current gap: [DEP-PROXY-021, DEP-PROXY-022, DEP-PROXY-023,
DEP-PROXY-024](reverse-proxy.md#requirements).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-SEC-001 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-SEC-002 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e` | unit |
| DEP-SEC-002 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_e2e_flag_set` | unit |
| DEP-SEC-002 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_debug` | unit |
| DEP-SEC-002 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_flag_unset` | unit |
| DEP-SEC-003 | `core/tests/test_deploy.py::DeployChecksTest::test_secret_key_weak_warning` | unit |
| DEP-SEC-004 | `core/tests/test_deploy.py::DeployChecksTest::test_allowed_hosts_wildcard_warning` | unit |
| DEP-SEC-005 | `core/tests/test_deploy.py::DeployChecksTest::test_secure_transport_warnings` | unit |
| DEP-SEC-006 | `core/tests/test_deploy.py::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit |
| DEP-SEC-007 | `core/tests/test_deploy.py::DeployChecksTest::test_sqlite_warning_only_when_debug_off` (W001 only); (planned) `core/tests/test_deploy.py::DeployChecksTest::test_all_deploy_checks_silent_in_debug` | unit |
| DEP-SEC-008 | (planned) `core/tests/test_deploy.py::SilencedChecksTest::test_w021_silenced_only_without_preload` | config |
| DEP-SEC-008 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-SEC-008 | (planned) `core/tests/test_deploy.py::HstsPreloadDefaultTest::test_w021_not_silenced_when_preload_on` | unit |
| DEP-SEC-009 | (planned) `scripts/smoke_gunicorn.sh` step "manage.py check --deploy" failing on errors | smoke |
| DEP-SEC-010 | (planned) `core/tests/test_deploy.py::DebugDefaultTest::test_debug_off_unless_truthy` | config |
| DEP-SEC-011 | (planned) `core/tests/test_deploy.py::AllowedHostsTest::test_unknown_host_is_400` | unit |
| DEP-SEC-012 | `core/tests/test_deploy.py::HstsPreloadDefaultTest::test_preload_off_by_default_even_with_hsts_seconds_set` | config |
| DEP-SEC-012 | `core/tests/test_deploy.py::HstsPreloadDefaultTest::test_preload_on_only_with_explicit_env_var` | config |
| DEP-SEC-012 | (planned) `core/tests/test_deploy.py::HstsPreloadDefaultTest::test_include_subdomains_follows_hsts_seconds` | unit |
| DEP-SEC-013 | (planned) `core/tests/test_deploy.py::ProxySslHeaderTest::test_header_trusted_only_with_env_flag` | config |
| DEP-SEC-014 | (planned) `core/tests/test_deploy.py::SecurityHeadersTest::test_default_security_headers` | unit |
| DEP-SEC-015 | (planned) `core/tests/test_deploy.py::CookieFlagsTest::test_session_cookie_flags` | unit |
| DEP-SEC-016 | `core/tests/test_api.py::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie` (cookie set only); (planned) `core/tests/test_deploy.py::CookieFlagsTest::test_csrf_cookie_flags` | unit |
| DEP-SEC-017 | (planned) `e2e/tests/test_deploy_tls.py::test_spa_login_behind_tls_proxy_passes_csrf` | e2e |
| DEP-SEC-018 | `core/tests/test_deploy.py::PasswordHasherTest::test_argon2_is_the_default_hasher` | unit |
| DEP-SEC-018 | `core/tests/test_deploy.py::PasswordHasherTest::test_pbkdf2_hash_is_upgraded_to_argon2_on_login` | unit |
| DEP-SEC-019 | (planned) `core/tests/test_deploy.py::InsecureHasherSettingTest::test_md5_ignored_without_debug_or_e2e` | config |
| DEP-SEC-020 | (planned) `core/tests/test_deploy.py::GitignoreTest::test_secret_key_ignored` | config |
| DEP-SEC-021 | — host obligation (multi-host deployments only); manual verification: `DJANGO_SECRET_KEY` is set and identical in every host's env file; (planned) covered by DEP-SEC-022's check once it also inspects `EnvironmentFile` | — |
| DEP-SEC-022 | (planned) `core/tests/test_deploy.py::DeployChecksTest::test_secret_files_permission_warning` | unit |
| DEP-SEC-023 | (planned) `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_run_unprivileged_and_sandboxed` | config |
| DEP-SEC-024 | `accounts/tests.py::DjangoAdminLockoutTest::test_locked_account_rejected_with_correct_password` | unit |
| DEP-SEC-024 | `e2e/tests/test_findings_security.py::test_b01_django_admin_login_bypasses_lockout` | e2e |
| DEP-SEC-025 | `e2e/tests/test_findings_security.py::test_permission_matrix_public` | e2e |
| DEP-SEC-026 | (planned) `core/tests/test_deploy_files.py::NginxExampleTest::test_auth_endpoints_rate_limited` | config |
| DEP-SEC-027 | (planned) `core/tests/test_harness_scripts.py::RequirementsPinTest::test_all_requirements_pinned` | config |
| DEP-SEC-028 | (planned) `core/tests/test_harness_scripts.py::RequirementsPinTest::test_package_lock_committed` | config |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-SEC-026 | No rate limiting anywhere: not in DRF (BE-AUTH-026) and not in the example nginx config. Password spraying across accounts and mail flooding via register/reset are unlimited. | `deploy/nginx.conf.example:43-54`; `cloudgene_django/settings.py:260-274` | major |
| DEP-SEC-022 | `settings.yaml` is created `0644` (holds `mail.password`); no check warns about secret file modes. | `core/config.py:377`; `core/checks.py` | major |
| DEP-SEC-023 | The code checkout is writable by the services. Details: [DEP-PROC-009 gap](process-management.md#known-gaps). | `deploy/systemd/cloudgene-web.service:25`, `cloudgene-worker.service:26`, `cloudgene-cleanup.service:21` | major |
| DEP-SEC-009 | The smoke test runs `check --deploy` with `|| true` and only prints the output; errors never fail it. | `scripts/smoke_gunicorn.sh:51` | minor |
| DEP-SEC-020 | If a second process loses the exclusive-create race and reads the file before the winner has written it, it gets an empty key (`settings.py:83` returns `read_text().strip()` unchecked) and fails to start. | `cloudgene_django/settings.py:80-86` | minor |
| DEP-SEC-025 | Swagger UI pulls JS/CSS from a public CDN at view time; this is a third-party script dependency and blocks a strict CSP. | `cloudgene_django/urls.py:10`; `cloudgene_django/settings.py:276-290` (no `SWAGGER_UI_DIST`) | minor |
| DEP-SEC-029 | No dependency audit, Dependabot or CI job exists; updates are manual. Transitive Python dependencies are not pinned (no lock file or hashes). | `requirements.txt`; `scripts/test.sh` | minor |

## Open questions

1. Should `/django-admin/` stay enabled in production at all, given the SPA admin area? If yes,
   should the reference nginx config restrict it by IP (DEP-SEC-024)?
2. Should `/api/schema/swagger-ui/` be admin-only or disabled when DEBUG is off, or should
   Swagger UI assets be self-hosted (drf-spectacular-sidecar) so a strict CSP is possible?
3. (Settled) CSP is emitted by Django: [DEP-PROXY-022](reverse-proxy.md#requirements).
4. Should the app support `SECRET_KEY_FALLBACKS` (e.g. `DJANGO_SECRET_KEY_FALLBACKS`) for
   key rotation without logging everyone out?
5. `docs/DEPLOYMENT.md` says `check --deploy` "must report no issues", but the smoke test
   ignores its result (DEP-SEC-009). Which is intended?
