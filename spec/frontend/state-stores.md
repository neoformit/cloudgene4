# State stores

## Purpose

The SPA keeps a small amount of app-wide state in Pinia stores: who is logged in (`auth`), the
public server configuration that drives the app shell (`server`), and a job-list cache (`jobs`).
Stores call API-module functions, never the HTTP client directly, and hold no credentials. This
file fixes each store's state, actions, which operations they call, when they load, and when
they refresh.

## Scope

Covered:

- `frontend/src/stores/auth.js` (`useAuthStore`)
- `frontend/src/stores/server.js` (`useServerStore`)
- `frontend/src/stores/jobs.js` (`useJobsStore`)
- Store initialisation order across `main.js`, `App.vue` and the router guard.

Out of scope:

- Components that render store state (navbar, footer, maintenance banner):
  [layout-navigation.md](layout-navigation.md).
- Route guards that read the auth store: [routing.md](routing.md).
- View-local state (forms, lists, polling): the view spec files.
- Server behaviour of the operations called: linked under Dependencies.

## Dependencies

- [api-client.md](api-client.md) — errors reach stores as rejected promises (FE-CLIENT-030).
- [overview.md](overview.md) — FE-ARCH-013 (`App.vue` triggers server loads), FE-ARCH-023
  (layering).
- [routing.md](routing.md) — FE-ROUTE-010 (guard awaits `boot()`), FE-ROUTE-030 (401 handler calls
  `_clear()`).
- [api-contract.md](api-contract.md) — API-module function ↔ operationId mapping.
- [../backend/authentication.md](../backend/authentication.md) — `auth_me_retrieve` (BE-AUTH-014),
  `auth_login_create` (BE-AUTH-001 to BE-AUTH-007), `auth_logout_create` (BE-AUTH-013).
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — `server_info`
  (BE-SRV-001 to BE-SRV-004, BE-SRV-022).
- [../backend/jobs-api.md](../backend/jobs-api.md) — `jobs_list`, `jobs_retrieve`.
- Contract operations and components: `auth_me_retrieve` → `Me`; `auth_login_create` →
  `LoginResponse`; `auth_logout_create` → `Message`; `server_info` → `ServerInfo`;
  `jobs_list` → `PaginatedJobListList`; `jobs_retrieve` → `JobDetail`.

## Requirements

### General

- **FE-STORE-001** — Stores MUST obtain data only through functions in `frontend/src/api/*.js`
  (constitution 5.1f) and MUST NOT persist any state in `localStorage`, `sessionStorage` or
  IndexedDB. State lives for one page load.

### Auth store (`auth`)

- **FE-STORE-002** — `boot()` MUST call `refresh()` (one `auth_me_retrieve` request) the first
  time it is called. Calls made while that request is in flight MUST share its promise. After it
  settles, `booted` MUST be `true` and later `boot()` calls MUST resolve immediately with the
  current user without a request.
- **FE-STORE-003** — `refresh()` MUST call `auth_me_retrieve` (`authApi.me`) and set `user` to the
  response `user` when `authenticated` is `true`, else to `null`. It MUST resolve with the new
  `user`.
- **FE-STORE-004** — If `auth_me_retrieve` fails (network error or any error status), `refresh()`
  MUST set `user` to `null` and resolve; it MUST NOT reject or block navigation.
- **FE-STORE-005** — `isLoggedIn` MUST be `true` exactly when `user` is non-null. `isAdmin` MUST be
  `true` exactly when `user.is_admin` is `true`. These getters are the only source of
  logged-in/admin state for the router and views.
- **FE-STORE-006** — `login(username, password)` MUST call `auth_login_create` (`authApi.login`).
  On success it MUST set `user` to the response `user` and `booted` to `true`, and resolve with
  that user. On failure it MUST reject with the original error and leave `user` unchanged, so the
  view can show `apiErrorMessage` / `apiErrorCode` (`invalid_credentials`, `account_inactive`,
  `account_locked`).
- **FE-STORE-007** — `logout()` MUST call `auth_logout_create` (`authApi.logout`) and MUST set
  `user` to `null` whether the call succeeds or fails. A failure MUST still reject so the caller
  can report it.
