# Exploratory QA findings

Findings from charter-based exploratory sessions (see `plans/E2E_TEST_PLAN.md` §4).
Each agent appends its own section; never rewrite someone else's. Confirmed defects have a red
test in `e2e/tests/test_findings_*.py` (`xfail(strict=True)`), removed by the fixing task.

## T07c — admin, config & multi-user

Session: 2026-09-20, branch `worktree-agent-a8ec08b4553a18d0c` (base `rebuild` @ 83cd54f).
Probes: `e2e/exploratory/test_probe_*.py` (run with `E2E_SKIP_BUILD=1 pytest e2e/exploratory/... -s`).
Red tests: `e2e/tests/test_findings_admin.py`.

| ID | Sev | Title |
|----|-----|-------|
| C-01 | Medium | A partial mail PUT bypasses the TLS/SSL mutual exclusion → all SMTP mail fails |
| C-02 | High | One invalid value in `settings.yaml` 500s the whole site after a web restart; `/api/health` still says `ok` |
| C-03 | Medium | Deleting a user leaves the workspace of their running job on disk (and logs an unhandled worker traceback) |
| C-04 | Low | Log `component` values do not match SPEC §3.8 / the Logs filter hint (`auth`, `jobs` find nothing) |
| C-05 | Low | Navbar `url` is not validated at all — a `javascript:` URL is stored and served to every visitor |
| C-06 | Low | `GET /api/admin/logs/?level=bogus` answers 200 + empty instead of 400 (the jobs `state` filter answers 400) |
| C-07 | Low | The admin workflow row of a broken app reports `enabled: true` although every submission is rejected |

---

### C-01 — A partial mail PUT bypasses the TLS/SSL mutual exclusion (Medium)

**Repro** (as admin, `e2e/exploratory/test_probe_mail_upload.py::test_mail_tls_ssl_both_true_breaks_mail`):

```
PUT /api/admin/settings/mail/  {"use_tls": true, "use_ssl": true}   -> 400 "TLS and SSL are mutually exclusive."
PUT /api/admin/settings/mail/  {"use_ssl": true}                    -> 200          # use_tls is already true
```

**Expected**: the stored configuration can never have both flags (the rule is enforced against the
resulting document, not against the request body).
**Actual**: `settings.yaml` ends up with `use_tls: true, use_ssl: true`; `GET …/settings/mail/`
echoes that impossible state back into the form. With `backend: smtp` **every** outgoing mail then
fails in `django.core.mail`:

```
POST /api/admin/settings/mail/test/  -> 502 {"code":"mail_failed","message":"Sending failed:
      EMAIL_USE_TLS/EMAIL_USE_SSL are mutually exclusive, so only set one of those settings to True."}
POST /api/auth/register/             -> 503 {"code":"mail_failed"}  and no account is created
POST /api/auth/password-reset/       -> 200 (silently sends nothing; the failure is only logged)
```

Saving the Mail form unchanged afterwards is refused with a 400 (it sends both flags), so the admin
must first untick one to get out of the state.

**Suspected cause**: `admin_panel/serializers.py::MailSettingsSerializer.validate` only looks at
`attrs` (the request body); `MailSettingsView.put` deep-merges the subset into `mail.*`. The
schema in `core/config.py` has no cross-field rule either.
**Red test**: `test_c01_mail_tls_and_ssl_cannot_both_be_enabled`.

---

### C-02 — One invalid value in `settings.yaml` 500s the whole site after a web restart (High)

**Repro** (`e2e/exploratory/test_probe_multiuser.py::test_broken_settings_file`, minimised in the
red test): hand-edit `$CLOUDGENE_HOME/config/settings.yaml` (this file is the documented source of
truth and is meant to be editable), e.g. `server.max_running_jobs: 0` — valid YAML, outside the
schema range — or break the YAML syntax, then restart the web process.

