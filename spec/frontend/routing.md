# Routing

## Purpose

`src/router/index.js` maps browser URLs to views, decides who may open each view, and sends
visitors who lack access to the right place (login with a return path, or home). It also turns a
401 from the API into a clean logout when the session has expired. Routing is a convenience
layer: the server enforces every permission ([../backend/access-control.md](../backend/access-control.md)),
so a guard failure in the browser can only hide UI, never grant data.

## Scope

Covered:

- `frontend/src/router/index.js`: route table, `beforeEach` guard, the `onUnauthorized` handler.
- Redirect after login: `safeNext` in `frontend/src/views/public/LoginView.vue` (the rest of the
  login view is in [auth-views.md](auth-views.md)).
- Deep links and hard refresh on every route, unknown routes, document title, scroll behaviour.

Out of scope:

- What each view shows: the view spec files listed in [README.md](README.md).
- The server-side catch-all that returns `index.html` for non-API paths:
  [../backend/server-pages-mail.md](../backend/server-pages-mail.md) BE-SRV-040/041 and
  [../deployment/static-assets.md](../deployment/static-assets.md).
- Navbar and sidebar links: [layout-navigation.md](layout-navigation.md).
- The auth store itself: [state-stores.md](state-stores.md).

## Dependencies

- [state-stores.md](state-stores.md) — `auth.boot()`, `isLoggedIn`, `isAdmin`, `_clear()`
  (FE-STORE-001 to FE-STORE-012).
- [api-client.md](api-client.md) — `onUnauthorized` (FE-CLIENT-040 to FE-CLIENT-042).
- [../backend/authentication.md](../backend/authentication.md) — `auth_me_retrieve` (BE-AUTH-014),
  401 for unauthenticated requests (BE-AUTH-021).
- [../backend/access-control.md](../backend/access-control.md) — server-side permissions.
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — BE-SRV-040 (SPA served for
  any non-API path).
- [../backend/accounts.md](../backend/accounts.md) — e-mails link to `/activate/<key>` and
  `/recover/<token>` (`accounts/views.py:212`, `accounts/views.py:275`).
- Contract operations: `auth_me_retrieve` (via `auth.boot()`).

## Requirements

### Route table

- **FE-ROUTE-001** — The router MUST use HTML5 history mode (`createWebHistory()`, base `/`):
  URLs have no `#`.
