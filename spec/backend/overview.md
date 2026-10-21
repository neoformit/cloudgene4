# Backend overview

## Purpose

Describes how the Django project is assembled: the settings module, the five project apps and
what each owns, the two runtime processes (web and worker), how an HTTP request is routed
(API, SPA catch-all, JSON 404), the middleware stack, the project's own system checks and the
test runner. It is the map a sub-agent reads first to find where a behaviour lives.

## Scope

Covered:

- `cloudgene_django/settings.py` (application-level behaviour only), `cloudgene_django/urls.py`,
  `cloudgene_django/wsgi.py`, `cloudgene_django/asgi.py`
- `core/middleware.py`, `workflows/middleware.py`
- `core/views.py` routing views: `spa_index`, `api_not_found`, `csrf_failure`
- `core/checks.py`, `core/apps.py`, `core/test_runner.py`
- App `ready()` hooks: `core/apps.py`, `accounts/apps.py`, `workflows/apps.py`, `jobs/apps.py`

Out of scope (linked instead):

- Error envelope, pagination, slash and auth conventions → [api-contract.md](api-contract.md)
- Session/CSRF/token authentication, cookies, lockout → [authentication.md](authentication.md)
- `settings.yaml` → [configuration.md](configuration.md); logging config → [logging.md](logging.md)
- `HealthView` (`health`) → [server-pages-mail.md](server-pages-mail.md)
- gunicorn, nginx, systemd, env-file hardening → [../deployment/README.md](../deployment/README.md)
- The worker loop itself → [job-queue-worker.md](job-queue-worker.md)

## Dependencies

- [api-contract.md](api-contract.md) — error envelope (`Error` component), operation catalogue.
- [authentication.md](authentication.md) — DRF authentication classes and CSRF rules.
- [workflow-registry.md](workflow-registry.md) — `registry.sync_if_changed()` called by middleware.
- [configuration.md](configuration.md) — `CLOUDGENE_HOME`, `core.config`.
- [logging.md](logging.md) — `LOGGING` dict and the `cloudgene.*` loggers.
- [data-model.md](data-model.md) — models owned by each app.

## Requirements

Process and apps

- **BE-ARCH-001** The project MUST install exactly these project apps: `core`, `accounts`,
  `workflows`, `jobs`, `admin_panel`, plus `rest_framework`, `rest_framework.authtoken`,
  `drf_spectacular` and the Django contrib apps listed in Interfaces. Loading settings, every
  URL module, `cloudgene_django.wsgi` and `cloudgene_django.asgi` MUST NOT import `celery`,
  `channels`, `redis`, `corsheaders` or `django_celery_results`.
- **BE-ARCH-002** The system MUST run as two process kinds: the web process (the WSGI/ASGI
  application) and one worker process (`manage.py run_worker`). They MUST communicate only
  through the database and the `CLOUDGENE_HOME` filesystem; there is no broker or socket
  between them. Submitting a job with no worker running MUST leave it `waiting`.
- **BE-ARCH-003** App `ready()` hooks MUST only register signal receivers and system checks.
  They MUST NOT touch the database or sync the workflow registry (unsafe during `migrate`).

Routing

- **BE-ARCH-004** Any request whose path is `/api` or starts with `/api/` and that no API route
  matches MUST get HTTP 404 with the error envelope, code `not_found`. It MUST NOT get the SPA.
- **BE-ARCH-005** Any other path, except those under `/static/` and `/django-admin/`, MUST be
  served the built SPA (`static/frontend/index.html`) with status 200, header
  `Cache-Control: no-cache`, and a `csrftoken` cookie set. Access: anonymous.
- **BE-ARCH-006** If the SPA build is missing, the catch-all MUST answer 503 with an HTML page
  that names the build command (`npm run build`), instead of a server error.
- **BE-ARCH-007** An `/api/...` path without a trailing slash MUST be routed to the same view
  as the slash form when only the slash form resolves, preserving method and body (no 301/308
  redirect). Paths that already resolve, or whose slash form does not resolve, are left alone.
- **BE-ARCH-008** `/api/schema/` (OpenAPI document) and `/api/schema/swagger-ui/` MUST be
  served by drf-spectacular. Access: anonymous (drf-spectacular default `SERVE_PERMISSIONS`).
