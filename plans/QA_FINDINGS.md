# Exploratory QA findings

Findings from charter-based exploratory QA sessions (`plans/E2E_TEST_PLAN.md` §4).
Each agent appends its own section; never rewrite someone else's.

Severity: **Blocker** (data loss / unusable) · **High** · **Medium** · **Low**.
Every confirmed defect has a red, `xfail(strict=True)` test in `e2e/tests/test_findings_*.py`
so the suite stays green today and flips loudly when the defect is fixed.

---

## T07a — run form & job lifecycle

Charter: break the run form and the job lifecycle. Session 2026-09-20/26, branch
`worktree-agent-ae9fb1324781d9029`, stack tip `83cd54f`. Probes live in `e2e/exploratory/`
(`probe_inputs.py`, `probe_files.py`, `probe_lifecycle.py`, `probe_ui.py`, `probe_edge.py`,
`probe_workdir.py`, `probe_lock.py`); red tests in `e2e/tests/test_findings_jobs.py`.

| ID | Sev | Finding |
|----|-----|---------|
| A-04 | High | A per-app Nextflow `work_dir` silently discards every result of that workflow |
| A-02 | High | >100 files in a folder input → HTTP 500 "Internal server error." |
| A-03 | High | SQLite write contention: 500s on admin pages and aborted worker ticks |
| A-01 | Medium | A file part sent for a text input is accepted and becomes the file's name |
| A-05 | Low | The server accepts numbers the run form rejects (`1_0`, Unicode digits) |

### A-01 — A file part sent for a text input is accepted and becomes the file's *name*

**Severity:** Medium

**Steps (API, minimal):**
```bash
curl -b cookies -H "X-CSRFToken: $CSRF" -X POST $BASE/api/jobs/ \
     -F workflow=hello -F 'message=@/tmp/m.txt'          # message is a `text` input
```
or with both a typed value and a file for the same field:
```bash
curl ... -F workflow=hello -F message=typed -F 'message=@/tmp/m.txt'
```

**Expected:** `message` is a `text` input, so a file part for it is a type error →
400 `invalid` with `fields.message`. At the very least the typed value must win.

**Actual:** 201 Created. The job's `message` parameter is the **uploaded file's name**
(`m.txt`); the file itself is written nowhere and the typed value (`typed`) is discarded.
A required text input can therefore be "satisfied" by an unrelated upload, and the pipeline
receives a value the user never entered.

**Evidence** (`e2e/exploratory/probe_inputs.py::test_missing_and_extra_fields`):
```
file sent for a text input        201 inputs=[{'id': 'message', 'type': 'text', 'value': 'm.txt', 'files': []}]
file AND text for the same input  201 [{'id': 'message', 'type': 'text', 'value': 'm.txt', 'files': []}]
```

**Suspected cause:** `jobs/views.py:88` calls `submit_job(request.user, request.data, request.FILES)`.
DRF's `request.data` is POST **merged with FILES**, so in `jobs/submission.py`
`_get(data, pid)` can return an `UploadedFile`; `validate_inputs` then does
`text = str(raw)`, and `str(UploadedFile)` is its file name. Fix: pass `request.POST`
as `data` (or reject non-string values in `_get`).

**Red test:** `test_a01_file_part_for_text_input_is_rejected`

---

### A-02 — More than 100 files in a folder input → HTTP 500 "Internal server error."

**Severity:** High

**Steps (UI):** log in as `alice`, open `/run/all-inputs`, pick any `.csv` for *CSV file*,
select **101 or more** files for *Folder of files*, tick the terms box, submit.

**Steps (API):** `POST /api/jobs/` with `workflow=all-inputs` and 101+ `data_folder` file parts.

**Expected:** a 4xx in the error envelope naming the limit (e.g. 400/413 with
`fields.data_folder = ["At most N files…"]`), so the user can act on it. A folder of >100
files is an ordinary genomics use case.

**Actual:** HTTP **500** `{"error":{"message":"Internal server error.","code":"server_error"}}`.
The run form shows the bare text *"Internal server error."* and stays on the page.
The boundary is exactly 100 file parts in the whole request (99 folder files + 1 file input
= 100 → OK; 100 folder files + 1 = 101 → 500).

