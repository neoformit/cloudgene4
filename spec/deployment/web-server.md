# Web server (gunicorn) and upload limits

## Purpose

The web process serves the Django application (API, SPA shell, static files through whitenoise)
with gunicorn behind nginx. This file specifies the gunicorn configuration in
`deploy/gunicorn.conf.py`, how each value can be overridden from the environment, how it interacts
with systemd stop handling, and the full chain of request-size limits that decides whether a large
upload reaches the job submission code. It is the single home for the **upload size chain**; the
individual links are owned by the files linked below.

## Scope

Covered:

- `deploy/gunicorn.conf.py` (all settings).
- The interaction between gunicorn timeouts and `deploy/systemd/cloudgene-web.service`
  (`TimeoutStopSec`, `ExecReload`) and nginx timeouts in `deploy/nginx.conf.example`.
- Upload-related Django settings in `cloudgene_django/settings.py:293-301`
  (`FILE_UPLOAD_MAX_MEMORY_SIZE`, `DATA_UPLOAD_MAX_MEMORY_SIZE`, `DATA_UPLOAD_MAX_NUMBER_FILES`)
  and `API_JSON_BODY_MAX_MB` (`core/middleware.py:15`).
- The cross-layer consistency of `server.max_upload_mb` (`home/config/settings.yaml:14`,
  `core/config.py:147`) and nginx `client_max_body_size`.

Out of scope:

- The systemd unit itself (user, sandboxing, restart policy): [process-management.md](process-management.md).
- nginx directives other than as a link in the size/timeout chain: [reverse-proxy.md](reverse-proxy.md).
- The meaning of each environment variable and its default: [environment-config.md](environment-config.md).
- The submission-time size check and its 413 response: [../backend/job-submission.md](../backend/job-submission.md) (BE-JSUB-023) and [../backend/api-contract.md](../backend/api-contract.md) (BE-API-023).
- Log format and shipping: [observability.md](observability.md).

## Dependencies

- [environment-config.md](environment-config.md) — `GUNICORN_*`, `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES`, `API_JSON_BODY_MAX_MB`.
- [reverse-proxy.md](reverse-proxy.md) — `client_max_body_size`, `proxy_read_timeout`, nginx 413 (DEP-PROXY-012..014).
- [process-management.md](process-management.md) — `cloudgene-web.service`.
- [../backend/configuration.md](../backend/configuration.md) — `server.max_upload_mb` (type, default 1024, min 1, editable at runtime).
- [../backend/job-submission.md](../backend/job-submission.md) — BE-JSUB-023 (total upload check, 413 `upload_too_large`).
- [../backend/api-contract.md](../backend/api-contract.md) — BE-API-023 (413 envelope).
- [../frontend/workflow-submit-form.md](../frontend/workflow-submit-form.md) — FE-FORM-024 (client-side size check from `workflows_retrieve.max_upload_mb`).
- Operations: `jobs_create` (multipart upload), `jobs_outputs_retrieve` (large downloads), `health` (readiness probe used by the smoke test).

## Requirements

### Process and binding