- **FE-ROUTE-002** — The router MUST define exactly the routes in the table under
  [Interfaces](#interfaces), with the listed access level. Adding, removing or renaming a route
  requires updating that table, [layout-navigation.md](layout-navigation.md) where linked, and
  `e2e/tests/test_deep_links.py`.
- **FE-ROUTE-003** — Every routed view MUST be lazy-loaded (dynamic `import()`), so a view's code
  is fetched only when its route is first visited.
- **FE-ROUTE-004** — `/admin/settings/templates` MUST redirect to `/admin/settings/pages` (old
  name kept for bookmarks).
- **FE-ROUTE-005** — Any path that matches no route MUST redirect to `/` (the URL changes to `/`;
  no 404 page is shown). Missing resources under a valid route (unknown job id, workflow id, page
  slug) are handled by the view, not the router.
- **FE-ROUTE-006** — Paths emitted by the backend in e-mails MUST match a route:
  `/activate/<key>` → `ActivateView`, `/recover/<token>` → `PasswordRecoveryView`.

### Guards

- **FE-ROUTE-010** — Before every navigation, including the first one after a page load, the guard
  MUST await `auth.boot()`, so the session state from `auth_me_retrieve` is known before any
  route decision or view render. Concurrent and later navigations MUST NOT trigger a second
  `auth_me_retrieve` (FE-STORE-002).
- **FE-ROUTE-011** — A route with `meta.requiresAuth` opened by an anonymous visitor MUST redirect
  to `/login?next=<to.fullPath>` (path plus query and hash of the requested URL).
- **FE-ROUTE-012** — A route with `meta.requiresAdmin` MUST redirect an anonymous visitor to
  `/login?next=<to.fullPath>` and a logged-in non-admin to `/`. It MUST NOT render the admin view
  for a non-admin, even briefly.
- **FE-ROUTE-013** — Routes without `meta.requiresAuth` or `meta.requiresAdmin` MUST be open to
  everyone, logged in or not.
- **FE-ROUTE-014** — Admin status for the guard MUST come from `user.is_admin` as returned by
  `auth_me_retrieve` or `auth_login_create`. Route guards MUST NOT be the only protection: every
  API call made by a protected view MUST also be refused by the server for an unauthorised caller
  ([../backend/access-control.md](../backend/access-control.md)).

### Redirect after login

- **FE-ROUTE-020** — After a successful login, `LoginView` MUST navigate to the `next` query
  parameter if it is a string that starts with `/` and does not start with `//`; otherwise it MUST
  navigate to `/`.
- **FE-ROUTE-021** — A `next` value MUST NOT be able to send the user to another origin. Values
  that a URL parser would read as protocol-relative (`//host`, `/\host`) or absolute
  (`https://…`, `javascript:…`) MUST fall back to `/`.

### Session expiry (401)

- **FE-ROUTE-030** — The router MUST register an `onUnauthorized` handler. When a request gets a
  401 while the auth store holds a user, the handler MUST clear the user (`auth._clear()`) and,
  if the current route has `requiresAuth` or `requiresAdmin`, navigate to
  `/login?next=<current fullPath>`. On a public route it MUST stay on the page (the navbar
  switches to the logged-out state).
- **FE-ROUTE-031** — A 401 while the store holds no user MUST be ignored by the handler (no
  navigation, no state change).

### Deep links

- **FE-ROUTE-040** — Every route in the table MUST work when opened directly (typed URL, bookmark,
  e-mail link) and after a browser reload, logged out and logged in, with the same outcome as
  in-app navigation (including the guard redirects of FE-ROUTE-011/012).
- **FE-ROUTE-041** — Route parameters (`:id`, `:workflowId`, `:slug`, `:key`, `:token`) MUST be
  passed to the view unchanged; views MUST treat them as untrusted strings (escape on output;
  encode when building API paths, see [api-client.md](api-client.md) FE-CLIENT-001).

### Navigation polish

- **FE-ROUTE-050** (planned) — On every navigation the router SHOULD set `document.title` to
  `<page title> – <server name>` (server name from the server store), falling back to the server
  name alone.
- **FE-ROUTE-051** (planned) — The router SHOULD scroll to the top on a new navigation and restore
  the saved position on browser back/forward (`scrollBehavior`).
- **FE-ROUTE-052** (planned) — If a lazy-loaded view chunk fails to load (typically after a
  redeploy replaced the hashed files under `/static/frontend/assets/`), the router MUST NOT leave
  the user on the old page without feedback; it SHOULD do a full page load of the target URL.

## Interfaces

### Route table (`frontend/src/router/index.js`)

| Path | View (`src/views/…`) | Access (`meta`) | Spec |
|------|----------------------|-----------------|------|
| `/` | `public/HomeView.vue` | everyone | [home-static-pages.md](home-static-pages.md) |
| `/login` | `public/LoginView.vue` | everyone | [auth-views.md](auth-views.md) |
| `/register` | `public/RegisterView.vue` | everyone | [auth-views.md](auth-views.md) |
| `/activate/:key` | `public/ActivateView.vue` | everyone | [auth-views.md](auth-views.md) |
| `/reset-password` | `public/PasswordResetView.vue` | everyone | [auth-views.md](auth-views.md) |
| `/recover/:token` | `public/PasswordRecoveryView.vue` | everyone | [auth-views.md](auth-views.md) |
| `/pages/:slug` | `public/StaticPageView.vue` | everyone | [home-static-pages.md](home-static-pages.md) |
| `/profile` | `public/ProfileView.vue` | `requiresAuth` | [profile.md](profile.md) |
| `/jobs` | `public/JobListView.vue` | `requiresAuth` | [job-list.md](job-list.md) |
| `/jobs/:id` | `public/JobDetailView.vue` | `requiresAuth` | [job-detail.md](job-detail.md) |
| `/run/:workflowId` | `public/WorkflowSubmitView.vue` | `requiresAuth` | [workflow-submit-form.md](workflow-submit-form.md) |
| `/admin` | `admin/AdminDashboardView.vue` | `requiresAdmin` | [admin-dashboard-jobs.md](admin-dashboard-jobs.md) |
| `/admin/jobs` | `admin/AdminJobsView.vue` | `requiresAdmin` | [admin-dashboard-jobs.md](admin-dashboard-jobs.md) |
| `/admin/users` | `admin/AdminUsersView.vue` | `requiresAdmin` | [admin-users-groups.md](admin-users-groups.md) |
| `/admin/workflows` | `admin/AdminWorkflowsView.vue` | `requiresAdmin` | [admin-workflows.md](admin-workflows.md) |
| `/admin/workflows/:id` | `admin/AdminWorkflowSettingsView.vue` | `requiresAdmin` | [admin-workflows.md](admin-workflows.md) |
| `/admin/settings/general` | `admin/settings/GeneralSettingsView.vue` | `requiresAdmin` | [admin-settings.md](admin-settings.md) |
| `/admin/settings/nextflow` | `admin/settings/NextflowSettingsView.vue` | `requiresAdmin` | [admin-settings.md](admin-settings.md) |
| `/admin/settings/mail` | `admin/settings/MailSettingsView.vue` | `requiresAdmin` | [admin-settings.md](admin-settings.md) |
| `/admin/settings/pages` | `admin/settings/PagesView.vue` | `requiresAdmin` | [admin-settings.md](admin-settings.md) |
| `/admin/settings/templates` | redirect → `/admin/settings/pages` | — | — |
| `/admin/settings/logs` | `admin/settings/LogsView.vue` | `requiresAdmin` | [admin-settings.md](admin-settings.md) |
| `/:pathMatch(.*)*` | redirect → `/` | — | — |

Routes have no `name`; code navigates by path. `/jobs/:id` and `/run/:workflowId` are reached
from in-app links and from `router.push('/jobs/<id>')` after a submission.

### Guard decision

| `meta` | Anonymous | Logged-in user | Admin |
|--------|-----------|----------------|-------|
| none | allow | allow | allow |
| `requiresAuth` | → `/login?next=…` | allow | allow |
| `requiresAdmin` | → `/login?next=…` | → `/` | allow |

## Behaviour

First load of a deep link (for example `/jobs/abc` with an expired session):

1. Django returns `index.html` for `/jobs/abc` (BE-SRV-040).
2. The router's initial navigation runs the guard, which awaits `auth.boot()` →
   `GET /api/auth/me/` → `{"authenticated": false, "user": null}`.
3. `/jobs/abc` has `requiresAuth`; the guard returns `/login?next=%2Fjobs%2Fabc`.
4. After login, `LoginView` pushes `/jobs/abc` (FE-ROUTE-020). The guard runs again; boot is done,
   the user is logged in, and the job view renders.

Session expires while a protected page is open:

1. A poll or action gets 401 (BE-AUTH-021). The client calls the router's handler (FE-CLIENT-041).
2. The handler clears the store user; `App.vue` sees the user id change and reloads server info.
3. Because the route needs auth, the router pushes `/login?next=<current page>`.

Non-admin opens an admin link: the guard returns `/` with no message.

`auth.boot()` failure (network error, 5xx on `auth_me_retrieve`) counts as anonymous
(FE-STORE-004); protected deep links then go to the login page.

Edge cases:

- `next` pointing to `/login` is followed; the logged-in user then sees the login form again.
- A logged-in user may open `/login` and `/register`; there is no redirect away from them.
- An unknown path loses its query string: `/foo?x=1` becomes `/`.

## Acceptance tests

| Requirement | Tests |
|-------------|-------|
| FE-ROUTE-001, FE-ROUTE-040 | e2e `e2e/tests/test_deep_links.py::test_public_route_logged_out`, `::test_user_route_deep_link_and_refresh`, `::test_admin_route_deep_link_and_refresh` |
| FE-ROUTE-002 | e2e `e2e/tests/test_deep_links.py` (route lists `PUBLIC_ROUTES`, `USER_ROUTES`, `ADMIN_ROUTES`); (planned) unit `frontend/src/test/router.test.js` › "route table matches the spec" |
| FE-ROUTE-003 | (planned) unit `frontend/src/test/router.test.js` › "every route component is a lazy import" |
| FE-ROUTE-004 | (planned) unit `frontend/src/test/router.test.js` › "/admin/settings/templates redirects to /admin/settings/pages" |
| FE-ROUTE-005 | e2e `e2e/tests/test_deep_links.py::test_unknown_route_redirects_home` |
| FE-ROUTE-006 | e2e `e2e/tests/test_accounts.py::test_a1_register_activate_login` (activation link from the e-mail), `::test_a4_password_reset` (recovery link) |
| FE-ROUTE-010 | unit `frontend/src/test/auth-store.test.js` › "router guards" › "waits for boot and redirects anonymous users to /login?next=", › "lets a logged-in user through after a hard refresh (session from /me)"; unit `auth-store.test.js` › "auth store" › "boots from /auth/me exactly once, even with concurrent callers" |
| FE-ROUTE-011 | unit `auth-store.test.js` › "router guards" › "waits for boot and redirects anonymous users to /login?next="; e2e `e2e/tests/test_deep_links.py::test_protected_route_logged_out_redirects_to_login_with_next` |
| FE-ROUTE-012 | unit `auth-store.test.js` › "router guards" › "sends non-admins away from admin routes", › "admins can open admin routes"; e2e `e2e/tests/test_deep_links.py::test_admin_route_forbidden_for_regular_user`, `::test_protected_route_logged_out_redirects_to_login_with_next`; e2e `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` |
| FE-ROUTE-013 | e2e `e2e/tests/test_deep_links.py::test_public_route_logged_out` |
| FE-ROUTE-014 | e2e `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api`; e2e `e2e/tests/test_findings_security.py::test_permission_matrix_admin_endpoints` |
| FE-ROUTE-020 | e2e `e2e/tests/test_auth.py::test_login_follows_next_parameter`; (planned) unit `frontend/src/test/login-view.test.js` › "falls back to / for a missing or foreign next" |
| FE-ROUTE-021 | (planned) unit `frontend/src/test/login-view.test.js` › "rejects //host, /\\host and absolute next values" |
| FE-ROUTE-030 | (planned) unit `frontend/src/test/auth-store.test.js` › "router guards" › "401 on a protected page clears the user and goes to /login?next="; (planned) e2e `e2e/tests/test_auth.py::test_session_expiry_returns_to_login` |
| FE-ROUTE-031 | (planned) unit `frontend/src/test/auth-store.test.js` › "router guards" › "401 while anonymous is ignored" |
| FE-ROUTE-041 | (planned) e2e `e2e/tests/test_deep_links.py::test_route_params_are_not_rendered_as_html` |
| FE-ROUTE-052 | (planned) unit `frontend/src/test/router.test.js` › "chunk load failure falls back to a full page load" |

## Known gaps

| Requirement | Current code | Reference | Severity |
|-------------|--------------|-----------|----------|
| FE-ROUTE-021 | `safeNext` accepts `/\evil.example`. Browsers parse it as `//evil.example`, so `history.pushState` throws a cross-origin `SecurityError`: not an open redirect, but the user stays on the login form after a successful login with an unhandled promise rejection. | `frontend/src/views/public/LoginView.vue:19-21` | minor |
| FE-ROUTE-030 | The 401 path (store reset and redirect) has no unit or e2e test. | `frontend/src/router/index.js:112-120` | minor |
| FE-ROUTE-050 | `document.title` is never set; every tab reads `Cloudgene` regardless of page or configured server name. | `frontend/index.html:7`, `frontend/src/router/index.js` | minor |
| FE-ROUTE-051 | No `scrollBehavior`: moving from a scrolled list to a detail page keeps the old scroll offset. | `frontend/src/router/index.js:5-7` | minor |
| FE-ROUTE-052 | No `router.onError` handler. After a redeploy (`emptyOutDir` removes old chunks), an open tab cannot lazy-load views it has not loaded yet; the click does nothing. | `frontend/src/router/index.js`, `frontend/vite.config.js:20-23` | major |
| FE-ROUTE-012 | A non-admin sent away from an admin route gets no message explaining why. | `frontend/src/router/index.js:102-104` | minor |
| — | The 401 handler calls the store's private `_clear()` action. | `frontend/src/router/index.js:115` | minor |

## Open questions

- Should unknown paths show a "Page not found" view (keeping the URL) instead of redirecting to
  `/`? The current redirect is codified by `test_unknown_route_redirects_home`.
- Should a logged-in user who opens `/login`, `/register`, `/reset-password` or
  `/recover/<token>` be redirected to `/` (or `next`)?
- Should routes get names so links survive path changes?
