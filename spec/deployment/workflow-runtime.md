# Workflow runtime on the host

## Purpose

The worker runs each job step as a child process on the host: Nextflow (a Java program) for
`nextflow` steps, or an executable / `bash -c` script for `command` steps. This file specifies what
the host must provide for those processes under systemd (Java, Nextflow, `bash`, writable cache and
work directories), how the global and per-app `nextflow.config` / `nextflow.env` files are used in
a deployment, which environment the processes inherit and how the deployment must limit the
secrets in it, and what isolation exists (or does not) between jobs, the worker and the web app.
How the runner builds command lines and environments is owned by
[../backend/job-runner.md](../backend/job-runner.md); this file only states the host-side
consequences.

## Scope

Covered:

- Host prerequisites for step processes: Java, Nextflow, `bash`, command-step tools.
- Worker environment under `deploy/systemd/cloudgene-worker.service` (PATH, HOME, `NXF_HOME`, `/tmp`).
- Deployment use of `CLOUDGENE_HOME/config/nextflow.config` and `nextflow.env` (shipped in `home/config/`).
- Nextflow work directories, executors (local and cluster) and container engines as deployment assumptions.
- Environment inheritance and the server-secrets leak (BE-RUN-019) — the deployment-side mitigation.
- Resource limits and isolation between jobs, and between jobs and the web app; network access of pipelines.

Code read: `jobs/runner.py` (`build_env` :117-129, `work_dir_for` :146-152, `find_bash` :181-182,
`prepare_command` :185-207, `prepare_step` :210-246, `resolve_binary` :249-254),
`jobs/worker.py:265-268`, `:308-311` (process launch), `workflows/template_utils.py:15-46`
(`CLOUDGENE_SMTP_*`), `core/config.py:385-401` (`parse_env`), `deploy/systemd/cloudgene-worker.service`.

Out of scope:

- Command line, env build order, exit handling and logs: [../backend/job-runner.md](../backend/job-runner.md).
- Queue limits, cancellation, graceful shutdown, orphan recovery: [../backend/job-queue-worker.md](../backend/job-queue-worker.md).
- The `nextflow.*` keys in `settings.yaml`: [../backend/configuration.md](../backend/configuration.md).
- Unit restart/stop/kill semantics: [process-management.md](process-management.md).
- `CLOUDGENE_HOME` layout, modes and retention of work dirs: [cloudgene-home.md](cloudgene-home.md).
- Database role privileges and `pg_hba.conf`: [database.md](database.md).
- Host firewalling in general: [security-hardening.md](security-hardening.md).

## Dependencies

- [../backend/job-runner.md](../backend/job-runner.md) — BE-RUN-005 (binary), BE-RUN-006 (command line),
  BE-RUN-010 (work dir), BE-RUN-012/013 (command argv, bash), BE-RUN-017/018/019 (environment).
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md) — `max_running_jobs`, BE-QUEUE-027.
- [process-management.md](process-management.md) — `cloudgene-worker.service`, its sandbox options.
- [cloudgene-home.md](cloudgene-home.md) — file modes of `nextflow.env` (DEP-HOME-009), external
  `work_dir` cleanup (DEP-HOME-015).
- [environment-config.md](environment-config.md) — the variables in `cloudgene.env`.
- [database.md](database.md) — DEP-DB-060 (role not superuser), DEP-DB-061 (no password-less access).
- [api-contract.md](api-contract.md) — DEP-API-051 (env file mode).
- Contract operations that change the runtime configuration: `admin_settings_nextflow_update`,
  `admin_workflows_nextflow_update`, `admin_workflows_install`
  ([../backend/api-contract.md](../backend/api-contract.md)).

## Requirements

### Executables

- **DEP-RT-001** A `nextflow` launcher MUST be installed where the worker finds it under systemd:
  either on the unit's default `PATH` (systemd's built-in `PATH`; `cloudgene.env` does not set one),
  at `/usr/local/bin/nextflow` (the runner also searches there), or at the absolute path set in
  `nextflow.binary`. Otherwise every Nextflow step fails with `Could not start Nextflow (<binary>): …`
  (BE-RUN-024).
- **DEP-RT-002** The launcher, the Java runtime and all command-step tools MUST be installed outside
  `/home`, `/root` and `/run/user` and be readable and executable by `cloudgene`, because the worker
  unit sets `ProtectHome=true`.
