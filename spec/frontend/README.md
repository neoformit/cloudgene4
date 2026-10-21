# Frontend spec

Vue 3 SPA in `frontend/` (Vite, Pinia, vue-router, Bootstrap 5, axios). All files follow
[the constitution](../constitution.md).

| File | Area code | Covers |
|------|-----------|--------|
| [overview.md](overview.md) | ARCH | Build/tooling, entry points (`main.js`, `App.vue`), directory layout, styling, dependencies |
| [api-contract.md](api-contract.md) | API | Every backend operationId → frontend API-module function (or why unused); fixtures and contract tests |
| [api-client.md](api-client.md) | CLIENT | `src/api/client.js`: base URL, CSRF, error helpers, 401 handling, interceptors |
| [routing.md](routing.md) | ROUTE | `src/router/index.js`: route table, auth/admin guards, redirects, deep links, 404 |
| [state-stores.md](state-stores.md) | STORE | Pinia stores: `auth`, `server`, `jobs` |
| [layout-navigation.md](layout-navigation.md) | NAV | App shell, navbar from server config, footer, maintenance banner, admin layout/sidebar |
| [common-components.md](common-components.md) | UI | Alerts, confirm dialog, spinner, pagination, avatar util, shared UI conventions, accessibility |
| [auth-views.md](auth-views.md) | AUTHV | Login, register, activate, password recovery/reset views; client-side validation |
| [profile.md](profile.md) | PROF | Profile view: details, email/password change, API token, account deletion |
| [home-static-pages.md](home-static-pages.md) | PAGE | Home view (workflow list), static HTML pages rendering and safety |
| [workflow-submit-form.md](workflow-submit-form.md) | FORM | Submit view, `DynamicForm`, `ParamInput`, `formModel.js`, per-input-type rendering and validation, submission |
| [job-list.md](job-list.md) | JLIST | User job dashboard: list, filters, pagination, cancel/delete |
| [job-detail.md](job-detail.md) | JDET | Job status page: polling, progress, log tab, results/downloads, cancel |
| [admin-dashboard-jobs.md](admin-dashboard-jobs.md) | ADASH | Admin dashboard (queue, counts, charts) and admin jobs view |
| [admin-users-groups.md](admin-users-groups.md) | AUSER | Admin users view, group management and membership modals |
| [admin-workflows.md](admin-workflows.md) | AWF | Admin workflows list and workflow settings view |
| [admin-settings.md](admin-settings.md) | ASET | General, Nextflow, Mail, Pages (templates) settings and Logs views |
| [tests.md](tests.md) | TEST | Test strategy, commands, traceability (vitest + e2e) |
