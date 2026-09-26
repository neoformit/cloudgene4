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