- **DEP-RT-003** A Java runtime of the version the installed Nextflow release requires (Java 17 or
  later for current releases) MUST be reachable by the launcher from the worker's environment:
  `java` on the unit's `PATH`, or `JAVA_HOME` set in `CLOUDGENE_HOME/config/nextflow.env`.
- **DEP-RT-004** The installed Nextflow MUST accept every option the runner passes (BE-RUN-006:
  `-log`, `run`, `-r`, `-params-file`, repeated `-c`, `-profile`, `-w`, `-with-trace`,
  `-with-report`, `-with-timeline`, `-ansi-log false`) and the `trace`/`report`/`timeline`
  `overwrite` settings of the generated `cloudgene.config`. The deployment SHOULD pin the release
  with `NXF_VER=<version>` in the global `nextflow.env` so the launcher does not drift or
  self-update.
- **DEP-RT-005** `bash` MUST be present at `/bin/bash` or on the step `PATH` when any installed app
  has a `bash: true` command step (BE-RUN-013). Executables named by command steps are looked up on
  the step `PATH` (worker `PATH` + `/usr/local/bin` + `PATH` from env files) and MUST be installed
  there; a missing one fails the job (BE-RUN-024).

### Nextflow state, configuration and work directories

- **DEP-RT-006** The Nextflow home (`NXF_HOME`; default `$HOME/.nextflow`, with `HOME` taken from the
  `cloudgene` user's passwd entry) MUST be writable inside the worker's sandbox, i.e. under a
  `ReadWritePaths=` entry. It SHOULD be set explicitly in the global `nextflow.env` to a dedicated
  directory outside the code checkout (it holds the launcher's framework JARs, plugins and pulled
  pipelines).
- **DEP-RT-007** The global `config/nextflow.config` and `config/nextflow.env` are passed to every
  run before the app's own files (BE-RUN-006, BE-RUN-017). The shipped versions contain only
  comments. On a host using the local executor, the global `nextflow.config` SHOULD set
  `executor.cpus` and `executor.memory` so that `server.max_running_jobs` concurrent runs fit in
  the host's capacity minus what web, worker and database need.
- **DEP-RT-008** Nextflow configuration and env files are code: Groovy config and env values run
  with the full rights of the `cloudgene` user. Admin accounts (who can edit them through
  `admin_settings_nextflow_update` and `admin_workflows_nextflow_update`, and install workflows)
  MUST be given only to people trusted with a shell as `cloudgene`.
- **DEP-RT-009** An external `work_dir` (`nextflow.work_dir` or a per-app `work_dir`, BE-RUN-010)
  MUST be an absolute path listed in the worker unit's `ReadWritePaths=`; a relative value is
  resolved under `CLOUDGENE_HOME`. It MUST NOT be inside the code checkout. Its cleanup is
  specified in [cloudgene-home.md](cloudgene-home.md) (DEP-HOME-015).
- **DEP-RT-010** The worker's `/tmp` is private (`PrivateTmp=true`) and lives on the root
  filesystem. Pipelines that use large temporary space SHOULD get `TMPDIR` (and `NXF_TEMP`) pointed
  at a large filesystem in `ReadWritePaths=` through the global `nextflow.env`.

### Executors and containers

- **DEP-RT-011** The supported default is Nextflow's `local` executor: all tasks run on the worker
  host as `cloudgene`, inside the worker unit's cgroup. A cluster executor MAY be configured through
  a profile or `nextflow.config`; then `CLOUDGENE_HOME/jobs` and every `work_dir` MUST be mounted at
  the same path on all compute nodes (params files and inputs are absolute workspace paths,
  `jobs/runner.py:81-98`), and the scheduler's client commands MUST be on the worker's step `PATH`.
- **DEP-RT-012** The code does not reference any container engine; containers are used only through
  a pipeline's own profile or config. The `cloudgene` user SHOULD NOT be added to the `docker`
  group (that is root-equivalent on the host); a rootless engine or Apptainer/Singularity in
  unprivileged (non-setuid) mode SHOULD be used, because the unit sets `NoNewPrivileges=true`.
  Image caches (`NXF_SINGULARITY_CACHEDIR`, `NXF_APPTAINER_CACHEDIR`) MUST be under `ReadWritePaths=`
  when used.

### Environment and secrets

- **DEP-RT-013** Step processes inherit the worker's whole environment (BE-RUN-017): under systemd
  that is systemd's own variables (`PATH`, `HOME`, `USER`, `LANG`, `INVOCATION_ID`, …) plus every
  variable in `/etc/cloudgene/cloudgene.env`, including `DJANGO_SECRET_KEY` and `DATABASE_URL`
  with the database password. Until BE-RUN-019 removes them in code, the global
  `CLOUDGENE_HOME/config/nextflow.env` MUST blank every server variable from `cloudgene.env` with an
  empty assignment — at least `DJANGO_SECRET_KEY=`, `DATABASE_URL=`, and every other `DJANGO_*`,
  `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `DB_*` and `GUNICORN_*` variable that is set. An empty `KEY=` line
  sets the variable to `""` for both Nextflow and command steps, and later `${KEY}` expansion in
  app env files sees the blank value.
- **DEP-RT-014** Blanking (DEP-RT-013) is not isolation. Step processes run as the same OS user as
  the worker and web app and can read `/proc/<worker pid>/environ`, `config/settings.yaml`,
  `config/secret_key`, and every job's workspace; they also receive `CLOUDGENE_SMTP_PASSWORD` by
  design (BE-RUN-018). The deployment MUST therefore: keep `cloudgene.env` root-only
  ([DEP-API-051](api-contract.md#filesystem)); make the database refuse password-less access for
  the `cloudgene` OS user ([DEP-DB-061](database.md#role-and-access)); and treat every installed
  workflow as trusted code (DEP-RT-008).
  The SMTP account in `mail.*` SHOULD be a dedicated, send-only credential.
- **DEP-RT-015** Step processes MUST NOT be able to modify the application code, its virtualenv or
  the built static files. The unit options that ensure this are
  [DEP-PROC-009](process-management.md#common-to-all-units).

### Isolation and resources

- **DEP-RT-016** Step processes MUST be started only by the worker, never by the web process, and the
  web and worker MUST run in separate systemd units, so job processes live in the worker's cgroup
  and a runaway job cannot consume the web unit's limits or be killed by a web restart.
- **DEP-RT-017** The worker unit SHOULD set resource limits (`MemoryMax=`, `TasksMax=`, and
  `CPUWeight=` or `CPUQuota=`) that leave headroom for the web app and the database; concurrency is
  otherwise bounded only by `server.max_running_jobs` and the Nextflow executor limits (DEP-RT-007).
- **DEP-RT-018** (planned) A job's step processes MUST NOT be able to read or modify another job's
  workspace or work directory.

### Network

- **DEP-RT-019** Step processes have the worker's network access; the units impose no egress
  restriction. The deployment MUST allow the outbound access the installed workflows need:
  HTTPS to the Nextflow download and plugin sites on first use of a release or plugin, to the
  source host (e.g. GitHub) for remote pipelines (`script: owner/repo`, BE-RUN-008), and to any
  container registries. Offline hosts MUST pre-populate `NXF_HOME` and set `NXF_OFFLINE=true` in
  the global `nextflow.env`.
- **DEP-RT-020** Step processes can reach services bound to `127.0.0.1` on the host, including
  PostgreSQL and gunicorn (whose `GUNICORN_FORWARDED_ALLOW_IPS` default `127.0.0.1` trusts
  `X-Forwarded-*` headers from them). The deployment SHOULD restrict job egress per site policy
  (for example an nftables rule matching the `cloudgene` UID that allows only the database port to
  the worker itself); systemd `IPAddressDeny=` on the worker unit alone cannot be used, because the
  worker needs the database.

## Interfaces

### Worker process environment under systemd

| Source | Variables | Reaches steps today | Interim mitigation |
|--------|-----------|---------------------|--------------------|
| systemd (`User=cloudgene`) | `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `INVOCATION_ID`, `LANG` | yes | none needed |
| `/etc/cloudgene/cloudgene.env` | `DJANGO_*`, `DATABASE_URL`, `DB_CONN_MAX_AGE`, `CLOUDGENE_HOME`, `LOG_*`, `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `API_JSON_BODY_MAX_MB`, `GUNICORN_*` | yes | blank in global `nextflow.env` (DEP-RT-013) |
| runner | `PATH` += `/usr/local/bin`, `NXF_ANSI_LOG=false` | yes | — |
| global / app `nextflow.env` | admin-defined | yes | mode `0600` (DEP-HOME-009) |
| runner (`CLOUDGENE_*`) | job, user, app, service and `CLOUDGENE_SMTP_*` values | yes, by design | dedicated SMTP credential (DEP-RT-014) |

### Recommended global `CLOUDGENE_HOME/config/nextflow.env`

```sh
# Pin the Nextflow release and keep its state out of the code checkout
NXF_VER=24.10.4
NXF_HOME=/var/lib/cloudgene-nxf
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
TMPDIR=/var/lib/cloudgene-nxf/tmp
# Interim for BE-RUN-019: blank the web app's secrets for every step process
DJANGO_SECRET_KEY=
DATABASE_URL=
EMAIL_BACKEND=
DEFAULT_FROM_EMAIL=
DJANGO_SECURE_COOKIES=
DJANGO_SECURE_SSL_REDIRECT=
DJANGO_BEHIND_TLS_PROXY=
DJANGO_HSTS_SECONDS=
DJANGO_HSTS_PRELOAD=
DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES=
```

Values are examples; paths in it must also appear in the worker unit's `ReadWritePaths=`
(`/var/lib/cloudgene-nxf` is not in the shipped unit).

### Recommended global `nextflow.config` for the local executor

```groovy
// max_running_jobs = 2 on a 32-core / 128 GB host, leaving room for web + DB
executor {
    name   = 'local'
    cpus   = 14
    memory = '56 GB'
}
```

## Behaviour

- **Start of a Nextflow step.** The runner resolves the binary (BE-RUN-005), builds the env
  (worker env → `/usr/local/bin` → global env file → app env file → `CLOUDGENE_*` →
  `NXF_ANSI_LOG`), and the worker starts it in a new session with the job workspace as cwd. The
  launcher finds Java via `JAVA_HOME` or `PATH`, downloads the framework into `NXF_HOME` if
  `NXF_VER` is not cached yet (needs network), pulls remote pipelines into `NXF_HOME/assets`, and
  writes task data under `-w` (default `jobs/<uuid>/work`). `jobs/<uuid>/.nextflow/` (Nextflow's
  run cache) is created in the workspace.
- **Missing runtime.** No start-up or health check verifies Nextflow or Java. The first job fails:
  missing binary → `Could not start Nextflow (…)`; missing Java or unwritable `NXF_HOME` → the
  launcher exits non-zero and the job fails with the tail of its output (BE-RUN-022).
- **Blanked variables.** With DEP-RT-013 in place, `DATABASE_URL` and `DJANGO_SECRET_KEY` are empty
  strings in step processes. Nothing in Nextflow or a command step needs them.
- **Sandbox writes.** Under `ProtectSystem=strict`, a step that writes outside `ReadWritePaths=` or
  the private `/tmp` gets `EROFS`/`EACCES`, and the job fails with the tool's own error.
- **Stop/cancel.** Nextflow, on SIGTERM from the worker, cancels its tasks (including cluster jobs)
  before exiting; local tasks are in the same process group and cgroup. Kill timing is in
  [process-management.md](process-management.md) and [../backend/job-queue-worker.md](../backend/job-queue-worker.md).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-RT-001 | `jobs/tests/test_worker.py::WorkerFailureTest::test_missing_binary` | unit |
| DEP-RT-001 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` (real Nextflow, harness not systemd) | e2e |
| DEP-RT-001 | `scripts/smoke_runtime.sh` (planned: runs `nextflow -version` via `systemd-run` with the worker unit's user, env file and sandbox) | smoke |
| DEP-RT-002 | `scripts/smoke_runtime.sh` (planned) | smoke |
| DEP-RT-003 | `scripts/smoke_runtime.sh` (planned) | smoke |
| DEP-RT-004 | `e2e/tests/test_jobs.py::test_submit_hello_with_unicode_job_name` | e2e |
| DEP-RT-004 | `e2e/tests/test_jobs.py::test_live_progress_multi_process` | e2e |
| DEP-RT-005 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_missing_executable` | unit |
| DEP-RT-005 | `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` | e2e |
| DEP-RT-006 | `scripts/smoke_runtime.sh` (planned: launcher run writes to `NXF_HOME` inside the sandbox) | smoke |
| DEP-RT-008 | — host obligation; manual verification: review the admin user list (`/admin/users`) against the people allowed a shell as `cloudgene` | — |
| DEP-RT-009 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_worker_read_write_paths_exclude_code_checkout` (planned) | config |
| DEP-RT-009 | `e2e/tests/test_findings_jobs.py::test_a04_per_app_work_dir_is_an_allowed_output_root` | e2e |
| DEP-RT-011 | — host obligation; manual verification (cluster executors only): on a compute node, `ls $CLOUDGENE_HOME/jobs` and each `work_dir` show the same paths as on the worker host, and the scheduler client is on the step `PATH` | — |
| DEP-RT-012 | — host obligation; manual verification: `id cloudgene` does not list `docker`; image cache variables point under `ReadWritePaths=` | — |
| DEP-RT-013 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_global_env_file_blanks_inherited_variables` (planned) | unit |
| DEP-RT-013 | `core/tests/test_deploy.py::NextflowEnvTest::test_shipped_nextflow_env_blanks_server_secrets` (planned) | config |
| DEP-RT-013 | `jobs/tests/test_worker.py::test_server_secrets_not_in_step_env` (planned, BE-RUN-019) | unit |
| DEP-RT-014 | `scripts/smoke_runtime.sh` (planned: `psql` as `cloudgene` without a password is refused) | smoke |
| DEP-RT-015 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_worker_read_write_paths_exclude_code_checkout` (planned) | config |
| DEP-RT-016 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_web_and_worker_are_separate_units` (planned) | config |
| DEP-RT-018 | `scripts/smoke_runtime.sh` (planned: a step cannot read another job's workspace) | smoke |
| DEP-RT-019 | `scripts/smoke_runtime.sh` (planned: launcher reaches its download host, or `NXF_OFFLINE` is set) | smoke |

## Known gaps

| Requirement | What the code/config does | Where | Severity |
|-------------|---------------------------|-------|----------|
| DEP-RT-013 | The worker passes its full environment, including `DJANGO_SECRET_KEY` and `DATABASE_URL` with the DB password, to every step process (BE-RUN-019). The shipped `nextflow.env` does not blank them, so a default install leaks both to every pipeline and command. | `jobs/runner.py:118`; `home/config/nextflow.env`; `deploy/systemd/cloudgene-worker.service:11` | major |
| DEP-RT-015 | Any pipeline can rewrite the application code, because the units list the checkout in `ReadWritePaths=`. Details: [DEP-PROC-009 gap](process-management.md#known-gaps). | `deploy/systemd/cloudgene-worker.service:26` | major |
| DEP-RT-018 | All jobs run as the same OS user with no per-job sandbox, and workspaces are created `0755`; any step can read and modify other users' job data. | `jobs/worker.py:265-268`, `:308-311` | major |
| DEP-RT-006 | With the documented `useradd --home /opt/cloudgene`, `NXF_HOME` defaults to `/opt/cloudgene/.nextflow`, inside the git checkout and not in `.gitignore`; it is writable only because the checkout is in `ReadWritePaths=`, which DEP-PROC-009 forbids. | `deploy/systemd/cloudgene-worker.service`; `.gitignore` | minor |
| DEP-RT-017 | No unit sets `MemoryMax=`, `TasksMax=` or CPU limits; the shipped `nextflow.config` sets no executor limits, so each local run may assume the whole host. | `deploy/systemd/cloudgene-worker.service`; `home/config/nextflow.config` | minor |
| DEP-RT-001, DEP-RT-003 | Nothing checks the runtime before the first job (no `check --deploy` item, no `/api/health` field); a missing Java or Nextflow is discovered by a failing user job. | `core/checks.py`; `core/server_views.py` | minor |
| DEP-RT-020 | Steps can send requests to gunicorn on `127.0.0.1:8000` with forged `X-Forwarded-For`/`-Proto` headers, bypassing nginx, because gunicorn trusts forwarded headers from `127.0.0.1`. | `deploy/gunicorn.conf.py:43` | minor |

## Open questions

1. Which Nextflow and Java versions are supported? Nothing in the code or deploy files pins them;
   `plans/SPEC.md` mentions Java 17 and `/usr/local/bin/nextflow`, `docs/DEPLOYMENT.md` says
   "Java 17+". Should the spec name a minimum Nextflow release (for `report.overwrite` /
   `timeline.overwrite`) and should `check --deploy` verify it?
2. Is per-job isolation (DEP-RT-018) in scope at all — for example running steps under a separate
   unprivileged user or a per-job transient systemd scope — or is Cloudgene a single-tenant tool
   where all users trust each other?
3. Should the worker get its own environment file without `DJANGO_SECURE_*`, `GUNICORN_*` and
   other web-only variables, reducing what DEP-RT-013 has to blank?
4. Should `CLOUDGENE_SMTP_PASSWORD` (inherited from Cloudgene 3) keep reaching every step, or be
   opt-in per app?
5. Where should `NXF_HOME` live by default: under `CLOUDGENE_HOME` (inside the existing
   `ReadWritePaths=`) or a sibling directory that the units must list?
