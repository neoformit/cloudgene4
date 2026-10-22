# CLOUDGENE_HOME in production

## Purpose

`CLOUDGENE_HOME` is the one directory that holds all of Cloudgene's on-disk state: application
settings, generated secrets, lock files, admin-edited pages, installed workflow apps and job
workspaces. This file specifies where that directory lives in production, who owns it, which file
modes it needs, what the repository's `home/` ships versus what appears at runtime, how disk use is
bounded by retention, and what a backup must contain. The application's view of the same paths
(what each module reads and writes) is owned by [../backend/configuration.md](../backend/configuration.md).

## Scope

Covered:

- `CLOUDGENE_HOME` value and its relation to the systemd units (`deploy/cloudgene.env.example`,
  `deploy/systemd/cloudgene-{web,worker,cleanup}.service`, `cloudgene-cleanup.timer`).
- Ownership and file modes of `CLOUDGENE_HOME` and the files in it.
- The committed defaults in `home/` and their use at first install.
- `.gitignore` coverage of runtime files under the repository's `home/` (development default).
- Disk space, retention (`cleanup_jobs`, `cleanup_logs`) and backup/restore scope of `CLOUDGENE_HOME`.

Code read: `cloudgene_django/settings.py:64-89` (home path, secret key), `core/config.py:282-349`
(paths, `ensure_home`), `core/config.py:362-382` (`write_text_atomic`), `core/config.py:523-531`
(settings lock), `jobs/worker.py:807-823` (worker lock), `core/mail.py:34-38` (mail outbox),
`jobs/management/commands/cleanup_jobs.py`, `admin_panel/management/commands/cleanup_logs.py`.

Out of scope:

- The schema and semantics of `settings.yaml`: [../backend/configuration.md](../backend/configuration.md).
- Workspace contents written by submission and runner: [../backend/job-submission.md](../backend/job-submission.md),
  [../backend/job-runner.md](../backend/job-runner.md).
- Command behaviour of `cleanup_jobs` / `cleanup_logs`: [../backend/management-commands.md](../backend/management-commands.md).
- Nextflow work directories, `NXF_HOME` and caches as a runtime concern: [workflow-runtime.md](workflow-runtime.md).
- Environment variables in general and `cloudgene.env` permissions: [environment-config.md](environment-config.md).
- Unit sandboxing options other than paths: [process-management.md](process-management.md).
- Database backups: [database.md](database.md).

## Dependencies

- [../backend/configuration.md](../backend/configuration.md) — `CLOUDGENE_HOME` layout table, BE-CONF-015.
- [../backend/job-queue-worker.md](../backend/job-queue-worker.md) — worker lock, retention rules (BE-QUEUE-026, BE-QUEUE-027).
- [../backend/management-commands.md](../backend/management-commands.md) — BE-CMD-050..055, BE-CMD-060.
- [../backend/server-pages-mail.md](../backend/server-pages-mail.md) — missing-page behaviour (BE-SRV-003, BE-SRV-013).
- [process-management.md](process-management.md) — the units that run as `cloudgene` with `ReadWritePaths=`.
- [workflow-runtime.md](workflow-runtime.md) — external `work_dir`, `NXF_HOME`.
- [database.md](database.md) — DB half of a consistent backup.
- Contract operations that write into `CLOUDGENE_HOME` (listed so a reader knows which API calls
  change files here): `admin_settings_general_update`, `admin_settings_mail_update`,
  `admin_settings_nextflow_update`, `admin_pages_update`, `admin_pages_destroy`, `admin_workflows_install`, `admin_workflows_nextflow_update`, `jobs_create`
  (see [../backend/api-contract.md](../backend/api-contract.md)).

## Requirements

### Location and ownership

- **DEP-HOME-001** In production `CLOUDGENE_HOME` MUST be set in the environment file to an absolute
  path outside the code checkout (reference value `/var/lib/cloudgene`). The web, worker and cleanup
  units MUST all load the same environment file so they resolve the same directory. If it is unset,
  the app falls back to `<repo>/home` (`cloudgene_django/settings.py:64`), which mixes runtime data
  into the git checkout.
