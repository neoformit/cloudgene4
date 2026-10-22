# Environment configuration

## Purpose

Cloudgene takes its infrastructure configuration (debug mode, secret key, hosts, database,
`CLOUDGENE_HOME`, TLS behaviour, logging, upload caps, gunicorn tuning) from environment
variables, and its application configuration from `settings.yaml`. This file specifies how each
environment variable is loaded, parsed and validated, what it means, what it defaults to in
development and production, how the secret key is created when none is given, and what happens
when a production value is missing. The list of variables with their consumers is in
[api-contract.md](api-contract.md#environment-variables); this file does not repeat it.

## Scope

| Source | Covered |
|--------|---------|
| `cloudgene_django/settings.py` (module docstring and code) | `.env` loading, `env_bool`, `env_list`, every variable read, secret key |
| `core/middleware.py:15` | `API_JSON_BODY_MAX_MB` |
| `core/checks.py` | how env values are judged by system checks (`core.E001`, `core.W001`–`W006`) |
| `core/config.py:290` | `CLOUDGENE_HOME` fallback outside Django |
| `core/management/commands/create_admin.py:33` | `CLOUDGENE_ADMIN_PASSWORD` |
| `deploy/gunicorn.conf.py` | `GUNICORN_*` parsing |
| `deploy/cloudgene.env.example` | the production template |

Out of scope: `settings.yaml` ([../backend/configuration.md](../backend/configuration.md));
`config/nextflow.env` ([workflow-runtime.md](workflow-runtime.md)); the meaning of each
`check --deploy` warning and the hardening values to choose
([security-hardening.md](security-hardening.md)); gunicorn tuning choices
([web-server.md](web-server.md)); test-harness variables ([test-harness.md](test-harness.md)).

## Dependencies

- [api-contract.md](api-contract.md) — variable table (DEP-API-003), change rule (DEP-API-001),
  env loading for one-off commands (DEP-API-005).
- [../backend/overview.md](../backend/overview.md) — BE-ARCH-019 (secret key source and
  creation), BE-ARCH-021 (SQLite options), BE-ARCH-022 (insecure hasher switch).
- [../backend/logging.md](../backend/logging.md) — what `LOG_LEVEL`/`LOG_FORMAT` control.
- [../backend/job-runner.md](../backend/job-runner.md) — BE-RUN-019 (worker environment passed
  to workflow processes).
- [security-hardening.md](security-hardening.md) — `check --deploy`.

## Requirements

### Loading

- **DEP-ENV-001** Settings MUST resolve each variable in this order: the process environment,
  then `<repo>/.env` (`BASE_DIR/.env`, loaded once at settings import with `override=False`),
  then the code default. A value in the process environment MUST win over the same key in
  `.env`.
- **DEP-ENV-002** In production all values MUST come from `/etc/cloudgene/cloudgene.env` via
  `EnvironmentFile=`. A `.env` file in `/opt/cloudgene` SHOULD NOT exist in production; if it
  does, it can add variables that are absent from the env file. One-off `manage.py` commands
  need the same values ([DEP-API-005](api-contract.md#environment) and its gap).
- **DEP-ENV-003** `GUNICORN_*` variables MUST be set in the process environment. They MUST NOT
  be expected to work from `.env`, because `deploy/gunicorn.conf.py` is evaluated before Django
  settings load `.env`.
- **DEP-ENV-004** `cloudgene.env` MUST use only syntax that both systemd `EnvironmentFile=` and
  python-dotenv read the same way: one `KEY=VALUE` per line, `#` comments on their own line, no
  `export` prefix, no spaces around `=`, no inline comments, no `$` in values.

### Parsing

- **DEP-ENV-010** Boolean variables (`DEBUG`, `DJANGO_SECURE_COOKIES`,
  `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_BEHIND_TLS_PROXY`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`,
  `DJANGO_HSTS_PRELOAD`, `CLOUDGENE_E2E`) MUST be true exactly when the value, stripped and
  lower-cased, is `1`, `true`, `yes` or `on`. Unset or empty MUST mean the default. Any other
  value (including `0`, `false`, `no` and typos) MUST mean false.
- **DEP-ENV-011** List variables (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) MUST be split on
  `,`, with each item stripped and empty items dropped. Unset MUST mean the default list; set
  but empty MUST mean an empty list.
- **DEP-ENV-012** Integer variables read by settings or middleware (`DB_CONN_MAX_AGE`,
  `DJANGO_HSTS_SECONDS`, `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES`, `API_JSON_BODY_MAX_MB`) MUST
  stop process start-up when the value is not an integer (including an empty value), with an
  error that names the variable.
- **DEP-ENV-013** Integer `GUNICORN_*` variables MUST stop gunicorn start-up with an error that
  names the variable when the value is not an integer. (planned)
- **DEP-ENV-014** `INSECURE_FAST_PASSWORD_HASHING` MUST be on only for the exact value `1`.
  It MUST select the MD5 hasher only when `DEBUG` is on or `CLOUDGENE_E2E` is true
  (BE-ARCH-022); otherwise every `manage.py` command MUST fail with `core.E001`.

### Semantics

- **DEP-ENV-020** `DEBUG` MUST default to off. With `DEBUG` off: the `core.W001`–`W006` deploy
  checks run, `CSRF_TRUSTED_ORIGINS` defaults to empty, whitenoise autorefresh is off, and the
  insecure hasher switch is refused.
- **DEP-ENV-021** `CLOUDGENE_HOME` MUST be resolved to an absolute path at settings import
  (relative values against the working directory, `/opt/cloudgene` under systemd). Empty MUST
  mean unset, which selects `<repo>/home`.
- **DEP-ENV-022** `DATABASE_URL` MUST be a URL understood by dj-database-url; unset MUST select
  SQLite at `<repo>/db.sqlite3`. Reserved characters in the password MUST be percent-encoded.
  `DB_CONN_MAX_AGE` (seconds, default `0` = close after each request) MUST be applied to
  whichever database is selected. For SQLite the BE-ARCH-021 options MUST be added.
- **DEP-ENV-023** (withdrawn — see [DEP-SEC-012](security-hardening.md#requirements) for the
  `DJANGO_HSTS_*` variables and [DEP-SEC-008](security-hardening.md#requirements) for
  `security.W021`)
- **DEP-ENV-024** `DJANGO_BEHIND_TLS_PROXY` true MUST set `SECURE_PROXY_SSL_HEADER =
  ('HTTP_X_FORWARDED_PROTO', 'https')`; false MUST leave it unset (DEP-API-021).
- **DEP-ENV-025** `DJANGO_SECURE_COOKIES` MUST set both `SESSION_COOKIE_SECURE` and
  `CSRF_COOKIE_SECURE`. `DJANGO_SECURE_SSL_REDIRECT` MUST set `SECURE_SSL_REDIRECT`.
- **DEP-ENV-026** `LOG_LEVEL` MUST be upper-cased and used for the console handler, the root
  logger and the `django` logger; an unknown level MUST stop start-up. `LOG_FORMAT=json`
  (case-insensitive) MUST select the JSON formatter; any other value MUST select the text
  formatter ([../backend/logging.md](../backend/logging.md)).
- **DEP-ENV-027** `API_JSON_BODY_MAX_MB` (default 10) MUST set the JSON body cap and
  `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES` MUST set `DATA_UPLOAD_MAX_NUMBER_FILES` (default
  10000). What each limit rejects, and with which response, is owned by
  [DEP-WEB-035 and DEP-WEB-036](web-server.md#upload-size-chain).
- **DEP-ENV-028** `EMAIL_BACKEND` (default file backend into `CLOUDGENE_HOME/mail`) and
  `DEFAULT_FROM_EMAIL` (default `noreply@localhost`) MUST affect only code that calls
  `django.core.mail` directly; application mail MUST use `settings.yaml` `mail.*`
  ([../backend/server-pages-mail.md](../backend/server-pages-mail.md)).
- **DEP-ENV-029** `CLOUDGENE_ADMIN_PASSWORD` MUST be used by `create_admin` only when
  `--password` is not given. It SHOULD be passed only to that one command and MUST NOT be stored
  in `cloudgene.env`, because the worker passes its whole environment to workflow processes
  (BE-RUN-019).

### Secret key

- **DEP-ENV-030** The secret key MUST be chosen as specified in BE-ARCH-019:
  `DJANGO_SECRET_KEY` if set and non-empty, else the content of
  `CLOUDGENE_HOME/config/secret_key`, else a new `secrets.token_urlsafe(50)` value written to
  that file with exclusive create and mode `0600`. Creating the file MUST create
  `CLOUDGENE_HOME/config/` if needed. This requirement is the single home of secret-key
  generation and its file mode.
- **DEP-ENV-031** Without `DJANGO_SECRET_KEY`, the web, worker and cleanup processes MUST
  resolve the same `CLOUDGENE_HOME` so they read the same file. If two processes create the
  file at the same time, both MUST end with the key that was written first.
- **DEP-ENV-032** If the key file exists but is empty, start-up MUST either write a new key or
  fail with a message that names the file. (planned)
- **DEP-ENV-033** If `CLOUDGENE_HOME/config/` cannot be created or the key file cannot be
  written, start-up MUST fail (non-zero exit) rather than run without a key.
- **DEP-ENV-034** `manage.py check --deploy` MUST warn (`core.W002`) when, with `DEBUG` off, the
  key is shorter than 50 characters or is one of `changeme`, `change-me`, `secret`,
  `insecure`, `dev`, `development`. It MUST also warn when the key equals the placeholder in
  `deploy/cloudgene.env.example`. (planned for the placeholder)

### Missing or unsafe production values

- **DEP-ENV-040** No variable MAY be made hard-required by `settings.py`: a missing variable
  MUST fall back to its default so that development works with no environment. Production
  safety MUST instead come from `manage.py check --deploy` (warnings `core.W001`–`W006`, Django's
  `security.*`) and the always-on error `core.E001`, with the consequences listed in the
  [missing-value table](#missing-value-consequences).
- **DEP-ENV-041** With `DEBUG` off, `check --deploy` SHOULD warn when `CLOUDGENE_HOME` is inside
  the repository checkout. (planned)

### Example file

- **DEP-ENV-050** `deploy/cloudgene.env.example` MUST contain every variable of the
  [api-contract.md](api-contract.md#environment-variables) table except test-only variables,
  each either set or commented out with its default, and each with a comment that states what it
  does. "never in prod" variables MUST appear only commented out, under a warning.
- **DEP-ENV-051** `manage.py check --deploy` MUST exit 0 and print `no issues` when run with
  exactly the variables set in `deploy/cloudgene.env.example`.

## Interfaces

### Parsing helpers (`cloudgene_django/settings.py`)

```
env_bool(name, default=False) -> bool   # unset/'' → default; '1','true','yes','on' → True; else False
env_list(name, default=()) -> list[str] # unset → list(default); else comma-split, stripped, non-empty
```

`core/checks.py:_env_true(name)` uses the same true set, with unset/empty meaning false.
`deploy/gunicorn.conf.py:_int_env(name, default)` returns the default when the value is not an
integer.

### Values by environment

| Variable | Parse | Dev default (`DEBUG` on, no env) | Production value (`cloudgene.env.example`) |
|----------|-------|----------------------------------|--------------------------------------------|
| `DEBUG` | bool | (must be set to `1` for dev) | `False` |
| `DJANGO_SECRET_KEY` | string | generated file | long random value |
| `ALLOWED_HOSTS` | list | `localhost,127.0.0.1,[::1]` | `cloudgene.example.org` |
| `CSRF_TRUSTED_ORIGINS` | list | `http://localhost:5173,http://127.0.0.1:5173` | `https://cloudgene.example.org` |
| `DATABASE_URL` | URL | `sqlite:///<repo>/db.sqlite3` | `postgres://cloudgene:…@127.0.0.1:5432/cloudgene` |
| `DB_CONN_MAX_AGE` | int (s) | `0` | `60` |
| `CLOUDGENE_HOME` | path | `<repo>/home` | `/var/lib/cloudgene` |
| `LOG_LEVEL` | level name | `INFO` | `INFO` |
| `LOG_FORMAT` | `json` or other | `standard` | `json` |
| `DJANGO_SECURE_COOKIES` | bool | off | `1` |
| `DJANGO_SECURE_SSL_REDIRECT` | bool | off | `1` |
| `DJANGO_BEHIND_TLS_PROXY` | bool | off | `1` |
| `DJANGO_HSTS_SECONDS` | int (s) | `0` | `31536000` |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | bool | = HSTS on | (commented; default on) |
| `DJANGO_HSTS_PRELOAD` | bool | off | `0` |
| `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES` | int | `10000` | `10000` |
| `API_JSON_BODY_MAX_MB` | int (MB) | `10` | `10` |
| `EMAIL_BACKEND` | dotted path | file backend → `CLOUDGENE_HOME/mail` | SMTP backend |
| `DEFAULT_FROM_EMAIL` | string | `noreply@localhost` | `noreply@cloudgene.example.org` |
| `GUNICORN_*` | int / string | see [api-contract.md](api-contract.md#environment-variables) | commented, defaults |
| `INSECURE_FAST_PASSWORD_HASHING` | exact `1` | unset | commented, never set |
| `CLOUDGENE_E2E` | bool | unset | commented, never set |

### Missing-value consequences

With `DEBUG` off and the variable unset:

| Variable | Result | Detected by |
|----------|--------|-------------|
| `DJANGO_SECRET_KEY` | key generated in `CLOUDGENE_HOME/config/secret_key`; fine on one host | — |
| `ALLOWED_HOSTS` | only `localhost`, `127.0.0.1`, `[::1]` accepted; every public request gets 400 | first request |
| `CSRF_TRUSTED_ORIGINS` | same-origin requests still pass while HTTPS is detected correctly; if HTTPS detection is wrong (proxy header not trusted), every unsafe request (login included) gets 403 `csrf_failed` | first login |
| `DATABASE_URL` | SQLite file `/opt/cloudgene/db.sqlite3`, empty until migrated | `core.W001` |
| `CLOUDGENE_HOME` | `/opt/cloudgene/home`: runtime data and admin edits go into the git checkout (`settings.yaml`, pages are tracked files) | nothing (DEP-ENV-041 planned) |
| `DJANGO_SECURE_COOKIES` | cookies without `Secure` | `core.W004` |
| `DJANGO_SECURE_SSL_REDIRECT` | plain HTTP not redirected by Django (nginx still redirects port 80) | `core.W005` |
| `DJANGO_BEHIND_TLS_PROXY` | HTTPS detected only through gunicorn's `forwarded_allow_ips` | nothing |
| `DJANGO_HSTS_SECONDS` | no HSTS header | `core.W006` |
| `LOG_FORMAT` | text logs in journald | — |

## Behaviour

**Start-up sequence.** `manage.py`/`wsgi.py` set `DJANGO_SETTINGS_MODULE` if absent → settings
import → `load_dotenv(BASE_DIR/'.env')` → `DEBUG` → `CLOUDGENE_HOME` → secret key (may create
`config/secret_key`) → hosts, database, security, upload, mail, logging values. Any exception in
this sequence (bad integer, unknown log level, unparseable `DATABASE_URL`, unwritable
`CLOUDGENE_HOME`) aborts the process before it serves or claims anything; systemd then restarts
it every 5 s and the reason is in journald. For `manage.py` commands, Django then runs system
checks; `core.E001` stops every command.

**Secret key file.** With exclusive create, the first process to start writes the key; a
process that loses the race reads the winner's file. With `preload_app` on, gunicorn imports
settings once in the master, so all web workers share the key. Changing the key (or switching
between the file and `DJANGO_SECRET_KEY`) logs every user out (session authentication hashes
are keyed by it). Activation and password-reset links are random tokens stored hashed in the
database, and DRF tokens are stored in the database, so both stay valid. The file is part of `CLOUDGENE_HOME` backups ([cloudgene-home.md](cloudgene-home.md)).

**Where variables travel.** The worker's whole environment, including the secret key and the
database URL, reaches Nextflow and command steps (BE-RUN-019 gap). Until that is fixed, keep
one-off secrets such as `CLOUDGENE_ADMIN_PASSWORD` out of `cloudgene.env`.

**DEBUG on a production host.** Turning `DEBUG` on disables the deploy checks, re-enables the
Vite origins in `CSRF_TRUSTED_ORIGINS` (when that variable is unset), allows the MD5 hasher
switch and shows Django error pages; it MUST NOT be used to debug a live installation.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-ENV-001 | `core/tests/test_settings_env.py::DotenvTest::test_process_env_wins_over_dotenv` (planned) | unit |
| DEP-ENV-002 | — host obligation; manual verification: `test ! -e /opt/cloudgene/.env` and `systemctl show -p EnvironmentFiles cloudgene-web cloudgene-worker` names `/etc/cloudgene/cloudgene.env` | — |
| DEP-ENV-003 | `core/tests/test_deploy_files.py::GunicornConfigTest::test_reads_only_process_env` (planned) | config |
| DEP-ENV-004 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` (parses the file with the `KEY=VALUE` pattern) | config |
| DEP-ENV-010 | `core/tests/test_settings_env.py::ParsingTest::test_env_bool_values` (planned) | unit |
| DEP-ENV-011 | `core/tests/test_settings_env.py::ParsingTest::test_env_list_values` (planned) | unit |
| DEP-ENV-012 | `core/tests/test_settings_env.py::ParsingTest::test_bad_integer_names_variable` (planned) | unit |
| DEP-ENV-013 | `core/tests/test_deploy_files.py::GunicornConfigTest::test_bad_integer_fails` (planned) | config |
| DEP-ENV-014 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_error_when_set_outside_debug_and_e2e` | unit |
| DEP-ENV-014 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_e2e_flag_set` | unit |
| DEP-ENV-014 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_debug` | unit |
| DEP-ENV-014 | `core/tests/test_deploy.py::InsecureHashingCheckTest::test_clean_when_flag_unset` | unit |
| DEP-ENV-020 | `core/tests/test_deploy.py::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit |
| DEP-ENV-021 | `core/tests/test_settings_env.py::ParsingTest::test_cloudgene_home_resolution` (planned) | unit |
| DEP-ENV-022 | `core/tests/test_settings_env.py::ParsingTest::test_database_url_and_conn_max_age` (planned) | unit |
| DEP-ENV-024 | `core/tests/test_settings_env.py::ParsingTest::test_behind_tls_proxy_sets_header` (planned) | unit |
| DEP-ENV-025 | `core/tests/test_deploy.py::DeployChecksTest::test_secure_transport_warnings` | unit |
| DEP-ENV-026 | `core/tests/test_deploy.py::JsonFormatterTest::test_produces_valid_json_with_expected_keys` | unit |
| DEP-ENV-027 | `core/tests/test_deploy.py::JsonBodySizeLimitMiddlewareTest::test_rejects_oversized_json_body_by_content_length_alone` | unit |
| DEP-ENV-027 | `core/tests/test_deploy.py::JsonBodySizeLimitMiddlewareTest::test_exempts_multipart_regardless_of_content_length` | unit |
| DEP-ENV-028 | `core/tests/test_settings_env.py::MailSettingsTest::test_email_backend_env_does_not_change_app_mail` (planned; today only inspected: `core/mail.py` builds its connection from `settings.yaml`) | unit |
| DEP-ENV-029 | `core/tests/test_commands.py::CreateAdminTest::test_password_from_env` (planned) | unit |
| DEP-ENV-030 | `core/tests/test_settings_env.py::SecretKeyTest::test_generated_key_file_mode_0600` (planned) | unit |
| DEP-ENV-031 | `core/tests/test_settings_env.py::SecretKeyTest::test_concurrent_start_shares_key` (planned) | unit |
| DEP-ENV-032 | `core/tests/test_settings_env.py::SecretKeyTest::test_empty_key_file_is_replaced_or_named_in_error` (planned) | unit |
| DEP-ENV-033 | `core/tests/test_settings_env.py::SecretKeyTest::test_unwritable_home_fails_start` (planned) | unit |
| DEP-ENV-034 | `core/tests/test_deploy.py::DeployChecksTest::test_secret_key_weak_warning` | unit |
| DEP-ENV-034 | `core/tests/test_deploy.py::DeployChecksTest::test_example_placeholder_key_warns` (planned) | unit |
| DEP-ENV-040 | `core/tests/test_deploy.py::DeployChecksTest::test_sqlite_warning_only_when_debug_off` | unit |
| DEP-ENV-040 | `core/tests/test_deploy.py::DeployChecksTest::test_allowed_hosts_wildcard_warning` | unit |
| DEP-ENV-040 | `core/tests/test_deploy.py::DeployChecksTest::test_secure_transport_warnings` | unit |
| DEP-ENV-050 | `core/tests/test_deploy_files.py::EnvContractTest::test_every_env_read_is_in_env_example` (planned) | config |
| DEP-ENV-051 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-ENV-034 | The placeholder `DJANGO_SECRET_KEY` in the example file is 84 characters and not in the weak list, so `check --deploy` passes when an operator copies the example and forgets to replace it. The key is public (it is in the repository), so sessions and reset links could be forged. | `deploy/cloudgene.env.example:17`, `core/checks.py:58-61` | major |
| DEP-ENV-012 | Integer variables are parsed with a bare `int()`: a bad or empty value (e.g. `DJANGO_HSTS_SECONDS=`) aborts start-up with `ValueError: invalid literal for int()` that does not name the variable. | `cloudgene_django/settings.py:158`, `:237`, `:301`; `core/middleware.py:15` | minor |
| DEP-ENV-013 | `_int_env` silently falls back to the default on a bad value (e.g. `GUNICORN_WORKERS=four` runs the default worker count). | `deploy/gunicorn.conf.py:15-19` | minor |
| DEP-ENV-032 | An existing but empty `config/secret_key` makes `_load_secret_key` try to create the file, lose the exclusive create, and return the empty content; Django then refuses to start (`SECRET_KEY must not be empty`) until the file is deleted. | `cloudgene_django/settings.py:72-83` | minor |
| DEP-ENV-041 | Nothing warns when `CLOUDGENE_HOME` is unset in production; runtime data and admin edits then modify tracked files in the checkout, and the next `git pull` may conflict. | `cloudgene_django/settings.py:64`, `core/checks.py` | minor |
| DEP-ENV-027 | `API_JSON_BODY_MAX_MB` above 10 has no effect: Django's fixed `DATA_UPLOAD_MAX_MEMORY_SIZE` (10 MiB) still rejects larger non-multipart bodies. | `cloudgene_django/settings.py:296`, `core/middleware.py:15` | minor |
| DEP-ENV-050 | The example file omits `CLOUDGENE_ADMIN_PASSWORD` and nine `GUNICORN_*` variables (listed in [api-contract.md](api-contract.md#known-gaps)). | `deploy/cloudgene.env.example` | minor |
| DEP-ENV-029 | `CLOUDGENE_ADMIN_PASSWORD`, if put in `cloudgene.env`, reaches every workflow process. Tracked as BE-RUN-019. | `jobs/runner.py:118` | major (BE-RUN-019) |

## Open questions

1. `deploy/cloudgene.env.example:12` says `DJANGO_SECRET_KEY` is "Required in production";
   `docs/DEPLOYMENT.md` §2, the `core.W002` hint and the code treat it as optional on a single
   host. Which is the rule? This spec follows the code (optional on one host).
2. Should `settings.py` refuse to start with `DEBUG` off and no `DATABASE_URL` or
   `CLOUDGENE_HOME`, instead of relying on `check --deploy` warnings (DEP-ENV-040)?
3. Should the worker strip application variables (`DJANGO_*`, `DATABASE_URL`, `EMAIL_*`,
   `CLOUDGENE_ADMIN_PASSWORD`) before starting workflow processes? (Owned by
   [../backend/job-runner.md](../backend/job-runner.md) BE-RUN-019.)
