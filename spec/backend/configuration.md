# Configuration

## Purpose

Cloudgene keeps its application settings in one YAML document,
`$CLOUDGENE_HOME/config/settings.yaml`, read and written only through `core/config.py`. Both
the web and the worker process use this module, so an admin change takes effect in every
process on its next read with no restart. This file specifies the `settings.yaml` schema, how
it is validated, cached and written, and the `CLOUDGENE_HOME` directory layout as the
application sees it.

## Scope

Covered: `core/config.py` (schema, load/cache, write, path helpers, page file helpers,
`parse_env`), `home/config/settings.yaml` (the committed default document), the
`CLOUDGENE_HOME` layout.

Out of scope:

- Django infrastructure settings and env vars → [overview.md](overview.md) and
  [../deployment/README.md](../deployment/README.md).
- Admin endpoints that edit settings (`admin_settings_*`, `admin_queue_*`,
  `admin_maintenance_*`, `admin_pages_*`) → [admin-api.md](admin-api.md).
- What each key *does*: listed in the Consumers column and specified in that file.
- `apps[]` semantics (install, sync, access) → [workflow-registry.md](workflow-registry.md).
- Nextflow config/env file use at run time → [job-runner.md](job-runner.md).

## Dependencies

- [overview.md](overview.md) — `settings.CLOUDGENE_HOME`, test runner isolation.
- [admin-api.md](admin-api.md) — maps `ConfigError` to the error envelope.
- [server-pages-mail.md](server-pages-mail.md) — `health` reports `config_status()`; page files.
- [logging.md](logging.md) — load errors are logged.

## Requirements

Location

- **BE-CONF-001** The settings file MUST be `<CLOUDGENE_HOME>/config/settings.yaml`, where
  `CLOUDGENE_HOME` is the Django setting `CLOUDGENE_HOME`, else env `CLOUDGENE_HOME`, else
  `<repo>/home`.

Load (fail-safe)

- **BE-CONF-002** A missing settings file MUST load as the schema defaults.
- **BE-CONF-003** Keys absent from the file MUST take their schema default. Unknown keys, at
  any level, MUST be preserved on load and on write, and are not validated.
- **BE-CONF-004** A key whose value fails validation MUST fall back to its default while every
  other key keeps its value. Loading MUST NOT raise. The error MUST be recorded under the
  key's dotted path (e.g. `server.max_running_jobs`, `navbar[0].url`) and logged at ERROR.
- **BE-CONF-005** A file that is not valid YAML, or whose top level is not a mapping, MUST load
  as the full defaults with an error recorded under the key `settings`.
- **BE-CONF-006** `config_status()` MUST return `{ok, errors}` for the current file. `health`
  MUST report `config.ok=false` and status `degraded` while errors exist
  ([server-pages-mail.md](server-pages-mail.md)); the admin dashboard MUST show the same status.
- **BE-CONF-007** Integer keys MUST accept integer strings (`'7'` → 7); boolean keys MUST
  accept only YAML booleans; string keys MUST accept numbers (converted with `str`).
- **BE-CONF-008** Cross-field rules MUST be applied to the whole resulting document:
  `mail.use_tls` and `mail.use_ssl` MUST NOT both be true (error on `mail.use_ssl`, which falls
  back to `false`); each `navbar[i].url` MUST be an internal path starting with `/` but not
  `//`, or an `http://`/`https://` URL (else error, value becomes `''`).

Cache

- **BE-CONF-009** Each process MUST cache the parsed document keyed by the file's
  `(mtime_ns, size, inode)`; a read MUST re-parse only when that key changes. An edit made by
  another process or by hand MUST be visible on the next read.
- **BE-CONF-010** `load_settings()` and `get()` MUST return deep copies; mutating a result MUST
  NOT change the cache.

Write

- **BE-CONF-011** Every write MUST validate the whole resulting document. If any error exists
  it MUST raise `ConfigError` (with `errors: {dotted.key: [message, …]}`) and MUST leave the
  file unchanged.
- **BE-CONF-012** Every write MUST be atomic: write a temp file in the same directory, `fsync`,
  then `os.replace`. A failed write MUST leave no temp file and the old file intact.
- **BE-CONF-013** Read-modify-write (`update_settings`, `set_value`, `save_settings`) MUST hold
  an exclusive `fcntl` lock on `<CLOUDGENE_HOME>/config/.settings.lock`, so concurrent writers
  in different processes never lose an update.
- **BE-CONF-014** `update_settings` MUST read the current file leniently: an invalid key starts
  from its default, and an unparseable file starts from the full defaults, so an admin can
  repair a broken file through the API. A dict patch MUST deep-merge mappings and replace lists.
