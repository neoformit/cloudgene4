# Static assets and SPA delivery

## Purpose

The Vue SPA is built once per deploy into hashed JavaScript/CSS files plus an `index.html` shell.
The web process serves the bundle and Django's own static files through whitenoise and serves the
shell for every client-side route. This file specifies how the bundle is built and placed, how it
is served and cached, and what a deploy must do so that users with the app already open are not
broken by the new release.

## Scope

Covered:

- The production build: `frontend/vite.config.js` (`base`, `build.outDir`, `build.emptyOutDir`),
  `frontend/package.json` scripts, the `/static/` entry in `.gitignore`.
- Static settings in `cloudgene_django/settings.py:206-216` (`STATIC_URL`, `STATICFILES_DIRS`,
  `STATIC_ROOT`, `SPA_INDEX_FILE`, `WHITENOISE_*`) and the whitenoise middleware position
  (`settings.py:119-121`).
- `manage.py collectstatic` as part of a deploy.
- Cache headers for hashed assets, unhashed assets and the SPA shell.
- Asset retention across releases (handoff from FE-ROUTE-052).
- The static-asset checks in `scripts/smoke_gunicorn.sh`.

Out of scope:

- What `spa_index` returns and when (status, `Cache-Control: no-cache`, `csrftoken` cookie, 503
  page): [../backend/server-pages-mail.md](../backend/server-pages-mail.md) BE-SRV-040, BE-SRV-041.
  This file only adds deployment constraints.
- Client-side handling of a failed chunk load: [../frontend/routing.md](../frontend/routing.md) FE-ROUTE-052.
- nginx serving `/static/` itself: [reverse-proxy.md](reverse-proxy.md) DEP-PROXY-016, -017.
- Order of the full upgrade procedure (pip, migrate, restart): [install-upgrade.md](install-upgrade.md).
- The e2e harness build (`e2e/stack.py`, `runserver --insecure`): [test-harness.md](test-harness.md).

## Dependencies

- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — BE-SRV-040..042 (SPA shell, missing build, `/api/` 404).
- [../frontend/routing.md](../frontend/routing.md) — FE-ROUTE-052 (lazy route chunks after a redeploy).
- [../frontend/overview.md](../frontend/overview.md) — build tooling.
- [web-server.md](web-server.md) — the gunicorn process that hosts whitenoise.
- [reverse-proxy.md](reverse-proxy.md) — optional nginx `/static/` location, compression, CSP (the bundle must stay CSP-compatible, DEP-PROXY-021).
- [install-upgrade.md](install-upgrade.md) — where the build/collectstatic/restart steps run.
- Operations: none (static files and the shell are not `/api/` operations).

## Requirements

### Build

- **DEP-STATIC-001** The production bundle MUST be produced by `npm ci && npm run build` in
  `frontend/`, writing to `static/frontend/` at the repository root.
- **DEP-STATIC-002** The bundle's public base path MUST be `/static/frontend/`, equal to
  `STATIC_URL` + `frontend/`; every asset URL in the built `index.html` MUST start with it.
- **DEP-STATIC-003** JavaScript and CSS emitted by the build MUST have a content hash in the file
  name (`assets/<name>-<hash>.<ext>`), so a changed file always has a new URL.
- **DEP-STATIC-004** Build output MUST NOT be committed (`/static/` and `staticfiles/` are
  git-ignored); every deploy that changes `frontend/` MUST rebuild.
- **DEP-STATIC-005** (planned) The Node.js major version used for the build SHOULD be pinned
  (`engines` in `frontend/package.json` or an `.nvmrc`).

### Serving

- **DEP-STATIC-010** In production (`DEBUG=False`) the gunicorn process MUST serve every file under
  `/static/` through whitenoise without nginx configuration; nginx serving `/static/` is optional.