**Expected**: a bad single value should not be fatal (SPEC §3.2 promises "validated, defaults
filled"), or at the very least the operator must be able to *see* it: `/api/health` reports
`degraded`/`error`, and the message names the key.
**Actual** (cold process, nothing cached):

```
GET /api/health   -> 200 {"status":"ok","db":{"ok":true},"worker":{"ok":true,…}}   # all green
GET /api/server/  -> 500 {"error":{"message":"Internal server error.","code":"server_error"}}
GET /            -> 200 (SPA shell only; every API call behind it 500s)
PUT /api/admin/settings/general/ -> 400 "settings: … is not valid YAML"            # cannot repair
```

So one typo takes the entire service down, monitoring stays green, and the admin UI cannot fix it —
only shell access can. While the web process is *already running*, the last valid document is kept
(as specified) and the site survives; the worker also keeps going on `default_settings()`.

**Suspected cause**: `core/config.py::load_settings` raises `ConfigError` when nothing is cached;
`core/views.py` health only checks the DB and the worker heartbeat.
**Red test**: `test_c02_invalid_settings_value_does_not_take_the_site_down`.

---

### C-03 — Deleting a user leaves the workspace of their running job on disk (Medium)

**Repro** (`e2e/exploratory/test_probe_users.py::test_delete_user_with_running_job`):
1. a user submits a job and the worker starts it (`state: running`);
2. admin `DELETE /api/admin/users/{id}` → 204 (the Job row cascades away);
3. 10 s later `$CLOUDGENE_HOME/jobs/<uuid>/` is **back on disk** with `work/`, `logs/`, `output/`
   and `.nextflow/` (only `input/`, written at submit time, is gone — proof that the rmtree ran).

**Expected**: SPEC §3.3 — "deleting a Job row (e.g. user deletion) removes the workspace via a
`post_delete` signal". Nothing of the deleted user's run should stay on disk.
**Actual**: the signal's `rmtree` runs while the Nextflow process is still alive, so the dying
execution (`Execution._log`, `prepare_step` dirs, Nextflow's own writes) recreates the directory.
The orphan is only removed later by `manage.py cleanup_jobs` (orphan sweep, >1 h), if scheduled —
a data-retention hole for a *deleted* account.

Same repro, second symptom: the worker logs an unhandled traceback instead of noticing the job is
gone (`e2e/.artifacts*/stack-main/logs/worker.log`):

```
ERROR cloudgene.worker Polling job 12a1a8cb… failed
  …
  jobs.models.JobStep.NotUpdated: Save with update_fields did not affect any rows.
```

It recovers (`poll_executions` → `execution.stop`) and kills the process group, and the queue keeps
running (verified: the next job succeeded, `/api/health` stayed ok) — but the error path is
accidental rather than designed.

**Suspected cause**: `jobs/signals.py::remove_workspace` (no interaction with a running execution);
`jobs/worker.py::Execution.poll/_finish` write to rows that may be gone.
**Red test**: `test_c03_deleting_user_removes_the_workspace_of_a_running_job`.

---

### C-04 — Log components do not match SPEC §3.8 (Low)

**Repro**: log in with a wrong password, run a job, then `GET /api/admin/logs/?component=auth`
(and `…=jobs`) — both return `count: 0`. The components that really occur are `accounts`, `admin`
and `worker` (`e2e/exploratory/test_probe_mail_upload.py::test_log_components`).

**Expected**: SPEC §3.8 names `cloudgene.auth`, `cloudgene.jobs`, `cloudgene.workflows`,
`cloudgene.admin`, `cloudgene.api`; the Logs page input even suggests "component (jobs, auth…)"
(`frontend/src/views/admin/settings/LogsView.vue:54`).
**Actual**: `accounts/views.py:41` uses `cloudgene.accounts`; job logging happens only in
`jobs/worker.py:33` (`cloudgene.worker`) — job submission/cancel/delete in the web process is not
logged at all, so an admin looking for a user's job activity finds nothing under `jobs`.
**Suspected cause**: logger names chosen per module; nothing pins them to the spec list.
**Red test**: `test_c04_log_components_follow_the_spec`.

---

### C-05 — Navbar URLs are not validated (Low)

**Repro**: `PUT /api/admin/settings/navbar/ {"navbar":[{"title":"Bad","url":"javascript:alert(1)"}]}`
→ 200; `GET /api/server/` serves that item to **every** visitor, and
`frontend/src/components/layout/AppNavbar.vue:37-47` renders any URL matching `^[a-z][a-z0-9+.-]*:`
as `<a :href="item.url" target="_blank">`.

**Expected**: the same care as `server.url` (`GeneralSettingsSerializer.validate_url`: must start
with `http://`/`https://`); navbar URLs should be an internal path or an http(s) URL.
**Actual**: any string is accepted (`data:`, `javascript:`, …). Admin-only injection, hence Low, but
it is a stored-content vector in a page every user loads and it is trivial to validate.
**Suspected cause**: `admin_panel/serializers.py::NavbarItemSerializer.url` is a bare `CharField`.
**Red test**: `test_c05_navbar_url_is_validated`.

---

### C-06 — Unknown log level filter is silently ignored (Low, no red test)

`GET /api/admin/logs/?level=bogus` → `200 {count: 0}`, so a typo in the filter looks like "no such
events". `GET /api/admin/jobs/?state=bogus` does it right: `400 state: Unknown state "bogus". Use
one of: …`. Same for `min_level`. Cause: `admin_panel/views.py::LogListView.get_queryset` filters
without validating. Reported as an inconsistency, not a behaviour the SPEC pins down.

### C-07 — A broken workflow still shows `enabled: true` in the admin list (Low, no red test)

After breaking an installed `cloudgene.yaml`, `GET /api/admin/workflows/` returns the row with
`valid: false`, `errors: […]` **and** `enabled: true`, while `POST /api/jobs` answers
`409 workflow_disabled` and the public list/detail hide it (404). The flag mirrors `apps[].enabled`
from settings.yaml rather than the effective state (`Workflow.status` is set to `disabled` by the
sync). Worth aligning the admin UI so it does not claim a dead app is enabled.

---

### Probed and found clean

* **General settings round-trip** — every field saved, re-read, present in `settings.yaml`, visible
  on `/api/server/`; unicode kept; rejects `0`/`-1`/`2.5`/`"abc"`/`null` for ints, blank name,
  >100 chars, non-http `url`; nothing bricks the app (every page still loads after a rejected save).
  Extreme-but-valid values (`max_running_jobs: 1e9`, `max_upload_mb: 1e12`) are accepted.
* **Settings really take effect, live, without restarting the worker**: `max_running_jobs`
  (1 → exactly one job runs; raised to 3 → the two waiting jobs start within one tick),
  `max_queue_size` (429 `queue_full`; `0` = unlimited), `max_upload_mb` (413 `upload_too_large`,
  workspace cleaned up), `job_retention_days` (`cleanup_jobs` keeps at `0`, deletes at `1`,
  `purged_at`/`expires_at` set), `queue.paused` (pause → waiting → resume → runs),
  `server.maintenance` (503 for users, admins exempt, banner via `/api/server/`),
  `security.require_activation: false` (account active at once).
* **Mail settings are really used**: `from_email`, `file_path` (outbox moves), `server.name` and
  `server.url` in the activation subject/link; `password` write-only, kept across unrelated PUTs,
  cleared by `clear_password`, never echoed.
* **Nextflow settings reach a running pipeline** (probe app `e2e/exploratory/apps/probe-env`):
  global `nextflow.config` + `nextflow.env`, per-app `apps/<id>/nextflow.config` + `nextflow.env`
  (both `-c` flags in the command line, app wins), `nextflow.profile` (`workflow.profile`),
  `nextflow.work_dir` (job dirs created under it), `CLOUDGENE_*` variables; a bad `binary` or a
  missing profile fails only that job, with a message, and leaves the stack healthy.
* **Workflow admin**: install from an absolute path, reload after adding an input (form updates),
  broken YAML → `valid:false` + errors in the admin row, hidden from the public API, submissions
  409, repaired by another reload; app directory deleted from disk → same; duplicate id → 409 on
  install and `id~index` + error for a hand-added duplicate (the first entry keeps working);
  colliding with an installed app id → 409; disable/uninstall with a running job → the job finishes
  and stays readable, the row is kept with `installed: false`; access changes (public/groups) take
  effect on the user's next request, including via group membership.
* **Users & groups**: deleting a group prunes it from `apps[].groups` for enabled *and* disabled
  workflows (and from its members); group names validated (case-insensitive duplicates, spaces,
  unicode, `../`, length) ; `admin` group protected; self-demote/self-deactivate/self-delete and
  last-admin deletion all refused; a second admin can be promoted and demoted and loses access
  immediately; deactivating a user kills their session at once (401) while their running job
  finishes normally.
* **Multi-user**: with `max_running_jobs: 1` two users' jobs run strictly FIFO (no starvation);
  an admin cancelling a running job is reflected on the owner's job page within the poll interval;
  admin job filters `state` (incl. comma lists and a 400 for unknown values), `user` (id or name),
  `workflow`, `search` all correct; non-admins get 403.
* **Pages/navbar**: slug rules enforced (`Probe-Page`, `probe page`, `ünicode`, `_leading`, >64
  chars, traversal and `%2f` all rejected; `1`, `trailing-` accepted), `home`/`footer` not
  deletable but editable, 404 for a missing page, 512 KB page saved and served, `admin_only` /
  `auth_only` correctly filtered for anonymous/user/admin.
* **Restarts**: settings, navbar and pages survive a web restart; a broken settings.yaml is
  tolerated by an already-running web process and by the worker (C-02 covers the cold start).
* **Logs**: admin actions (settings, queue, pages), logins and failed logins are recorded with the
  acting user; `level`, `min_level`, `component`, `search`, paging and `page_size` work;
  a 200 KB message is stored and returned intact; `cleanup_logs --days 0` empties the table.

### Notes (not defects)

* Offset pagination overlaps while jobs are being submitted (`page=2` repeats a row after a new job
  arrives) — inherent to page/`page_size` pagination as specified.
* Under heavy concurrent writes SQLite occasionally makes the worker tick fail with
  `database is locked` (logged as `ERROR cloudgene.worker Worker tick failed`, next tick recovers).
  Only seen while a probe wrote a 200 KB log row from a second process; SQLite is dev/test only.
* A navbar entry pointing at an unknown SPA route silently lands on the home page; deleting a page
  that a navbar item links to leaves the item in place (no warning).