- **BE-CONF-015** A newly created `settings.yaml` MUST NOT be readable by other OS users
  (mode `0600`), because it holds `mail.password`. An existing file's mode MUST be preserved.
  (planned)
- **BE-CONF-016** After a successful write the writing process's cache MUST hold the written
  document with no errors.

Paths

- **BE-CONF-017** `app_dir(id)` and `page_path(slug)` MUST accept only `^[a-z0-9][a-z0-9_-]{0,63}$`
  and `job_dir(id)` only `^[0-9a-fA-F-]{8,64}$`; anything else MUST raise `ValueError`. These
  are the only functions that turn ids into paths under `CLOUDGENE_HOME`.

Committed defaults

- **BE-CONF-018** The committed `home/config/settings.yaml` MUST validate without errors and
  MUST spell out every key of every mapping section of the schema.
- **BE-CONF-019** The committed `home/` MUST contain `config/nextflow.config`,
  `config/nextflow.env`, `pages/home.html`, `pages/footer.html`, `pages/about.html` and
  `apps/.gitkeep`; runtime data (`jobs/`, `mail/`, `config/secret_key`,
  `config/.settings.lock`, temp files) MUST NOT be committed.

`nextflow.env` format

- **BE-CONF-020** `parse_env` MUST read `KEY=VALUE` lines, skipping blank lines, `#` comments,
  lines without `=` and keys not matching `^[A-Za-z_][A-Za-z0-9_]*$`; it MUST strip an
  `export ` prefix and one pair of matching surrounding quotes.

## Interfaces

### Public functions (`core/config.py`)

| Function | Returns / effect |
|----------|------------------|
| `load_settings(force=False)` | cleaned document (deep copy) |
| `get(key, default=None)` | value at a dotted path, else `default` |
| `config_status()` | `{ok: bool, errors: {key: [msg]}}` |
| `validate_settings(data)` | cleaned copy, or raises `ConfigError` |
| `save_settings(data)` | locked validate + atomic write of the whole document |
| `update_settings(patch_or_callable)` | locked read-modify-write; callable may mutate in place and return `None` |
| `set_value(key, value)` | `update_settings` for one dotted key |
| `default_settings()`, `clear_cache()` | |
| `cloudgene_home()`, `config_dir()`, `settings_path()`, `nextflow_config_path()`, `nextflow_env_path()`, `pages_dir()`, `apps_dir()`, `jobs_dir()` | paths |
| `app_dir(id)`, `job_dir(id)`, `page_path(slug)` | validated paths (BE-CONF-017) |
| `read_page`, `write_page`, `delete_page`, `list_pages` | page files ([server-pages-mail.md](server-pages-mail.md)) |
| `read_text(path, default='')`, `write_text_atomic(path, text)`, `parse_env(text)` | file helpers |
| `ensure_home()` | creates `config/`, `pages/`, `apps/`, `jobs/` |

`ConfigError(ValueError)`: `.errors` maps dotted keys to message lists; `str()` is
`"<first key>: <first message>"`.

### `settings.yaml` schema

Validation messages: `Must be true or false.`, `Must be an integer.`, `Must be a string.`,
`Must be a list of strings.`, `Must be at least N.`, `Must be at most N.`,
`Must be one of: …`, `Must be a mapping.`, `Must be a list.`, `This field is required.`