- **DEP-STATIC-011** (planned) **Production static path.** With `DEBUG=False`, whitenoise MUST serve
  `/static/` from `STATIC_ROOT` (`staticfiles/`, populated by `manage.py collectstatic --noinput`)
  only; the finders (`static/`, the build output directory) MUST NOT be used
  (`WHITENOISE_USE_FINDERS = DEBUG`). With `DEBUG=True`, the finders MUST be used so
  `npm run build` alone is enough. `collectstatic` is therefore a required deploy step.
- **DEP-STATIC-012** (planned) With `DEBUG=False`, the SPA shell MUST come from
  `STATIC_ROOT/frontend/index.html` (the same tree as the assets) and MUST be read once per web
  process (at start-up or first request) and served from memory afterwards; the shell a process
  serves and the asset list whitenoise indexed at its start MUST belong to the same release. With
  `DEBUG=True` the shell MAY be read from `static/frontend/index.html` on every request. A missing
  shell MUST still give the 503 page (BE-SRV-041).
- **DEP-STATIC-013** A request for a path under `/static/` that matches no file MUST return 404 and
  MUST NOT return the SPA shell, so a missing chunk fails as a load error (which FE-ROUTE-052
  detects) rather than as HTML parsed as JavaScript.
- **DEP-STATIC-014** whitenoise MUST run directly after `SecurityMiddleware`, so static responses
  get the security headers that middleware sets (DEP-PROXY-020) and skip the rest of the stack.

### Caching

- **DEP-STATIC-020** (planned) Hashed build assets (`/static/frontend/assets/*-<hash>.*`) MUST be
  served with `Cache-Control: max-age=31536000, public, immutable`.
- **DEP-STATIC-021** The SPA shell served by `spa_index` MUST carry `Cache-Control: no-cache`
  (BE-SRV-040), so a browser revalidates it on every navigation and picks up a new release.
- **DEP-STATIC-022** Unhashed static files (Django admin, DRF, `favicon.svg`, `icons.svg`, and
  `/static/frontend/index.html` when requested directly) MUST NOT be cached for longer than
  whitenoise's production default (60 s).
- **DEP-STATIC-023** Static files that change across a deploy without a URL change (DEP-STATIC-022)
  MUST be revalidatable (`Last-Modified` / `ETag`).
- **DEP-STATIC-024** (planned) Text assets SHOULD be stored precompressed (gzip and brotli) at
  `collectstatic` time so whitenoise serves `Content-Encoding` variants to clients that accept them.

### Releases and open tabs

- **DEP-STATIC-030** (planned) After a deploy, every hashed asset referenced by the **previous**
  release's `index.html` MUST still return 200 with its original content for at least 7 days (or
  until the next-but-one release, whichever is later), so a browser tab opened before the deploy
  can still lazy-load routes it has not visited.
