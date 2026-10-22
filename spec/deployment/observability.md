# Observability

## Purpose

Defines how an operator sees what a production Cloudgene deployment is doing: where each process
writes its logs and in what format, how those logs are rotated and retained, how health is
monitored through `/api/health` (including the worker heartbeat), and which alerts an operator
must set up. Cloudgene has no metrics endpoint; monitoring is health polling, log reading and host
metrics.

## Scope

Covered:

| Source | What |
|--------|------|
| `cloudgene_django/settings.py:311-350` | `LOG_LEVEL`, `LOG_FORMAT`, console handler (deployment view) |
| `core/logging_formatters.py` | JSON line format (deployment view) |
| `deploy/gunicorn.conf.py:45-47` | gunicorn access/error log destinations and level |
| `deploy/systemd/*.service`, `cloudgene-cleanup.timer` | Which journald unit each process logs under; log retention job |
| `deploy/nginx.conf.example` | nginx access/error logs (inherited defaults) |
| `deploy/cloudgene.env.example:28-31, 58-63` | Logging variables in production |
| `scripts/smoke_gunicorn.sh` | Health probe in the smoke test |

Out of scope (linked, not restated):

- Logger names, logged events, the `SystemLog` table, JSON key set and the Admin → Logs API →
  [../backend/logging.md](../backend/logging.md).
- `cleanup_logs` and `cleanup_jobs` command behaviour →
  [../backend/management-commands.md](../backend/management-commands.md).
- `/api/health` response semantics → [../backend/server-pages-mail.md](../backend/server-pages-mail.md)
  (BE-SRV-030–035); heartbeat writing → [../backend/job-queue-worker.md](../backend/job-queue-worker.md).
- Per-job Nextflow logs → [../backend/job-runner.md](../backend/job-runner.md) and
  [../backend/job-progress-outputs.md](../backend/job-progress-outputs.md).
- Timer schedule and unit definitions → [process-management.md](process-management.md).
- Variable parsing → [environment-config.md](environment-config.md).

## Dependencies

- [../backend/logging.md](../backend/logging.md) — BE-LOG-001–013.
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — operation `health`
  (`GET /api/health/`, schema component `Health`).
- [../backend/admin-api.md](../backend/admin-api.md) — operation `admin_dashboard` (queue counts;
  admin only).
- [../backend/management-commands.md](../backend/management-commands.md) — BE-CMD-060.
- [process-management.md](process-management.md) — unit names, restart policy, cleanup timer.
- [reverse-proxy.md](reverse-proxy.md) — nginx in front of `/api/health`.
- [security-hardening.md](security-hardening.md) — who may read logs that contain tokens.

## Requirements

Log destinations and format

- **DEP-OBS-001** The web (gunicorn), worker (`run_worker`) and cleanup (`cleanup_jobs`,
  `cleanup_logs`) processes MUST write all log output to stdout/stderr and MUST NOT open log
  files of their own by default. Under systemd this output MUST land in journald under the units
  `cloudgene-web`, `cloudgene-worker` and `cloudgene-cleanup` respectively.
- **DEP-OBS-002** gunicorn's access log and error log MUST default to stdout/stderr (`-`) and MUST
  be redirectable with `GUNICORN_ACCESS_LOG` / `GUNICORN_ERROR_LOG`; its level MUST be set by
  `GUNICORN_LOG_LEVEL` (default `info`), independent of `LOG_LEVEL`.
- **DEP-OBS-003** With `LOG_FORMAT=json`, every application log record (Django and `cloudgene.*`
  loggers, web and worker) MUST be written as exactly one line of JSON, including records with a
  traceback (the traceback goes in `exc_info`). Key set: BE-LOG-004.
- **DEP-OBS-004** The production example environment MUST set `LOG_FORMAT=json` and
  `LOG_LEVEL=INFO`.
- **DEP-OBS-005** `LOG_LEVEL` MUST accept the standard level names case-insensitively. An unknown
  name MUST make the process fail at start-up (Django logging configuration error, non-zero exit)
  rather than run with an unintended level.
- **DEP-OBS-006** (planned) The gunicorn access log SHOULD record the real client address (from
  `X-Forwarded-For` / `X-Real-IP` set by nginx), not the proxy's `127.0.0.1`.
- **DEP-OBS-007** Access logs (nginx and gunicorn) contain one-time activation keys and password
  reset tokens in URL paths. They and the journal MUST be readable only by root and
  administrators (journald default: `systemd-journal`/`adm` group; nginx default: `adm`).

Rotation and retention