- **BE-ARCH-009** `/django-admin/` MUST serve the Django admin site, using the same
  authentication backend as the API ([authentication.md](authentication.md)).

Middleware

- **BE-ARCH-010** A non-multipart request to an `/api/` path whose `Content-Length` exceeds
  `API_JSON_BODY_MAX_MB` MiB (default 10) MUST be rejected with HTTP 413, envelope code
  `upload_too_large`, before the body is read and before authentication. Multipart requests
  and non-`/api/` paths MUST NOT be checked by this rule.
- **BE-ARCH-011** Every `/api/` request MUST call `workflows.registry.sync_if_changed()` before
  the view runs. An exception from the sync MUST be logged on `cloudgene.workflows` with a
  traceback and MUST NOT change the response.
- **BE-ARCH-012** A CSRF failure on an `/api/` path MUST return 403 with envelope code
  `csrf_failed`; on other paths a `text/plain` 403.
- **BE-ARCH-013** Every response MUST carry `X-Frame-Options: DENY`.

Framework defaults

- **BE-ARCH-014** DRF views MUST default to `IsAuthenticated`; a view open to anonymous users
  MUST opt out explicitly. An unauthenticated call to a protected view MUST get 401 with the
  error envelope (Token authentication is listed first so `WWW-Authenticate: Token` is sent).
- **BE-ARCH-015** Every DRF exception MUST pass through `core.exceptions.api_exception_handler`
  so the response uses the error envelope; an unhandled exception MUST become 500 with code
  `server_error` and no internal detail in the body.
- **BE-ARCH-016** Any 5xx response for an `/api/` path, including one raised outside a DRF view
  (middleware, URL resolution), MUST use the error envelope, not Django's HTML error page.
  (planned)
- **BE-ARCH-017** List endpoints MUST paginate with `core.pagination.StandardPagination`
  (default 20, `page_size` up to 200); shape in [api-contract.md](api-contract.md).
- **BE-ARCH-018** Datetimes MUST be stored timezone-aware in UTC (`USE_TZ=True`,
  `TIME_ZONE='UTC'`).

Settings bootstrap

- **BE-ARCH-019** `SECRET_KEY` MUST come from `DJANGO_SECRET_KEY` when set. Otherwise it MUST be
  read from `$CLOUDGENE_HOME/config/secret_key`, or generated once (`secrets.token_urlsafe(50)`) and written there with mode `0600` using exclusive create, so concurrent web and
  worker start-ups end with the same key.
- **BE-ARCH-020** Application settings (server name, queue limits, mail, Nextflow, navbar,
  installed workflows) MUST NOT be Django settings; they live in `settings.yaml`
  ([configuration.md](configuration.md)). `settings.py` holds infrastructure only.
- **BE-ARCH-021** With SQLite, the database connection MUST use a 20 s lock timeout,
  `transaction_mode=IMMEDIATE` and WAL journal mode, so web and worker can share the file.
- **BE-ARCH-022** The `INSECURE_FAST_PASSWORD_HASHING=1` switch MUST only select the MD5 hasher
  when `DEBUG` is on or `CLOUDGENE_E2E=1`; otherwise the Argon2-first hasher list applies.

System checks

- **BE-ARCH-023** Check `core.E001` (Error, always on) MUST fire for every `manage.py` command
  when `INSECURE_FAST_PASSWORD_HASHING=1` and neither `DEBUG` nor `CLOUDGENE_E2E` is set.
- **BE-ARCH-024** With `DEBUG` off, `manage.py check --deploy` MUST report: `core.W001` SQLite
  in use; `core.W002` secret key shorter than 50 chars or a known weak value; `core.W003`
  `ALLOWED_HOSTS` contains `*`; `core.W004` cookies not Secure; `core.W005` no SSL redirect;
  `core.W006` HSTS off. With `DEBUG` on, none of these MUST fire.

Tests

- **BE-ARCH-025** `manage.py test` MUST run against a temporary copy of `CLOUDGENE_HOME`
  (excluding `jobs/` and `mail/`) that is deleted afterwards, so the committed `home/` is never
  modified; the `core.config` cache MUST be cleared on entry and exit.

## Interfaces

### Apps

