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

## Checked and found clean (T07a)

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

## Observations (not defects — a product decision may be needed)

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
