# Workflow registry

## Purpose

The registry decides which workflows are installed and who may use them. `settings.yaml`
`apps[]` is the source of truth: each entry points at an app directory (or its
`cloudgene.yaml`) and carries the access rules `enabled`, `public`, `groups` and the per-app
Nextflow `profile` / `work_dir`. The `workflows.Workflow` table is a cache of each valid app's
parsed YAML plus those rules, rebuilt by a sync. Everything else (public API, job submission,
worker) reads the cache row; only the registry writes `apps[]`.

## Scope

- `workflows/registry.py` — scan, sync, install, uninstall, access, reload, per-app Nextflow
  settings, group pruning.
- `workflows/models.py` — `Workflow`, `WorkflowCategory` behaviour (fields are in
  [data-model.md](data-model.md)).
- `workflows/middleware.py` — lazy sync on API requests.
- `workflows/apps.py` — group-delete signal.
- `workflows/template_utils.py` — the `CLOUDGENE_*` variable catalogue.

Out of scope: YAML validation rules ([workflow-definition.md](workflow-definition.md)); HTTP
endpoints ([workflows-api.md](workflows-api.md)); `install_workflow` / `sync_workflows`
command-line options ([management-commands.md](management-commands.md)); the `settings.yaml`
schema, locking and lenient loading ([configuration.md](configuration.md)); how the runner
merges variables into the process environment ([job-runner.md](job-runner.md)); the admin
group model ([access-control.md](access-control.md)).

## Dependencies

- [configuration.md](configuration.md): `load_settings`, `update_settings` (locked
  read-modify-write), `write_text_atomic`, `apps_dir()`, `app_dir(id)`, `SLUG_RE`.
- [workflow-definition.md](workflow-definition.md): `load_definition(path)`.
- [data-model.md](data-model.md): `Workflow`, `WorkflowCategory`, `jobs.Job.workflow`
  (`related_name='jobs'`, `SET_NULL`).
- [access-control.md](access-control.md): `core.permissions.is_admin`.

## Requirements

Source of truth and paths

- **BE-WREG-001** The set of installed apps and their `enabled`, `public`, `groups`, `profile`,
  `work_dir` MUST be read only from `settings.yaml` `apps[]`. The cache row MUST NOT be the
  source of any of them.
- **BE-WREG-002** `apps[].path` resolution: an absolute path MUST be used as is; a relative path is
  tried against `$CLOUDGENE_HOME/apps/` then `$CLOUDGENE_HOME/`. A directory resolves to its
  `cloudgene.yaml`, else `cloudgene.yml`; a file is used as is. No match is a registry error
  with code `not_found`.
- **BE-WREG-003** When the registry writes a path into `apps[]`, it MUST be relative to
  `$CLOUDGENE_HOME/apps/` when the app is inside it, else the absolute app directory.

Scan and validity

- **BE-WREG-004** A scan MUST produce one status per `apps[]` entry, in order, with: `id`,
  `index`, `path` (as written), `yaml_path` (resolved, `''` if not found), `enabled`, `public`,
  `groups`, `profile`, `work_dir`, `errors`, `warnings`. `valid` is `errors == []`.
- **BE-WREG-005** An entry is invalid when its path does not resolve, its YAML does not parse,
  the definition fails validation, or its id fails `SLUG_RE`. Invalid entries MUST still be
  listed (never dropped) with their errors.
- **BE-WREG-006** The id of an entry MUST be the definition id when valid; else the YAML `id` when it is a
  readable slug; else a slug derived from the path (directory name, max 64 chars, `app` if
  empty).
- **BE-WREG-007** When two entries have the same id, the later entry MUST be marked invalid with
  `Duplicate workflow id "<id>" (already installed by apps[<i>]).` and get the id
  `<id>~<index>`. The earlier entry is unaffected.

Sync (cache rebuild)

- **BE-WREG-008** `sync_all()` MUST, inside one DB transaction: upsert a row for every valid
  entry (name, version, description, website, category, `yaml_config` = file text,
  `app_path` = resolved yaml path, `status` = `enabled`/`disabled` from `apps[].enabled`,
  `public`, `errors=[]`, `installed=true`, `synced_at`).
- **BE-WREG-009** An invalid entry whose id already has a row MUST set that row to
  `status='disabled'`, store `errors`, keep its last good `yaml_config`; an invalid entry with
  no row MUST NOT create one. An invalid app is therefore never runnable.
- **BE-WREG-010** A row that the registry created (non-empty `app_path`) and whose id is no
  longer in `apps[]` MUST be deleted when it has no jobs, or kept with `installed=false`,
  `status='disabled'` when it has jobs. Rows with an empty `app_path` (not registry-managed)
  MUST NOT be touched by a sync.
