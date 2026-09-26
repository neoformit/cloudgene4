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

---
