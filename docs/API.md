# API Guide

This is a short orientation to the HTTP API. It does not repeat the endpoint list or exact request/
response shapes — those are the committed OpenAPI document (`schema.yaml`, kept in sync with the
code by a staleness test) and `plans/SPEC.md` §3.5/§3.6, which is the contract of record. Read one
of those for "does this endpoint exist / what does it return"; read this file for the conventions
that apply across all of them.

## Browsing the schema

- The committed OpenAPI document is `schema.yaml` at the repo root (generated with `python
  manage.py spectacular --file schema.yaml`; a test fails if it is stale relative to the code).
- A live, interactive copy (Swagger UI) is served at `/api/schema/swagger-ui/` by the running
  server; the raw document is at `/api/schema/`.

## Base path and trailing slashes

Every API endpoint is under `/api/`. Paths are canonical **with** a trailing slash (as written in
`schema.yaml`), but the slash-less form is also routed without a redirect (`core.middleware`), so
`POST /api/auth/login` and `POST /api/auth/login/` both work.

Requests and responses are JSON, except job submission (`multipart/form-data`, to carry uploaded
files) and file downloads (`GET /api/jobs/{id}/outputs/{file_id}/`, `GET /api/jobs/{id}/log/`).

## Authentication

Two schemes are accepted, checked in this order:
1. **Token** — `Authorization: Token <key>`. A user creates one at `POST /api/me/token` (the key
   is only ever returned once, at creation) and revokes it with `DELETE /api/me/token`. A password
   change or a completed password reset revokes the existing token automatically.
2. **Session + CSRF** — the mechanism the SPA uses. `GET /api/auth/me` always returns 200 (never
   401) and, as a side effect, sets the `csrftoken` cookie; every unsafe method (`POST`, `PATCH`,
   `PUT`, `DELETE`) on a session-authenticated request must carry the cookie's value in the
   `X-CSRFToken` header, including on `POST /api/auth/login` itself ("login CSRF"). A successful
   login rotates the CSRF token, so re-read the cookie after logging in.

An unauthenticated request to a protected endpoint gets **401** (`WWW-Authenticate: Token`), not
403 — 403 is reserved for an authenticated-but-not-permitted request (e.g. a non-admin calling an
admin endpoint, or an inactive account).

Login has its own error codes and a per-account lockout — see `plans/SPEC.md` §3.4 for the exact
codes (`invalid_credentials`, `account_inactive`, `account_locked`) and the lockout window
(`security.max_login_attempts` / `security.lockout_duration`, configurable — see
`docs/ADMIN_GUIDE.md`). The lockout applies identically to `/django-admin/login/`.

Admin-only endpoints (everything under `/api/admin/`) require the caller to be an admin:
`is_superuser`, `is_staff`, or a member of the `admin` group (`core.permissions.is_admin`).

## Error envelope

Every error response — validation failures, permission denials, not-found, unhandled server
errors, everything — has the same shape:

```json
{
  "error": {
    "message": "job_name: This field may not be blank.",
    "code": "invalid",
    "fields": {"job_name": ["This field may not be blank."]}
  }
}
```

- `fields` is always present (an empty object when the error isn't about specific fields).
- Nested field names are dotted, e.g. `nested.a`; a list item is `field[0]`.
- A non-field error (e.g. "not found", "queue is full") has an empty `fields` and the reason in
  `message`.
- `code` is one of DRF's standard codes (`invalid`, `not_authenticated`, `authentication_failed`,
  `permission_denied`, `not_found`, `method_not_allowed`, `throttled`, …), plus a few
  application-specific ones used where they add information a generic code wouldn't: `csrf_failed`,
  `server_error` (an unhandled exception — logged server-side with a generic public message),
  and endpoint-specific codes such as `account_locked`, `queue_full`, `maintenance`,
  `workflow_disabled`, `upload_too_large`, `cannot_delete_self`, `protected_group`. See
  `plans/SPEC.md` §3.6 for which codes a given endpoint can return.
- An unknown path under `/api/...` returns a 404 in this same envelope (not Django's HTML 404
  page).

## Pagination

List endpoints that are paginated return:

```json
{"count": 42, "next": "http://.../api/jobs/?page=2", "previous": null, "results": [...]}
```

controlled by `?page=` and `?page_size=` (default 20, max 200). A few admin list endpoints are
**not** paginated because they are always small and a client needs the whole set at once — notably
`GET /api/admin/groups/` (plain array) and `GET /api/admin/workflows/` (plain array, includes
disabled/invalid apps). `schema.yaml` is authoritative on which is which.

## Timestamps and IDs

Timestamps are ISO-8601 UTC. Job IDs are UUID strings; workflow IDs are the slug from
`cloudgene.yaml`'s `id:`; user and group IDs are integers.

## Uploads and size limits

Job submission (`POST /api/jobs/`) is `multipart/form-data`: one field named `workflow` (or
`workflow_id`), an optional `job_name`, and one field per workflow input id (a `folder`-type input
repeats the field once per file). Total upload size is capped by the admin-configured
`server.max_upload_mb` (413 `upload_too_large` beyond it); Django's own
`DATA_UPLOAD_MAX_NUMBER_FILES`/`TooManyFieldsSent`/`RequestDataTooBig` limits are mapped to the same
error envelope (413/400) rather than a bare 500 if a submission is unusually large or malformed.

## Downloads are never active content

`GET /api/jobs/{id}/outputs/{file_id}/` (optionally `?inline=1` to attempt an inline view) only
ever serves a small allowlist of content types with their real type — `text/plain`,
`image/png`, `image/jpeg`, `image/gif`, `application/pdf` (and `application/json` is served as
`text/plain`) — and only those may be `inline`. Every other type, including HTML/SVG/XML/JS or
anything unrecognised, is always sent as `application/octet-stream` with `Content-Disposition:
attachment`, regardless of `?inline=1`; every response also carries `X-Content-Type-Options:
nosniff` and `Content-Security-Policy: sandbox`. A pipeline output can never be used to run script
content on the application's own origin.

## Health check

`GET /api/health` (no auth) is meant for a load balancer / uptime check: `200` unless the database
itself is unreachable (`503`). The body reports three independent things — `db.ok`, the worker
heartbeat (`worker.ok`/`last_seen`/`age_seconds`/`pid`; stale after 30 s), and the last
`settings.yaml` load (`config.ok`/`config.errors`) — `status` is `"ok"` only when all three are
healthy, `"degraded"` when the database is fine but the worker is stale/absent or the config has a
bad key (the app is still serving requests, just running instances of a setting's default value
until the file is fixed), and `"error"` when the database check itself failed.

## Frontend HTTP layer

For anyone working on the SPA: `frontend/src/api/*.js` is the *only* place that calls the HTTP
client (`src/api/client.js`); components never call `axios`/`fetch` directly. `apiErrorMessage(err)`,
`apiFieldErrors(err)` and `apiErrorCode(err)` read the envelope above uniformly, and the client
already sends `withCredentials` + the CSRF header for session requests.
