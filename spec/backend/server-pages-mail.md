# Server info, pages, maintenance, health and mail

## Purpose

This area holds the public, non-workflow surface of the server: the server info the SPA needs on
every page (service name, navbar for the current viewer, footer, maintenance banner), the HTML
pages kept in `$CLOUDGENE_HOME/pages`, the effects of maintenance mode, the `/api/health`
liveness/readiness probe, serving the SPA's `index.html` for non-API routes, and outgoing e-mail
configured from `settings.yaml`.

## Scope

| Source | What |
|--------|------|
| `core/server_views.py` | `server_info`, `pages_retrieve`, navbar filtering |
| `core/views.py` | `health`, `spa_index`, `api_not_found`, `csrf_failure` |
| `core/urls.py`, `cloudgene_django/urls.py` (catch-all routes only) | Routing of the above |
| `core/mail.py` | Mail connection and `send_mail` |
| `core/models.py` (`WorkerHeartbeat.status`, `STALE_AFTER`) | Heartbeat staleness as reported by health |

Out of scope (linked instead):

- Editing settings, navbar and pages, and the mail test endpoint: [admin-api.md](admin-api.md).
- `settings.yaml` keys (`server.*`, `mail.*`, `navbar`) and page file helpers: [configuration.md](configuration.md).
- Who writes the heartbeat and how often: [job-queue-worker.md](job-queue-worker.md).
- Submission rejection in maintenance mode (the rule's home): [job-submission.md](job-submission.md).
- Which e-mails accounts send (activation, password reset): [accounts.md](accounts.md).
- Error envelope, trailing-slash middleware, JSON body limit: [api-contract.md](api-contract.md), [overview.md](overview.md).
- CSRF cookie semantics: [authentication.md](authentication.md).
- How the SPA renders pages and the banner: `spec/frontend/`.
- nginx/static file serving in production: `spec/deployment/`.

## Dependencies

- [api-contract.md](api-contract.md): `server_info`, `pages_retrieve`, `health` operations and the error envelope.
- [configuration.md](configuration.md): `load_settings`, `get`, `config_status`, `read_page`, `cloudgene_home`.
- [access-control.md](access-control.md): `is_admin()` (navbar filtering, maintenance exemption).
- [job-queue-worker.md](job-queue-worker.md): `WorkerHeartbeat.beat()` once per worker tick.

## Requirements

### Server info

- **BE-SRV-001** `server_info` MUST be available to anyone (anonymous, user, admin) and return `name`, `url`, `maintenance`, `maintenance_message` and `footer_html` from the current settings, plus `navbar`.
- **BE-SRV-002** `navbar` MUST contain the configured items in stored order, minus items with `admin_only: true` when the viewer is not an admin and items with `auth_only: true` when the viewer is anonymous. Each item MUST have all five keys (`title`, `url`, `icon`, `admin_only`, `auth_only`), missing ones filled with defaults. Navbar filtering is presentation only; it MUST NOT be relied on for access control.
- **BE-SRV-003** `footer_html` MUST be the content of `pages/footer.html`, or `""` if the file is missing.
- **BE-SRV-004** A settings change saved by an admin MUST be visible in the next `server_info` response from any web process without a restart (settings are re-read when the file changes).

### Pages

- **BE-SRV-010** `pages_retrieve` MUST be available to anyone and return `{slug, html}` with the content of `$CLOUDGENE_HOME/pages/<slug>.html`.
- **BE-SRV-011** The slug MUST match `^[a-z0-9][a-z0-9_-]{0,63}$`. A slug that does not match (path traversal, `/`, `.`, upper case, encoded separators) MUST return 404 `not_found` — the same answer as a missing page — and MUST NOT read any file outside `pages/`.
- **BE-SRV-012** Page and footer HTML MUST be returned exactly as stored, without sanitising or escaping. This HTML is trusted: only admins can write it ([admin-api.md](admin-api.md) BE-ADM-001, BE-ADM-065), and the SPA renders it as HTML. No user-supplied (non-admin) data MAY be inserted into page HTML by the backend.
- **BE-SRV-013** `home` and `footer` are expected pages. A missing `home` page MUST yield 404 on `pages_retrieve` (the SPA then shows its default home), not a 500.

### Maintenance mode

- **BE-SRV-020** While `server.maintenance` is true, job submission by non-admins MUST be rejected with 503 `maintenance` and the maintenance message ([job-submission.md](job-submission.md)). Admins MAY still submit.
- **BE-SRV-021** Maintenance mode MUST NOT stop running jobs, stop the worker from claiming waiting jobs, block login, or block read access to jobs and outputs. Stopping new work is done by pausing the queue ([admin-api.md](admin-api.md) BE-ADM-012).
- **BE-SRV-022** `server_info` MUST report `maintenance` and `maintenance_message` to every viewer so the SPA can show a banner.

### Health

- **BE-SRV-030** `health` MUST be available without authentication (no session or token is read) and MUST NOT require CSRF.
- **BE-SRV-031** `health` MUST check the database with a trivial query. If it fails, the response MUST be 503 with `status: "error"` and `db.ok: false`, and the error MUST be logged at ERROR with traceback.
- **BE-SRV-032** If the database is reachable, the response MUST be 200. `status` MUST be `"ok"` when the worker heartbeat is fresh and `settings.yaml` is valid, else `"degraded"`.
- **BE-SRV-033** `worker` MUST report `{ok, last_seen, age_seconds, pid}` for the `default` worker. `ok` MUST be true only if a heartbeat exists and is at most 30 seconds old. With no heartbeat row, `ok` is false and the other fields are null.
- **BE-SRV-034** `config` MUST report `{ok, errors[]}` for the last load of `settings.yaml`, each error as `"<dotted.key>: <message>"`. An invalid or unparseable `settings.yaml` MUST be reported here and MUST NOT make `health` (or the site) fail.
- **BE-SRV-035** The 503 response of `health` MUST be described in `schema.yaml` with the `Health` component (it is not the error envelope).

### SPA and fallbacks

- **BE-SRV-040** Any GET to a path that is not under `/api/`, `/static/` or `/django-admin/` MUST return the built SPA `index.html` with status 200 and `Cache-Control: no-cache`, and MUST set the `csrftoken` cookie.
- **BE-SRV-041** If the SPA build is missing, those paths MUST return 503 with a short HTML page explaining how to build the frontend.
- **BE-SRV-042** Any `/api/` path that matches no route MUST return 404 with the JSON error envelope (`not_found`), never the SPA.
- **BE-SRV-043** A CSRF failure MUST return 403: the JSON envelope with code `csrf_failed` under `/api/`, plain text elsewhere.

### Mail

- **BE-SRV-050** All outgoing mail MUST go through `core.mail.send_mail`, which reads `mail.*` from `settings.yaml` at send time, so a saved change applies to the next message without a restart.
- **BE-SRV-051** `mail.backend` MUST select delivery: `smtp` (host, port, user, password, `use_tls`/`use_ssl`, 30-second timeout; empty user/password means no authentication), `file` (one file per message in `mail.file_path`, relative paths resolved against `$CLOUDGENE_HOME`; the directory is created if missing), or `console` (written to stdout).
- **BE-SRV-052** The sender address MUST be `mail.from_email`.
- **BE-SRV-053** When Django's test runner has switched `EMAIL_BACKEND` to the in-memory backend, `send_mail` MUST use it regardless of `settings.yaml`, so tests never send real mail.
- **BE-SRV-054** A delivery failure MUST raise to the caller (unless the caller passes `fail_silently=True`); each caller decides the user-facing outcome ([accounts.md](accounts.md), [admin-api.md](admin-api.md) BE-ADM-054).
- **BE-SRV-055** The SMTP password MUST NOT be logged or returned by any API.

## Interfaces

| operationId | Method, path | Access | Source |
|-------------|--------------|--------|--------|
| `server_info` | GET `/api/server/` | anyone | `core/server_views.py` `ServerInfoView` |
| `pages_retrieve` | GET `/api/pages/{slug}/` | anyone | `core/server_views.py` `PublicPageView` |
| `health` | GET `/api/health/` | anyone, no auth | `core/views.py` `HealthView` |

Non-API routes (not in `schema.yaml`):

| Route | Handler | Response |
|-------|---------|----------|
| `^api(/.*)?$` not matched earlier | `core.views.api_not_found` | 404 envelope `not_found` |
| `^(?!static/)(?!django-admin/).*$` | `core.views.spa_index` | 200 `index.html` / 503 build hint |
| CSRF failure (`CSRF_FAILURE_VIEW`) | `core.views.csrf_failure` | 403 envelope or text |

Python interface (`core/mail.py`):

```python
get_connection(mail_settings=None, fail_silently=False)  # Django connection for mail.* settings
from_email() -> str                                       # mail.from_email
send_mail(subject, message, recipient_list, *, html_message=None, fail_silently=False) -> int
```

Health response (shape is the `Health` component in `schema.yaml`):

```json
{"status": "ok|degraded|error", "db": {"ok": true},
 "worker": {"ok": true, "last_seen": "…", "age_seconds": 1.2, "pid": 123},
 "config": {"ok": true, "errors": []}}
```

## Behaviour

**Health state table.**

| DB reachable | Worker fresh | Config valid | HTTP | `status` |
|--------------|--------------|--------------|------|----------|
| no | — (reported false) | as loaded | 503 | `error` |
| yes | yes | yes | 200 | `ok` |
| yes | no | any | 200 | `degraded` |
| yes | any | no | 200 | `degraded` |

The worker writes its heartbeat every tick (default 1 s), so a 30 s staleness window tolerates a
slow tick but flags a stopped worker within half a minute. Load balancers SHOULD use the HTTP
status (DB only); monitoring SHOULD alert on `status != "ok"`.

**Navbar filtering** (`core/server_views.py:40`). Admin = `is_admin(user)`; authenticated =
`user.is_authenticated`. An `admin_only` item is shown only to admins; an `auth_only` item only to
logged-in users; an item with both needs an admin.

**Maintenance.** The flag and message are plain settings. Entering maintenance from the admin
dashboard can also set a new message ([admin-api.md](admin-api.md)). The only server-side
enforcement is in submission; everything else is the banner.

**Mail file backend.** Messages land as `.log` files under `$CLOUDGENE_HOME/mail` by default; this
is the default backend, so a fresh install never tries to reach an SMTP server.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| BE-SRV-001, 003, 022 | `admin_panel/tests/test_api.py::ServerInfoTest::test_public_server_info`; `e2e/tests/test_smoke.py::test_footer_renders_footer_template` | unit, e2e |
| BE-SRV-002 | `admin_panel/tests/test_api.py::NavbarTest::test_round_trip_and_public_filtering`; `e2e/tests/test_smoke.py::test_navbar_items_from_yaml_in_order` | unit, e2e |
| BE-SRV-004 | `e2e/tests/test_admin_settings.py::test_d5_general_settings_round_trip`, `::test_d6_navbar_editor` | e2e |
| BE-SRV-010 | `admin_panel/tests/test_api.py::PagesTest::test_public_page`; `e2e/tests/test_smoke.py::test_about_page_renders_pages_file` | unit, e2e |
| BE-SRV-011 | `admin_panel/tests/test_api.py::PagesTest::test_public_page_traversal_rejected`; `e2e/tests/test_admin_settings.py::test_d6_traversal_slugs_rejected` | unit, e2e |
| BE-SRV-012 | `e2e/tests/test_smoke.py::test_home_renders_home_template`; `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer` | e2e |
| BE-SRV-013 | `e2e/tests/test_smoke.py::test_unknown_page_shows_not_found`; missing `home` returns 404 (planned unit) | unit, e2e |
| BE-SRV-020 | `jobs/tests/test_api.py::SubmissionTest::test_maintenance_blocks_users_not_admins`; `e2e/tests/test_queue.py::test_maintenance_blocks_users_not_admins` | unit, e2e |
| BE-SRV-021 | worker claims and login during maintenance (planned unit, `jobs/tests/test_worker.py`) | unit |
| BE-SRV-030–034 | `core/tests/test_api.py::HealthTest::test_health_without_worker`, `::test_health_reports_a_broken_settings_file`, `::test_health_with_fresh_and_stale_heartbeat`, `::test_health_db_down`; `e2e/tests/test_findings_admin.py::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e |
| BE-SRV-035 | contract test of the 503 body against `Health` (planned) | contract |
| BE-SRV-040–042 | `core/tests/test_api.py::MiscRoutingTest::test_spa_catch_all_sets_csrf_cookie`, `::test_spa_missing_build_message`, `::test_unknown_api_path_is_json_404`; `e2e/tests/test_deep_links.py::test_user_route_deep_link_and_refresh` | unit, e2e |
| BE-SRV-043 | `core/tests/test_api.py::AuthSessionTest::test_session_write_without_csrf_rejected`; non-API plain-text branch (planned) | unit |
| BE-SRV-050–052 | `admin_panel/tests/test_api.py::MailSettingsTest::test_send_test_mail_to_admin`; `e2e/tests/test_admin_settings.py::test_d5_mail_test_lands_in_outbox` | unit, e2e |
| BE-SRV-053 | all mail-sending unit tests rely on it (e.g. `accounts/tests.py::RegistrationTest::test_register_sends_activation_mail_and_stores_hashed_key`) | unit |
| BE-SRV-054 | SMTP failure propagates (planned unit, mocked connection) | unit |
| BE-SRV-055 | `admin_panel/tests/test_api.py::MailSettingsTest::test_password_write_only`; no-password-in-logs check (planned) | unit |
| all operations | schema-validated contract tests for `server_info`, `pages_retrieve`, `health` (planned, Article 5.1d) | contract |

## Known gaps

| ID | What the code does | Where | Severity |
|----|--------------------|-------|----------|
| BE-SRV-035 | `health` returns the `Health` body with 503 when the DB is down, but `schema.yaml` documents only 200 and a `default` Error envelope, so the 503 body contradicts the contract. | `core/views.py:72`, `schema.yaml` `/api/health/` | major |
| BE-SRV-031 | The DB error is logged on logger `core.views`, which is outside `cloudgene.*`, so it does not reach Admin → Logs (moot while the DB is down, but inconsistent with [logging.md](logging.md)). | `core/views.py:17`, `core/views.py:57` | minor |
| BE-SRV-034 | `health` is public and returns the full `settings.yaml` validation messages (key names and values' errors) to anonymous callers. Low risk, but more than a probe needs. | `core/views.py:59-71` | minor |
| BE-SRV-012 | Page/footer HTML is rendered with `v-html` on the app origin with no Content-Security-Policy; a compromised admin account can run script in every visitor's browser. By design (plans/QA_FINDINGS.md I-2, I-3). | `core/server_views.py:67`, `core/server_views.py:82` | minor |
| BE-SRV-054 | SMTP sends happen synchronously in web requests (registration, password reset, mail test) with a 30 s timeout; a slow SMTP server ties up a web worker. | `core/mail.py:32` | minor |
| BE-SRV-021, 043, 054 | No tests for maintenance not affecting the worker, the non-API CSRF text branch, or SMTP failure propagation. | — | minor |

## Open questions

1. Should `health` hide `config.errors` from anonymous callers and show only `ok`?
2. Should maintenance mode also pause the queue, or stay banner + submission block only?
3. Should mail be sent asynchronously (e.g. by the worker) to avoid blocking web requests?