- **DEP-OBS-008** Rotation of process output MUST be delegated to journald (its `SystemMaxUse`
  / `MaxRetentionSec`); Cloudgene ships no logrotate config for it. If `GUNICORN_ACCESS_LOG` or
  `GUNICORN_ERROR_LOG` points at a file, the operator MUST rotate it externally and signal
  gunicorn with `USR1` to reopen it.
- **DEP-OBS-009** `SystemLog` rows MUST be pruned daily by `cloudgene-cleanup.service`
  (`cleanup_logs`, default 30 days, BE-CMD-060), so the table does not grow without bound.
- **DEP-OBS-010** Per-job Nextflow logs MUST be removed together with the job workspace by
  `cleanup_jobs` after `server.job_retention_days`; they are not shipped to journald.

Health monitoring

- **DEP-OBS-011** An external monitor MUST poll `GET /api/health/` through the public URL (via
  nginx) at least every 60 s. It MUST treat as failures: connection error or timeout, any status
  other than 200 (503 = database down; 502/504 = gunicorn down), and a body whose `status` is not
  `"ok"`.
- **DEP-OBS-012** The monitor MUST raise a "worker down" alert when `worker.ok` is false on two
  consecutive polls. `worker.ok` turns false when the heartbeat is older than 30 s
  (`WorkerHeartbeat.STALE_AFTER`) or missing; the worker beats every tick (1 s default), so
  30 s tolerates a systemd restart (`RestartSec=5`).
- **DEP-OBS-013** The monitor MUST raise a "configuration invalid" alert when `config.ok` is
  false, reporting `config.errors`.
- **DEP-OBS-014** The operator MUST monitor free space on the filesystems holding
  `$CLOUDGENE_HOME` (job workspaces, uploads), every external Nextflow `work_dir` and `NXF_HOME`
  ([cloudgene-home.md](cloudgene-home.md) DEP-HOME-015, DEP-HOME-016), the host `/tmp` behind the
  units' private `/tmp` (upload spooling, DEP-HOME-012), the database data directory and the
  journal, and alert before they are full. The application exposes no disk signal. This is the
  single home of the disk-space alert; DEP-HOME-014 links here.
- **DEP-OBS-015** The operator SHOULD alert on failed systemd units (`systemctl is-failed
  cloudgene-web cloudgene-worker cloudgene-cleanup`), so a failed nightly cleanup is noticed
  before disk fills.
- **DEP-OBS-016** (planned) `/api/health/` SHOULD expose enough queue state (waiting count, age of
  the oldest waiting job, `paused`) to detect a stuck queue without admin credentials, or the
  deployment MUST document using `admin_dashboard` with an admin API token for that check.
- **DEP-OBS-017** The gunicorn smoke test MUST fetch `/api/health` from a live gunicorn and fail
  if the body has no `status` field.
- **DEP-OBS-018** Because neither `check --deploy` nor `/api/health/` checks the workflow runtime,
  the operator MUST run a runtime preflight after install, after every upgrade and after any
  change to Java, Nextflow or the global `nextflow.env`, before users submit jobs: `nextflow
  -version` run as `cloudgene` with the worker unit's environment file and sandbox (for example
  `systemd-run --uid=cloudgene -p EnvironmentFile=/etc/cloudgene/cloudgene.env
  -p ProtectSystem=strict -p ProtectHome=true -p ReadWritePaths=… --pipe --wait`). It MUST exit 0
  and print the pinned release; otherwise the launcher, Java or a writable `NXF_HOME`
  ([workflow-runtime.md](workflow-runtime.md) DEP-RT-001, DEP-RT-003, DEP-RT-006) is missing.

## Interfaces

### Where each process logs

| Process | Unit | Stream | Format | Contents |
|---------|------|--------|--------|----------|
| gunicorn master/workers | `cloudgene-web` | stderr | gunicorn's own text format | start/stop, worker timeouts/boots, `[CRITICAL] WORKER TIMEOUT` |
| gunicorn access log | `cloudgene-web` | stdout | gunicorn default access format (`%(h)s … "%(r)s" %(s)s …`) | one line per request |
| Django + `cloudgene.*` (web) | `cloudgene-web` | stderr | `LOG_FORMAT` (text or JSON) | app events (BE-LOG-010), unhandled API errors |
| `run_worker` | `cloudgene-worker` | stderr (logs), stdout (start banner) | `LOG_FORMAT` | job state changes, orphan reconcile, tick errors |
| `cleanup_jobs`, `cleanup_logs` | `cloudgene-cleanup` | stdout | plain text summary lines | e.g. `Deleted <n> log entries older than <N> days.` |
| nginx | — (files) | `/var/log/nginx/access.log`, `error.log` (distro defaults, not set in the example) | nginx `combined` | real client IP, status, upstream errors |
| `cloudgene.*` INFO+ | — (DB) | `SystemLog` table | structured row | Admin → Logs (`admin_logs_list`) |
| Nextflow | — (files) | `$CLOUDGENE_HOME/jobs/<id>/logs/` | Nextflow | per-job; job Logs tab |