| App | Owns | Models ([data-model.md](data-model.md)) | URL prefixes |
|-----|------|------------------------------------------|--------------|
| `core` | config service, mail, error handler, pagination, permissions, health, server info, public pages, SPA/404 views, system checks | `WorkerHeartbeat` | `/api/health/`, `/api/server/`, `/api/pages/<slug>/` |
| `accounts` | custom user, auth views, registration, profile, tokens, admin users/groups, lockout backend | `User` | `/api/auth/…`, `/api/me/…`, `/api/admin/users/`, `/api/admin/groups/` |
| `workflows` | `cloudgene.yaml` parsing, registry, workflow APIs, admin workflow APIs | `WorkflowCategory`, `Workflow` | `/api/workflows/`, `/api/categories/`, `/api/admin/workflows/…` |
| `jobs` | submission, worker, runner, progress, outputs, job APIs | `Job`, `JobStep`, `JobMessage`, `JobOutput` | `/api/jobs/…`, `/api/admin/jobs/…` |
| `admin_panel` | dashboard, queue/maintenance switches, settings editors, pages, logs, DB log handler | `SystemLog` | `/api/admin/dashboard/`, `/api/admin/queue/…`, `/api/admin/maintenance/…`, `/api/admin/settings/…`, `/api/admin/pages/…`, `/api/admin/logs/` |

Django contrib apps: `admin`, `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`.
`AUTH_USER_MODEL = 'accounts.User'`. Operations per prefix: [api-contract.md](api-contract.md).

### Processes

| Process | Entry point | Notes |
|---------|-------------|-------|
| web | `cloudgene_django.wsgi:application` (`asgi.py` is plain HTTP, no WebSockets) | serves API, SPA, static files (WhiteNoise, finders on, no `collectstatic` needed) |
| worker | `manage.py run_worker` | single instance via `fcntl` lock on `$CLOUDGENE_HOME/config/worker.lock`; heartbeat in `WorkerHeartbeat` ([job-queue-worker.md](job-queue-worker.md)) |
| maintenance | `manage.py` commands | [management-commands.md](management-commands.md) |

### URL table (`cloudgene_django/urls.py`, order matters)

| # | Pattern | Target |
|---|---------|--------|
| 1 | `django-admin/` | Django admin |
| 2 | `api/schema/`, `api/schema/swagger-ui/` | drf-spectacular |
| 3–7 | `''` include of `core`, `accounts`, `workflows`, `jobs`, `admin_panel` urls | app APIs |
| 8 | `^api(/.*)?$` | `core.views.api_not_found` (url name `api-not-found`) |
| 9 | `^(?!static/)(?!django-admin/).*$` | `core.views.spa_index` (must stay last) |

### Middleware (in order)

| # | Class | Role |
|---|-------|------|
| 1 | `SecurityMiddleware` | SSL redirect / HSTS per env ([../deployment/README.md](../deployment/README.md)) |
| 2 | `whitenoise…WhiteNoiseMiddleware` | static files incl. the SPA bundle under `/static/frontend/` |
| 3 | `core.middleware.ApiTrailingSlashMiddleware` | BE-ARCH-007 |
| 4 | `core.middleware.JsonBodySizeLimitMiddleware` | BE-ARCH-010 |
| 5 | `SessionMiddleware` | |
| 6 | `CommonMiddleware` | `APPEND_SLASH` default; non-API only in practice (catch-all matches everything) |
| 7 | `CsrfViewMiddleware` | failures → `core.views.csrf_failure` (BE-ARCH-012) |
| 8 | `AuthenticationMiddleware` | |
| 9 | `workflows.middleware.WorkflowSyncMiddleware` | BE-ARCH-011 |
| 10 | `MessageMiddleware`, `XFrameOptionsMiddleware` | BE-ARCH-013 |

### Settings module (application-relevant values)

