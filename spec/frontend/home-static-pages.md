# Home and static pages

## Purpose

The home page is the public entry point: it shows the admin-authored `home` page HTML and a card
for every workflow the viewer may see, with a way to run it. Static pages (`/pages/<slug>`) show
other admin-authored HTML pages such as `about`. Both render HTML that comes from
`$CLOUDGENE_HOME/pages/` (and, for workflow descriptions, from installed `cloudgene.yaml` files),
so this file also fixes the trust boundary for that HTML in the browser.

## Scope

| Source | What |
|--------|------|
| `frontend/src/views/public/HomeView.vue` | Home page: `home` page HTML, workflow cards |
| `frontend/src/views/public/StaticPageView.vue` | `/pages/:slug` view, not-found and error states |
| `frontend/src/api/server.js` (`getPage`) | Page fetch |
| `frontend/src/api/workflows.js` (`listWorkflows`, `listCategories`) | Workflow list (categories: unused) |

Out of scope (linked instead):

- Route definitions and the catch-all redirect for unknown SPA routes: [routing.md](routing.md).
- Footer HTML: [layout-navigation.md](layout-navigation.md) FE-NAV-030.
- Admin editing and preview of pages: [admin-settings.md](admin-settings.md).
- Workflow descriptions/labels on the run form: [workflow-submit-form.md](workflow-submit-form.md).
- Server side of pages (slug rule, verbatim HTML, 404): [../backend/server-pages-mail.md](../backend/server-pages-mail.md).
- Which workflows a viewer may see: [../backend/workflows-api.md](../backend/workflows-api.md), [../backend/access-control.md](../backend/access-control.md).

## Dependencies

- [api-contract.md](api-contract.md): `pages_retrieve` → `getPage(slug)`; `workflows_list` → `listWorkflows()`; `categories_list` → `listCategories()` (not called by any view).
- [api-client.md](api-client.md): `apiErrorMessage()`.
- [state-stores.md](state-stores.md): `useAuthStore().isLoggedIn`.
- [common-components.md](common-components.md): `LoadingSpinner`, error-display conventions.
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) BE-SRV-010…013; [../backend/workflow-definition.md](../backend/workflow-definition.md) (description is passed through unmodified).

## Requirements

### Home page

- **FE-PAGE-001** `/` MUST be reachable by anyone (no route guard) and MUST NOT redirect anonymous visitors to `/login`.
- **FE-PAGE-002** On mount the home view MUST request `pages_retrieve` for slug `home` and `workflows_list` in parallel, and show `LoadingSpinner` in the workflow area until both settle.
- **FE-PAGE-003** When the `home` page is returned, its `html` MUST be rendered above the workflow list (`data-testid="home-content"`). When it is missing (404) or fails, the home view MUST render without that block and MUST NOT show an error for it.
- **FE-PAGE-004** The home view MUST show one card per workflow returned for the viewer, in the order returned, each with the workflow `name` as text and its `description`. The SPA MUST NOT filter workflows itself; visibility is decided by the server.
- **FE-PAGE-005** The home view MUST show every workflow visible to the viewer, not only the first API page. Because `workflows_list` is paginated (`PaginatedWorkflowList`, default page size 20), the view MUST either follow `next` until it is null or page the list in the UI.
- **FE-PAGE-006** For a logged-in viewer each card MUST link `Run` to `/run/<id>`. For an anonymous viewer each card MUST instead link `Login to run` to `/login`, and that link SHOULD carry `?next=/run/<id>` so the user returns to the workflow after login.
- **FE-PAGE-007** If `workflows_list` fails, the view MUST show `apiErrorMessage(err, 'Could not load workflows.')` in an error alert (`home-error`) and no empty-state text.
- **FE-PAGE-008** If no workflows are returned, the view MUST show `No workflows are currently available.` to logged-in users and `No workflows are currently available — log in to see more.` to anonymous visitors (`no-workflows`).
- **FE-PAGE-009** (planned) If workflows have categories (`category_name`), the home view SHOULD group or label cards by category. Today categories are not shown and `listCategories()` is unused.

### Static pages

- **FE-PAGE-020** `/pages/:slug` MUST be reachable by anyone and MUST request `pages_retrieve` with the slug URL-encoded. When the route's slug changes without leaving the view, it MUST load the new page.
- **FE-PAGE-021** While loading, the view MUST show `LoadingSpinner`. On success it MUST render the page `html` (`page-content`).
- **FE-PAGE-022** On 404 (missing page, or any slug the server rejects, BE-SRV-011) the view MUST show `Page not found.` (`page-not-found`) and no HTML.
- **FE-PAGE-023** On any other error the view MUST show `apiErrorMessage(err)` in an error alert (`page-error`) and no HTML.
- **FE-PAGE-024** The SPA MUST NOT validate or rewrite the slug itself; the server's slug rule is authoritative. Paths with more than one segment under `/pages/` are not matched by this route and fall to the unknown-route handling in [routing.md](routing.md).