- **BE-WREG-011** A sync MUST set the row's `allowed_groups` to the existing groups named in
  `apps[].groups`. Unknown names MUST NOT be created by a sync; each yields the warning
  `Group "<name>" does not exist (ignored).`
- **BE-WREG-012** The category named in the YAML MUST be created on demand
  (`WorkflowCategory.get_or_create`) and linked; no category leaves the link null.
- **BE-WREG-013** A sync MUST NOT write `settings.yaml` or any app file.

Lazy sync and read paths

- **BE-WREG-014** `sync_if_changed()` MUST run `sync_all()` only when, since this process's last
  sync, `settings.yaml` (mtime, size, inode, path) or any resolved `cloudgene.yaml` (mtime,
  size) changed, or no sync has run yet in this process. Otherwise it MUST NOT write the DB.
- **BE-WREG-015** `WorkflowSyncMiddleware` MUST call `sync_if_changed()` before every request
  whose path starts with `/api/`. A sync failure MUST be logged and MUST NOT fail the request.
- **BE-WREG-016** Read paths (`list_apps`, `get_status`, `reload`) MUST NOT write
  `settings.yaml`, and MUST NOT write the DB when nothing changed on disk (BE-WREG-014).
- **BE-WREG-017** An edit to `apps[]` or to an installed `cloudgene.yaml` by hand MUST be
  visible through the API on the next `/api/` request, without a restart.

Writes

- **BE-WREG-018** `install(path, enabled=True, public=False, groups=(), copy=False,
  replace=False)` MUST: reject a blank path (`A path is required.`); resolve and fully validate
  the app (errors → 400 with the definition errors, nothing written); with `copy`, copy the app
  directory to `$CLOUDGENE_HOME/apps/<id>/` (target exists → 409 `conflict`); reject an id that
  is already installed with 409 `conflict` unless `replace`, which only updates that entry's
  `path`; create named groups that do not exist; append
  `{path, enabled, public, groups}` to `apps[]`; then sync and return the row.
- **BE-WREG-019** `uninstall(id)` MUST remove the entry from `apps[]` and sync. App files and
  `$CLOUDGENE_HOME/apps/<id>/nextflow.*` MUST stay on disk. Unknown id → 404 `not_found`.
- **BE-WREG-020** `update_access(id, enabled?, public?, groups?)` MUST change only the given
  keys in that `apps[]` entry; `groups` is stored trimmed, de-duplicated and sorted; named
  groups are created if missing. It then syncs and returns the status. Unknown id → 404.
  It works on invalid entries too.
- **BE-WREG-021** `reload(id)` MUST re-read the app (sync if changed) and return its status,
  including errors. Unknown id → 404.
- **BE-WREG-022** Deleting a `Group` MUST remove its name from every `apps[].groups` and sync;
  failure MUST be logged and MUST NOT block the delete. A later sync MUST NOT recreate it.
- **BE-WREG-023** Every registry write to `settings.yaml` MUST go through the locked
  read-modify-write in [configuration.md](configuration.md) and MUST be followed by `sync_all()`.

Per-app Nextflow settings

- **BE-WREG-024** `get_nextflow_settings(id)` MUST return `{profile, work_dir, config, env,
  config_path, env_path}`: `profile`/`work_dir` from the `apps[]` entry (`''` = use global
  `nextflow.*`), `config`/`env` the contents of `$CLOUDGENE_HOME/apps/<id>/nextflow.config` and
  `nextflow.env` (`''` if absent).
- **BE-WREG-025** `set_nextflow_settings(id, profile?, work_dir?, config_text?, env_text?)` MUST
  store trimmed `profile`/`work_dir` in `apps[]` and write the two files atomically, each only
  when given. Unknown id → 404 and nothing written.

Access helpers

- **BE-WREG-026** `Workflow.can_access(user)` MUST return false for anonymous users, true when
  the row is `public`, true for admins, else true only when the user is in one of
  `allowed_groups`. It does not consider `status`; callers check `status == 'enabled'`
  separately (see [job-submission.md](job-submission.md)).
- **BE-WREG-027** `Workflow.enabled` MUST be `status == 'enabled'`; `app_location` MUST be the
  directory of `app_path` (`''` when empty).

Variables

- **BE-WREG-028** `template_utils.VARIABLES` MUST list exactly the `CLOUDGENE_*` names with a
  scope (`global`, `app`, `job`) and description shown in the admin UI.
  `cloudgene_variables(workflow?, job?, user?)` MUST return the global variables always and the
  app / job / user variables only when that object is given, with values from settings,
  the workflow, the job and its submitter.