Reading:

```
journalctl -u cloudgene-web -f
journalctl -u cloudgene-worker -f
journalctl -u cloudgene-cleanup --since today
journalctl -u cloudgene-worker -o cat | jq 'select(.level=="ERROR")'   # with LOG_FORMAT=json
```

### Logging variables

| Variable | Default | Affects |
|----------|---------|---------|
| `LOG_LEVEL` | `INFO` | root and `django` loggers, console handler threshold |
| `LOG_FORMAT` | `standard` | console formatter: `json` → `JsonFormatter`, anything else → text |
| `GUNICORN_ACCESS_LOG` | `-` | gunicorn access log target |
| `GUNICORN_ERROR_LOG` | `-` | gunicorn error log target |
| `GUNICORN_LOG_LEVEL` | `info` | gunicorn's own logger |

The `cloudgene` logger level is fixed at INFO (BE-LOG-002); `LOG_LEVEL` filters only what reaches
the console, never what reaches `SystemLog`.

### Recommended alerts

| Alert | Signal | Condition | Severity |
|-------|--------|-----------|----------|
| Web down | `GET /api/health/` via nginx | connection error, timeout, 502, 504 | page |
| Database down | `GET /api/health/` | 503 or `status: "error"` | page |
| Worker down | `GET /api/health/` | `worker.ok: false` on 2 consecutive polls | page |
| Config invalid | `GET /api/health/` | `config.ok: false` | warn |
| Disk filling | host metrics | `$CLOUDGENE_HOME`, external `work_dir`, `NXF_HOME`, host `/tmp`, DB, journal filesystems > 85 % used | warn; page at 95 % |
| Cleanup failed | systemd | `cloudgene-cleanup.service` in failed state | warn |
| Queue stuck | `admin_dashboard` (admin token) or DB | waiting > 0, running = 0, worker ok, not paused, for > 15 min | warn |
| TLS certificate | external probe | expires in < 14 days | warn |

### Metrics

None. There is no Prometheus/StatsD endpoint and no gunicorn `statsd_host` setting. Request rate
and latency come only from access logs.

## Behaviour

Startup. Logging is configured when Django settings load, so the first line of a misconfigured
`LOG_LEVEL` failure appears in the unit's journal and systemd restarts the unit every 5 s
(`Restart=always`).

Health poll. `/api/health/` runs one `SELECT 1`, reads the heartbeat row and the last
`settings.yaml` load status. It is anonymous and CSRF-free, so a plain `curl -fsS` works. Polling
through nginx also checks TLS and proxying; polling gunicorn directly on `127.0.0.1:8000`
checks only the app.

Worker states as seen by the monitor:

| Situation | `status` | `worker.ok` | HTTP |
|-----------|----------|-------------|------|
| All fine | `ok` | true | 200 |
| Worker stopped or hung > 30 s | `degraded` | false | 200 |
| Worker never started on this DB | `degraded` | false (`last_seen` null) | 200 |
| `settings.yaml` invalid | `degraded` | (any) | 200 |
| Database unreachable | `error` | false | 503 |