- **DEP-STATIC-031** (planned) While a deploy is in progress, the shell served to a new page load and
  the assets the running web process can serve MUST belong to the same release: no page load may
  reference an asset that returns 404, and no request may get the 503 missing-build page. The
  build strategy that meets this is [Release switch](#release-switch): build into `static/`
  (never served in production, DEP-STATIC-011), add the new release to `staticfiles/` with
  `collectstatic` (old files kept, DEP-STATIC-033), and switch with the web restart (DEP-STATIC-012).
- **DEP-STATIC-034** (withdrawn — see [DEP-HARN-017](test-harness.md#requirements), which owns
  what `scripts/smoke_gunicorn.sh` may touch)
- **DEP-STATIC-032** (planned) Old hashed assets kept for DEP-STATIC-030 MUST be pruned after the
  retention window, so `STATIC_ROOT` does not grow without bound.
- **DEP-STATIC-033** `collectstatic` in the upgrade procedure MUST NOT use `--clear`, since that
  deletes the previous release's assets (DEP-STATIC-030).

## Interfaces

### Settings and files

| Item | Value | Reference |
|------|-------|-----------|
| Vite `base` (build) | `/static/frontend/` | `frontend/vite.config.js:8` |
| Vite `build.outDir` | `../static/frontend` | `frontend/vite.config.js:21` |
| Vite `build.emptyOutDir` | `true` | `frontend/vite.config.js:22` |
| `STATIC_URL` | `/static/` | `cloudgene_django/settings.py:208` |
| `STATICFILES_DIRS` | `[BASE_DIR/'static']` if it exists | `settings.py:209` |
| `STATIC_ROOT` | `BASE_DIR/'staticfiles'` | `settings.py:210` |
| `SPA_INDEX_FILE` | `BASE_DIR/'static'/'frontend'/'index.html'` | `settings.py:211` |
| `WHITENOISE_USE_FINDERS` | `True` | `settings.py:213` |
| `WHITENOISE_AUTOREFRESH` | `DEBUG` | `settings.py:214` |
| `STORAGES['staticfiles']` | not set (Django `StaticFilesStorage`: no manifest, no compression) | `settings.py` |
| SPA catch-all | `^(?!static/)(?!django-admin/).*$` → `core.views.spa_index` | `cloudgene_django/urls.py:19` |

### Build output layout

```
static/frontend/
  index.html                 # shell; read by spa_index on every request
  favicon.svg, icons.svg     # copied from frontend/public/, unhashed
  assets/index-<hash>.js     # entry chunk
  assets/<View>-<hash>.js    # lazy route chunks
  assets/*-<hash>.css, fonts # hashed
```

### Release switch

The required production order (static part; the full procedure is
[install-upgrade.md](install-upgrade.md) DEP-INST-021):

```bash
(cd frontend && npm ci && npm run build)   # rewrites static/frontend/ — not served in prod
python manage.py migrate --noinput         # (not static; shown for ordering)
python manage.py collectstatic --noinput   # adds new hashed files to staticfiles/, keeps old ones,
                                           # overwrites staticfiles/frontend/index.html
systemctl restart cloudgene-web            # new process: re-reads shell + re-indexes staticfiles/
```

| Phase | Old web process serves | New page load gets | Old tab lazy-loads |
|-------|------------------------|--------------------|--------------------|
| build, migrate | old shell (memory) + old assets (`staticfiles/`) | old release, consistent | old chunks, 200 |
| after `collectstatic`, before restart | unchanged (shell in memory, index from start-up) | old release, consistent | 200 |
| after restart | new shell + old and new assets | new release | old chunks still 200 (DEP-STATIC-030) |

Only unhashed files overwritten in place by `collectstatic` (admin CSS, `favicon.svg`) can be served
inconsistently in the short gap before restart; the restart MUST follow `collectstatic` directly.

## Behaviour

**Request routing.** `/static/…` is answered by whitenoise inside gunicorn if the file is in its
index; otherwise the request reaches Django's URL resolver, where the SPA catch-all excludes
`static/`, so the result is Django's 404. Any other non-API, non-admin path gets the shell from
`spa_index`.

**File index.** With `WHITENOISE_AUTOREFRESH=False` (production), whitenoise builds its file list
once, at process start, from `STATIC_ROOT` and then (today, `WHITENOISE_USE_FINDERS=True`) from the
finders (`static/`), the finder entry winning for a name present in both. Files added later are not
served until restart; files deleted later stay in the index but can no longer be opened. Required
state (DEP-STATIC-011): `STATIC_ROOT` only, so nothing the build touches is in the served set.

**Cache headers today.** whitenoise marks a file immutable only when its name is a hash produced
by Django's manifest storage. Vite's `-<hash>` names are not recognised and no
`WHITENOISE_IMMUTABLE_FILE_TEST` is set, so every static file, hashed or not, gets whitenoise's
default `max-age=60`. The shell gets `no-cache` from `spa_index`. `scripts/smoke_gunicorn.sh`
prints the asset's `Cache-Control` but does not assert it.

**Redeploy with tabs open (FE-ROUTE-052 handoff).** `npm run build` empties `static/frontend/`,
deleting the previous release's chunks. Whether an old tab can still load them depends on
`STATIC_ROOT`: `collectstatic` without `--clear` leaves the old files there, and after the restart
whitenoise serves them from `STATIC_ROOT`. So the current documented procedure keeps old chunks
by accident; `scripts/smoke_gunicorn.sh` clears the checkout's `staticfiles/` (DEP-HARN-017 gap),
and nothing prunes `STATIC_ROOT`. When an old chunk is gone, the SPA has no fallback today
(FE-ROUTE-052 gap): the click does nothing.

**Deploy window today.** Between `npm run build` and `systemctl restart cloudgene-web`, the
running process still has the old index: `spa_index` already serves the new shell (read from
`static/frontend/index.html` on each request), but the new hashed files are not in whitenoise's
list, so new page loads get 404 for the entry chunk and show a blank page (or the 503 page while
`emptyOutDir` has removed `index.html`). Old tabs fail for chunks removed from `static/` that
whitenoise had indexed there. The documented upgrade runs `migrate` inside this window. The
[Release switch](#release-switch) removes the window by taking `static/` out of the served set
and pinning the shell per process.

**Missing build.** With no `static/frontend/index.html`, every SPA route returns the 503 page
(BE-SRV-041); `/api/` keeps working.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-STATIC-001 | `scripts/smoke_gunicorn.sh` step "Building the SPA (npm run build)" | smoke |
| DEP-STATIC-002 | `scripts/smoke_gunicorn.sh` step "GET a hashed static asset" (asset path matched under `/static/frontend/assets/`) | smoke |
| DEP-STATIC-003 | `scripts/smoke_gunicorn.sh` step "GET a hashed static asset" (`index-<hash>.js` pattern) | smoke |
| DEP-STATIC-004 | (planned) `core/tests/test_deploy.py::StaticConfigTest::test_build_output_is_gitignored` | config |
| DEP-STATIC-010 | `scripts/smoke_gunicorn.sh` step "GET a hashed static asset" (200 from gunicorn, `DEBUG=False`) | smoke |
| DEP-STATIC-011 | (planned) `core/tests/test_deploy.py::StaticConfigTest::test_finders_off_when_debug_off` | config |
| DEP-STATIC-011 | (planned) `scripts/smoke_gunicorn.sh` step "asset missing from staticfiles/ is 404 even if present in static/" | smoke |
| DEP-STATIC-012 | `core/tests/test_api.py::MiscRoutingTest::test_spa_missing_build_message` (missing shell → 503) | unit |
| DEP-STATIC-012 | (planned) `core/tests/test_api.py::MiscRoutingTest::test_spa_shell_read_once_per_process` | unit |
| DEP-STATIC-013 | (planned) `core/tests/test_api.py::MiscRoutingTest::test_missing_static_file_is_404_not_spa` | unit |
| DEP-STATIC-014 | (planned) `core/tests/test_deploy.py::StaticConfigTest::test_whitenoise_follows_security_middleware` | config |
| DEP-STATIC-020 | (planned) `scripts/smoke_gunicorn.sh` step "hashed asset is immutable" (assert `Cache-Control`) | smoke |
| DEP-STATIC-021 | (planned) `core/tests/test_api.py::MiscRoutingTest::test_spa_shell_is_no_cache` | unit |
| DEP-STATIC-022 | (planned) `scripts/smoke_gunicorn.sh` step "unhashed asset has short max-age" | smoke |
| DEP-STATIC-023 | (planned) `scripts/smoke_gunicorn.sh` step "unhashed asset has Last-Modified" | smoke |
| DEP-STATIC-030 | (planned) `scripts/smoke_gunicorn.sh` step "previous release chunk still served after rebuild + restart" | smoke |
| DEP-STATIC-031 | (planned) `scripts/smoke_gunicorn.sh` step "shell and assets consistent after rebuild" | smoke |
| DEP-STATIC-032 | (planned) `core/tests/test_deploy.py::StaticPruneTest::test_prunes_assets_older_than_retention` | unit |
| DEP-STATIC-033 | (planned) `core/tests/test_deploy.py::StaticConfigTest::test_upgrade_procedure_has_no_collectstatic_clear` | config |

DEP-STATIC-005 and DEP-STATIC-024 are SHOULD and have no test.

## Known gaps

| Requirement | Current behaviour | Reference | Severity |
|-------------|-------------------|-----------|----------|
| DEP-STATIC-030 | Old chunks survive a redeploy only because `collectstatic` is run without `--clear`; this is not stated anywhere in `deploy/`, not tested, and the smoke script clears the checkout's `staticfiles/` ([DEP-HARN-017 gap](test-harness.md#known-gaps)). Combined with FE-ROUTE-052, an open tab cannot navigate to an unvisited route after a redeploy that lost its chunks. | `frontend/vite.config.js:22`, `scripts/smoke_gunicorn.sh:46` | major |
| DEP-STATIC-031 | Build happens in place in the served tree while the old process runs; `spa_index` serves the new shell immediately, but whitenoise does not know the new files until restart, so new page loads are blank (or 503) for the whole build → migrate → collectstatic → restart window. | `frontend/vite.config.js:21-22`, `cloudgene_django/settings.py:211-214`, `core/views.py:94-96` | major |
| DEP-STATIC-011 | `WHITENOISE_USE_FINDERS=True` in every environment, so production serves the build directory directly and `collectstatic` is not actually required for the SPA. | `cloudgene_django/settings.py:212-213` | major |
| DEP-STATIC-012 | `SPA_INDEX_FILE` is `static/frontend/index.html` in every environment and is read on every request. | `cloudgene_django/settings.py:211`, `core/views.py:94` | major |
| DEP-STATIC-020 | Hashed Vite assets get `max-age=60` (whitenoise default) instead of a far-future immutable header; browsers revalidate every minute. | `cloudgene_django/settings.py:213-214` | minor |
| DEP-STATIC-032 | Nothing prunes `staticfiles/`; every release's chunks accumulate. | `cloudgene_django/settings.py:210` | minor |
| DEP-STATIC-024 | No `STORAGES` setting, so no precompressed files; whitenoise serves JS/CSS uncompressed. | `cloudgene_django/settings.py:206-216` | minor |
| DEP-STATIC-005 | No `engines` field or `.nvmrc`; the Node version for the build is unpinned. | `frontend/package.json` | minor |
| DEP-STATIC-011 | `scripts/smoke_gunicorn.sh:2-4,45` says that with `DEBUG=False` whitenoise serves from `STATIC_ROOT`, "not the finders"; because finders are on, the smoke test cannot detect a missing `collectstatic`. | `scripts/smoke_gunicorn.sh:45`, `cloudgene_django/settings.py:213` | minor |

## Open questions

1. Settled here: production serves from `STATIC_ROOT` only (DEP-STATIC-011), matching
   `docs/DEPLOYMENT.md` §2; the code (`settings.py:213`) diverges and is recorded as a gap. Confirm
   the maintainer accepts that `collectstatic` becomes mandatory for the SPA in production.
2. DEP-STATIC-030 relies on `collectstatic` without `--clear` plus a prune step (DEP-STATIC-032).
   Should the prune be a management command run by the daily cleanup timer
   ([process-management.md](process-management.md)), or a step in the upgrade procedure?
3. Mechanism for DEP-STATIC-020: `WHITENOISE_IMMUTABLE_FILE_TEST` matching
   `^frontend/assets/.+-[A-Za-z0-9_-]{8,}\.\w+$`, or `CompressedManifestStaticFilesStorage` (adds
   Django-style hashes and covers admin assets, but post-processes Vite CSS and fails on missing
   references)? `CompressedStaticFilesStorage` alone would give DEP-STATIC-024 without the manifest
   risks.
4. Is 7 days the right retention for DEP-STATIC-030? It should cover the longest-lived open tab
   that still has a valid session (`SESSION_COOKIE_AGE`, see [security-hardening.md](security-hardening.md)).