**Evidence** (`e2e/exploratory/probe_files.py::test_folder_input`, `probe_ui.py::test_many_files_in_folder_input`):
```
folder with  99 files   201 files_on_disk=100
folder with 100 files   500 {"error": {"message": "Internal server error.", "code": "server_error"}}
folder with 150 files   500 …
run-error shown         Internal server error.
```
server.log:
```
django.core.exceptions.TooManyFilesSent: The number of files exceeded settings.DATA_UPLOAD_MAX_NUMBER_FILES.
ERROR django.request Internal Server Error: /api/jobs/
```

**Suspected cause:** `DATA_UPLOAD_MAX_NUMBER_FILES` is never set (Django default 100) in
`cloudgene_django/settings.py` (which does set `FILE_UPLOAD_MAX_MEMORY_SIZE` /
`DATA_UPLOAD_MAX_MEMORY_SIZE`), and `core/exceptions.api_exception_handler` does not map
Django's `SuspiciousOperation` subclasses (`TooManyFilesSent`, `RequestDataTooBig`) —
`drf_exception_handler` returns `None`, so they become `server_error` 500. Two fixes needed:
raise/configure the limit, and translate those exceptions into a 400/413 envelope.

**Red test:** `test_a02_many_files_in_folder_input_is_a_client_error`

---

### A-03 — SQLite write contention: 500s on admin pages and failed worker ticks

**Severity:** High

**What happens:** `GET /api/admin/workflows/` runs a **full registry sync inside the request**
(`workflows/registry.list_apps()` → `sync_all()` → `_upsert()` → `row.save()` +
`allowed_groups.set()` for *every* app, with `synced_at=now`). So a read-only admin list
writes to the DB on every single call, while the worker writes its heartbeat and job
progress every ~1 s. On SQLite the two processes collide.

**Steps (observed twice, two different runs, both unprovoked by the test body):**
1. Start the stack with the worker and submit a couple of jobs so the worker is busy.
2. Browse to `/admin/jobs` (loads `/api/admin/workflows/` for the filter dropdown), or issue
   a few concurrent `GET /api/admin/workflows/` while jobs run
   (`e2e/exploratory/probe_lock.py`).

**Expected:** 200. A read-only endpoint should not write; two processes sharing the DB must
not produce 5xx or break the worker loop.

**Actual, symptom 1 (web):** `GET /api/admin/workflows/` → **500** `server_error`.
`e2e/.artifacts/stack-main/logs/server.log`:
```
File ".../workflows/registry.py", line 362, in list_apps  -> sync_all()
File ".../workflows/registry.py", line 298, in _upsert    -> row.save()
django.db.utils.OperationalError: database is locked
ERROR django.request Internal Server Error: /api/admin/workflows/
```
This failed `e2e/exploratory/probe_ui.py::test_xss_job_name_admin` through the browser-error
guard — i.e. it is exactly the kind of flake that will randomly redden the scripted suite.

**Actual, symptom 2 (worker):** the worker tick aborts, 6× in one 25 s window
(`e2e/.artifacts/stack-main/logs/worker.log`):
```
ERROR cloudgene.worker Worker tick failed
  ... core/models.py WorkerHeartbeat.beat -> update_or_create
django.db.utils.OperationalError: database is locked
```
`Worker.tick()` does heartbeat → reconcile → `poll_executions()` → `claim()` in one method
and the whole tick is abandoned on the exception, so a lock storm also stalls progress
updates and job scheduling, and `/api/health` can report the worker as stale/degraded.