| Setting | Value / source |
|---------|----------------|
| `CLOUDGENE_HOME` | env `CLOUDGENE_HOME`, else `<repo>/home`, resolved to an absolute path |
| `DATABASES` | `DATABASE_URL` (dj-database-url), default `sqlite:///<repo>/db.sqlite3`; `DB_CONN_MAX_AGE` |
| `REST_FRAMEWORK` | Token then Session auth; `IsAuthenticated`; `StandardPagination`, `PAGE_SIZE=20`; `api_exception_handler`; spectacular `AutoSchema` |
| `SPECTACULAR_SETTINGS` | title `Cloudgene API`, `COMPONENT_SPLIT_REQUEST`, hooks `postprocess_schema_enums` + `core.serializers.add_error_envelope`, enum overrides `JobStatusEnum`, `WorkflowStatusEnum`, `HealthStatusEnum` |
| `SPA_INDEX_FILE` | `<repo>/static/frontend/index.html` |
| Upload limits | `FILE_UPLOAD_MAX_MEMORY_SIZE` = `DATA_UPLOAD_MAX_MEMORY_SIZE` = 10 MiB; `DATA_UPLOAD_MAX_NUMBER_FILES` env, default 10000 (per-job cap is `server.max_upload_mb`, [job-submission.md](job-submission.md)) |
| Mail fallback | `EMAIL_BACKEND` filebased into `$CLOUDGENE_HOME/mail`; effective mail config is `settings.yaml` ([server-pages-mail.md](server-pages-mail.md)) |
| `LOGGING` | [logging.md](logging.md) |
| `TEST_RUNNER` | `core.test_runner.CloudgeneTestRunner` |

A `.env` file in the repo root is loaded before settings are read. The full env-var list is in
the `settings.py` module docstring; hardening values are specified in the deployment section.

### System check IDs (`core/checks.py`)

| ID | Level | When |
|----|-------|------|
| `core.E001` | Error | always (BE-ARCH-023) |
| `core.W001`–`core.W006` | Warning | `check --deploy`, `DEBUG` off (BE-ARCH-024) |

`security.W021` (HSTS preload) is silenced while `DJANGO_HSTS_PRELOAD` is off.

## Behaviour

Request flow for `/api/...`:

1. Security/WhiteNoise.
2. Trailing-slash rewrite if `path` does not resolve to a real view but `path + '/'` does (a
   resolution to `api-not-found` counts as not resolving).
3. Body-size gate by `Content-Length` (absent or non-numeric length counts as 0).
4. Session, CSRF, authentication. DRF views are CSRF-exempt at the Django middleware level;
   CSRF is enforced by DRF's `SessionAuthentication` for session-authenticated unsafe methods
   ([authentication.md](authentication.md)).
5. Lazy registry sync (cheap `stat` calls when nothing changed).
6. View; DRF exceptions → envelope; unknown path → `api_not_found`.

Non-API paths go to WhiteNoise (static), the Django admin, or the SPA catch-all. The SPA does its
own client-side routing, including its own "not found" page.

Start-up: the web process never syncs the registry or touches the DB at import; the first API
request performs the sync. `secret_key` creation is race-safe (`O_EXCL`; the loser re-reads).

Test runner: copies `CLOUDGENE_HOME` to a temp dir, overrides `CLOUDGENE_HOME` and
`PASSWORD_HASHERS` (MD5), silences `django.request` and the `cloudgene` console handler (the DB
handler still records), and removes the temp dir at teardown.

## Acceptance tests