- **DEP-HOME-002** The web, worker and cleanup processes MUST run as the same OS user (`cloudgene`),
  and that user MUST own `CLOUDGENE_HOME` and everything below it. The web process writes uploads
  into `jobs/<uuid>/input/` and the worker writes the rest of the same workspace; different users
  would break that.
- **DEP-HOME-003** `CLOUDGENE_HOME` MUST have mode `0750` or stricter, so other local users cannot
  traverse into job data, `config/` or the mail outbox. The units SHOULD set `UMask=0027` (or
  `0077`) so new directories and files are not world-readable.
- **DEP-HOME-004** Each unit that writes to `CLOUDGENE_HOME` (web, worker, cleanup) MUST list that
  exact path in `ReadWritePaths=`, because `ProtectSystem=strict` makes everything else read-only.
  Changing `CLOUDGENE_HOME` MUST be accompanied by the same change in all three units.
- **DEP-HOME-005** `config/` (which holds `.settings.lock` and `worker.lock`) MUST be on a filesystem
  where `fcntl.flock` locks are honoured between processes on the host (a local filesystem). The
  lock files MUST NOT be deleted while web or worker processes run; a deleted `worker.lock` would
  let a second worker start.

### Layout, defaults and first install

- **DEP-HOME-006** An empty or partially populated `CLOUDGENE_HOME` MUST be a valid starting state:
  each component creates the directories it writes on first use, and a missing `settings.yaml`
  MUST mean "all defaults" without error ([BE-CONF](../backend/configuration.md)). No process
  creates the full layout at start-up (`core.config.ensure_home()` has no production caller).
- **DEP-HOME-007** At first install the operator MUST seed `CLOUDGENE_HOME` from the repository's
  `home/` without overwriting files that already exist: `config/settings.yaml`,
  `config/nextflow.config`, `config/nextflow.env`, `pages/home.html`, `pages/footer.html`,
  `pages/about.html`. Without this, the home page returns 404 (the SPA shows its built-in default,
  BE-SRV-013), the footer is empty (BE-SRV-003) and the `About` navbar link points to a missing page.
- **DEP-HOME-008** `config/settings.yaml` MUST have mode `0600` (owner `cloudgene`), because it holds
  `mail.password` in plain text. Until BE-CONF-015 is fixed, the deployment MUST obtain this by
  creating the file with mode `0600` at first install (DEP-HOME-007, e.g. `install -m 0600`); later
  rewrites keep the existing mode (`core/config.py:374-375`).
- **DEP-HOME-009** `config/nextflow.env` and every `apps/<id>/nextflow.env` SHOULD have mode `0600`;
  they are the only place for credentials that pipelines need (tokens, registry passwords). As with
  `settings.yaml`, the mode of an existing file is kept on rewrite; a new file gets `0644`.