## Interfaces

```
sync_all() -> list[AppStatus]          sync_if_changed() -> bool
list_apps() -> list[AppStatus]         get_status(id) -> AppStatus
install(path, *, enabled, public, groups, copy, replace) -> Workflow
uninstall(id)                          reload(id) -> AppStatus
update_access(id, *, enabled, public, groups) -> AppStatus
prune_group(name) -> int               resolve_app_path(path) -> Path
get_nextflow_settings(id) -> dict      set_nextflow_settings(id, *, profile, work_dir,
                                                             config_text, env_text) -> dict
RegistryError(message, errors=[], status=400, code='invalid')   # codes: invalid, not_found, conflict
```

`settings.yaml` entry (schema owned by [configuration.md](configuration.md)):

```yaml
apps:
  - path: hello            # required
    enabled: true
    public: false
    groups: [lab]
    profile: ''            # per-app nextflow -profile
    work_dir: ''           # per-app nextflow work dir
```

Files: `$CLOUDGENE_HOME/apps/<id>/nextflow.config`, `$CLOUDGENE_HOME/apps/<id>/nextflow.env`.

`CLOUDGENE_*` variables (`workflows/template_utils.py:162-184`):

| Scope | Names |
|---|---|
| global | `SERVICE_NAME`, `SERVICE_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`, `WORKSPACE_TYPE` (`local`), `WORKSPACE_HOME` |
| app | `APP_ID`, `APP_NAME`, `APP_VERSION`, `APP_LOCATION` |
| job | `JOB_ID`, `JOB_NAME`, `JOB_LOCATION`, `JOB_SUBMITTED_ON`, `USER_NAME`, `USER_EMAIL`, `USER_FULL_NAME` |

(all prefixed `CLOUDGENE_`).

## Behaviour

Lifecycle of an app entry:

```
 not in apps[] --install--> valid ──edit YAML (bad)──> invalid (row disabled, errors kept)
       ^                     │  ^                         │
       │                     │  └──edit YAML (good)───────┘
       └──uninstall──────────┘  row deleted, or kept installed=false/disabled if it has jobs
```

Effective availability to users = row exists AND `status == 'enabled'` (configured enabled AND
valid) AND `can_access(user)`.

Sync triggers: `manage.py sync_workflows`; the middleware on `/api/` requests; `POST
/api/admin/workflows/sync/`; after every registry write; first `list_apps()` in a process.

Concurrency: `sync_all` holds a per-process thread lock; `settings.yaml` writes hold the
cross-process file lock from [configuration.md](configuration.md). The worker process does not
run the middleware; it reads cache rows written by web processes and reads per-app Nextflow
settings directly through `get_nextflow_settings`.

Settings-load failures: `load_settings` is lenient, so a broken `settings.yaml` falls back to
defaults (`apps: []`). A sync in that state will uninstall every registry-managed row (see
Known gaps).

## Acceptance tests

