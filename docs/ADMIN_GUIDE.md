# Admin Guide

This guide covers day-to-day administration of a Cloudgene deployment: server configuration
(`settings.yaml`), the admin panel pages, users/groups, installing workflows, the job queue, and
logs. It documents the code as it exists on `rebuild`; where the on-disk contract lives in more
detail, this guide points at `plans/SPEC.md`.

For installing the service itself (systemd units, nginx, Postgres, backups) see
`docs/DEPLOYMENT.md`. For the `cloudgene.yaml` format see `docs/WORKFLOW_YAML_REFERENCE.md`.

## Who is an admin

A user is treated as an admin (`core.permissions.is_admin`) if any of the following is true:
- `is_superuser`
- `is_staff`
- member of the Django group named `admin`

Admin-only API endpoints use the `IsAdmin` permission class, which checks the same rule. The
Django admin site at `/django-admin/` is intentionally kept for trusted staff/superusers (it does
not print API token keys — DRF's token admin is unregistered — and shares the same login lockout
as the SPA, see *Security notes* below); it is not part of the day-to-day admin panel and is not
documented further here.

## `CLOUDGENE_HOME` layout

All server-editable configuration and runtime state lives under one directory, `$CLOUDGENE_HOME`
(env var; defaults to `./home` in the repo for development):

```
$CLOUDGENE_HOME/
  config/
    settings.yaml       # the single source of truth for server settings (below)
    nextflow.config      # global Nextflow config, admin-editable
    nextflow.env          # global Nextflow environment (KEY=VALUE), admin-editable
    secret_key            # generated once if DJANGO_SECRET_KEY is not set in env
    .settings.lock         # fcntl lock file used by writes; not user content
    worker.lock             # single-worker-instance lock
  pages/
    home.html            # required, rendered at "/"
    footer.html          # required, rendered in the page footer
    <slug>.html          # any other page, served at /pages/<slug>
  apps/
    <app-id>/
      cloudgene.yaml       # workflow definition (see WORKFLOW_YAML_REFERENCE.md)
      main.nf, ...          # the workflow's own files
      nextflow.config        # per-app Nextflow override, admin-editable
      nextflow.env             # per-app Nextflow environment, admin-editable
  jobs/
    <job-uuid>/
      input/ output/ logs/ work/   # one job's workspace
  mail/                   # outbox when mail.backend = "file"
```

Everything under `config/settings.yaml`, `pages/*.html`, and the per-app `nextflow.config`/
`nextflow.env` files can be edited either directly on disk or through the admin panel (they are the
same files — a hand edit is picked up by both the web process and the worker without a restart,
subject to the caching described below).

Workflows are **not copied** into `apps/` by default: `apps[].path` can point at any directory
containing a `cloudgene.yaml` (see *Installing workflows* below); `apps/<id>/` is simply the
conventional location and is where `nextflow.config`/`nextflow.env` overrides for that app always
live, resolved by app id regardless of where the workflow's own files are.

## `settings.yaml` reference

The config service (`core/config.py`) loads, validates, defaults, caches (by file mtime/size/inode)
and atomically writes this file. Every key below has a type, default and validation rule; an
invalid value in a hand-edited file **never crashes the app** — that one key falls back to its
default, the problem is logged once at `ERROR`, and it is reported by `GET /api/health` (`config`
block, `status: degraded`) and on the admin dashboard, so it is visible and fixable from the UI
even while the file is broken (an admin `PUT` can still repair it, since a write reads the
on-disk document leniently first).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `server.name` | string | `Cloudgene` | Service name shown in the navbar and in e-mails |
| `server.url` | string | `''` | Public base URL used in e-mail links (activation, reset); empty = use the request's host |
| `server.max_running_jobs` | int ≥ 1 | `2` | Jobs the worker runs concurrently |
| `server.max_queue_size` | int ≥ 0 | `50` | Max `waiting` jobs; further submissions get 429 `queue_full`. `0` = unlimited |
| `server.maintenance` | bool | `false` | Blocks non-admin submissions (503 `maintenance`) and shows the maintenance banner |
| `server.maintenance_message` | string | *(default text)* | Shown in the banner and in the 503 body |
| `server.job_retention_days` | int ≥ 0 | `7` | `manage.py cleanup_jobs` removes a finished job's workspace after this many days; `0` = keep forever |
| `server.max_upload_mb` | int ≥ 1 | `1024` | Max total upload size per job submission (413 `upload_too_large` beyond it) |
| `queue.paused` | bool | `false` | The worker starts no new jobs while `true`; running jobs finish normally |
| `security.max_login_attempts` | int ≥ 0 | `5` | Failed logins before lockout; `0` disables lockout |
| `security.lockout_duration` | int ≥ 0 | `300` | Lockout length in seconds |
| `security.require_activation` | bool | `true` | New accounts must click an e-mailed activation link before they can log in |
| `mail.backend` | `smtp` \| `file` \| `console` | `file` | `file` writes outgoing mail to `$CLOUDGENE_HOME/mail/`; `console` prints it; use `smtp` in production |
| `mail.file_path` | string | `mail` | Outbox directory for `backend: file`, relative to `CLOUDGENE_HOME` |
| `mail.host` / `mail.port` | string / int | `localhost` / `587` | SMTP server |
| `mail.user` / `mail.password` | string | `''` | SMTP auth; `password` is write-only in the admin API (never read back — only `password_set: true/false` is reported) |
| `mail.use_tls` / `mail.use_ssl` | bool | `true` / `false` | SMTP transport security — **mutually exclusive**; setting both `true` is rejected |
| `mail.from_email` | string | `noreply@localhost` | Sender address |
| `nextflow.binary` | string | `nextflow` | Nextflow executable (path or name on `$PATH`) |
| `nextflow.profile` | string | `''` | Default `-profile` for all workflows (overridden per-app) |
| `nextflow.work_dir` | string | `''` | Global Nextflow work directory; empty = `<job>/work` (overridden per-app) |
| `navbar[]` | list | `[]` | `{title, url, icon, admin_only: false, auth_only: false}`; `url` must be an internal path (`/…`, not `//…`) or an `http(s)://` URL — anything else is a validation error |
| `apps[]` | list | `[]` | Installed workflows: `{path, enabled: true, public: false, groups: [], profile: '', work_dir: ''}` — see *Installing workflows* |

