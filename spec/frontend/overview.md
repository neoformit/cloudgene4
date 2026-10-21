# Frontend overview

## Purpose

The frontend is a Vue 3 single-page application (SPA) built with Vite. It is the only browser UI
for Cloudgene users and admins (the Django admin at `/django-admin/` is out of scope). This file
fixes the build, the entry points, the directory layout, the layering rules between views, stores
and API modules, and the dependency set. Everything else in `spec/frontend/` builds on it.

## Scope

Covered:

- `frontend/package.json`, `frontend/package-lock.json` (scripts, dependencies)
- `frontend/vite.config.js` (dev server, proxy, build base and output, vitest config)
- `frontend/index.html`, `frontend/public/`
- `frontend/src/main.js`, `frontend/src/App.vue`
- `frontend/src/assets/main.css` and other files in `frontend/src/assets/`
- The directory layout of `frontend/src/` and the layering conventions

Out of scope:

- How Django and nginx serve the built bundle, cache headers, `collectstatic`, the SPA fallback
  route: [../deployment/static-assets.md](../deployment/static-assets.md) and
  [../backend/server-pages-mail.md](../backend/server-pages-mail.md) (BE-SRV-040, BE-SRV-041).
- The HTTP client: [api-client.md](api-client.md). Routes and guards: [routing.md](routing.md).
  Stores: [state-stores.md](state-stores.md). App shell components (navbar, footer, maintenance
  banner): [layout-navigation.md](layout-navigation.md).
- `frontend/README.md` is the unmodified Vite template text and is not part of the spec.

## Dependencies

- [api-client.md](api-client.md), [routing.md](routing.md), [state-stores.md](state-stores.md)
- [layout-navigation.md](layout-navigation.md) (components mounted by `App.vue`)
- [tests.md](tests.md) (test commands)
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — SPA catch-all serves
  `static/frontend/index.html` (BE-SRV-040/041)
- [../backend/authentication.md](../backend/authentication.md) — `csrftoken` cookie set on SPA
  pages (BE-AUTH-016)
- [../deployment/static-assets.md](../deployment/static-assets.md)
- Contract operations: none directly (see the files above).

## Requirements

### Build and dev server

- **FE-ARCH-001** — `npm run build` MUST write the production bundle to `static/frontend/` at the
  repository root (`build.outDir: '../static/frontend'`), MUST empty that directory first
  (`emptyOutDir: true`), and MUST produce `static/frontend/index.html`.
- **FE-ARCH-002** — A production build MUST use the public base path `/static/frontend/`, so every
  script, stylesheet and asset URL in the built `index.html` starts with `/static/frontend/`. The
  dev server MUST use base `/`.
- **FE-ARCH-003** — `npm run dev` MUST proxy every request whose path starts with `/api` to
  `http://localhost:8000` (the Django dev server) with `changeOrigin: true`. No other path is
  proxied.
- **FE-ARCH-004** — The import alias `@` MUST resolve to `frontend/src/` in the app build, the dev
  server and vitest.
- **FE-ARCH-005** — Files in `frontend/public/` referenced from `index.html` by an absolute path
  (the favicon `/favicon.svg`) MUST resolve after a production build (served under
  `/static/frontend/`).

### Entry points

- **FE-ARCH-010** — `index.html` MUST declare `lang="en"`, UTF-8, a responsive viewport meta tag,
  the default document title `Cloudgene`, a single mount element `<div id="app">`, and load
  `src/main.js` as an ES module.
- **FE-ARCH-011** — `src/main.js` MUST create the app from `App.vue`, install Pinia before the
  router, install the router, and mount on `#app`. It MUST import, before mounting, the Bootstrap
  5 CSS, the Bootstrap JS bundle (dropdowns, collapse, modals), the Font Awesome CSS and
  `src/assets/main.css`.
- **FE-ARCH-012** — `App.vue` MUST render, in this order: `AppNavbar`, `MaintenanceBanner`,
  `RouterView`, `AppFooter`. All routes, including admin routes, render inside this shell.
- **FE-ARCH-013** — `App.vue` MUST trigger the server-info load once on mount and MUST force a
  reload whenever the logged-in user id changes (login, logout, session expiry). The load rules
  are in [state-stores.md](state-stores.md) (FE-STORE-020 to FE-STORE-024).

### Layering

- **FE-ARCH-020** — Only modules in `frontend/src/api/*.js` MAY import the default export of
  `@/api/client` or `axios` and issue HTTP requests (constitution 5.1f). Views, components and
  stores MUST call API-module functions instead.
- **FE-ARCH-021** — Views, components and stores MAY import the error helpers `apiErrorMessage`,
  `apiFieldErrors` and `apiErrorCode` from `@/api/client`. They MUST NOT read the error response
  body directly (see [api-client.md](api-client.md) FE-CLIENT-034).