### HTML rendering and trust (Article 8.2)

- **FE-PAGE-030** Page HTML (`home`, `/pages/<slug>`) MUST be rendered with `v-html` exactly as returned. It is trusted content: only admins can write it (BE-ADM-065) and the server returns it verbatim without sanitising (BE-SRV-012). Neither side sanitises it today; the protection is that the author is an admin.
- **FE-PAGE-031** A workflow `description` MUST be rendered with `v-html`, as authored in the workflow's `cloudgene.yaml`. It is privileged content: it reaches the SPA only from a workflow an admin installed. Installing a workflow MUST therefore be treated as trusting its author with script execution in every visitor's browser (same trust as running its pipeline).
- **FE-PAGE-032** No value that a non-admin user can set (usernames, job names, form values, messages) MUST be rendered through these `v-html` surfaces. All other workflow fields on the card (`name`) MUST be text-interpolated.
- **FE-PAGE-033** (planned) The SPA SHOULD be served with a Content-Security-Policy that forbids inline script, so that injected `<script>`/event-handler markup in page or description HTML does not execute. Ownership: [../deployment/](../deployment/README.md) for the header, this file for verifying pages still render.

### 404 handling

- **FE-PAGE-040** A missing static page MUST be reported in-page (FE-PAGE-022) with HTTP 200 for the SPA shell (BE-SRV-040); unknown SPA routes are handled by [routing.md](routing.md) (today: redirect to `/`).

## Interfaces

API calls (shapes in `schema.yaml`, see [api-contract.md](api-contract.md)):

| Function | operationId | Response component | Fields used |
|----------|-------------|--------------------|-------------|
| `getPage(slug)` → GET `/api/pages/{slug}/` | `pages_retrieve` | `PublicPage` | `html` |
| `listWorkflows()` → GET `/api/workflows/` | `workflows_list` | `PaginatedWorkflowList` | `results[].id`, `.name`, `.description` |
| `listCategories()` → GET `/api/categories/` | `categories_list` | `PaginatedWorkflowCategoryList` | — (not called) |

Test ids: `home-content`, `home-error`, `workflow-list`, `workflow-card` (with `data-workflow-id`),
`workflow-run`, `workflow-login`, `no-workflows`, `page-content`, `page-not-found`, `page-error`.

`v-html` surfaces in this area:

| Surface | Source | Author |
|---------|--------|--------|
| `HomeView.vue:32` `home-content` | `pages/home.html` | admin |
| `HomeView.vue:50` card description | `cloudgene.yaml` `description` | workflow author (installed by admin) |
| `StaticPageView.vue:39` `page-content` | `pages/<slug>.html` | admin |

## Behaviour

**Home load.** `Promise.allSettled([getPage('home'), listWorkflows()])`
(`HomeView.vue:16-26`). The page result is used only if fulfilled; the workflow result sets
`workflows = data.results ?? data` or the error. `loading` turns false after both settle, so the
`home-content` block may appear before the cards.

| Page result | Workflows result | Shown |
|-------------|------------------|-------|
| ok | ok, non-empty | home HTML + cards |
| ok | ok, empty | home HTML + empty text |
| 404 / error | ok | cards only (no page error) |
| any | error | home HTML if any + `home-error` |

**Static page state machine** (`StaticPageView.vue:14-30`): `loading` → one of `content`,
`notFound`, `error`. Each slug change resets to `loading`. Responses for an earlier slug are not
cancelled.