- **FE-STORE-008** — `_clear()` MUST set `user` to `null` without any request. It is used when
  the server has already ended the session (401, FE-ROUTE-030; account deleted on the profile
  page).
- **FE-STORE-009** — `updateUser(user)` MUST replace `user` with the given object without a
  request. Callers MUST pass an object that has at least the `User` component fields (`id`,
  `username`, `is_admin`, …).
- **FE-STORE-010** — A change of `user.id` (including to or from `null`) MUST cause the server
  store to reload (FE-STORE-023).

### Server store (`server`)

- **FE-STORE-020** — Before the first successful load, the state MUST be: `name: 'Cloudgene'`,
  `url: ''`, `maintenance: false`, `maintenanceMessage: ''`, `navbar: []`, `footerHtml: ''`,
  `loaded: false`, `error: null`. The app shell MUST render with these defaults.
- **FE-STORE-021** — `load()` MUST call `server_info` (`getServerInfo`) and, on success, copy
  `name`, `url`, `maintenance`, `maintenance_message` → `maintenanceMessage`, `navbar` (or `[]`)
  and `footer_html` → `footerHtml` (or `''`), then set `loaded: true` and `error: null`.
- **FE-STORE-022** — `load()` MUST NOT send a request when `loaded` is `true`; `load(true)` MUST
  always send one.
- **FE-STORE-023** — `load(true)` MUST be called whenever the logged-in user changes (the navbar is
  filtered per viewer, BE-SRV-002) and after an admin action that changes server info: saving
  general settings, toggling maintenance, saving the `footer` page.
- **FE-STORE-024** — If `server_info` fails, `load()` MUST keep the previous values, set `error`
  to the error and leave `loaded` unchanged; it MUST NOT reject. The next `load()` call retries.
- **FE-STORE-025** — The store MUST hold `footerHtml` exactly as received. Rendering it as HTML is
  allowed only because the backend guarantees it is admin-authored trusted HTML (BE-SRV-012); the
  rendering rule is owned by [layout-navigation.md](layout-navigation.md).

### Jobs store (`jobs`)

- **FE-STORE-030** — `fetchJobs(page = 1, stateFilter = this.stateFilter)` MUST call `jobs_list`
  (`listJobs`) with `{page}` plus `{state}` when `stateFilter` is non-empty, then set `jobs` to
  `results`, `total` to `count`, `currentPage` and `stateFilter`, and resolve with `jobs`. Errors
  MUST reject unchanged.
- **FE-STORE-031** — `refreshJob(id)` MUST call `jobs_retrieve` (`getJob`), replace the matching
  entry in `jobs` if present, and resolve with the response.
- **FE-STORE-032** — A store that no view or component uses MUST NOT be kept. Either
  `JobListView` uses the jobs store, or the store is removed and FE-STORE-030/031 are withdrawn.

## Interfaces

### `useAuthStore` (`frontend/src/stores/auth.js`)

| Member | Kind | Notes |
|--------|------|-------|
| `user` | state | `User` component from `schema.yaml`, or `null` |
| `booted` | state | `true` once the first `auth_me_retrieve` has settled or a login succeeded |
| `_bootPromise` | state | internal: in-flight boot |
| `isLoggedIn`, `isAdmin` | getters | FE-STORE-005 |
| `boot()` | action | → `Promise<User|null>`; `auth_me_retrieve` once |
| `refresh()` | action | → `Promise<User|null>`; `auth_me_retrieve` |
| `login(username, password)` | action | → `Promise<User>`; `auth_login_create` |
| `logout()` | action | → `Promise<void>`; `auth_logout_create` |
| `_clear()` | action | local reset |
| `updateUser(user)` | action | local replace |

Users: router guard and 401 handler, `App.vue`, `AppNavbar`, `LoginView`, `HomeView`,
`ProfileView`, `JobDetailView`, `AdminUsersView`.

### `useServerStore` (`frontend/src/stores/server.js`)

| Member | Kind | From `ServerInfo` |
|--------|------|-------------------|
| `name` | state | `name` |
| `url` | state | `url` |
| `maintenance` | state | `maintenance` |
| `maintenanceMessage` | state | `maintenance_message` |
| `navbar` | state | `navbar` (`ServerNavbarItem[]`) |
| `footerHtml` | state | `footer_html` |
| `loaded`, `error` | state | load bookkeeping |
| `load(force = false)` | action | `server_info` |