Unknown keys are preserved (not validated) so that in-progress features can add keys before this
table is updated.

### Cross-field validation

Two rules apply to the *resulting* document, not just the fields in one request, so a partial
admin `PUT` (or a hand-edited file) can never produce an invalid combination:
- `mail.use_tls` and `mail.use_ssl` cannot both be `true`.
- Every `navbar[].url` must start with `/` (and not `//`) or be an `http://`/`https://` URL.

## Admin panel pages

All admin endpoints are under `/api/admin/` and require `IsAdmin`; the SPA's admin views live
under `frontend/src/views/admin/`.

### Dashboard (`AdminDashboardView.vue`, `GET /api/admin/dashboard/`)
Shows: queue state (`paused`, `maintenance`, running/waiting counts, `max_running`/`max_queue`,
worker liveness — `ok`, `last_seen`, `age_seconds`, `pid`), job counts by state, user counts
(total/active/admins), workflow counts (total/enabled/disabled/invalid), the 10 most recent jobs,
and a `config` block (`{ok, errors}`) mirroring `/api/health` — a bad `settings.yaml` key shows up
here, not only in the logs.

Queue controls: `POST /api/admin/queue/pause|resume` (writes `queue.paused`), `POST
/api/admin/maintenance/enter {message?}` / `exit` (writes `server.maintenance` and, if supplied,
`server.maintenance_message`).

### Workflows (`AdminWorkflowsView.vue`, `AdminWorkflowSettingsView.vue`)
`GET /api/admin/workflows/` lists **every** installed app, including disabled and invalid ones (the
public `/api/workflows/` list only shows enabled, accessible apps). Each row reports:
- `enabled` — exactly what `apps[].enabled` says (what the admin configured).
- `effective_status` — `"enabled"` only when `enabled` **and** `valid` are both true; a workflow
  whose `cloudgene.yaml` fails to parse is never effectively enabled even if `apps[].enabled: true`
  (this is a deliberate choice — see *Discrepancies* below).
- `valid`, `errors[]`, `warnings[]` — the result of parsing `cloudgene.yaml` through
  `workflows.definition.load_definition`.
- `public`, `groups[]`, `path`, `yaml_path`, `job_count`.

Actions: `PATCH /api/admin/workflows/{id} {enabled?, public?, groups[]?}` (groups by name),
`DELETE /api/admin/workflows/{id}` (uninstalls — removes the `apps[]` entry only, files are never
deleted from disk), `POST /api/admin/workflows/{id}/reload` (re-parses the YAML and returns the
fresh status), `POST /api/admin/workflows/sync` (rescans all apps).

**Installing a workflow**: `POST /api/admin/workflows/install {path, enabled?, public?, groups?,
copy?}`. `path` is a directory containing `cloudgene.yaml` (or the YAML file itself), relative to
`$CLOUDGENE_HOME/apps` first, then to `$CLOUDGENE_HOME`, or absolute. By default the app is
referenced **in place** — nothing is copied; pass `copy: true` to copy it into
`$CLOUDGENE_HOME/apps/<id>/` first. The workflow's `id` (from its YAML) becomes its permanent
identifier; installing a second app with the same id is a 409 conflict. The equivalent CLI is
`manage.py install_workflow <path> [--public] [--groups a,b] [--disabled] [--copy] [--replace]`.

