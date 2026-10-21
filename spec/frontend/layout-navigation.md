# Layout and navigation

## Purpose

The app shell is what every page shares: the top navbar (service name, configured navigation
items, user menu or login/sign-up links), the maintenance banner, the footer, and, for admin
pages, the admin layout with its sidebar. The navbar, banner and footer are driven by the public
server info (`server_info`) so an admin can change them in `settings.yaml` and `pages/` without a
rebuild.

## Scope

| Source | What |
|--------|------|
| `frontend/src/App.vue` | Shell composition; loading and reloading server info |
| `frontend/src/components/layout/AppNavbar.vue` | Navbar: brand, configured items, user menu, logout |
| `frontend/src/components/layout/MaintenanceBanner.vue` | Maintenance banner |
| `frontend/src/components/layout/AppFooter.vue` | Footer (admin-authored HTML or default text) |
| `frontend/src/components/layout/AdminLayout.vue` | Two-column admin page frame |
| `frontend/src/components/layout/AdminSidebar.vue` | Admin section links |
| `frontend/src/assets/main.css` (`body` padding only) | Offset for the fixed navbar |

Out of scope (linked instead):

- The `server` store's state and `load()` semantics: [state-stores.md](state-stores.md).
- Route table, auth/admin guards, unknown-route handling: [routing.md](routing.md).
- Server-side navbar filtering, footer source, maintenance flag: [../backend/server-pages-mail.md](../backend/server-pages-mail.md).
- Editing the navbar, footer and maintenance mode: [admin-settings.md](admin-settings.md), [admin-dashboard-jobs.md](admin-dashboard-jobs.md).
- Shared alert/spinner/dialog components: [common-components.md](common-components.md).

## Dependencies

- [api-contract.md](api-contract.md): `server_info` → `getServerInfo()` (`src/api/server.js`); `auth_logout_create` via the auth store.
- [state-stores.md](state-stores.md): `useServerStore` (`name`, `navbar`, `maintenance`, `maintenanceMessage`, `footerHtml`, `load(force)`), `useAuthStore` (`user`, `isLoggedIn`, `isAdmin`, `logout()`).
- [routing.md](routing.md): every `AdminSidebar` link and every fixed navbar link resolves to a route.
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) BE-SRV-001…003, BE-SRV-022.
- [../backend/admin-api.md](../backend/admin-api.md) BE-ADM-057 (navbar URL validation on save).

## Requirements

### Shell

- **FE-NAV-001** Every route MUST render, in order: the navbar, the maintenance banner (when active), the routed view, the footer. This applies to anonymous users, users and admins alike.
- **FE-NAV-002** The shell MUST load server info once when the app mounts (`server.load()`), and MUST reload it (`server.load(true)`) whenever the logged-in user's id changes (login, logout, session expiry), because the navbar is filtered for the viewer.
- **FE-NAV-003** If `server_info` fails, the shell MUST still render with defaults (brand `Cloudgene`, no navbar items, no banner, default footer text) and MUST NOT block the routed view.

### Navbar

- **FE-NAV-010** The brand MUST show `server.name` as text (interpolated, never HTML) and link to `/`.
- **FE-NAV-011** The navbar MUST render the items of `server.navbar` in the order received, one `nav-item` per item, showing `title` as text and, when `icon` is non-empty, a Font Awesome icon `fas fa-<icon>`. The SPA MUST NOT re-filter by `admin_only`/`auth_only`; it relies on the server-filtered list (BE-SRV-002).
- **FE-NAV-012** An item whose `url` starts with `http://` or `https://` (case-insensitive) MUST render as an external link opening in a new tab with `rel="noopener"`.
- **FE-NAV-013** An item whose `url` is an internal path MUST render as an in-app router link. An internal path MUST start with a single `/` (not `//`), matching the backend rule (BE-ADM-057).
- **FE-NAV-014** An item whose `url` is neither shape (e.g. `javascript:`, `data:`, relative text) MUST render as non-clickable disabled text. The SPA MUST NOT put such a value in an `href`. (Defence in depth for Article 8.2: the backend already rejects these on save.)
- **FE-NAV-015** For an anonymous visitor, the right side MUST show `Sign up` (`/register`) and `Login` (`/login`) links and no user menu.
- **FE-NAV-016** For a logged-in user, the right side MUST show a dropdown labelled with the username (text), containing `My Jobs` (`/jobs`), `Profile` (`/profile`) and `Logout`. The `Admin Panel` (`/admin`) entry MUST appear only when `auth.isAdmin` is true. Hiding the entry is presentation only; access to `/admin` is enforced by the route guard and the API ([routing.md](routing.md)).
- **FE-NAV-017** `Logout` MUST call the auth store's `logout()` and then navigate to `/`. The user menu MUST switch to the anonymous links even if the logout request fails (the store clears the user in `finally`), and the SPA SHOULD still navigate to `/` in that case.

### Maintenance banner