Users: `App.vue`, `AppNavbar`, `AppFooter`, `MaintenanceBanner`, `AdminDashboardView`,
`GeneralSettingsView`, `PagesView`.

### `useJobsStore` (`frontend/src/stores/jobs.js`)

| Member | Kind | Notes |
|--------|------|-------|
| `jobs`, `total`, `currentPage`, `stateFilter` | state | last fetched page |
| `fetchJobs(page, stateFilter)` | action | `jobs_list` |
| `refreshJob(id)` | action | `jobs_retrieve` |

Users: none.

## Behaviour

### Initialisation order on a page load

1. `main.js`: `app.use(createPinia())`, then `app.use(router)`; the router module registers
   the 401 handler. `app.mount('#app')`.
2. The router's initial navigation runs the guard, which calls `auth.boot()` →
   `auth_me_retrieve`. No view renders until it settles.
3. `App.vue` `onMounted` calls `server.load()` → `server_info`, concurrently with step 2 (both
   requests carry the session cookie, so both see the same viewer).
4. When boot sets a user, `user.id` changes from `null` and `App.vue` calls `server.load(true)`:
   a second `server_info` request.

### Refresh rules

| Event | Auth store | Server store |
|-------|-----------|--------------|
| Page load | `boot()` once | `load()` once |
| Login | `user` from login response | `load(true)` (user id changed) |
| Logout (navbar) | `user = null` | `load(true)` |
| Any 401 with a user set | `_clear()` | `load(true)` |
| Profile saved | `updateUser(profile)` | — (user id unchanged) |
| Account deleted | `_clear()` | `load(true)` |
| Admin saves general settings / toggles maintenance / saves `footer` page | — | `load(true)` |

The auth store never polls. A session that ends on the server is noticed only on the next API
call that returns 401. Settings changed by another admin are seen only after a reload or one of
the events above.

### Failure behaviour

- `auth_me_retrieve` failing at boot makes the app run as anonymous for the rest of the page load;
  protected routes redirect to login (FE-STORE-004).
- `server_info` failing leaves the default name `Cloudgene`, an empty navbar and no footer; no
  error is shown to the user (FE-STORE-024).
- `logout()` rejecting after clearing `user`: `AppNavbar` awaits it before `router.push('/')`, so
  on failure the user is logged out locally but stays on the current page
  ([layout-navigation.md](layout-navigation.md)).

## Acceptance tests