| Key | Type | Default | Rule | Consumers |
|-----|------|---------|------|-----------|
| `server.name` | str | `Cloudgene` | | [server-pages-mail.md](server-pages-mail.md) |
| `server.url` | str | `''` | public base URL for e-mail links; `''` = request host | [accounts.md](accounts.md) |
| `server.max_running_jobs` | int | 2 | ≥ 1 | [job-queue-worker.md](job-queue-worker.md) |
| `server.max_queue_size` | int | 50 | ≥ 0 | [job-submission.md](job-submission.md) |
| `server.maintenance` | bool | false | | [server-pages-mail.md](server-pages-mail.md) |
| `server.maintenance_message` | str | `The service is in maintenance mode. Job submission is temporarily disabled.` | | same |
| `server.job_retention_days` | int | 7 | ≥ 0; 0 = keep | [management-commands.md](management-commands.md) |
| `server.max_upload_mb` | int | 1024 | ≥ 1 | [job-submission.md](job-submission.md) |
| `queue.paused` | bool | false | | [job-queue-worker.md](job-queue-worker.md) |
| `security.max_login_attempts` | int | 5 | ≥ 0; 0 = off | [authentication.md](authentication.md) |
| `security.lockout_duration` | int | 300 | ≥ 0, seconds | same |
| `security.require_activation` | bool | true | | [accounts.md](accounts.md) |
| `mail.backend` | str | `file` | one of `smtp`, `file`, `console` | [server-pages-mail.md](server-pages-mail.md) |
| `mail.file_path` | str | `mail` | relative to `CLOUDGENE_HOME` unless absolute | same |
| `mail.host` | str | `localhost` | | same |
| `mail.port` | int | 587 | 1–65535 | same |
| `mail.user` | str | `''` | | same |
| `mail.password` | str | `''` | write-only in APIs ([admin-api.md](admin-api.md)) | same |
| `mail.use_tls` | bool | true | not with `use_ssl` | same |
| `mail.use_ssl` | bool | false | not with `use_tls` | same |
| `mail.from_email` | str | `noreply@localhost` | | same |
| `nextflow.binary` | str | `nextflow` | | [job-runner.md](job-runner.md) |
| `nextflow.profile` | str | `''` | default `-profile` | same |
| `nextflow.work_dir` | str | `''` | `''` = `<job>/work`; relative = under `CLOUDGENE_HOME` | same |
| `navbar` | list of mappings | `[]` | each item: `title` (str, required), `url` (str, required, BE-CONF-008), `icon` (str), `admin_only` (bool), `auth_only` (bool) | [server-pages-mail.md](server-pages-mail.md) |
| `apps` | list of mappings | `[]` | each item: `path` (str, required; app dir or `cloudgene.yaml`, relative to `apps/` then `CLOUDGENE_HOME`, or absolute), `enabled` (bool, true), `public` (bool, false), `groups` (list of str, `[]`), `profile` (str), `work_dir` (str) | [workflow-registry.md](workflow-registry.md) |