- **FE-NAV-020** When `server.maintenance` is true, a warning banner with `role="status"` MUST be shown below the navbar on every page to every viewer, containing `server.maintenanceMessage` as text (never HTML). When false, no banner element MUST be rendered.
- **FE-NAV-021** After an admin enters or leaves maintenance mode from the dashboard, the admin's own banner MUST update without a page reload (the dashboard calls `server.load(true)`). Other open sessions see the change on their next server-info load (next login/logout or page load); the SPA does not poll.

### Footer

- **FE-NAV-030** When `server.footerHtml` is non-empty, the footer MUST render it as HTML (`v-html`). This HTML is trusted, admin-authored content returned verbatim by the server (BE-SRV-012); the SPA MUST NOT render any other source through this slot.
- **FE-NAV-031** When `server.footerHtml` is empty, the footer MUST show the text `Powered by Cloudgene`.
- **FE-NAV-032** The footer MUST show a `Back to top` link.

### Admin layout

- **FE-NAV-040** Every admin view (`/admin` and `/admin/**`) MUST render its content inside `AdminLayout`, which shows `AdminSidebar` beside a `main` content area, below the global navbar (so admins keep the site navigation).
- **FE-NAV-041** `AdminSidebar` MUST list, in this order: Dashboard (`/admin`), Jobs (`/admin/jobs`), Users (`/admin/users`), Workflows (`/admin/workflows`), then a `Settings` heading with General, Nextflow, Pages, Mail, Logs (`/admin/settings/<name>`). Every link MUST resolve to a defined route.
- **FE-NAV-042** The sidebar link for the current section MUST be marked active. `Dashboard` MUST be active only on exactly `/admin`; other links MUST be active on their path and its sub-paths (e.g. `Workflows` on `/admin/workflows/hello`).
- **FE-NAV-043** The sidebar MUST be shown only inside admin routes, which are admin-only by route guard; non-admins never see it.

### Responsive behaviour

- **FE-NAV-050** The navbar MUST be fixed to the top and the page body MUST be offset so no content is hidden under it.
- **FE-NAV-051** Below Bootstrap's `md` breakpoint the navbar items and user menu MUST collapse behind a toggle button that has `aria-label="Toggle navigation"`, `aria-controls` and `aria-expanded`.
- **FE-NAV-052** (planned) After choosing a navbar or user-menu link on a collapsed (mobile) navbar, the menu SHOULD close.
- **FE-NAV-053** (planned) On narrow screens the admin sidebar SHOULD NOT take a fixed 210 px column; it SHOULD stack above the content or collapse.

## Interfaces

Server info consumed (shape: `ServerInfo` / `ServerNavbarItem` in `schema.yaml`, see
[api-contract.md](api-contract.md)): `name`, `maintenance`, `maintenance_message`, `navbar[]`
(`title`, `url`, `icon`, `admin_only`, `auth_only`), `footer_html`. `url` is read into the store
but not used by the shell.

Components:

| Component | Props / slots | Test ids |
|-----------|---------------|----------|
| `AppNavbar` | none (reads stores) | `navbar`, `nav-brand`, `nav-item`, `nav-user-menu`, `nav-jobs`, `nav-profile`, `nav-admin`, `nav-logout`, `nav-signup`, `nav-login` |
| `MaintenanceBanner` | none | `maintenance-banner` |
| `AppFooter` | none | `footer` |
| `AdminLayout` | default slot = page content | `admin-main` |
| `AdminSidebar` | none | `admin-sidebar`, `admin-nav-<id>` (`dashboard`, `jobs`, `users`, `workflows`, `general`, `nextflow`, `pages`, `mail`, `logs`) |

Bootstrap JS (`bootstrap.bundle.min.js`, imported in `main.js`) drives the collapse and dropdown
through `data-bs-*` attributes.

## Behaviour

**Navbar item rendering decision** (`AppNavbar.vue:13-14`, `:40-58`):

| `url` | Rendered as |
|-------|-------------|
| `^https?://` (any case) | `<a href target="_blank" rel="noopener">` |
| starts with `/` | `<RouterLink :to>` |
| anything else | `<span class="nav-link disabled">` |

**Server info refresh points.** App mount; user id change (`App.vue:15-20`); admin dashboard
maintenance enter/exit; general settings and navbar save; footer page save
([admin-settings.md](admin-settings.md)). There is no periodic refresh.

**Logout.** `auth.logout()` posts to the API and clears the user in `finally`; the user-id watcher
then reloads server info, which drops `auth_only`/`admin_only` items. If the user was on a
protected page, navigation to `/` leaves it.