**Per-app Nextflow settings**: `GET/PUT /api/admin/workflows/{id}/nextflow/` — `profile` and
`work_dir` (empty = fall back to the global `nextflow.profile`/`nextflow.work_dir`), and the
app's own `nextflow.config`/`nextflow.env` file contents (`config_path`/`env_path` are reported
read-only), plus the list of environment variables ("template variables") available to the
pipeline (see next section).

### Template / environment variables available to a running workflow
The worker exports (`workflows.template_utils.VARIABLES`/`cloudgene_variables()`), in addition to
the global and per-app `nextflow.env` contents: `CLOUDGENE_JOB_ID`, `CLOUDGENE_JOB_NAME`,
`CLOUDGENE_USER_NAME`, `CLOUDGENE_USER_EMAIL`, `CLOUDGENE_USER_FULL_NAME`, `CLOUDGENE_APP_ID`,
`CLOUDGENE_APP_VERSION`, `CLOUDGENE_APP_LOCATION`, plus service/SMTP variables. The admin
Nextflow settings page's "template variables" list is exactly this set — what a pipeline script
can rely on being present in its environment.

### Users (`AdminUsersView.vue`)
`GET /api/admin/users/?search=&group=&is_active=&page=&page_size=` (paginated; `search` matches
username/email/full name). `PATCH /api/admin/users/{id} {groups?, is_active?, is_admin?}` —
`groups` replaces group membership **by name**; the special `admin` group is not settable through
`groups` and is managed only via `is_admin` (which toggles membership of the `admin` group
together with `is_staff`). An admin cannot deactivate or de-admin themselves, and a superuser can
never have `is_admin` set to `false` (superuser status always implies admin) — both are 400 field
errors. `DELETE /api/admin/users/{id}` → 204; 400 `cannot_delete_self`. There is no separate
"last remaining admin" check on this endpoint, but the acting admin's own membership is untouched
by deleting or demoting someone else, so the admin count can never be driven to zero through it.
The one place a lone admin *could* remove the last admin account is their own self-service
`DELETE /api/me` (profile deletion, see *Auth for API clients* / `plans/SPEC.md` §3.4) — that path
is guarded explicitly: if the caller is the only administrator, it is refused with 400
`last_admin` rather than deleted. Deleting a user who has a
**running** job
does not orphan the job or its workspace: the worker owns cleanup of any claimed job (see
*Job lifecycle* below) — it detects the vanished row, stops the Nextflow process group, and then
removes the workspace; a job that was still only `waiting` (never claimed) has its workspace
removed immediately by the delete itself.

Groups: `GET /api/admin/groups/` → unpaginated `[{id, name, member_count}]`; `POST
/api/admin/groups/ {name}` (unique ignoring case); `DELETE /api/admin/groups/{id}` → 400
`protected_group` for the `admin` group. Deleting a group also removes its name from every
workflow's `apps[].groups` (a workflow that named a deleted group as an access group is simply
not restricted by it any more).

### Settings pages (`frontend/src/views/admin/settings/`)
- **General** (`GeneralSettingsView.vue`) — `server.*` keys listed above except `maintenance`
  banner text, which is edited from the dashboard's maintenance control.
- **Mail** (`MailSettingsView.vue`) — `mail.*`; `password` is write-only (send `''` or omit to
  keep the current one, `clear_password: true` to remove it); a "Send test e-mail" action posts to
  `/api/admin/settings/mail/test/ {to?}` (defaults to the admin's own address; 502 `mail_failed` on
  an SMTP error).
- **Nextflow** (`NextflowSettingsView.vue`) — the *global* `nextflow.*` keys and
  `config/nextflow.config`/`nextflow.env` file contents (per-app overrides are on each workflow's
  own settings page, above).
- **Navbar** — `GET/PUT /api/admin/settings/navbar/ {navbar: [...]}` (errors keyed
  `navbar[i].title` / `navbar[i].url`).
- **Pages** (`PagesView.vue`) — `GET /api/admin/pages/` lists all pages (`slug`, `size`,
  `updated_at`, `deletable`); `GET/PUT/DELETE /api/admin/pages/{slug}` edits the HTML file
  directly. `home` and `footer` always exist and cannot be deleted (400 `protected`); any other
  slug matching `^[a-z0-9][a-z0-9_-]{0,63}$` can be created, edited or removed and becomes
  reachable at `/pages/<slug>`.