| Requirement | Tests |
|-------------|-------|
| FE-STORE-001 | unit `frontend/src/test/auth-store.test.js` › "auth store" › "boots from /auth/me exactly once, even with concurrent callers" (localStorage stays empty), › "login stores the returned user; logout clears it even if the call fails"; (planned) unit `frontend/src/test/layering.test.js` › "stores import only API modules" |
| FE-STORE-002 | unit `auth-store.test.js` › "auth store" › "boots from /auth/me exactly once, even with concurrent callers" |
| FE-STORE-003, FE-STORE-004 | unit `auth-store.test.js` › "auth store" › "anonymous and failing /me both mean logged out"; contract `frontend/src/test/contracts/auth.test.js` › "Session" › "me() calls GET /auth/me/ and accepts both anonymous and authenticated shapes" |
| FE-STORE-005 | unit `auth-store.test.js` › "auth store" › "login stores the returned user; logout clears it even if the call fails"; unit `auth-store.test.js` › "router guards" › "sends non-admins away from admin routes" |
| FE-STORE-006 | unit `auth-store.test.js` › "auth store" › "login stores the returned user; …"; e2e `e2e/tests/test_auth.py::test_login_and_logout_via_ui`, `::test_login_wrong_password_shows_error`; (planned) unit `auth-store.test.js` › "failed login rejects and keeps user unchanged" |
| FE-STORE-007 | unit `auth-store.test.js` › "auth store" › "login stores the returned user; logout clears it even if the call fails"; e2e `e2e/tests/test_auth.py::test_login_and_logout_via_ui` |
| FE-STORE-008 | e2e `e2e/tests/test_accounts.py::test_a6_delete_own_account`; (planned) unit `auth-store.test.js` › "_clear resets the user without a request" |
| FE-STORE-009 | e2e `e2e/tests/test_accounts.py::test_a5_profile_name_email_password_token`; (planned) unit `auth-store.test.js` › "updateUser replaces the user" |
| FE-STORE-010, FE-STORE-023 | e2e `e2e/tests/test_auth.py::test_admin_sees_admin_link_regular_user_does_not`; e2e `e2e/tests/test_smoke.py::test_navbar_items_from_yaml_in_order`; (planned) unit `frontend/src/test/app.test.js` › "reloads server info when the user id changes" |
| FE-STORE-020, FE-STORE-024 | unit `frontend/src/test/server-store.test.js` › "server store" › "keeps defaults and records the error when the request fails" |
| FE-STORE-021 | unit `server-store.test.js` › "server store" › "loads name, maintenance, navbar and footer"; e2e `e2e/tests/test_smoke.py::test_footer_renders_footer_template` |
| FE-STORE-022 | unit `server-store.test.js` › "server store" › "loads once unless forced (navbar depends on the viewer)" |
| FE-STORE-025 | unit `server-store.test.js` › "server store" › "loads name, maintenance, navbar and footer" (`footerHtml` unchanged) |
| FE-STORE-030, FE-STORE-031 | (planned) unit `frontend/src/test/jobs-store.test.js` › "fetchJobs maps the paginated response", › "refreshJob replaces the cached job" — or withdrawn per FE-STORE-032 |
| FE-STORE-032 | (planned) unit `frontend/src/test/layering.test.js` › "every store is used" |

## Known gaps

| Requirement | Current code | Reference | Severity |
|-------------|--------------|-----------|----------|
| FE-STORE-032 | `useJobsStore` is not imported anywhere; `JobListView` calls `listJobs` itself. Dead code with no tests. | `frontend/src/stores/jobs.js:1-31` | minor |
| FE-STORE-030 | `fetchJobs` accepts a non-paginated array (`data.results ?? data`, `data.count ?? length`), a shape `schema.yaml` does not allow for `jobs_list` (`PaginatedJobListList`). It hides a contract break instead of failing. | `frontend/src/stores/jobs.js:17-18` | minor |
| FE-STORE-009 | `ProfileView` passes the `me_retrieve` / `me_partial_update` response (`Profile` component, which adds `api_token`) into `updateUser`, so the auth store holds a `Profile`, not a `User`. Works today because `Profile` is a superset, but the store's type depends on which endpoint last wrote it. | `frontend/src/views/public/ProfileView.vue:60-65` | minor |
| FE-STORE-008 | `_clear()` is a private (underscore) action but is called from the router and `ProfileView`; it should be a public action (for example `clearLocal()`). | `frontend/src/router/index.js:115`, `frontend/src/views/public/ProfileView.vue:180` | minor |
| FE-STORE-022 | `load()` does not de-duplicate concurrent calls. A logged-in hard refresh sends `server_info` twice (mount load plus the forced load after boot); if they resolve out of order, the older response wins. | `frontend/src/stores/server.js:21-36`, `frontend/src/App.vue:12-20` | minor |
| FE-STORE-024 | A failed `server_info` is recorded in `error` but nothing shows it or retries; the shell silently shows defaults. | `frontend/src/stores/server.js:33-35` | minor |
| FE-STORE-004 | A transient failure of `auth_me_retrieve` at boot logs a logged-in user out for the whole page load (no retry); a deep link to a protected page then lands on the login form. | `frontend/src/stores/auth.js:34-43` | minor |
| — | The comment in `server.js` cites "SPEC §3.6" (`plans/SPEC.md`), which `spec/` supersedes. | `frontend/src/stores/server.js:5` | minor |

## Open questions

- Remove `useJobsStore`, or move `JobListView` onto it (would let the job list keep its page and
  filter when the user comes back from a job detail page)?
- Should the auth store re-check the session (`refresh()`) when the tab becomes visible again, so
  an expired session is noticed before the user acts?
- Should `server.load()` share an in-flight promise like `auth.boot()` does?