**Script in HTML.** `v-html` sets `innerHTML`, so `<script>` elements do not run, but event-handler
attributes (`<img onerror=…>`) and `javascript:` links do. This is why FE-PAGE-030/031 are trust
statements, not sanitisation claims.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-PAGE-001 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_anonymous`; `e2e/tests/test_deep_links.py::test_public_route_logged_out` | e2e |
| FE-PAGE-002, 003 | `e2e/tests/test_smoke.py::test_home_renders_home_template`; missing `home` page renders cards without error (planned, `frontend/src/test/home-view.test.js` › HomeView › renders without home page on 404) | e2e, unit |
| FE-PAGE-004 | `e2e/tests/test_admin_workflows.py::test_w1_workflow_visibility_per_user`, `::test_w1_d4_disable_hides_workflow_and_enable_restores` | e2e |
| FE-PAGE-005 | more than 20 workflows all listed (planned, `home-view.test.js` › HomeView › follows pagination) | unit |
| FE-PAGE-006 | `e2e/tests/test_smoke.py::test_home_loads_cleanly_logged_in`; anonymous `Login to run` with `next` (planned, `home-view.test.js` › HomeView › login link carries next) | e2e, unit |
| FE-PAGE-007, 008 | error and empty states (planned, `home-view.test.js` › HomeView › error alert / empty text) | unit |
| FE-PAGE-020, 021 | `e2e/tests/test_smoke.py::test_about_page_renders_pages_file`; `e2e/tests/test_admin_settings.py::test_d6_create_view_delete_page` | e2e |
| FE-PAGE-022 | `e2e/tests/test_smoke.py::test_unknown_page_shows_not_found`; `e2e/tests/test_admin_settings.py::test_d6_create_view_delete_page` | e2e |
| FE-PAGE-023 | non-404 error shown (planned, `frontend/src/test/static-page-view.test.js` › StaticPageView › shows error alert) | unit |
| FE-PAGE-024 | `e2e/tests/test_admin_settings.py::test_d6_traversal_slugs_rejected` (server side of the same rule) | e2e |
| FE-PAGE-030 | `e2e/tests/test_admin_settings.py::test_d6_edit_home_and_footer` | e2e |
| FE-PAGE-031 | description HTML rendered on card (planned, `home-view.test.js` › HomeView › renders description HTML) | unit |
| FE-PAGE-032 | job names, user names escaped (exploratory only: `e2e/exploratory/probes_xss.py`); suite test planned `e2e/tests/test_findings_security.py::test_user_values_never_rendered_as_html` | e2e |
| FE-PAGE-040 | `e2e/tests/test_deep_links.py::test_unknown_route_redirects_home` | e2e |
| contract | `frontend/src/test/contracts/workflows.test.js` › workflows api › lists and gets workflows; `pages_retrieve` fixture validated against `PublicPage` (planned) | contract |

## Known gaps

| ID | What the code does | Where | Severity |
|----|--------------------|-------|----------|
| FE-PAGE-005 | `listWorkflows()` fetches only the first page and the view uses `data.results`; with more than 20 visible workflows the rest never appear on the home page and there is no pagination control. | `frontend/src/api/workflows.js:3-4`, `frontend/src/views/public/HomeView.vue:20-21` | major |
| FE-PAGE-005 | `data.results ?? data` assumes the response may be a bare array, which `schema.yaml` (`PaginatedWorkflowList`) does not allow. | `frontend/src/views/public/HomeView.vue:21` | minor |
| FE-PAGE-031, 033 | Workflow descriptions and page HTML are rendered with `v-html`, no client-side sanitiser and no CSP. A malicious or compromised workflow repository runs script on the app origin for every visitor (accepted by design in plans/QA_FINDINGS.md I-2/I-3; mirrors backend gap BE-SRV-012). | `frontend/src/views/public/HomeView.vue:32,50`, `frontend/src/views/public/StaticPageView.vue:39` | major |
| FE-PAGE-006 | `Login to run` links to `/login` with no `next`, so after login the user lands on the default page, not the workflow. | `frontend/src/views/public/HomeView.vue:61` | minor |
| FE-PAGE-003 | Any `home` page failure, including 500 or network error, is silently ignored. | `frontend/src/views/public/HomeView.vue:18` | minor |
| FE-PAGE-009 | `listCategories()` is defined but never called and `category_name` is not shown; no category grouping exists. | `frontend/src/api/workflows.js:9-10` | minor |
| FE-PAGE-020 | A slow response for a previous slug can overwrite the page for the current slug (no request cancellation or slug check). | `frontend/src/views/public/StaticPageView.vue:14-30` | minor |
| FE-PAGE-007 | A load failure on the home page is not retried and has no retry control. | `frontend/src/views/public/HomeView.vue:22-24` | minor |
| — | No unit tests exist for `HomeView` or `StaticPageView`; `pages_retrieve` has no contract fixture. | `frontend/src/test/` | minor |

## Open questions

1. Should page HTML and workflow descriptions be sanitised (client-side allow-list or server-side), or is a CSP the chosen mitigation? Mirrors [../backend/admin-api.md](../backend/admin-api.md) open question 3 and [../backend/workflow-definition.md](../backend/workflow-definition.md) open questions.
2. Should the SPA show a dedicated "not found" page for unknown routes instead of redirecting to `/` (owned by [routing.md](routing.md))?
3. Should the home page group workflows by category, and is `categories_list` then needed or is `category_name` enough?