- **DEP-HOME-010** A `config/secret_key` that the operator copies or restores (for example from a
  backup, DEP-DB-040) MUST keep owner `cloudgene` and mode `0600`. Generation by the app is
  [DEP-ENV-030](environment-config.md#secret-key).
  Production SHOULD set `DJANGO_SECRET_KEY` instead ([environment-config.md](environment-config.md));
  an existing file is then ignored but SHOULD be removed so it is not carried into backups.
- **DEP-HOME-011** Workflow apps installed with `--copy` (or `copy: true`) live in `apps/<id>/`.
  Apps installed in place stay at their own path; that path MUST be readable by `cloudgene` under
  the units' sandbox (not under `/home` or `/root`, which `ProtectHome=true` hides) and is outside
  `CLOUDGENE_HOME`'s backup scope (DEP-HOME-019).

### Disk space and retention

- **DEP-HOME-012** `CLOUDGENE_HOME/jobs` SHOULD be on a filesystem sized for: `max_running_jobs`
  concurrent workspaces (inputs + outputs + `work/` when no external `work_dir` is set) plus all
  finished workspaces kept for `server.job_retention_days`. Uploads larger than 10 MB pass through
  the web unit's private `/tmp` before being copied into the workspace
  (`FILE_UPLOAD_MAX_MEMORY_SIZE`, `jobs/submission.py:374-385`), so the filesystem behind `/tmp`
  SHOULD have room for concurrent submissions of up to `server.max_upload_mb` each. Because
  `PrivateTmp=true` places that directory on the host's `/tmp`, a host whose `/tmp` is a
  size-limited `tmpfs` MUST either size it for this peak or give the web unit a disk-backed
  `/tmp` (for example a `BindPaths=` of a disk directory
  onto `/tmp`); otherwise large submissions fail once `/tmp` is full. The app has no setting to move
  the upload temp directory (`FILE_UPLOAD_TEMP_DIR` is not read from the environment).
- **DEP-HOME-013** `cloudgene-cleanup.timer` MUST be enabled in production. It MUST run
  `cleanup_jobs` and then `cleanup_logs` daily, as `cloudgene`, with the same environment file as
  web and worker, so retention (BE-CMD-050..055, BE-CMD-060) actually happens.
- **DEP-HOME-014** With `server.job_retention_days: 0` finished workspaces are kept forever; the
  operator MUST then monitor free space on `jobs/` as in
  [DEP-OBS-014](observability.md#requirements).
- **DEP-HOME-015** When an external Nextflow `work_dir` (global or per app) is configured, the
  `<work_dir>/<job uuid>` directory of a job MUST be removed no later than the job's workspace
  (BE-QUEUE-027, planned). Until then the deployment MUST remove these directories itself
  (for example a `systemd-tmpfiles` age rule or a timer job on each configured `work_dir`), and the
  cleanup unit MUST list each external `work_dir` in `ReadWritePaths=` once the app removes them.
- **DEP-HOME-016** Paths no retention covers SHOULD be monitored or cleaned by the operator:
  `mail/` (the `file` mail backend's outbox; it holds activation and reset tokens), `NXF_HOME`
  caches ([workflow-runtime.md](workflow-runtime.md)), and `apps/`. Production SHOULD use
  `mail.backend: smtp`; when `file` is used, `mail/` SHOULD have mode `0700`.

### Backup and restore

- **DEP-HOME-017** A backup of `CLOUDGENE_HOME` MUST include `config/` (`settings.yaml`,
  `nextflow.config`, `nextflow.env`, `secret_key` if present), `pages/` and `apps/`. `jobs/` MAY be
  excluded (job rows survive; outputs are lost). Lock files and `.*.tmp` files MAY be excluded.
  External `work_dir`s and `NXF_HOME` SHOULD be excluded (intermediate, re-creatable data).
- **DEP-HOME-018** Backups of `CLOUDGENE_HOME` MUST be stored with the same protection as secrets,
  because they contain `settings.yaml` (mail password), possibly `secret_key`, and user data.
- **DEP-HOME-019** App directories installed in place outside `CLOUDGENE_HOME` (DEP-HOME-011) MUST
  be backed up separately or be reproducible; `settings.yaml` stores only their path.
- **DEP-HOME-020** `CLOUDGENE_HOME` and the database MUST be restored as one consistent pair, with
  `cloudgene-worker` and `cloudgene-cleanup.timer` stopped until both are in place.
  `cleanup_jobs` deletes UUID-named workspaces that have no job row and are over one hour old
  (BE-CMD-052), and a starting worker fails `running` jobs with no live process; either would
  destroy restored data if run against a mismatched database.

### Repository defaults (development home)

- **DEP-HOME-021** The repository's `home/` MUST contain only defaults: `config/settings.yaml`,
  `config/nextflow.config`, `config/nextflow.env`, `pages/home.html`, `pages/footer.html`,
  `pages/about.html`, `apps/.gitkeep`. The committed `settings.yaml` MUST validate against the
  schema and spell out every schema key.
- **DEP-HOME-022** `.gitignore` MUST ignore every file the app creates at runtime under the
  repository's `home/`: `jobs/`, `mail/`, `config/secret_key`, `config/.settings.lock`,
  `config/worker.lock`, and `config/.*.tmp`.

## Interfaces

### Production layout (`CLOUDGENE_HOME=/var/lib/cloudgene`)

| Path | Shipped in `home/` | Created at runtime by | Required mode | Backup |
|------|--------------------|-----------------------|---------------|--------|
| `.` | — | operator at install | `0750` | — |
| `config/settings.yaml` | yes (seed) | admin settings writes (`write_text_atomic`) | `0600` (DEP-HOME-008) | yes |
| `config/.settings.lock` | no | first settings write (`core/config.py:524`) | default | no |
| `config/.settings.yaml.*.tmp` | no | transient during atomic writes | — | no |
| `config/secret_key` | no | `settings.py` if `DJANGO_SECRET_KEY` unset | `0600` | yes, as secret |
| `config/worker.lock` | no | `run_worker` (`jobs/worker.py:811`), holds the PID | default | no |
| `config/nextflow.config` | yes (comments only) | `admin_settings_nextflow_update` | `0644` ok | yes |
| `config/nextflow.env` | yes (comments only) | `admin_settings_nextflow_update` | `0600` (DEP-HOME-009) | yes |
| `pages/<slug>.html` | `home`, `footer`, `about` | `admin_pages_update` | default | yes |
| `apps/<id>/` | `.gitkeep` only | `install_workflow --copy`, per-app Nextflow settings | default | yes |
| `apps/<id>/nextflow.{config,env}` | no | `admin_workflows_nextflow_update` | env: `0600` | yes |
| `jobs/<uuid>/` | no | `jobs_create` (web), runner (worker) | `0750` dirs | optional |
| `mail/` | no | `core.mail` when `mail.backend=file` | `0700` | optional |

Operation names for pages/workflows are those in [../backend/api-contract.md](../backend/api-contract.md).

### Seeding at first install (DEP-HOME-007, DEP-HOME-008)

```bash
H=/var/lib/cloudgene
sudo install -d -o cloudgene -g cloudgene -m 0750 $H $H/config $H/pages $H/apps $H/jobs
sudo -u cloudgene cp -n /opt/cloudgene/home/pages/*.html $H/pages/
sudo -u cloudgene cp -n /opt/cloudgene/home/config/nextflow.config $H/config/
[ -e $H/config/nextflow.env ]  || sudo install -o cloudgene -g cloudgene -m 0600 /opt/cloudgene/home/config/nextflow.env  $H/config/
[ -e $H/config/settings.yaml ] || sudo install -o cloudgene -g cloudgene -m 0600 /opt/cloudgene/home/config/settings.yaml $H/config/
```

### Retention schedule

`cloudgene-cleanup.service` (oneshot, `User=cloudgene`, `EnvironmentFile=/etc/cloudgene/cloudgene.env`):
`manage.py cleanup_jobs` then `manage.py cleanup_logs`. `cloudgene-cleanup.timer`:
`OnCalendar=daily`, `RandomizedDelaySec=1800`, `Persistent=true`.

| What | Removed by | Rule |
|------|-----------|------|
| finished job workspaces | `cleanup_jobs` | older than `server.job_retention_days` (0 = keep) or deleted |
| orphan `jobs/<uuid>` dirs | `cleanup_jobs` | no job row, mtime > 1 h |
| `SystemLog` rows (DB) | `cleanup_logs` | older than 30 days (`--days`) |
| `<work_dir>/<uuid>` (external) | nobody (BE-QUEUE-027) | operator, DEP-HOME-015 |
| `mail/`, `NXF_HOME`, `apps/` | nobody | operator, DEP-HOME-016 |

## Behaviour

- **Fresh install without seeding.** Web and worker start normally. `settings.yaml` is absent, so
  defaults apply and `/api/health` reports config ok. The first admin settings write creates
  `settings.yaml` with mode `0644` (BE-CONF-015) unless DEP-HOME-007/008 were followed.
  `pages_retrieve` for `home` returns 404 and the footer is empty until pages are created.
- **Directory creation.** `config/` appears with the first secret-key generation, settings write or
  worker start; `jobs/<uuid>/{input,output,logs}` at submission; `mail/` at the first mail sent with
  the `file` backend; `pages/` and `apps/<id>/` on first admin write.
- **Modes.** No unit sets `UMask=`, so systemd's default `0022` applies: workspaces are `0755`/`0644`.
  Only `secret_key` (`0600`) and files whose mode existed before a rewrite are protected; the parent
  mode of `CLOUDGENE_HOME` (DEP-HOME-003) is therefore the main barrier for job data.
- **Retention run.** The timer fires once a day at a random offset of up to 30 minutes; a missed run
  (host down) is caught up at boot (`Persistent=true`). Both commands are safe while the worker runs.
- **Restore.** Stop worker and cleanup timer, restore DB and `CLOUDGENE_HOME`, start the worker,
  then re-enable the timer. Jobs that were `running` at backup time are failed by the worker's
  orphan recovery ([../backend/job-queue-worker.md](../backend/job-queue-worker.md)).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| DEP-HOME-001 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_share_environment_file` (planned) | config |
| DEP-HOME-001 | `core/tests/test_deploy.py::DeployEnvExampleTest::test_check_deploy_is_clean_with_the_example_env` | config |
| DEP-HOME-002 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_run_as_cloudgene` (planned) | config |
| DEP-HOME-003 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_units_set_restrictive_umask` (planned) | config |
| DEP-HOME-004 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_read_write_paths_include_cloudgene_home` (planned) | config |
| DEP-HOME-005 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| DEP-HOME-005 | `core/tests/test_config.py::ConfigWriteTest::test_concurrent_writers_from_processes_do_not_lose_updates` | unit |
| DEP-HOME-006 | `core/tests/test_config.py::ConfigLoadTest::test_missing_file_yields_defaults` | unit |
| DEP-HOME-006 | `scripts/smoke_gunicorn.sh` (boots on an empty throw-away `CLOUDGENE_HOME`) | smoke |
| DEP-HOME-007 | `scripts/smoke_gunicorn.sh` seeded-home check of `pages_retrieve` for `home` (planned) | smoke |
| DEP-HOME-008 | `core/tests/test_config.py::ConfigWriteTest::test_existing_file_mode_is_preserved` (planned) | unit |
| DEP-HOME-008 | `core/tests/test_config.py::ConfigWriteTest::test_new_settings_file_is_owner_only` (planned, BE-CONF-015) | unit |
| DEP-HOME-010 | — host obligation; manual verification: `stat -c '%U %a' $CLOUDGENE_HOME/config/secret_key` prints `cloudgene 600` after a restore | — |
| DEP-HOME-011 | — host obligation; manual verification: for each app installed in place, `sudo systemd-run --pty -p ProtectHome=true -p User=cloudgene ls <app path>` succeeds | — |
| DEP-HOME-012 | — host obligation; manual verification: `df -h $CLOUDGENE_HOME/jobs /tmp` against the sizing rule before go-live and after raising `max_running_jobs` or `job_retention_days` | — |
| DEP-HOME-013 | `core/tests/test_deploy_files.py::SystemdUnitsTest::test_cleanup_timer_runs_both_commands_daily` (planned) | config |
| DEP-HOME-013 | `jobs/tests/test_api.py::CleanupCommandTest::test_retention` | unit |
| DEP-HOME-013 | `admin_panel/tests/test_api.py::LogsTest::test_cleanup_logs` | unit |
| DEP-HOME-014 | — host obligation; manual verification: with `job_retention_days: 0`, confirm the disk-space alert of DEP-OBS-014 covers `jobs/` | — |
| DEP-HOME-015 | `jobs/tests/test_api.py::CleanupCommandTest::test_external_work_dir_removed` (planned, BE-QUEUE-027) | unit |
| DEP-HOME-017 | — host obligation; manual verification: list the latest backup and confirm `config/`, `pages/` and `apps/` are present | — |
| DEP-HOME-018 | — host obligation; manual verification: backup files and their storage are readable only by root/backup operators | — |
| DEP-HOME-019 | — host obligation; manual verification: for each app with a path outside `CLOUDGENE_HOME` in `settings.yaml`, a backup or reproducible source exists | — |
| DEP-HOME-020 | `e2e/tests/test_queue.py::test_worker_restart_fails_orphans_and_queue_continues` (worker half only) | e2e |
| DEP-HOME-020 | `jobs/tests/test_api.py::CleanupCommandTest::test_retention` (orphan removal rule) | unit |
| DEP-HOME-021 | `core/tests/test_config.py::CommittedHomeTest::test_committed_layout` | unit |
| DEP-HOME-021 | `core/tests/test_config.py::CommittedHomeTest::test_committed_settings_yaml_is_valid_and_complete` | unit |
| DEP-HOME-022 | `core/tests/test_deploy.py::GitignoreTest::test_runtime_home_files_are_ignored` (planned) | config |

## Known gaps

| Requirement | What the code/config does | Where | Severity |
|-------------|---------------------------|-------|----------|
| DEP-HOME-008 | New `settings.yaml` (and new `nextflow.env` files) are written with mode `0644`; `mail.password` is readable by any local user who can traverse `CLOUDGENE_HOME` (BE-CONF-015). Nothing in the install path pre-creates the file with `0600`. | `core/config.py:376-377` | major |
| DEP-HOME-003 | No unit sets `UMask=`; workspaces, uploads, outputs and mail files are created world-readable (`0755`/`0644`). The only barrier is the mode of `CLOUDGENE_HOME`, which no deploy file sets. | `deploy/systemd/cloudgene-{web,worker,cleanup}.service` | major |
| DEP-HOME-015 | External `work_dir`s are never cleaned; on a busy host they fill the disk. | `jobs/management/commands/cleanup_jobs.py:45-55`; `jobs/runner.py:146-152` | major |
| DEP-HOME-007 | No tooling seeds `CLOUDGENE_HOME`; `ensure_home()` is defined but never called outside tests, so a fresh production home has no pages and no `settings.yaml`. | `core/config.py:345-349` | minor |
| DEP-HOME-004 | `ReadWritePaths=/opt/cloudgene /var/lib/cloudgene` is hard-coded in each unit; a different `CLOUDGENE_HOME` in the env file silently makes the home read-only (writes fail with `EROFS`). | `deploy/systemd/*.service` | minor |
| DEP-HOME-022 | `config/worker.lock` is not in `.gitignore`; running the worker on the default home leaves an untracked file in the repo. | `.gitignore:128-135` | minor |
| DEP-HOME-016 | The default `mail.backend` is `file`; in production an unchanged install accumulates activation and reset tokens in `mail/` forever. | `home/config/settings.yaml` (`mail.backend: file`); `core/mail.py:34-38` | minor |
| DEP-HOME-012 | Upload temp files go to the web unit's private `/tmp`; there is no env-configurable `FILE_UPLOAD_TEMP_DIR`, so on a `tmpfs` `/tmp` concurrent large uploads can exhaust it (and RAM). | `cloudgene_django/settings.py:295`; `deploy/systemd/cloudgene-web.service` | minor |
| DEP-HOME-001 | No deploy check warns when `CLOUDGENE_HOME` is unset with `DEBUG=False` (runtime data then lands in the checkout). | `core/checks.py` | minor |

## Open questions

1. `docs/DEPLOYMENT.md` says `settings.yaml` "is created with defaults on first run
   (`core.config.ensure_home()`, called by `migrate`/`run_worker`/the web process)". The code never
   calls `ensure_home()` and never creates `settings.yaml` until an admin write. Should the app seed
   `CLOUDGENE_HOME` from `home/` at start-up (and with mode `0600`), or should the docs describe the
   manual seeding of DEP-HOME-007? This is the single home of this question; install-upgrade.md
   links here.
2. Worker "exclusive DB lock" (docs) versus `flock` (code): see
   [overview.md](overview.md#open-questions) question 1.
3. `docs/DEPLOYMENT.md` names the per-job Nextflow log `.nextflow.log`; the runner writes
   `logs/nextflow.log` (and `logs/step<N>-nextflow.log`). Docs or code?
4. Should `cleanup_jobs` also prune `mail/` (file backend outbox), or should production simply
   forbid `mail.backend: file`?
5. Should the deployment ship a `systemd-tmpfiles` snippet (`d /var/lib/cloudgene 0750 cloudgene cloudgene`)
   so DEP-HOME-003 is enforced by config rather than by an install step?