| Requirement | Test | Layer |
|---|---|---|
| 001, 002, 003, 008, 011, 012, 018 | `workflows/test_registry.py::RegistryInstallTest::test_install_app_dir_writes_settings_and_cache_row` | unit |
| 002, 003 | `workflows/test_registry.py::RegistryInstallTest::test_install_yaml_file_outside_apps_is_referenced_absolute` | unit |
| 018 (copy) | `workflows/test_registry.py::RegistryInstallTest::test_install_with_copy` | unit |
| 018 (invalid) | `workflows/test_registry.py::RegistryInstallTest::test_install_invalid_app_rejected_with_errors`, `::test_install_missing_path` | unit |
| 018 (conflict) | `workflows/test_registry.py::RegistryInstallTest::test_install_duplicate_id_conflict` | unit |
| 018 (replace) | (planned) `RegistryInstallTest::test_install_replace_updates_path_only` | unit |
| 019 | `workflows/test_registry.py::RegistryInstallTest::test_uninstall_removes_entry_and_row`, `::test_uninstall_unknown` | unit |
| 002, 004, 005, 006, 009, 011 | `workflows/test_registry.py::RegistrySyncTest::test_sync_from_hand_written_settings` | unit |
| 007 | `workflows/test_registry.py::RegistrySyncTest::test_duplicate_ids_in_settings` | unit |
| 009 | `workflows/test_registry.py::RegistrySyncTest::test_app_becoming_invalid_disables_row` | unit |
| 021 | `workflows/test_registry.py::RegistrySyncTest::test_reload_picks_up_new_input` | unit |
| 014, 017 | `workflows/test_registry.py::RegistrySyncTest::test_sync_if_changed_detects_settings_edit` | unit |
| 016 | `workflows/test_registry.py::RegistrySyncTest::test_list_apps_does_not_write_on_a_plain_read`; `e2e/tests/test_findings_jobs.py::test_a03_admin_workflow_list_does_not_write_on_every_read` | unit, e2e |
| 010 | `workflows/test_registry.py::RegistrySyncTest::test_manual_rows_untouched_by_sync`, `::test_removed_entry_with_jobs_is_kept_disabled` | unit |
| 015 | `workflows/test_registry.py::RegistrySyncTest::test_middleware_syncs_lazily_on_api_request` | unit |
| 015 (failure swallowed) | (planned) `RegistrySyncTest::test_middleware_sync_failure_does_not_fail_request` | unit |
| 020, 026 | `workflows/test_registry.py::RegistryAccessTest::test_groups_written_to_yaml_and_access_follows`, `::test_enable_disable_public` | unit |
| 022 | `workflows/test_registry.py::RegistryAccessTest::test_deleted_group_is_pruned_from_settings` | unit |
| 024, 025 | `workflows/test_registry.py::RegistryAccessTest::test_nextflow_settings_round_trip` | unit |
| 013, 023 | (planned) `RegistrySyncTest::test_sync_never_writes_settings` | unit |
| 026 | `workflows/tests.py::WorkflowTest::test_can_access_public_workflow`, `::test_can_access_group_restricted_workflow`, `::test_admin_access`, `::test_unauthenticated_access` | unit |
| 027 | `workflows/test_registry.py::RegistryInstallTest::test_install_yaml_file_outside_apps_is_referenced_absolute` | unit |
| 028 | (planned) `workflows/test_template_utils.py::test_scopes_and_names` | unit |
| 017, 020 (end to end) | `e2e/tests/test_admin_workflows.py::test_w1_d4_disable_hides_workflow_and_enable_restores`, `::test_d4_reload_after_yaml_edit` | e2e |

## Known gaps

| Requirement | What the code does | Where | Severity |
|---|---|---|---|
| BE-WREG-001, -010 | When `settings.yaml` is unreadable, `load_settings` falls back to `apps: []`; the next sync deletes (or marks uninstalled) every registry-managed row, so all workflows vanish until the file is fixed. A sync should be skipped when the settings load reported errors. | `workflows/registry.py:317-337`, `core/config.py:469-490` | major |
| BE-WREG-017 | The change signature tracks only resolved `cloudgene.yaml` files. An entry whose path did not resolve stays invalid after the directory is created, until `settings.yaml` changes or an admin syncs. | `workflows/registry.py:338` | minor |
| BE-WREG-007 | An earlier invalid entry whose YAML still has a readable `id` claims that id, so a later valid entry with the same id is marked duplicate and becomes unavailable. | `workflows/registry.py:222-238` | minor |
| BE-WREG-024 | For a duplicate entry (id `<id>~<n>`) `app_config_dir` raises `ValueError` (not a slug), so the Nextflow settings endpoints return 500. | `workflows/registry.py:510-512`, `core/config.py:330` | minor |
| BE-WREG-018 | With `copy=True`, the directory is copied before the duplicate-id check; a 409 leaves the copied directory behind. | `workflows/registry.py:417-438` | minor |
| BE-WREG-008 | The YAML is read again after validation; a file changed in between is cached unvalidated in `yaml_config`. | `workflows/registry.py:322-324` | minor |
| BE-WREG-016 | The first `list_apps()`/API request in every new process always runs a full sync (DB writes), including in each web worker. | `workflows/registry.py:354-359`, `:371-372` | minor |
| BE-WREG-014 | `sync_all` uses a per-process thread lock only; several web processes can sync at once (SQLite write contention; failures are swallowed by the middleware). | `workflows/registry.py:247`, `workflows/middleware.py:241-245` | minor |
| BE-WREG-002 | A path that does not resolve raises code `not_found` with HTTP status 400 (mismatched code/status). | `workflows/registry.py:156-157` | minor |
| — | `Workflow.STATUS_CHOICES` includes `maintenance`, which nothing sets or reads. | `workflows/models.py:31-35` | minor |

## Open questions

- `CLOUDGENE_SMTP_PASSWORD` is exported to every job's environment, so any workflow script can
  read the mail password. Keep, or restrict to opt-in?
- Should invalid apps that were never valid get a cache row (status `disabled`) so the public
  and admin APIs see one model, rather than the admin view reading `settings.yaml` directly?
- Should `uninstall` offer to remove the copied app directory and `apps/<id>/nextflow.*`?