| Req | Test | Layer |
|-----|------|-------|
| BE-ARCH-001 | `core/tests/test_platform.py::NoCeleryChannelsTest::test_django_boots_without_celery_channels_redis` | unit |
| BE-ARCH-002 | `core/tests/test_platform.py::SubmissionWithoutWorkerTest::test_submitted_job_waits_until_the_worker_claims_it` | unit |
| BE-ARCH-003 | (planned) `core/tests/test_platform.py::AppReadyTest::test_migrate_on_empty_db_does_not_query_workflows` | unit |
| BE-ARCH-004 | `core/tests/test_api.py::MiscRoutingTest::test_unknown_api_path_is_json_404` | unit |
| BE-ARCH-005 | `core/tests/test_api.py::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`; (planned) assertion on `Cache-Control: no-cache` | unit |
| BE-ARCH-006 | `core/tests/test_api.py::MiscRoutingTest::test_spa_missing_build_message` | unit |
| BE-ARCH-007 | `core/tests/test_api.py::AuthSessionTest::test_login_me_logout_flow_without_trailing_slash` | unit |
| BE-ARCH-008 | `core/tests/test_schema.py::SchemaStalenessTest::test_platform_endpoints_documented`; (planned) anonymous GET `/api/schema/` → 200 | unit |
| BE-ARCH-009 | `accounts/tests.py::DjangoAdminLockoutTest` | unit |
| BE-ARCH-010 | `core/tests/test_deploy.py::JsonBodySizeLimitMiddlewareTest` (all four tests) | unit |
| BE-ARCH-011 | `workflows/test_registry.py::RegistrySyncTest::test_sync_if_changed_detects_settings_edit`; (planned) `WorkflowSyncMiddlewareTest::test_sync_failure_is_logged_and_request_succeeds` | unit |
| BE-ARCH-012 | `core/tests/test_api.py::AuthSessionTest::test_login_requires_csrf`, `::test_session_write_without_csrf_rejected` | unit |
| BE-ARCH-013 | (planned) `core/tests/test_deploy.py::SecurityHeadersTest::test_x_frame_options_deny` | unit |
| BE-ARCH-014 | `core/tests/test_api.py::TokenAuthTest::test_unauthenticated_protected_endpoint_is_401_envelope` | unit |
| BE-ARCH-015 | `core/tests/test_api.py::ErrorEnvelopeHandlerTest::test_unhandled_exception_becomes_500_envelope` | unit |
| BE-ARCH-016 | (planned) `core/tests/test_api.py::MiscRoutingTest::test_middleware_error_on_api_path_is_json_500` | unit |
| BE-ARCH-017 | `core/tests/test_api.py::MiscRoutingTest::test_pagination_page_size` | unit |
| BE-ARCH-018 | (planned) settings assertion test | unit |
| BE-ARCH-019 | (planned) `core/tests/test_deploy.py::SecretKeyFileTest::test_generated_once_mode_0600` | unit |
| BE-ARCH-020 | `core/tests/test_config.py::CommittedHomeTest::test_committed_settings_yaml_is_valid_and_complete` | unit |
| BE-ARCH-021 | `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest` | unit |
| BE-ARCH-022 | `core/tests/test_deploy.py::PasswordHasherTest::test_argon2_is_the_default_hasher` | unit |
| BE-ARCH-023 | `core/tests/test_deploy.py::InsecureHashingCheckTest` (all four tests) | unit |
| BE-ARCH-024 | `core/tests/test_deploy.py::DeployChecksTest` (all four tests), `::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | unit |
| BE-ARCH-025 | (planned) `core/tests/test_platform.py::TestRunnerIsolationTest::test_cloudgene_home_is_a_temp_copy` | unit |

## Known gaps

| Req | Current behaviour | Ref | Severity |
|-----|-------------------|-----|----------|
| BE-ARCH-016 | No `handler500`; an exception outside a DRF view (e.g. in middleware) on an `/api/` path returns Django's HTML 500 page. | `cloudgene_django/urls.py:17` | minor |
| BE-ARCH-008 | `/api/schema/` and `/api/schema/swagger-ui/` are `/api/` routes with no `operationId` in `schema.yaml` (`SERVE_INCLUDE_SCHEMA: False`), contrary to constitution 5.1a, and are public. | `cloudgene_django/settings.py:279`, `cloudgene_django/urls.py:9` | minor |
| BE-ARCH-010 | A request without `Content-Length` (chunked) is not checked; it falls back to Django's `DATA_UPLOAD_MAX_MEMORY_SIZE`, which reads the body first. | `core/middleware.py:61` | minor |
| BE-ARCH-011 | `WorkflowSyncMiddleware` and `csrf_failure` test `request.path`, the other middleware tests `request.path_info`; under a `SCRIPT_NAME` prefix the sync and the JSON CSRF error would not apply. | `workflows/middleware.py:20`, `core/views.py:108` | minor |
| BE-ARCH-019 | Secret-key generation is untested. | `cloudgene_django/settings.py:67` | minor |
| BE-ARCH-025 | Test-runner isolation is untested. | `core/test_runner.py:11` | minor |

## Open questions

- Should `/api/schema/` be documented in `schema.yaml` (amend 5.1a to exempt it) or be
  restricted to admins / disabled when `DEBUG` is off?
- Should the worker lock file `config/worker.lock` be listed in `.gitignore` like
  `.settings.lock`? (see [configuration.md](configuration.md#known-gaps))