**Admin pages.** Each admin view wraps itself in `<AdminLayout>`; the layout has no logic of its
own. Admin access is decided by the route guard, not the layout.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-NAV-001 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous`, `::test_home_loads_cleanly_logged_in` | e2e |
| FE-NAV-002 | `frontend/src/test/server-store.test.js` › server store › loads once unless forced (navbar depends on the viewer); `e2e/tests/test_admin_settings.py::test_d6_navbar_editor` | unit, e2e |
| FE-NAV-003 | `frontend/src/test/server-store.test.js` › server store › keeps defaults and records the error when the request fails; shell renders when `server_info` fails (planned, `frontend/src/test/layout.test.js` › AppNavbar › renders defaults without server info) | unit |
| FE-NAV-010 | brand shows server name as text (planned, `layout.test.js` › AppNavbar › brand is server name text) | unit |
| FE-NAV-011 | `e2e/tests/test_smoke.py::test_navbar_items_from_yaml_in_order` | e2e |
| FE-NAV-012–014 | item rendering per URL shape incl. `javascript:` and `//host` (planned, `layout.test.js` › AppNavbar › renders links only for internal paths and http(s)) | unit |
| FE-NAV-015 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous` | e2e |
| FE-NAV-016 | `e2e/tests/test_auth.py::test_admin_sees_admin_link_regular_user_does_not` | e2e |
| FE-NAV-017 | `e2e/tests/test_auth.py::test_login_and_logout_via_ui`; logout with failing API (planned, `layout.test.js` › AppNavbar › logout navigates home when the request fails) | e2e, unit |
| FE-NAV-020, 021 | `e2e/tests/test_admin_dashboard.py::test_d1_maintenance_mode_banner` | e2e |
| FE-NAV-030 | `e2e/tests/test_smoke.py::test_footer_renders_footer_template`; `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer` | e2e |
| FE-NAV-031, 032 | default footer text and back-to-top link (planned, `layout.test.js` › AppFooter › default text) | unit |
| FE-NAV-040, 041 | `e2e/tests/test_deep_links.py::test_admin_route_deep_link_and_refresh`; every sidebar link has a route (planned, `layout.test.js` › AdminSidebar › every link resolves) | e2e, unit |
| FE-NAV-042 | active-link rules (planned, `layout.test.js` › AdminSidebar › dashboard exact, others prefix) | unit |
| FE-NAV-043 | `e2e/tests/test_deep_links.py::test_admin_route_forbidden_for_regular_user` | e2e |
| FE-NAV-050, 051 | navbar collapses at phone width (planned, `e2e/tests/test_smoke.py::test_navbar_collapses_on_mobile`) | e2e |

## Known gaps

| ID | What the code does | Where | Severity |
|----|--------------------|-------|----------|
| FE-NAV-013 | `isInternal` accepts any value starting with `/`, including `//evil.example` (protocol-relative). The backend rejects these on save, so this is defence-in-depth only. | `frontend/src/components/layout/AppNavbar.vue:14` | minor |
| FE-NAV-017 | `logout()` has no `catch`: if the logout request fails, `auth.logout()` rethrows after clearing the user, `router.push('/')` is skipped and the rejection is unhandled (console error). | `frontend/src/components/layout/AppNavbar.vue:16-19`, `frontend/src/stores/auth.js:52-58` | minor |
| FE-NAV-002 | Two `server.load()` calls can overlap (mount and the user-id watcher once boot resolves); responses are applied in arrival order, so a late anonymous response could overwrite the logged-in navbar. | `frontend/src/App.vue:12-20`, `frontend/src/stores/server.js:21-35` | minor |
| FE-NAV-003 | A failed `server_info` is recorded in `server.error` but never shown; the user sees an empty navbar with no explanation. | `frontend/src/stores/server.js:33-35` | minor |
| FE-NAV-052 | The collapsed navbar is not closed on route change; on mobile the menu stays open after following a `RouterLink`. | `frontend/src/components/layout/AppNavbar.vue:38` | minor |
| FE-NAV-053 | `AdminLayout` is a fixed `d-flex` row with a `min-width: 210px` sidebar and no breakpoint; on a phone the content column is squeezed. | `frontend/src/components/layout/AdminLayout.vue:7`, `frontend/src/components/layout/AdminSidebar.vue:26` | minor |
| FE-NAV-050 | The body offset (`padding-top: 70px`) is a fixed value; a navbar that wraps or a long service name can overlap content. | `frontend/src/assets/main.css:1-3` | minor |
| — | The browser tab title is the static `Cloudgene` from `index.html`; `server.name` and the current page are never reflected in `document.title`. | `frontend/index.html:7` | minor |
| — | The footer `Back to top` link is `href="#"`; with the HTML5 history router it scrolls to the top but appends `#` to the URL. | `frontend/src/components/layout/AppFooter.vue:11` | minor |
| — | `AdminSidebar` icons and navbar icons have no `aria-hidden="true"`; screen readers may announce them. | `AdminSidebar.vue:40`, `AppNavbar.vue:49,53,56,71` | minor |

## Open questions

1. Should the SPA re-check server info periodically (or on route change) so that a maintenance banner reaches open sessions without a reload?
2. Should the document title follow `server.name` (and the page), and is that this file's or [overview.md](overview.md)'s concern?