Retention. The cleanup service runs `cleanup_jobs` then `cleanup_logs` as two `ExecStart=`
lines of a oneshot unit; if `cleanup_jobs` fails, `cleanup_logs` does not run that night and the
unit is marked failed (DEP-OBS-015).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-OBS-001 | (planned) `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_log_to_journal` (no `StandardOutput=file:`; gunicorn logs `-`) | config |
| DEP-OBS-002 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_log_targets_default_to_stdio` | config |
| DEP-OBS-003 | `core/tests/test_deploy.py::JsonFormatterTest::test_produces_valid_json_with_expected_keys` | unit |
| DEP-OBS-003 | `core/tests/test_deploy.py::JsonFormatterTest::test_extra_data_is_included` | unit |
| DEP-OBS-003 | (planned) `core/tests/test_deploy.py::JsonFormatterTest::test_traceback_stays_on_one_line` | unit |
| DEP-OBS-004 | (planned) `core/tests/test_deploy.py::DeployEnvExampleTest::test_example_uses_json_logging` | config |
| DEP-OBS-005 | (planned) `core/tests/test_deploy.py::LogLevelTest::test_unknown_log_level_fails_startup` | config |
| DEP-OBS-006 | (planned) `core/tests/test_deploy_files.py::GunicornConfigTest::test_access_log_uses_forwarded_client_ip` | config |
| DEP-OBS-007 | — host obligation; manual verification: `ls -l /var/log/nginx/access.log` shows group `adm` and mode without world read; `journalctl` as `cloudgene` without `systemd-journal` membership shows no other units | — |
| DEP-OBS-008 | — host obligation; manual verification: `journalctl --disk-usage` stays under `SystemMaxUse`; if a gunicorn log file is configured, a logrotate rule with `postrotate kill -USR1` exists | — |
| DEP-OBS-009 | (planned) `core/tests/test_deploy_files.py::SystemdUnitsTest::test_cleanup_service_runs_cleanup_logs` | config |
| DEP-OBS-010 | (planned) `core/tests/test_deploy_files.py::SystemdUnitsTest::test_cleanup_service_runs_cleanup_jobs` | config |
| DEP-OBS-011 | `core/tests/test_api.py::HealthTest::test_health_db_down` | unit |
| DEP-OBS-011 | `core/tests/test_api.py::HealthTest::test_health_without_worker` | unit |
| DEP-OBS-012 | `core/tests/test_api.py::HealthTest::test_health_with_fresh_and_stale_heartbeat` | unit |
| DEP-OBS-013 | `core/tests/test_api.py::HealthTest::test_health_reports_a_broken_settings_file` | unit |
| DEP-OBS-013 | `e2e/tests/test_findings_admin.py::test_c02_invalid_settings_value_does_not_take_the_site_down` | e2e |
| DEP-OBS-014 | — host obligation; manual verification: the monitoring system has a free-space alert for each filesystem listed | — |
| DEP-OBS-015 | — host obligation; manual verification: `systemctl start cloudgene-cleanup` with a broken env and confirm the failed-unit alert fires | — |
| DEP-OBS-016 | (planned) `core/tests/test_api.py::HealthTest::test_health_reports_queue_state` | unit |
| DEP-OBS-017 | `scripts/smoke_gunicorn.sh` step "GET /api/health" | smoke |
| DEP-OBS-018 | — host obligation. Manual: run the preflight command of DEP-OBS-018 with the worker unit's `ReadWritePaths=`; it MUST exit 0 and print the expected Nextflow version. | — |

DEP-OBS-007, -008, -014, -015 and -018 are operator obligations on the host; no repository test can
prove them. [tests.md](tests.md) lists them as untestable-in-repo.

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| DEP-OBS-016 | `/api/health/` reports DB, worker and config only. A stuck queue (worker alive but not starting jobs, or queue left paused) is invisible to an anonymous monitor; `admin_dashboard` needs admin credentials. | `core/views.py:49-73` | major |
| DEP-OBS-003 | With `LOG_FORMAT=json`, gunicorn's own error and access lines in the same `cloudgene-web` journal stay plain text, so a log shipper sees mixed formats per unit. | `deploy/gunicorn.conf.py:45-47` (no `logconfig_dict` / `access_log_format`) | minor |
| DEP-OBS-006 | gunicorn access log uses the default format with `%(h)s`, which is `127.0.0.1` behind nginx; no app log records the client IP either. | `deploy/gunicorn.conf.py:45` | minor |
| DEP-OBS-007 | Activation keys and reset tokens are path segments (`/api/auth/activate/<key>/`, `/api/auth/password-reset/<token>/`), so they are written to every access log. | `accounts/urls.py:16-19` | minor |
| — | `LOG_LEVEL=DEBUG` cannot enable DEBUG output for `cloudgene.*` loggers (fixed at INFO); there is no way to get debug logs from the worker in production. | `cloudgene_django/settings.py:348` | minor |
| — | `/api/health/` returns `config.errors` (setting names and messages) to anonymous callers (see BE-SRV-034 gap). | `core/views.py:59-71` | minor |
| — | No metrics endpoint or gunicorn statsd integration exists. | `deploy/gunicorn.conf.py` | minor |

## Open questions

1. Should Cloudgene expose metrics (e.g. a Prometheus endpoint with queue depth, job counts per
   state, heartbeat age), or is health polling plus logs enough for the target deployments?
2. Should the health response add a `queue` block (DEP-OBS-016), and should it then require
   a token or stay anonymous?
3. Should gunicorn's logs go through Django's `LOGGING` (`logconfig_dict`) so `LOG_FORMAT=json`
   covers the whole `cloudgene-web` journal?
4. `docs/DEPLOYMENT.md` §7 says SystemLog "survives `cleanup_logs`' retention window rather than
   journald's own log rotation", which reads as the opposite of the code (SystemLog is pruned by
   `cleanup_logs`, independently of journald). Docs wording to fix?