A mapping section given as a non-mapping records `Must be a mapping.` and uses `{}`. A list
entry that is not a mapping is dropped with an error on `<key>[i]`; a list entry missing a
required key is kept (with the key's default) and the error is recorded on `<key>[i].<field>`.

### `CLOUDGENE_HOME` layout

| Path | Owner | Notes |
|------|-------|-------|
| `config/settings.yaml` | `core.config` | this file |
| `config/.settings.lock` | `core.config` | write lock (BE-CONF-013) |
| `config/secret_key` | `settings.py` | generated when `DJANGO_SECRET_KEY` unset ([overview.md](overview.md)) |
| `config/worker.lock` | `jobs.worker` | single-worker lock, holds the PID ([job-queue-worker.md](job-queue-worker.md)) |
| `config/nextflow.config`, `config/nextflow.env` | admin (`admin_settings_nextflow_*`) | global Nextflow config / env ([job-runner.md](job-runner.md)) |
| `apps/<id>/` | registry | installed app files; `nextflow.config`, `nextflow.env` per app |
| `pages/<slug>.html` | admin pages | `home`, `footer` protected ([server-pages-mail.md](server-pages-mail.md)) |
| `jobs/<uuid>/` | jobs | workspace ([job-submission.md](job-submission.md)) |
| `mail/` | `core.mail` | outbox for `mail.backend=file` (default `file_path`) |

## Behaviour

Load: `stat` the file → if the stamp equals the cached stamp (and path), return a copy of the
cache. Otherwise parse leniently, clean against the schema (each failing key takes its default),
apply cross-field rules, merge parse errors and field errors, log at ERROR on logger
`core.config` if any, store document + errors + stamp, return a copy. The ERROR is logged once
per file change per process.

Write: acquire the `fcntl` lock → (for `update_settings`) lenient read + clean, apply the patch
or callable → `validate_settings` on the result (raise on error, file untouched) → dump with a
two-line header comment, `sort_keys=False` → atomic replace (temp file `.<name>.*.tmp`, fsync,
mode copied from the existing file or `0644` for a new one) → update the cache. Comments in a
hand-edited file are not preserved after the first API write.

Repairing a broken file: because `update_settings` reads leniently, any admin save rewrites
invalid hand-edited values with their defaults. A file that does not parse is replaced by
defaults plus the patch.

Cross-process: the worker reads settings on each tick and sees admin changes via the stamp;
there is no notification channel.

## Acceptance tests

| Req | Test | Layer |
|-----|------|-------|
| BE-CONF-001 | `core/tests/test_config.py::PathsAndPagesTest::test_paths` | unit |
| BE-CONF-002 | `core/tests/test_config.py::ConfigLoadTest::test_missing_file_yields_defaults` | unit |
| BE-CONF-003 | `core/tests/test_config.py::ConfigLoadTest::test_partial_file_filled_with_defaults_and_unknown_keys_kept` | unit |
| BE-CONF-004 | `core/tests/test_config.py::ConfigLoadTest::test_validation_errors_are_keyed_by_path`, `::test_broken_key_after_valid_load_falls_back_to_its_default` | unit |
| BE-CONF-005 | `core/tests/test_config.py::ConfigLoadTest::test_invalid_yaml_falls_back_to_defaults` | unit |
| BE-CONF-006 | `core/tests/test_config.py::ConfigLoadTest::test_config_status_ok_after_a_clean_load`; `core/tests/test_api.py::HealthTest::test_health_reports_a_broken_settings_file`; `e2e/tests/test_findings_admin.py::test_c02_invalid_settings_value_does_not_take_the_site_down` | unit, e2e |
| BE-CONF-007 | `core/tests/test_config.py::ConfigLoadTest::test_numeric_strings_coerced` | unit |
| BE-CONF-008 | `core/tests/test_config.py::ConfigLoadTest::test_navbar_url_must_be_internal_or_http_in_a_hand_edited_file`, `::test_mail_tls_and_ssl_mutually_exclusive_in_a_hand_edited_file`; `e2e/tests/test_findings_admin.py::test_c01_mail_tls_and_ssl_cannot_both_be_enabled`, `::test_c05_navbar_url_is_validated` | unit, e2e |
| BE-CONF-009 | `core/tests/test_config.py::ConfigLoadTest::test_external_edit_picked_up_via_mtime`, `::test_cache_hit_does_not_reparse` | unit |
| BE-CONF-010 | `core/tests/test_config.py::ConfigLoadTest::test_returned_dict_is_a_copy` | unit |
| BE-CONF-011 | `core/tests/test_config.py::ConfigWriteTest::test_set_value_persists_and_validates`, `::test_failed_write_leaves_original_intact` | unit |
| BE-CONF-012 | `core/tests/test_config.py::ConfigWriteTest::test_save_is_atomic_no_temp_files_left`, `::test_failed_write_leaves_original_intact` | unit |
| BE-CONF-013 | `core/tests/test_config.py::ConfigWriteTest::test_concurrent_writers_from_processes_do_not_lose_updates` | unit |
| BE-CONF-014 | `core/tests/test_config.py::ConfigWriteTest::test_update_settings_repairs_a_broken_file`, `::test_update_settings_deep_merge_and_callable` | unit |
| BE-CONF-015 | (planned) `core/tests/test_config.py::ConfigWriteTest::test_new_settings_file_is_owner_only` | unit |
| BE-CONF-016 | (planned) `core/tests/test_config.py::ConfigWriteTest::test_cache_updated_after_write` | unit |
| BE-CONF-017 | `core/tests/test_config.py::PathsAndPagesTest::test_traversal_rejected` | unit |
| BE-CONF-018 | `core/tests/test_config.py::CommittedHomeTest::test_committed_settings_yaml_is_valid_and_complete` | unit |
| BE-CONF-019 | `core/tests/test_config.py::CommittedHomeTest::test_committed_layout`; (planned) `.gitignore` coverage test | unit |
| BE-CONF-020 | `core/tests/test_config.py::PathsAndPagesTest::test_parse_env` | unit |

Also relevant: `e2e/exploratory/test_probe_misc.py::test_unknown_keys_preserved` (exploratory,
not part of the gating suite).

## Known gaps

| Req | Current behaviour | Ref | Severity |
|-----|-------------------|-----|----------|
| BE-CONF-015 | A new `settings.yaml` is created with mode `0644`, so `mail.password` (stored in plain text) is readable by every local user. | `core/config.py:377` | major |
| BE-CONF-019 | `config/worker.lock` is created in `CLOUDGENE_HOME` but is not listed in `.gitignore` (unlike `.settings.lock`). | `jobs/worker.py:811`, `.gitignore:128` | minor |
| BE-CONF-004 | Load errors are logged on `core.config`, which is not a `cloudgene.*` logger, so they never reach Admin → Logs (only `health`/dashboard show them). | `core/config.py:44` | minor |
| — | Mis-spelled keys (e.g. `server.max_runing_jobs`) are kept as unknown keys and silently ignored; the real key uses its default with no warning. | `core/config.py:193` | minor |
| — | `server.url`, `mail.from_email`, `mail.file_path`, `nextflow.work_dir`, `apps[].work_dir` are not format-checked (any string). They are admin-only inputs; `mail.file_path` and `work_dir` may point anywhere on disk. | `core/config.py:140`, `core/config.py:160`, `core/config.py:172` | minor |
| — | `ensure_home()` is never called by the application; directories are created lazily by each writer. | `core/config.py:345` | minor |

## Open questions

- Should the SMTP password move out of `settings.yaml` (env var or a separate `0600` secret
  file) instead of tightening the whole file's mode?
- Should unknown keys inside known sections produce a warning in `config_status()`?
