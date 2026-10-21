# HTTP client

## Purpose

`src/api/client.js` is the single HTTP client of the SPA. It fixes how every API request is
addressed (`/api` base), authenticated (Django session cookie), protected against CSRF
(`X-CSRFToken` header), encoded (JSON or multipart) and how errors come back to the UI (one set
of helpers that read the error envelope). A 401 from any call is reported to one registered
handler so the app can drop a stale session. Keeping all of this in one module is what makes the
API modules thin and lets views treat errors uniformly.

## Scope

Covered:

- `frontend/src/api/client.js`: the axios instance, `getCookie`, request and response
  interceptors, `onUnauthorized`, `apiErrorMessage`, `apiFieldErrors`, `apiErrorCode`.
- Rules every API module (`frontend/src/api/*.js`) follows when it uses the client.

Out of scope:

- Which API-module function calls which operation: [api-contract.md](api-contract.md).
- What the router does on a 401 (store reset, redirect): [routing.md](routing.md) FE-ROUTE-030.
- The error envelope itself, error codes and status mapping:
  [../backend/api-contract.md](../backend/api-contract.md#error-envelope).
- Session, cookie and CSRF rules on the server:
  [../backend/authentication.md](../backend/authentication.md).

## Dependencies

- [../backend/api-contract.md](../backend/api-contract.md) — `Error` component, error codes,
  security schemes (`cookieAuth`, `tokenAuth`), cookies and headers.
- [../backend/authentication.md](../backend/authentication.md) — BE-AUTH-015 (CSRF on unsafe
  session requests), BE-AUTH-016 (`csrftoken` cookie on SPA pages and `auth_me_retrieve`),
  BE-AUTH-021 (401 for unauthenticated requests).
- [overview.md](overview.md) — FE-ARCH-020 to FE-ARCH-023 (only API modules use the client).
- [routing.md](routing.md) — registers the 401 handler.
- Contract component: `Error` (`schema.yaml`), returned as `default` by every operation.

## Requirements

### Addressing and authentication

- **FE-CLIENT-001** — The module MUST export exactly one axios instance (default export) with
  `baseURL: '/api'`. API modules MUST pass paths relative to it, beginning with `/` and ending
  with `/` as listed in `schema.yaml` (for example `/auth/me/`, `/jobs/${id}/status/`). Path
  segments built from data (ids, slugs, tokens, activation keys) that are not integers MUST be
  passed through `encodeURIComponent`.
- **FE-CLIENT-002** — The instance MUST send cookies (`withCredentials: true`). The SPA
  authenticates only with the Django session cookie.
- **FE-CLIENT-003** — The client MUST NOT send an `Authorization` header and MUST NOT read or
  write any credential in `localStorage`, `sessionStorage` or a non-HttpOnly cookie of its own.
  (API tokens are for non-browser clients; see BE-AUTH-019.)

### CSRF

- **FE-CLIENT-010** — Every request whose method is not `GET`, `HEAD` or `OPTIONS` MUST carry the
  header `X-CSRFToken` set to the current value of the `csrftoken` cookie, read from
  `document.cookie` at the time the request is sent (so a token rotated by login is picked up
  without a reload).
- **FE-CLIENT-011** — `GET`, `HEAD` and `OPTIONS` requests MUST NOT carry `X-CSRFToken`.
- **FE-CLIENT-012** — When no `csrftoken` cookie exists, the request MUST still be sent without the
  header; the server then answers 403 `csrf_failed` (BE-AUTH-015), which reaches the view as a
  normal error.
- **FE-CLIENT-013** — `getCookie(name)` MUST return the URI-decoded value of the named cookie, or
  `null` when it is absent or when there is no `document`.

### Request encoding

- **FE-CLIENT-020** — When the request body is a `FormData`, the client MUST remove any
  `Content-Type` header so the browser sets `multipart/form-data` with its boundary. File uploads
  (`jobs_create`) MUST be sent this way.
- **FE-CLIENT-021** — When the request body is any other object, the client MUST send it as JSON
  with `Content-Type: application/json`. Requests without a body MUST NOT get a JSON content type
  from the client.
- **FE-CLIENT-022** — An API module MAY override the response handling of one request with axios
  per-request config (for example `jobs_log_retrieve` uses `responseType: 'text'` and an identity
  `transformResponse` so log text is never parsed as JSON). It MUST NOT change `baseURL`,
  `withCredentials` or the CSRF header.

### Errors

- **FE-CLIENT-030** — Every response with a non-2xx status, and every network failure, MUST reject
  the returned promise with the axios error. The client MUST NOT resolve an error into a success
  value or show UI itself.
- **FE-CLIENT-031** — `apiErrorMessage(err, fallback)` MUST return, in this order of precedence:
  1. `fallback` when `err` is null or undefined;
  2. when there is no response: `"Cannot reach the server. Check your connection."` if
     `err.message` is `"Network Error"`, else `err.message`, else `fallback`;
  3. `data.error.message` when the body is the `Error` envelope;
  4. for non-envelope bodies (defensive only): `data.error` if it is a string, else
     `data.message` if a string, else `data.detail` if a string;
  5. `"Server error. Please try again later."` for status ≥ 500;
  6. `fallback` (default `"Something went wrong. Please try again."`).
- **FE-CLIENT-032** — `apiFieldErrors(err)` MUST return `error.fields` from the envelope (an object
  mapping field name to a list of messages) or `{}` when absent. Views MUST use it to show
  per-field errors.
- **FE-CLIENT-033** — `apiErrorCode(err)` MUST return `error.code` from the envelope or `null`.
  Views that branch on a specific failure (for example `account_locked`, `not_found`) MUST branch
  on this code, not on the message text.
- **FE-CLIENT-034** — Views, components and stores MUST read API errors only through
  FE-CLIENT-031 to FE-CLIENT-033 (constitution 5.2).
- **FE-CLIENT-035** (transitional) — While any code still reads `err.response.data.message`, the
  response interceptor MUST copy `data.error.message` to `data.message` on envelope errors that
  lack a `message`. Once no reader remains, this shim SHOULD be removed and this requirement
  withdrawn.

### 401 handling

- **FE-CLIENT-040** — `onUnauthorized(handler)` MUST register one handler (a later call replaces
  the earlier one; `null` removes it).
- **FE-CLIENT-041** — On every 401 response the client MUST call the registered handler once with
  the error, and then reject the promise as in FE-CLIENT-030.
- **FE-CLIENT-042** — The client MUST NOT navigate, reload the page or clear state on a 401 by
  itself; that is the handler's job ([routing.md](routing.md) FE-ROUTE-030). A 401 on a call that
  anonymous users may make simply rejects.

### Timeouts

- **FE-CLIENT-050** — The client currently sets no request timeout (axios default: none). API
  modules MAY set a per-request timeout; job submission uploads MUST NOT be given a timeout
  shorter than the server's upload limits allow.

## Interfaces

```js
// frontend/src/api/client.js
export default client                       // axios instance: baseURL '/api', withCredentials
export function getCookie(name): string | null
export function onUnauthorized(handler: ((err) => void) | null): void
export function apiErrorMessage(err, fallback = 'Something went wrong. Please try again.'): string
export function apiFieldErrors(err): { [field: string]: string[] }
export function apiErrorCode(err): string | null
```

Error envelope read by the helpers (component `Error` in `schema.yaml`; defined in
[../backend/api-contract.md](../backend/api-contract.md#error-envelope)):

```json
{"error": {"message": "…", "code": "…", "fields": {"<field>": ["…"]}}}
```

Headers set by the client:

| Header | When | Value |
|--------|------|-------|
| `X-CSRFToken` | method not in GET/HEAD/OPTIONS and cookie present | `csrftoken` cookie |
| `Content-Type` | body is a plain object | `application/json` |
| `Content-Type` | body is `FormData` | removed (browser sets multipart boundary) |

Typical use in a view:

```js
try { await submitJob(fd) }
catch (e) { error.value = apiErrorMessage(e); fieldErrors.value = apiFieldErrors(e) }
```

## Behaviour

Request pipeline: API-module call → request interceptor (content type, CSRF header) → axios
adapter → response interceptor.

Response interceptor on error:

1. If the body is an object with `error.message` and no `message`, copy it to `message`
   (FE-CLIENT-035).
2. If the status is 401 and a handler is registered, call it (FE-CLIENT-041).
3. Reject with the original error.

Edge cases:

- Non-JSON error bodies (an nginx 502 HTML page, a gunicorn timeout) produce "Server error.
  Please try again later." through FE-CLIENT-031 step 5.
- A 4xx with a non-envelope body and none of the legacy keys yields the caller's fallback.
- A 403 `csrf_failed` (cookie missing or expired in a long-open tab) is shown as the server's
  message `"CSRF Failed: …"`; the client does not refresh the token or retry.
- Login rotates the CSRF token server-side; because FE-CLIENT-010 reads the cookie per request,
  the next unsafe request uses the new value.
- A 401 while the store already has no user is ignored by the router's handler
  ([routing.md](routing.md) FE-ROUTE-031).

## Acceptance tests

| Requirement | Tests |
|-------------|-------|
| FE-CLIENT-001 | unit `frontend/src/test/client.test.js` › "api client" › "uses cookies and the /api base URL"; contract `frontend/src/test/contracts/jobs.test.js` › "uses the SPEC paths for detail, status, cancel, delete, log"; contract `frontend/src/test/contracts/auth.test.js` › "Session" › "me() calls GET /auth/me/ …"; (planned) unit `frontend/src/test/client.test.js` › "encodes string path segments" |
| FE-CLIENT-002 | unit `client.test.js` › "uses cookies and the /api base URL" |
| FE-CLIENT-003 | unit `client.test.js` › "never sends an Authorization token from localStorage"; unit `frontend/src/test/auth-store.test.js` › "auth store" › "boots from /auth/me exactly once …" (asserts empty localStorage) |
| FE-CLIENT-010, FE-CLIENT-011 | unit `client.test.js` › "sends X-CSRFToken from the csrftoken cookie on unsafe requests only"; e2e `e2e/tests/test_auth.py::test_login_and_logout_via_ui` (CSRF-checked login and logout through the real stack) |
| FE-CLIENT-012 | (planned) unit `client.test.js` › "sends unsafe requests without X-CSRFToken when no cookie exists" |
| FE-CLIENT-013 | unit `client.test.js` › "sends X-CSRFToken from the csrftoken cookie on unsafe requests only" (`getCookie` assertion) |
| FE-CLIENT-020 | unit `client.test.js` › "never forces a JSON content type on FormData …"; contract `frontend/src/test/contracts/jobs.test.js` › "submits multipart FormData unchanged"; e2e `e2e/tests/test_jobs.py::test_all_inputs_uploads_folder_and_write_file` |
| FE-CLIENT-021 | (planned) unit `client.test.js` › "sends plain objects as application/json" |
| FE-CLIENT-022 | contract `frontend/src/test/contracts/jobs.test.js` › "uses the SPEC paths for detail, status, cancel, delete, log" |
| FE-CLIENT-030 | unit `client.test.js` › "calls the 401 handler but does not redirect by itself" (promise rejects) |
| FE-CLIENT-031 | unit `client.test.js` › "apiErrorMessage" › "reads the SPEC §3.5 envelope", › "falls back for legacy shapes, server errors and network errors"; e2e `e2e/tests/test_auth.py::test_login_wrong_password_shows_error` |
| FE-CLIENT-032 | unit `client.test.js` › "apiErrorMessage" › "exposes field errors"; contract `frontend/src/test/contracts/auth.test.js` › "Session" › "login field errors arrive in error.fields" |
| FE-CLIENT-033 | unit `client.test.js` › "apiErrorMessage" › "reads the SPEC §3.5 envelope"; e2e `e2e/tests/test_accounts.py::test_a3_lockout` |
| FE-CLIENT-034 | (planned) unit `frontend/src/test/layering.test.js` › "no view reads err.response.data" |
| FE-CLIENT-035 | unit `client.test.js` › "mirrors the envelope message to data.message for legacy views" |
| FE-CLIENT-040, FE-CLIENT-041, FE-CLIENT-042 | unit `client.test.js` › "calls the 401 handler but does not redirect by itself" |
| FE-CLIENT-050 | (planned) contract `frontend/src/test/contracts/jobs.test.js` › "submitJob sets no short timeout" |

## Known gaps

| Requirement | Current code | Reference | Severity |
|-------------|--------------|-----------|----------|
| FE-CLIENT-001 | String ids taken from route params (job ids, workflow ids, output file ids) are interpolated without `encodeURIComponent` (`auth.js` and `server.js` do encode). A crafted deep link such as `/run/..%2Fjobs` makes `getWorkflow` request a different API path (same-origin GET only, so the effect is a confusing error, not a privilege gain). | `frontend/src/api/jobs.js:12-36`, `frontend/src/api/workflows.js:7`, `frontend/src/api/admin.js:33-52` | minor |
| FE-CLIENT-034 | Four views read `err.response?.status` directly to detect 404 instead of `apiErrorCode(err) === 'not_found'`. | `frontend/src/views/public/WorkflowSubmitView.vue:32`, `frontend/src/views/public/StaticPageView.vue:23`, `frontend/src/views/public/JobDetailView.vue:78`, `frontend/src/views/admin/AdminWorkflowSettingsView.vue:53` | minor |
| FE-CLIENT-035 | The transitional `data.message` copy is still installed, but no code reads `err.response.data.message` any more; the shim is dead and can be removed. | `frontend/src/api/client.js:51-55` | minor |
| FE-CLIENT-031 | Step 4 (legacy `data.error` string, `data.message`, `data.detail`) accepts shapes that `schema.yaml` does not allow for `/api/` errors; they hide a backend contract break instead of surfacing it. Kept as defence for non-API proxies. | `frontend/src/api/client.js:74-79` | minor |
| FE-CLIENT-012 | A missing or expired `csrftoken` cookie surfaces to users as the raw message "CSRF Failed: …" with no recovery (no re-fetch of `auth_me_retrieve` to re-seed the cookie and retry). | `frontend/src/api/client.js:31-35` | minor |
| FE-CLIENT-050 | No timeout on any request: a hung backend leaves spinners running indefinitely (polling in job detail stacks no new request until the hung one settles). | `frontend/src/api/client.js:8-13` | minor |
| — | The client comment and helpers cite "SPEC §3.5" (`plans/SPEC.md`), which `spec/` supersedes; references should point to `backend/api-contract.md`. | `frontend/src/api/client.js:63-64` | minor |

## Open questions

- Should the client set a default timeout (for example 30 s) for JSON requests, with uploads and
  log downloads exempt?
- Should a 403 `csrf_failed` trigger one automatic `auth_me_retrieve` (which re-sets the cookie)
  and a retry of the original request?
- Should the legacy-shape fallbacks in `apiErrorMessage` be removed so that a non-envelope error
  from `/api/` is treated as a contract violation (generic message plus console warning)?