### Jobs (`AdminJobsView.vue`)
`GET /api/admin/jobs/?state=&user=<id|username>&workflow=<id>&search=` lists **every** user's jobs
(the non-admin `GET /api/jobs/` only ever shows the caller's own). `POST
/api/admin/jobs/{id}/cancel/` and `POST /api/admin/jobs/{id}/restart/` act on any job; restart
requires an intact workspace and a workflow that is still installed and enabled (409
`workspace_removed` / `workflow_unavailable` otherwise) and re-parses the **current**
`cloudgene.yaml` (not the snapshot the job originally ran with).

### Logs (`LogsView.vue`, `GET /api/admin/logs/`)
Application log records are written to the `admin_panel.SystemLog` table by a DB log handler
attached to five/six loggers (`logging.getLogger('cloudgene.<area>')`):

| Logger | Area |
|---|---|
| `cloudgene.auth` | accounts: login, failed login, lockout, register, activate, password reset |
| `cloudgene.jobs` | job submit/cancel/delete, in the **web** process |
| `cloudgene.worker` | the `run_worker` process: heartbeat, scheduling, per-job state changes/failures, tick errors |
| `cloudgene.workflows` | registry sync/install/uninstall/access changes |
| `cloudgene.admin` | admin panel actions: settings, pages, queue, maintenance |
| `cloudgene.api` | the global exception handler's `server_error` entries (unhandled exceptions) |

`GET /api/admin/logs/?level=&min_level=&component=&search=&page=` — `component` is the part after
`cloudgene.` (e.g. `jobs`, `worker`, `auth`). `level` is an exact match, `min_level` is "this level
and above"; both are case-insensitive and must be one of the standard Python levels
(`debug|info|warning|error|critical`) — an unrecognised value is a 400 `invalid` field error, the
same shape as the jobs `state` filter. Retention: `manage.py cleanup_logs [--days 30]`.

## Job lifecycle and queue (operational summary)

See `plans/SPEC.md` §3.3 for the full contract; the operationally relevant points for an admin:
- A single `python manage.py run_worker` process schedules and executes jobs (no Celery, no
  Redis, no WebSockets — the job page polls `GET /api/jobs/{id}/status/`). Only one worker
  instance may run per `CLOUDGENE_HOME` (enforced by `config/worker.lock`).
- The worker's liveness is a heartbeat row read by `/api/health` and the dashboard: `ok: false`
  (and the site is `degraded`) once the last heartbeat is more than 30 seconds old.
- `queue.paused` stops new jobs from starting without touching already-running ones;
  `server.maintenance` additionally blocks new **submissions** from non-admins.
- Cancelling a job sends `SIGTERM` to its Nextflow process group, then `SIGKILL` after a 10 s
  grace period.
- Deleting a job (self-service, finished jobs only, or an admin/user deletion cascading to a
  running one) is always handled safely: the worker is the only process that ever touches a
  running job's workspace, so a delete never races a Nextflow process still writing into the
  directory it is about to remove.
- If no worker is running at all, `manage.py cleanup_jobs` is the backstop: it removes orphaned
  workspace directories (no matching Job row, older than 1 hour) and expired ones
  (`server.job_retention_days`).

## Security notes worth knowing as an admin

- **Login lockout applies everywhere.** `security.max_login_attempts` /
  `security.lockout_duration` are enforced by a single Django authentication backend
  (`accounts.backends.LockoutModelBackend`), so `/django-admin/login/` shares exactly the same
  lockout state as the SPA's `POST /api/auth/login/` — a locked account cannot log in through
  either surface, and a wrong password at either counts toward the lock.
- **A password change or reset revokes the user's API token.** `PATCH /api/me` with a new
  `password`, and a successful password-reset confirmation, both delete the user's existing DRF
  token (if any) so a leaked-but-since-rotated credential cannot keep working.
- **Job output downloads are safe by default.** `GET /api/jobs/{id}/outputs/{file_id}/` only ever
  serves `text/plain`, `image/png`, `image/jpeg`, `image/gif` and `application/pdf` with their
  real content type (and only those may be shown inline with `?inline=1`); every other type —
  including HTML, SVG, XML and JavaScript — is always downloaded as
  `application/octet-stream` with `Content-Disposition: attachment`, regardless of `?inline=1`,
  plus `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox` on every response.
  This means a malicious pipeline output can never execute as a page on the app's own origin.
- No admin interface (SPA or `/django-admin/`) ever displays a user's API token key in cleartext;
  it is shown once, at creation time, by `POST /api/me/token`.

## Discrepancies between the code and `plans/SPEC.md` found while writing this guide

- SPEC §3.6 describes `enabled` as "exactly `apps[].enabled`" and `effective_status` as the
  AND of `enabled` and `valid` — the code (`workflows/views.py` admin serializer,
  `workflows/registry.py`) matches this exactly; no discrepancy found there.
- SPEC's endpoint inventory lists `GET /api/admin/groups` as a plain unpaginated array; the code
  matches. No other discrepancies were found between the endpoints exercised above and SPEC §3.6
  during this pass — see `docs/API.md` for the general contract conventions.