**Suspected cause:**
* `workflows/registry.list_apps()` calls `sync_all()` unconditionally instead of
  `sync_if_changed()` (SPEC §3.2 says the API only syncs "when settings.yaml or an installed
  cloudgene.yaml changed"), so every admin read is a write transaction.
* `cloudgene_django/settings.py:150` sets `OPTIONS['timeout'] = 20`, but SQLite's busy
  handler is **not** invoked when a connection that already holds a read transaction tries to
  upgrade to a write (`transaction.atomic()` in `sync_all()` reads first, then writes) — it
  fails immediately with "database is locked". Journal mode is the default (no WAL).
  Fix direction: `sync_if_changed()` in read paths, plus WAL +
  `OPTIONS['transaction_mode'] = 'IMMEDIATE'` (Django ≥5.1), and a per-statement retry or a
  narrower `tick()` so one lock does not abandon the whole worker tick.

**Red test:** `test_a03_admin_workflow_list_does_not_write_on_every_read` (deterministic:
asserts the registry is not rewritten by a plain GET — the write amplification that causes
the contention; the 500 itself is a race and is documented by the log excerpts above).

Reproduced 3×: once through the browser (`probe_ui.py::test_xss_job_name_admin`, 500 on
`/api/admin/workflows/`), once in the worker (6 aborted ticks) and once through
`probe_lock.py` (500 on `/api/admin/dashboard/`, 2 × "database is locked" in server.log out
of 189 requests).

---

### A-04 — A per-app Nextflow `work_dir` silently discards every result of that workflow

**Severity:** High (silent data loss)

**Steps (minimal, `e2e/exploratory/probe_workdir.py`):**
1. Install an app whose pipeline publishes with the **default** `publishDir` mode (symlink) —
   `e2e/exploratory/apps/symlink-out/` is a 10-line fixture for this. Nextflow's default
   `publishDir` mode is `symlink`; the E2E fixture apps all use `mode: 'copy'`, which is why
   the scripted suite never sees this.
2. Set a per-app work dir: `apps[]` entry `work_dir: custom-work` in `settings.yaml`, or in
   the admin UI *Workflows → \<app\> → Nextflow → Work dir*
   (`PUT /api/admin/workflows/{id}/nextflow {"work_dir": "custom-work"}`).
3. Run the workflow.

**Expected:** the same results as without the override — the job's outputs are listed and
downloadable.

**Actual:** the job reports **success**, the file really is published
(`<job>/output/outdir/out.txt` → symlink into `<home>/custom-work/<job id>/…`, target
exists), but `JobOutput` is empty: the Results tab says *"No downloadable results."* and the
API returns `outputs: []`. Nothing warns the user or the admin.

```
test_default_work_dir   outputs [('outdir/out.txt', 6)]   download 200
test_per_app_work_dir   outputs []                        published entries [('out.txt', True, True)]
                        work dir used  <home>/custom-work/5c2ab3b1-…
test_global_work_dir    outputs [('outdir/out.txt', 6)]   download 200   # global setting is fine
```

**Suspected cause:** the two sides disagree about which work dir is in use.
`jobs/runner.work_dir_for(job, workflow_bridge.nextflow_work_dir(wf))` honours the **per-app**
`apps[].work_dir` (falling back to the global one), but `jobs/outputs._allowed_roots(job)`
only builds roots from `cloudgene_config.get('nextflow.work_dir')` — the **global** setting.
So `collect_outputs()` resolves each published symlink, finds it outside every allowed root
and skips it (and `resolve_output_file()` would 404 the download for the same reason).
`_allowed_roots` must use the same resolution as the runner (per-app first).

**Red test:** `test_a04_per_app_work_dir_is_an_allowed_output_root` (fast, structural: it
compares the two code paths instead of running Nextflow; the full E2E reproduction is
`e2e/exploratory/probe_workdir.py`).

---

### A-05 — The server accepts numbers the run form rejects (`1_0`, `٥`, …)

**Severity:** Low

**Steps:** `POST /api/jobs/` with `workflow=all-inputs`, `number_in=1_0` (or `٥`, the
Arabic-Indic digit five).

**Expected:** the same verdict as the form. `frontend/src/components/workflows/form/formModel.js`
validates numbers with `/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/` and rejects both, so the
UI shows *"Please enter a number."*

**Actual:** the API accepts them — `1_0` becomes `10.0` (Python's `float()` allows digit
group separators) and `٥` becomes `5` (Python's `re` `\d` and `int()` accept Unicode digits,
JavaScript's `\d` does not). The value that reaches `params.json` is not the text the user
sent.

**Evidence** (`e2e/exploratory/probe_inputs.py::test_number_input`):
```
number='1_0'   201 -> 10.0        number='٥'   201 -> 5
number=' 7 '   201 -> 7           number='+5'  201 -> 5
```
(`-1e999`, `1e999`, `nan`, `inf`, `Infinity`, `0x10`, `1,5`, `abc`, `true` are all correctly
rejected, and min/max are enforced — this is only about the lenient accepts.)

**Suspected cause:** `jobs/submission.parse_number` uses `re.match(r'^[+-]?\d+$', s)` (Unicode
`\d`) and bare `float(s)`. SPEC §3.7 requires client-side validation to mirror the server
rules. Fix: anchor on an ASCII pattern equivalent to the frontend's.

**Red test:** `test_a05_number_input_rejects_values_the_form_rejects`

---

### Checked and found clean

These were probed and behaved correctly — worth knowing so they are not re-tested blindly.

**Job names (K3).** Spaces, leading/trailing whitespace, newlines/tabs and NUL (control
characters → space, then trimmed), unicode/emoji/RTL, 255 chars (ok) vs 256/1000 chars
(400 with a field error), empty / whitespace-only / control-only names (fall back to
`<workflow> <date>`), and the `name` alias for `job_name`. `<script>`/`<img onerror>` names
render escaped everywhere checked — job list, job page, admin jobs — and the three
`ConfirmDialog`s (which use `v-html`) escape the name explicitly; `window.__xss` stayed
undefined in every view.

**Text inputs.** Empty and whitespace-only rejected when required; 100 000 chars ok,
100 001 rejected; HTML, newlines, `../../etc/passwd`, `$(touch …); rm -rf /` and NUL bytes
are stored and passed to Nextflow verbatim (a NUL round-trips into the output file and the
job succeeds — no crash, no shell injection: the fixture writes from Groovy and the job name
is never used in a path or command line). Oversized bodies (5 MB and 11 MB fields, multipart
*and* JSON) return the 400 envelope, not a 500.

**Uploads.** Filenames with spaces, unicode/emoji, `../..`, `..\..`, `/etc/shadow.csv`,
leading dots, 300 characters, quotes and `;` are all reduced to a safe basename under
`input/<param-id>/` while the original name is kept for display; `accept` is enforced
(`notes.txt` rejected for `.csv`, `DATA.CSV` accepted); 0-byte files accepted; an empty
filename and a missing file both give "Please select a file."; two files for a single-file
input are rejected; duplicate names in a folder input are de-duplicated (`x.txt`,
`x_1.txt`); `max_upload_mb` is enforced per submission (2 MB with a 1 MB limit → 413
`upload_too_large`, and the sum over a folder input counts).

**Submission guards.** Missing/unknown/forbidden workflow (400/404/404), disabled workflow
(409 `workflow_disabled` for users *and* admins), missing required input, invalid list/radio
choice, unticked `terms_checkbox`, hidden and `serialize: false` inputs that cannot be
overridden from the request, unknown extra fields ignored, JSON instead of multipart works.

**Lifecycle.** Submit-then-immediately-cancel (waiting → `cancelled` in the same request);
cancel twice → 409 `invalid_state`; cancel after the job finished → 409; delete while
waiting/running → 409; delete finished → 204 + workspace removed + 404 everywhere after;
delete twice → 404. Restart: only admins (owner gets 404), 409 while running, 409
`workflow_unavailable` when the workflow is disabled, 200 after re-enabling.

**Results, logs, retention.** Download of a finished job's output (correct bytes,
`attachment` vs `inline` with `?inline=1`), `download_count` increments atomically, bogus /
negative / cross-job output ids → 404, log of a failed job contains the Nextflow error
block. After `manage.py cleanup_jobs` past the retention window: `purged_at` set, outputs
removed, downloads 404, log "No log available.", `can_restart` false, Results tab shows
"The results of this job have been deleted."

**Queue & polling.** `queue_position` 1/2/3 and re-numbering after a cancel;
`duration_seconds`/`expires_at` null while waiting; the job page stops polling the moment
the job reaches a final state (0 further `/status` calls in 12 s) and the badge matches the
API; two tabs on the same job both follow a cancel without a reload; a double-click on
*Submit* creates exactly one job; Back after a submit returns to an empty run form and does
not resubmit anything; `?state=` validation, pagination bounds, non-UUID ids and the
admin-only endpoints all behave.

### Observations (not defects — a product decision may be needed)

* **An omitted checkbox is `false`, even when the YAML default is `true`.** Visible checkbox
  inputs fall back to `false` when the field is absent from the request, while *hidden*
  inputs use the YAML `value`. The run form always sends `true`/`false`, so the UI is
  unaffected; an API client that omits the field silently loses the default.
  (`probe_inputs.py::test_list_radio_checkbox`: `flag omitted → 'no'` although
  `flag: value: true`.)
* **A failed job can show the same `::error::` message three times.** For the `fail`
  fixture, `::error::Intentional failure` really does appear three times in
  `logs/stdout.txt` (the workflow's `println`, and twice more because Nextflow echoes the
  failed task's output in its error report) and once in the task's `.command.out`.
  `MessageMerger` emits `max(n, m)` per source by design, so all three are stored and the
  job page repeats the error. Behaving as specified, but noisy.
* **NUL bytes survive end to end.** `message=a\x00b` is stored, written into `params.json`
  and lands in the output file as `b'before\x00after\n'`. Nothing breaks; worth deciding
  whether text inputs should strip control characters the way job names do.
Findings from charter-based exploratory sessions (see `plans/E2E_TEST_PLAN.md` §4).
Each agent appends its own section; never rewrite someone else's. Confirmed defects have a red
test in `e2e/tests/test_findings_*.py` (`xfail(strict=True)`), removed by the fixing task.

## T07c — admin, config & multi-user

Session: 2026-09-20 & 2026-09-26, branch `worktree-agent-a8ec08b4553a18d0c` (base `rebuild` @ 83cd54f).
Probes: `e2e/exploratory/test_probe_*.py` — scratch scripts, skipped by `pytest e2e`; run them with
`E2E_EXPLORATORY=1 E2E_SKIP_BUILD=1 venv/bin/python -m pytest e2e/exploratory -q -s`.
Red tests: `e2e/tests/test_findings_admin.py` (5 × `xfail(strict=True)`, each reproduced twice).

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
* **Multi-user**: with `max_running_jobs: 1` two users' jobs run strictly FIFO, alice's two jobs
  then bob's, no starvation; a job page open in the browser picks up an
  `POST /api/admin/jobs/{id}/cancel` of the running job within the poll interval (badge →
  `cancelled`), and an admin cancelling alice's *waiting* job is visible to alice immediately;
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

* Admin user edits are last-write-wins: two admins PATCHing `groups` on the same user in sequence
  silently overwrite each other (no ETag/version in the contract, `groups` replaces membership by
  design — SPEC §3.6). Worth knowing before two people work the users page at once.
* Offset pagination overlaps while jobs are being submitted (`page=2` repeats a row after a new job
  arrives) — inherent to page/`page_size` pagination as specified.
* Under heavy concurrent writes SQLite occasionally makes the worker tick fail with
  `database is locked` (logged as `ERROR cloudgene.worker Worker tick failed`, next tick recovers).
  Only seen while a probe wrote a 200 KB log row from a second process; SQLite is dev/test only.
* A navbar entry pointing at an unknown SPA route silently lands on the home page; deleting a page
  that a navbar item links to leaves the item in place (no warning).
---

## T07b — security & access control

Charter: security and access control (IDOR/object permissions, privilege escalation, CSRF,
path traversal, XSS/injection, secrets, auth lifecycle, light DoS) against the scripted suite's
blind spots. Stack: `rebuild` @ 83cd54f, E2E stack (`e2e/exploratory/serve.py`), seeded users
admin/alice/bob. Probe scripts: `e2e/exploratory/` (`matrix.py`, `probes_api.py`,
`probes_auth.py`, `probes_djangoadmin*.py`, `probes_injection.py`, `probes_xss.py`,
`probes_misc.py`, `probes_inline_html.py`). Red tests: `e2e/tests/test_findings_security.py`.

### B-01 — `/django-admin/` login bypasses the account lockout and yields a full API session (High)

**Severity:** High — the entire brute-force protection promised by SPEC §3.4
(`security.max_login_attempts` / `security.lockout_duration`, 429 `account_locked`) is
bypassable, and the accounts it protects best (admins) are exactly the ones reachable there.

**Minimal repro** (probe: `e2e/exploratory/probes_djangoadmin.py`):
1. Make an account an admin (`PATCH /api/admin/users/{id} {"is_admin": true}` — this sets
   `is_staff=True`, which is what the Django admin site requires).
2. Lock it out through the documented endpoint: 6 × `POST /api/auth/login` with a wrong password
   → `429 account_locked`, and a 7th attempt *with the correct password* is still 429.
3. `POST /django-admin/login/` with the **correct** password (plus the form's
   `csrfmiddlewaretoken`) → `302 /django-admin/`.
4. Send the resulting `sessionid` cookie to the API: `GET /api/auth/me` →
   `{"authenticated": true, "user": {...}}`, `GET /api/admin/dashboard` → `200`.

**Expected:** while the account is locked no login path may succeed, and wrong passwords at any
login surface must count towards `login_attempts`.
**Actual:** `/django-admin/login/` uses Django's own `AuthenticationForm`; it never touches
`User.login_attempts` / `locked_until`, is not rate-limited at all, and the session it creates is
the same `django.contrib.sessions` session the SPA API trusts. 8 wrong passwords there left the
account unlocked (`POST /api/auth/login` afterwards → 200).

**Evidence:**
```
API login while locked: 429 {"error":{"message":"Too many failed logins. ...","code":"account_locked"}}
django-admin login while locked -> 302 /django-admin/
/api/auth/me with that cookie: True dja5cd660
/api/admin/dashboard with that cookie: 200
```

**Suspected cause:** `cloudgene_django/urls.py` routes `path('django-admin/', admin.site.urls)`
and `django.contrib.admin` is in `INSTALLED_APPS` (`cloudgene_django/settings.py`), while the
lockout is implemented only in `accounts.views.LoginView`. SPEC §3.6 does not list the Django
admin as part of the product at all.
**Fix direction:** drop `django.contrib.admin` / the `django-admin/` route from the deployed
URLconf (or gate it behind an env flag that defaults to off); if it is kept, move the lockout into
an authentication backend / signal (`user_login_failed`) so every login surface counts.

### B-02 — a password change or password reset does not revoke the API token (Medium)

**Severity:** Medium — the account-recovery flow does not evict an attacker. Sessions *are*
invalidated (Django's session-auth hash), so the token is the one credential that survives.

**Minimal repro** (probe: `e2e/exploratory/probes_auth.py`):
1. As alice: `POST /api/me/token` → key `K`.
2. Change the password: `PATCH /api/me {"password", "password_confirm", "current_password"}`
   (or run the whole `POST /api/auth/password-reset` → `/api/auth/password-reset/{token}` flow).
3. `GET /api/me` with `Authorization: Token K` → **200**.

**Expected:** SPEC §3.4 makes the reset link single-use and treats a reset as account recovery;
a credential created before the reset must not keep working.
**Actual:** the DRF token row is untouched by both flows (`session: password change kills the
other session` passes, `token: password change revokes the API token` fails; same for reset).

**Evidence:** `token: password change revokes the API token  GET /api/me with the old token -> 200`
and `reset: password reset revokes the API token  GET /api/me with the pre-reset token -> 200`.

**Suspected cause:** `accounts/views.py` — `ProfileView.patch` / `PasswordResetConfirmView.post`
call `user.set_password()` + `save()` and never touch `rest_framework.authtoken.models.Token`.
**Fix direction:** `Token.objects.filter(user=user).delete()` in both paths (and mention it in the
UI), or hash-bind the token to the password like the session auth hash.

### B-03 — every user's API token key is readable in cleartext via `/django-admin/` (Medium)

**Severity:** Medium — contradicts SPEC §3.4/§3.6 ("the key is only ever returned here, once";
`GET /api/me` deliberately exposes only `api_token.created`). Any superuser — or anyone who gets
a superuser session, e.g. through B-01 — can copy a user's token and act as that user, invisibly.

**Minimal repro** (probe: `e2e/exploratory/probes_djangoadmin2.py`):
1. alice: `POST /api/me/token` → key `K`.
2. Log in at `/django-admin/login/` as the seeded superuser (`manage.py create_admin`).
3. `GET /django-admin/authtoken/tokenproxy/` → the changelist prints `K` in full.

**Expected:** no interface returns an existing token key.
**Actual:** `alice's token key readable in the Django admin: True`
(`sample: ['75d953336059c5c0797d0fba551ef2df325a6919', ...]`).

**Suspected cause:** `rest_framework.authtoken` registers its own `ModelAdmin`, which is
reachable because `django.contrib.admin` is installed and routed (same root cause as B-01).
DRF stores token keys in plaintext, so removing the admin surface is the practical fix.

### B-04 — job outputs are served with a sniffed content type; `?inline=1` renders user-controlled output as HTML on the app origin (Medium)

**Severity:** Medium — stored XSS in the application origin. The victim is whoever opens the
inline link, including an **admin** (admins may download any user's outputs), and `csrftoken` is
deliberately not `HttpOnly`, so the payload can drive authenticated state-changing API calls.

**Minimal repro** (probe: `e2e/exploratory/probes_inline_html.py`, red test uses a pre-seeded
output file so it needs no worker):
1. Any workflow whose output folder contains an `.html` file built from a user input (the probe
   installs a 12-line fixture app; real Cloudgene pipelines publish HTML reports).
2. alice submits it with `message = <script>document.title="XSS-T07B"</script>`.
3. `GET /api/jobs/{id}/outputs/{file_id}/?inline=1` →
   `200, Content-Type: text/html, Content-Disposition: inline; filename="report.html"`, payload
   present — as alice **and** as admin.

**Expected:** a download endpoint must not turn job artefacts into active content on the app's
own origin.
**Actual:** `FileResponse(open(path,'rb'), as_attachment=not inline, filename=output.name)` lets
Django guess the type from the file name; `X-Content-Type-Options: nosniff` does not help because
the declared type already *is* `text/html`.

**Suspected cause:** `jobs/views.py:JobViewSet.output_download`.
**Fix direction:** force `content_type='application/octet-stream'` (or an allowlist:
text/plain, application/json, image/*) unless the file type is known-safe, keep
`Content-Disposition: attachment` for everything else, and/or serve downloads from a separate
origin plus a `Content-Security-Policy: sandbox` header.

### B-05 — a text/string/textarea input accepts a file upload and uses its raw file name as the value (Low)

**Severity:** Low — input-validation inconsistency, no traversal or shell exposure (K3 holds),
but a required text input can be satisfied without any text and the value that reaches
`params.json` is an unsanitised client-supplied file name.

**Minimal repro:**
```
POST /api/jobs  (multipart)  workflow=hello  + file part named "message"
                              (filename "sneaky-name.txt")
→ 201, inputs: [{"id":"message","type":"text","value":"sneaky-name.txt","files":[]}]
→ the pipeline receives params.message = "sneaky-name.txt" and writes it to hello.txt
```
**Expected:** 400 `invalid` with `fields.message` — a file is not a value for a text input, and
`required` is not satisfied.
**Actual:** DRF merges `request.FILES` into `request.data`, so
`jobs/submission.py:_get(data, pid)` returns the `UploadedFile`; `str(raw)` is its `.name`.

**Suspected cause:** `jobs/submission.py:validate_inputs` (the non-file branch does not reject
file-like values). **Fix direction:** in `_get`, ignore values that are `UploadedFile`s for
non-file params (or read from `request.POST` for value inputs).

### Informational / accepted-by-design (no test)

- **I-1 Lockout is a login-time control only.** A locked account's *existing* session and its API
  token keep working (`GET /api/me` → 200). Consistent with SPEC §3.4 wording, but worth a
  decision: a lockout usually implies the account is frozen.
- **I-2 No `Content-Security-Policy`** on the SPA (`X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` are present). A CSP would
  contain B-04 and the intentional `v-html` surfaces.
- **I-3 Intentional HTML rendering (trust boundary).** `v-html` is used for admin-authored page
  HTML (`home`, `footer`, `/pages/{slug}`), the footer, and for `workflow.description` /
  input `label`s from `cloudgene.yaml`. Both are admin-controlled (installing a workflow already
  means arbitrary Nextflow execution), so this is by design — but it means *workflow YAML is
  privileged input*: anything a pipeline author writes is executed in every visitor's browser.
  Verified escaped everywhere user-controlled data appears: job names, `::message::` text from a
  pipeline's stdout, user full names/e-mails in the admin lists (`e2e/exploratory/probes_xss.py`,
  6/6 checks; `ConfirmDialog` messages pass job names through a local `escapeHtml`).
- **I-4 No body-size limit for JSON endpoints.** `DATA_UPLOAD_MAX_MEMORY_SIZE = 10 MB` only
  applies to form parsing; an 11 MB JSON body to `POST /api/auth/register` is parsed fully
  (400 after 2.7 s). Multipart uploads are streamed and bounded by `server.max_upload_mb`.
- **I-5 Public surface beyond SPEC §3.6.** `/api/schema/` and `/api/schema/swagger-ui/` are
  anonymous (full API surface disclosure) and `/api/categories/` is public and undocumented.
- **I-6 Admin = arbitrary code execution, by design.** `POST /api/admin/workflows/install`
  accepts any path containing a `cloudgene.yaml` (`/etc` → 400 "No cloudgene.yaml found"), the
  installed app's `nextflow.config`/`nextflow.env` are admin-editable, and `nextflow.work_dir`
  may be any path. Nothing to fix; the trust boundary is "admin == root-equivalent".
- **I-7 Registration reveals whether a username / e-mail exists** (`This username is already
  taken.`), while login and password-reset do not (verified identical bodies / messages). This is
  the documented behaviour (`accounts/serializers.py` MSG_USERNAME_TAKEN, SPEC §3.4 K1) — flagged
  only so the choice is explicit. Login timing was measured (unknown 0.090 s vs existing 0.115 s
  with the E2E fast hasher; the unknown-user path does a dummy `set_password`, so the real
  deployment is equalised).

### Probed and found clean

- **Endpoint × role matrix** over every path/method in `schema.yaml` (66 operations ×
  anon/bob/alice/admin): anonymous → 401 on every protected endpoint (never 403), non-admin →
  403 on all 30 `/api/admin/*` operations, non-owner → 404 (never 403) on
  `/api/jobs/{id}[/status|/log|/outputs/{file_id}|/cancel]` and `DELETE /api/jobs/{id}`.
  Full matrix: `e2e/exploratory/matrix.py`, regression test `test_permission_matrix`.
- **IDOR:** alice's output id under bob's own job → 404; unknown/malformed job UUIDs → 404;
  `?user=` on `GET /api/jobs` is ignored; token auth is scoped exactly like the session.
- **Privilege escalation:** `PATCH /api/me` with `is_staff`/`is_superuser`/`is_active`/`is_admin`/
  `groups`/`username`/nested `user{}` → all ignored; `POST /api/auth/register` with the same keys
  → inactive, no groups; `PATCH /api/admin/users/{id} {"groups":["admin"]}` does not grant admin
  (managed only via `is_admin`); self-deactivation / self-demotion / self-delete-as-last-admin
  refused.
- **CSRF:** missing header, wrong header, and a cross-origin `Origin` are all 403 `csrf_failed` —
  including on `POST /api/auth/login` (login CSRF) and `POST /api/auth/logout`; token auth is
  correctly exempt; `sessionid` is `HttpOnly; SameSite=Lax`.
- **Sessions:** the session id rotates on login (no fixation), logout kills the old cookie,
  a password change kills the *other* sessions, deactivating or deleting a user kills both the
  session and the token.
- **Auth lifecycle:** password-reset tokens are single-use (2nd use → 400) and the request answer
  is identical for unknown e-mails; a reused activation key does not re-activate an
  admin-deactivated account; lockout counts case-varied usernames against the same account.
- **Path traversal:** `/api/pages/{slug}` with `..%2f`, `%2e%2e%2f`, `....//`, `%00`, absolute
  paths, upper case and `.html` suffixes → 404 (slug regex `^[a-z0-9][a-z0-9_-]{0,63}$` in
  `core/config.py`); `PUT /api/admin/pages/../../config/secret_key` → 404; output downloads
  re-validate the stored relative path (`jobs/outputs.py:safe_relative` + `_within`).
- **Injection (K3):** a job named ``$(touch …) `id` ; rm -rf / & | ../../etc/passwd %s ${HOME}``
  runs fine, is stored verbatim, never appears in a path (`jobs/<uuid>/`), is not in
  `params.json`, and creates no side effects; control characters are stripped; text inputs with
  quotes/`;`/traversal reach the pipeline as literal text (`nextflow` is spawned with an argv
  list, never a shell). SQL-ish payloads in `search`/`user`/`category`/`state` filters → 200/400,
  never 500.
- **Secrets:** `GET /api/admin/settings/mail` never returns `password` (only `password_set`), the
  value does not appear in `/api/admin/logs`; no password or token key is logged; `GET /api/me`
  exposes no hash/activation fields; non-admin payloads contain no other users' e-mail addresses;
  `config/secret_key` is not reachable through any endpoint; DEBUG is off (no traceback in any
  4xx/5xx body probed, unknown `/api/...` → JSON 404 envelope).
- **Limits:** `page_size` capped at 200 on `/api/jobs` and `/api/admin/logs`; over-long job names
  (>255) and text inputs (>100 000) rejected; deeply nested (200 levels) JSON handled without a
  500; invalid `page`/`page_size`/`state` handled with the error envelope.