- **FE-ARCH-022** — Modules MUST NOT use `fetch`, `XMLHttpRequest` or a second axios instance for
  `/api/` calls. Plain links to same-origin API URLs (`<a href="/api/jobs/…/log/">`) are allowed for
  downloads; they are built by API-module helpers (`jobLogUrl`, `jobOutputUrl`).
- **FE-ARCH-023** — Views MAY call stores and API modules. Stores MAY call API modules. API modules
  MUST NOT import stores, the router or views.
- **FE-ARCH-024** — Source files SHOULD follow this layout:

  | Directory | Contents |
  |-----------|----------|
  | `src/api/` | `client.js` and one module per backend area (`auth`, `jobs`, `server`, `users`, `workflows`, `admin`) |
  | `src/stores/` | Pinia stores (`auth`, `server`, `jobs`) |
  | `src/router/` | `index.js`: route table and guards |
  | `src/views/public/` | Routed views for anonymous and logged-in users |
  | `src/views/admin/`, `src/views/admin/settings/` | Routed admin views |
  | `src/components/<area>/` | Non-routed components: `common`, `layout`, `jobs`, `workflows/form`, `admin` |
  | `src/utils/` | Framework-free helpers (`avatar.js`, `validation.js`) |
  | `src/assets/` | Global CSS and images imported by code |
  | `src/test/` | vitest tests, contract tests (`contracts/`), fixtures |

### Styling

- **FE-ARCH-030** — Styling MUST use Bootstrap 5 classes plus the global rules in
  `src/assets/main.css`. `main.css` MUST define the job-state classes `badge-<state>`,
  `bg-<state>` and `job-<state>` for every job state used by the UI, the `.log-output` pane and the
  `.admin-sidebar` styles.
- **FE-ARCH-031** — The body MUST reserve the fixed navbar height (`padding-top: 70px`) so page
  content is not hidden under the navbar.
- **FE-ARCH-032** — Icons MUST come from the bundled Font Awesome package. The SPA MUST NOT load
  fonts, scripts or styles from a third-party CDN at run time.

### Dependencies and tooling

- **FE-ARCH-040** — Runtime dependencies MUST be limited to: `vue`, `vue-router`, `pinia`,
  `axios`, `bootstrap`, `@fortawesome/fontawesome-free`, `chart.js`. Adding one requires updating
  this file.
- **FE-ARCH-041** — `package-lock.json` MUST be committed, and automated installs MUST use
  `npm ci` (as `scripts/test.sh` does).
- **FE-ARCH-042** — `npm run test:run` MUST run the vitest suite once in a `happy-dom` environment
  with `src/test/setup.js` as setup file; `npm test` runs it in watch mode.
- **FE-ARCH-043** — `package.json` SHOULD declare the supported Node.js version in `engines`.
- **FE-ARCH-044** — Files in `src/assets/` and `public/` that no code or HTML references SHOULD
  NOT be kept.

## Interfaces

### npm scripts (`frontend/package.json`)

| Script | Command | Use |
|--------|---------|-----|
| `dev` | `vite` | Dev server on `:5173`, proxies `/api` to `:8000` |
| `build` | `vite build` | Production bundle → `../static/frontend/` |
| `preview` | `vite preview` | Serve the built bundle locally |
| `test` | `vitest` | Watch mode |
| `test:run` | `vitest run` | One run (CI, `scripts/test.sh`) |
| `test:ui` | `vitest --ui` | Browser UI for tests |
| `test:coverage` | `vitest run --coverage` | Coverage (no coverage provider is installed) |

### Dependencies (`package.json`, ranges as declared)

| Package | Range | Kind | Used for |
|---------|-------|------|----------|
| `vue` | `^3.5.32` | runtime | Framework |
| `vue-router` | `^4.6.4` | runtime | Routing |
| `pinia` | `^3.0.4` | runtime | Stores |
| `axios` | `^1.15.2` | runtime | HTTP client |
| `bootstrap` | `^5.3.8` | runtime | CSS and JS components |
| `@fortawesome/fontawesome-free` | `^7.2.0` | runtime | Icons |
| `chart.js` | `^4.5.1` | runtime | Admin dashboard charts |
| `vite` | `^5.4.21` | dev | Build and dev server |
| `@vitejs/plugin-vue` | `^5.2.4` | dev | SFC compilation |
| `vitest`, `@vitest/ui` | `^3.2.4` | dev | Unit and contract tests |
| `@vue/test-utils` | `^2.4.10` | dev | Component tests |
| `happy-dom` | `^20.9.0` | dev | Test DOM |
| `ajv`, `ajv-formats` | `^8.20.0`, `^3.0.1` | dev | Contract schema validation |

### URL layout seen by the browser

| URL | Served by | Notes |
|-----|-----------|-------|
| `/`, `/jobs/…`, any non-API path | Django `spa_index` → `static/frontend/index.html` | BE-SRV-040; sets `csrftoken` |
| `/static/frontend/assets/*` | whitenoise / nginx | Hashed bundle files |
| `/api/*` | Django REST API | Via [api-client.md](api-client.md) |

## Behaviour

Start-up sequence in the browser:

1. The server returns `index.html` for the requested path and sets the `csrftoken` cookie
   (BE-AUTH-016).
2. `main.js` installs Pinia and the router and mounts `App.vue`.
3. The router resolves the initial route. Its global guard awaits `auth.boot()`
   (`GET /api/auth/me/`) before any view renders ([routing.md](routing.md) FE-ROUTE-010).
4. In parallel, `App.vue` `onMounted` calls `server.load()` (`GET /api/server/`).
5. When boot finds a logged-in user, the user id changes from `null`, and `App.vue` forces
   `server.load(true)` so the navbar is filtered for that user.

In development the browser talks to Vite on `:5173`; `/api` is proxied to Django on `:8000`. The
`csrftoken` cookie then comes from `auth_me_retrieve` (Vite serves `index.html`, not Django).

## Acceptance tests

| Requirement | Tests |
|-------------|-------|
| FE-ARCH-001, FE-ARCH-002 | e2e harness build `e2e/stack.py` (runs `npm run build`; every e2e test loads the bundle); `scripts/smoke_gunicorn.sh` (asserts `/static/frontend/assets/index-*.js` is referenced and served); (planned) unit `frontend/src/test/build.test.js` › "built index.html references only /static/frontend/ assets" |
| FE-ARCH-003 | (planned) unit `frontend/src/test/vite-config.test.js` › "dev server proxies /api to :8000 only" |
| FE-ARCH-004 | every vitest test importing `@/…` (e.g. `frontend/src/test/client.test.js`) |
| FE-ARCH-005 | (planned) e2e `e2e/tests/test_smoke.py::test_favicon_served` |
| FE-ARCH-010, FE-ARCH-011, FE-ARCH-012 | e2e `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous`, `::test_home_loads_cleanly_logged_in` (no console errors; navbar, footer rendered) |
| FE-ARCH-013 | e2e `e2e/tests/test_smoke.py::test_navbar_items_from_yaml_in_order`; e2e `e2e/tests/test_auth.py::test_admin_sees_admin_link_regular_user_does_not`; (planned) unit `frontend/src/test/app.test.js` › "reloads server info when the user id changes" |
| FE-ARCH-020, FE-ARCH-022, FE-ARCH-023 | (planned) unit `frontend/src/test/layering.test.js` › "only src/api imports the client default export or axios" |
| FE-ARCH-021 | (planned) unit `frontend/src/test/layering.test.js` › "no view reads err.response.data" |
| FE-ARCH-030, FE-ARCH-031 | (planned) e2e `e2e/tests/test_jobs.py::test_state_badge_classes`; visual only otherwise |
| FE-ARCH-032 | (planned) e2e `e2e/tests/test_smoke.py::test_no_third_party_requests` |
| FE-ARCH-040, FE-ARCH-041 | `scripts/test.sh` (`npm ci` fails on a lockfile mismatch); (planned) unit `frontend/src/test/layering.test.js` › "runtime dependencies match the spec list" |
| FE-ARCH-042 | `scripts/test.sh` (runs `npx vitest run`, equivalent to `npm run test:run`) |

## Known gaps

| Requirement | Current code | Reference | Severity |
|-------------|--------------|-----------|----------|
| FE-ARCH-021 | Four views branch on `err.response?.status === 404` instead of `apiErrorCode(err) === 'not_found'`. | `frontend/src/views/public/WorkflowSubmitView.vue:32`, `frontend/src/views/public/StaticPageView.vue:23`, `frontend/src/views/public/JobDetailView.vue:78`, `frontend/src/views/admin/AdminWorkflowSettingsView.vue:53` | minor |
| FE-ARCH-020 | No automated check enforces the layering rule; it holds today only by inspection. | `frontend/src/` | minor |
| FE-ARCH-043 | No `engines` field; the supported Node.js version is undocumented. | `frontend/package.json` | minor |
| FE-ARCH-044 | `src/assets/hero.png`, `src/assets/vite.svg` and `public/icons.svg` are not referenced anywhere (Vite template leftovers). | `frontend/src/assets/`, `frontend/public/icons.svg` | minor |
| — | `test:coverage` needs `@vitest/coverage-v8` (or istanbul), which is not a dev dependency; the script fails. | `frontend/package.json` | minor |
| — | `frontend/README.md` is the stock Vite template and says nothing about this project. | `frontend/README.md` | minor |
| — | `src/test/setup.js` registers custom matchers (`toMatchApiSchema`, which relies on the `global.ajv` each contract test file sets) that no test uses. | `frontend/src/test/setup.js` | minor |
| — | There is no CI workflow in the repository; `scripts/test.sh` is the only runner. | repository root | minor |

## Open questions

- Should `document.title` include the server name from `server_info` (`index.html` hard-codes
  `Cloudgene`)? See [routing.md](routing.md) open questions.
- Should admin views get their own layout route (nested routes under `/admin` with
  `AdminLayout`) instead of each admin view wrapping itself? Owned by
  [layout-navigation.md](layout-navigation.md).