- **DEP-WEB-001** The web process MUST be started as
  `gunicorn -c deploy/gunicorn.conf.py cloudgene_django.wsgi:application`, and every value in
  `deploy/gunicorn.conf.py` MUST be overridable by the environment variable listed in
  [Interfaces](#interfaces) without editing the file.
- **DEP-WEB-002** By default gunicorn MUST bind to `127.0.0.1:8000` (loopback only). An operator who
  changes `GUNICORN_BIND` to a non-loopback address MUST also restrict that port to the proxy
  (firewall or private network), because `DJANGO_BEHIND_TLS_PROXY=1` makes Django trust
  `X-Forwarded-Proto` from any client that can reach the port. This file owns the bind rule;
  [api-contract.md](api-contract.md#sockets) lists the address in its socket table.
- **DEP-WEB-003** (withdrawn — see [DEP-ENV-013](environment-config.md#parsing), which owns
  `GUNICORN_*` parsing and requires a bad integer to stop start-up)
- **DEP-WEB-004** The default worker count MUST be `min(2 × CPU + 1, 8)` sync workers with 1 thread
  each.
- **DEP-WEB-005** (withdrawn — see [DEP-API-022](api-contract.md#proxy-headers))

### Timeouts and lifecycle

- **DEP-WEB-010** `GUNICORN_TIMEOUT` (default 300 s) MUST be at least the time the slowest accepted
  request takes inside a worker: receiving an upload of `server.max_upload_mb` from nginx at
  local speed plus copying it into the job workspace. A worker exceeding it is killed and the
  client receives nginx's 502.
- **DEP-WEB-011** nginx `proxy_read_timeout` MUST be greater than or equal to `GUNICORN_TIMEOUT`, so
  that a request gunicorn is still allowed to finish is not cut off by nginx first (504).
- **DEP-WEB-012** On stop (SIGTERM), gunicorn MUST stop accepting new requests and give in-flight
  requests `GUNICORN_GRACEFUL_TIMEOUT` (default 30 s) to finish before killing workers.
- **DEP-WEB-013** (withdrawn — see [DEP-PROC-013](process-management.md#web-cloudgene-webservice))
- **DEP-WEB-014** Each worker MUST be recycled after `GUNICORN_MAX_REQUESTS` (default 10000) requests
  plus up to `GUNICORN_MAX_REQUESTS_JITTER` (default 500), to bound memory growth.
- **DEP-WEB-015** (planned) A job output download (`jobs_outputs_retrieve`) MUST NOT be terminated by
  a web-tier timeout while data is still flowing to the client, for any file size the retention
  policy keeps.
- **DEP-WEB-016** The application MUST be loaded in the master before forking
  (`GUNICORN_PRELOAD_APP=1`, default). Because of this, a code change MUST be applied with a full
  restart (`systemctl restart cloudgene-web`), not with SIGHUP / `systemctl reload`.

### Logging

- **DEP-WEB-020** (withdrawn — see [DEP-OBS-002](observability.md#requirements))
- **DEP-WEB-021** (withdrawn — see [DEP-OBS-006](observability.md#requirements))

### Upload size chain

- **DEP-WEB-030** The total size of file uploads accepted for one job MUST be governed by exactly one
  setting, `server.max_upload_mb`; every other layer's limit MUST be at least as permissive, so a
  submission is rejected for size only by BE-JSUB-023 (413 `upload_too_large`, JSON envelope).
- **DEP-WEB-031** nginx `client_max_body_size` MUST be at least `server.max_upload_mb` MiB **plus**
  headroom for multipart framing and non-file fields. The headroom MUST be at least
  `DATA_UPLOAD_MAX_MEMORY_SIZE` (10 MiB); `deploy/nginx.conf.example` MUST ship a value that
  satisfies this for the default `max_upload_mb` (1024).
- **DEP-WEB-032** gunicorn MUST NOT impose a request-body size limit (it has none by default), and
  `deploy/gunicorn.conf.py` MUST NOT lower the `limit_request_*` header limits below gunicorn's
  defaults.
- **DEP-WEB-033** `DATA_UPLOAD_MAX_MEMORY_SIZE` (10 MiB) MUST bound only non-file form data; a
  multipart request whose non-file fields exceed it MUST receive 413 `upload_too_large` with the
  JSON envelope (BE-API-023), not 400 or 500.
- **DEP-WEB-034** `FILE_UPLOAD_MAX_MEMORY_SIZE` (10 MiB) MUST be the in-memory threshold: any uploaded
  file larger than it MUST be streamed to a temporary file, never held in memory.
- **DEP-WEB-035** A request with more files than `DATA_UPLOAD_MAX_NUMBER_FILES` (set from
  `DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES`, parsed and defaulted by
  [DEP-ENV-027](environment-config.md#requirements)) MUST yield 413 `upload_too_large`.
- **DEP-WEB-036** A non-multipart `/api/` request whose `Content-Length` exceeds `API_JSON_BODY_MAX_MB`
  (parsed and defaulted by [DEP-ENV-027](environment-config.md#requirements)) MUST be rejected
  with 413 `upload_too_large` before the body is read; multipart requests MUST be exempt from this
  check. This file owns the limit semantics of DEP-WEB-035 and DEP-WEB-036.
- **DEP-WEB-037** The host MUST have free space for the temporary copies of an upload in flight: the
  nginx request-body buffer (`client_body_temp_path`), Django's upload temp files (system temp
  directory; private under `PrivateTmp=true`), and the job workspace — up to three copies of
  `max_upload_mb` per concurrent upload.
- **DEP-WEB-038** (planned) Raising `server.max_upload_mb` (admin settings, `admin_settings_general_update`)
  above what nginx admits SHOULD be visible to the operator (for example a warning in the admin
  response or `health` config errors), because the resulting nginx 413 bypasses the JSON envelope.

## Interfaces

### `deploy/gunicorn.conf.py` settings

| gunicorn setting | Env override | Default | Line |
|------------------|--------------|---------|------|
| `bind` | `GUNICORN_BIND` | `127.0.0.1:8000` | 22 |
| `workers` | `GUNICORN_WORKERS` | `min(2*cpu+1, 8)` | 29 |
| `threads` | `GUNICORN_THREADS` | `1` | 30 |
| `worker_class` | `GUNICORN_WORKER_CLASS` | `sync` | 31 |
| `timeout` | `GUNICORN_TIMEOUT` | `300` | 37 |
| `graceful_timeout` | `GUNICORN_GRACEFUL_TIMEOUT` | `30` | 38 |
| `keepalive` | `GUNICORN_KEEPALIVE` | `5` | 39 |
| `forwarded_allow_ips` | `GUNICORN_FORWARDED_ALLOW_IPS` | `127.0.0.1` | 43 |
| `accesslog` | `GUNICORN_ACCESS_LOG` | `-` (stdout) | 45 |
| `errorlog` | `GUNICORN_ERROR_LOG` | `-` (stderr) | 46 |
| `loglevel` | `GUNICORN_LOG_LEVEL` | `info` | 47 |
| `max_requests` | `GUNICORN_MAX_REQUESTS` | `10000` | 51 |
| `max_requests_jitter` | `GUNICORN_MAX_REQUESTS_JITTER` | `500` | 52 |
| `preload_app` | `GUNICORN_PRELOAD_APP` (`1` = on) | on | 54 |

Integer values are parsed by `_int_env` (lines 15-19), which returns the default on a parse error
([DEP-ENV-013 gap](environment-config.md#known-gaps)).

### Upload size chain (request order)

| # | Layer | Limit | Default | Over the limit | Owner |
|---|-------|-------|---------|----------------|-------|
| 1 | SPA form | sum of selected files ≤ `max_upload_mb` MiB | 1024 | blocked client-side, message `Uploads exceed the maximum total size of <n> MB.` | FE-FORM-024 |
| 2 | nginx | `client_max_body_size` (whole request body) | `1024m` | nginx HTML 413, no envelope | DEP-PROXY-012, -013 |
| 3 | nginx | `client_body_timeout` (between reads) | 300 s | 408 | DEP-PROXY-015 |
| 4 | gunicorn | none (body); `timeout` per request | 300 s | worker killed → nginx 502 | DEP-WEB-010 |
| 5 | Django middleware | `API_JSON_BODY_MAX_MB` (non-multipart `/api/` only) | 10 MiB | 413 envelope | DEP-WEB-036 |
| 6 | Django | `DATA_UPLOAD_MAX_MEMORY_SIZE` (non-file fields) | 10 MiB | 413 envelope | DEP-WEB-033 |
| 7 | Django | `DATA_UPLOAD_MAX_NUMBER_FILES` | 10000 | 413 envelope | DEP-WEB-035 |
| 8 | Django | `FILE_UPLOAD_MAX_MEMORY_SIZE` (spool threshold, not a limit) | 10 MiB | file goes to temp file | DEP-WEB-034 |
| 9 | Submission | sum of file sizes ≤ `max_upload_mb` × 1 MiB | 1024 | 413 envelope, message per file input | BE-JSUB-023 |

Consistency rule (DEP-WEB-030, -031): `client_max_body_size ≥ max_upload_mb + DATA_UPLOAD_MAX_MEMORY_SIZE`
and `proxy_read_timeout ≥ GUNICORN_TIMEOUT`.

## Behaviour

**Normal upload.** nginx buffers the whole request body to disk (default
`proxy_request_buffering on`), then sends it to gunicorn over loopback. A slow client therefore
consumes nginx time (`client_body_timeout` per read), not gunicorn time. Django streams each file
over 10 MiB to a temp file; the submission code sums sizes and enforces `max_upload_mb`; accepted
files are moved into the job workspace.

**Boundary mismatch today.** `client_max_body_size 1024m` equals the default `max_upload_mb`.
nginx counts the whole multipart body (boundaries, part headers, non-file fields); the submission
check counts file bytes only. Files totalling just under 1024 MiB pass the client check (layer 1)
but exceed nginx's limit (layer 2): the user sees the generic `Job submission failed.`
(FE-FORM-030 gap) instead of the size message.

**Runtime change of `max_upload_mb`.** Admins can change it without a restart. Nothing re-checks
nginx. Lowering it is safe. Raising it above nginx's limit produces the mismatch above for every
upload between the two values.

**Stop and restart.** systemd sends SIGTERM to the service's cgroup. The gunicorn master waits
`graceful_timeout` (30 s), then kills remaining workers; an in-flight request running longer than
30 s is cut. The unit's `TimeoutStopSec=310` never comes into play (DEP-PROC-013 and its gap in
[process-management.md](process-management.md#known-gaps)).

**Reload.** `ExecReload` sends SIGHUP. With `preload_app` on, gunicorn re-forks workers from the
already-loaded master, so new Python code is **not** picked up; only a restart does that.

**Long downloads.** `jobs_outputs_retrieve` streams a `FileResponse` through a sync worker. nginx
buffers up to `proxy_max_temp_file_size` (nginx default 1024 MiB) of the response; beyond that it
reads from gunicorn only as fast as the client drains. A sync worker that spends more than
`GUNICORN_TIMEOUT` on one response is killed by the arbiter, truncating the download.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-WEB-001 | `scripts/smoke_gunicorn.sh` step "Starting gunicorn" (starts with `-c deploy/gunicorn.conf.py`, `GUNICORN_BIND`/`GUNICORN_WORKERS` overrides) | smoke |
| DEP-WEB-002 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_default_bind_is_loopback` | config |
| DEP-WEB-004 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_default_workers_formula` | config |
| DEP-WEB-010 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_timeout_default_300` | config |
| DEP-WEB-011 | (planned) `core/tests/test_deploy_files.py::DeployFilesConsistencyTest::test_proxy_read_timeout_covers_gunicorn_timeout` | config |
| DEP-WEB-012 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_graceful_timeout_default` | config |
| DEP-WEB-014 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_max_requests_defaults` | config |
| DEP-WEB-015 | (planned) `scripts/smoke_gunicorn.sh` step "slow download of a large output survives GUNICORN_TIMEOUT" | smoke |
| DEP-WEB-016 | (planned) `core/tests/test_deploy_files.py::DeployFilesConsistencyTest::test_web_unit_has_no_misleading_reload` | config |
| DEP-WEB-030 | `jobs/tests/test_api.py::SubmissionTest::test_upload_size_limit` | unit |
| DEP-WEB-031 | (planned) `core/tests/test_deploy_files.py::DeployFilesConsistencyTest::test_client_max_body_size_covers_default_max_upload_mb` | config |
| DEP-WEB-032 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_no_request_limits_lowered` | config |
| DEP-WEB-033 | `core/tests/test_api.py::ErrorEnvelopeHandlerTest::test_upload_suspicious_operations_are_4xx_not_500` | unit |
| DEP-WEB-034 | (planned) `core/tests/test_deploy.py::UploadSettingsTest::test_file_upload_spool_threshold` | config |
| DEP-WEB-035 | `jobs/tests/test_api.py::SubmissionTest::test_many_files_in_folder_input_is_a_client_error_not_500` | unit |
| DEP-WEB-035 | `core/tests/test_api.py::ErrorEnvelopeHandlerTest::test_upload_suspicious_operations_are_4xx_not_500` | unit |
| DEP-WEB-036 | `core/tests/test_deploy.py::JsonBodySizeLimitMiddlewareTest::test_rejects_oversized_json_body_by_content_length_alone` | unit |
| DEP-WEB-036 | `core/tests/test_deploy.py::JsonBodySizeLimitMiddlewareTest::test_exempts_multipart_regardless_of_content_length` | unit |
| DEP-WEB-037 | — host obligation; manual verification: before raising `max_upload_mb`, check free space with `df` on the nginx `client_body_temp_path`, the web unit's private `/tmp` and `CLOUDGENE_HOME` | — |

DEP-WEB-038 is SHOULD and has no test.

## Known gaps

| Requirement | Current behaviour | Reference | Severity |
|-------------|-------------------|-----------|----------|
| DEP-WEB-015 | Sync workers are killed after `timeout` (300 s) on a single request; a large output download to a slow client (beyond nginx's 1 GiB temp-file buffer) is truncated. No `X-Accel-Redirect`, no larger `proxy_max_temp_file_size`, no async/threaded worker. | `deploy/gunicorn.conf.py:31,37`, `jobs/views.py:62` | major |
| DEP-WEB-031 | `client_max_body_size 1024m` equals default `max_upload_mb` with no headroom for multipart overhead; uploads just under the limit get nginx's HTML 413. | `deploy/nginx.conf.example:26`, `home/config/settings.yaml:14` | minor |
| DEP-WEB-038 | `max_upload_mb` can be raised at runtime (min 1, no max) with no check against nginx. | `admin_panel/serializers.py:17` | minor |
| DEP-WEB-016 | `ExecReload=/bin/kill -s HUP` with `preload_app` on does not load new code, so a reload after an upgrade keeps running the old code; nothing warns an operator who uses `systemctl reload`. This is the single home of this gap. | `deploy/systemd/cloudgene-web.service:13`, `deploy/gunicorn.conf.py:54` | minor |
| DEP-WEB-010 | The comment at `deploy/gunicorn.conf.py:33-36` justifies the 300 s timeout by slow clients; behind nginx (request buffering on) slow clients never reach gunicorn. The value is still reasonable for workspace copy time. | `deploy/gunicorn.conf.py:33-37` | minor |
| — | No config test reads `deploy/gunicorn.conf.py`; the smoke script is the only check. | `core/tests/test_deploy.py` | minor |

## Open questions

1. Should `graceful_timeout` default to `timeout` (300 s) so that a restart drains in-flight uploads,
   matching what the unit comment intends? This lengthens every deploy by up to 5 minutes.
2. Fix for DEP-WEB-015: `X-Accel-Redirect` to an nginx `internal` location for job outputs
   (keeps permission checks in Django, frees the worker), or `gthread` workers, or a larger
   `proxy_max_temp_file_size`? `X-Accel-Redirect` changes the download path that BE-JAPI-018..021
   describe and would need nginx to add the `nosniff`/`sandbox` headers.
3. Should `FILE_UPLOAD_TEMP_DIR` point under `CLOUDGENE_HOME` (same filesystem as the job
   workspace, so the final move is a rename and `/tmp` size does not cap uploads)? Today Django uses
   the systemd private `/tmp`.
4. `docs/DEPLOYMENT.md` §4 says to keep `client_max_body_size >= max_upload_mb`; this spec requires
   additional headroom (DEP-WEB-031). The docs should follow.
5. Bind rule (DEP-WEB-002): the shipped files bind loopback only, and the gunicorn config comment
   anticipates a container network CIDR in `GUNICORN_FORWARDED_ALLOW_IPS`. The spec therefore
   allows a non-loopback bind restricted to the proxy by firewall. Confirm this, or forbid
   non-loopback binds outright (the former DEP-API-010 wording). Either way, DEP-RT-020 (workflow
   steps on the same host can reach the loopback port) is unaffected.
