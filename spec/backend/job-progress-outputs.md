# Job progress, outputs and logs

## Purpose

While a job runs, the worker turns what a step prints and what Nextflow writes into three things a
user can see: per-process task counts on each step, job messages (from annotations and from
flagged command-step streams), and a combined plain-text job log. When a job ends, the worker
lists the files the workflow published as downloadable outputs, and the web process later serves
them only if they still resolve inside the job's own directories. This file defines the parsing
rules, the progress model, output discovery, path safety, and what step output is visible to the
job owner.

## Scope

Covered:

- `jobs/progress.py`: annotation parser, Nextflow stdout task-line parser, incremental trace-file
  reader, per-process task tracker, message de-duplication, task annotation files.
- `jobs/outputs.py`: `collect_outputs`, `resolve_output_file`, `safe_relative`, allowed roots,
  `read_job_log`.
- The parts of `jobs/worker.py` (`Execution._read_progress`, `_save_processes`, `_read_command`,
  `_append_job_log`, `_finish`, `_failure_message`, `_command_failure_message`) that decide what
  becomes a message, a log line or a step's `processes` value.

Out of scope:

- Building the Nextflow command line, trace/log file locations and the environment:
  [job-runner.md](job-runner.md).
- Job and step state transitions, cancellation, heartbeat, recovery:
  [job-queue-worker.md](job-queue-worker.md).
- The HTTP endpoints that expose steps, messages, outputs, the log and downloads (including
  download headers): [jobs-api.md](jobs-api.md).
- The `outputs`, `steps[].processes`, `stdout`/`stderr` keys of `cloudgene.yaml`:
  [workflow-definition.md](workflow-definition.md).
- Models (`JobStep`, `JobMessage`, `JobOutput`): [data-model.md](data-model.md).
- Retention purge of workspaces: [management-commands.md](management-commands.md).

## Dependencies

- [job-runner.md](job-runner.md): per-step files under `<job_dir>/logs/` (`stdout.txt`,
  `<prefix>trace.txt`, `<prefix>nextflow.log`, `<prefix>command.stdout.txt`,
  `<prefix>command.stderr.txt`), the trace field list (`TRACE_FIELDS`), and `work_dir_for`.
- [job-queue-worker.md](job-queue-worker.md): the worker tick that calls the progress reader.
- [configuration.md](configuration.md): `job_dir(id)`, `nextflow.work_dir`, per-app `work_dir`.
- [workflow-definition.md](workflow-definition.md): `OutputParam.download`, `Step.processes`
  labels, `Step.stdout` / `Step.stderr`.
- Contract operations that read this data: `jobs_retrieve`, `jobs_status_retrieve`,
  `jobs_log_retrieve`, `jobs_outputs_retrieve` (see [jobs-api.md](jobs-api.md)).

## Requirements

### Annotations (job messages from Nextflow output)

- **BE-PROG-001** A line whose stripped text has the form `::<name>[ k=v,…]::<value>` MUST be
  treated as an annotation. `<name>` is case-insensitive and MUST match `[a-z][a-z-]*`; a line
  that does not parse is ordinary output.
- **BE-PROG-002** Annotation names MUST map to message levels as follows: `message`, `notice`,
  `info` → `info`; `success` → `success`; `warning` → `warning`; `error` → `error`. `debug` and
  any other name (counters, values, …) MUST produce no message. An annotation with an empty value
  MUST produce no message. The value MAY contain `::`.
- **BE-PROG-003** `::group[ type=<name>]::[title]` MUST start collecting the following plain lines
  (title first, if given); `::endgroup::`, a new `::group::`, or the end of the step's output MUST
  emit the collected text, trimmed, as one message whose level is mapped from `type` (default
  `info`). An empty group MUST produce no message.
- **BE-PROG-004** Each emitted message text MUST be truncated to 10 000 characters.
- **BE-PROG-005** For a Nextflow step the worker MUST parse annotations from the step's stdout as
  it grows, and, for each trace row whose status becomes `COMPLETED` or `FAILED`, from the
  task's `cloudgene.out` (preferred) or else `.command.out` in its `workdir` (first 2 MiB only).
- **BE-PROG-006** A message that appears both in stdout and in a task file (a `debug true`
  process) MUST be stored once; a message that genuinely repeats n times in one source and m
  times in the other MUST be stored max(n, m) times.
- **BE-PROG-007** Every stored message MUST be linked to the step that was current when it was
  read. Messages MUST be returned in insertion order (`created_at`, `id`).
- **BE-PROG-008** The worker MUST add the lifecycle messages `info "Job started."` at start, and
  exactly one final message on finish: `success "Job completed successfully."`, `warning` with
  the cancel text, or `error` with the failure text (see BE-PROG-021).
- **BE-PROG-009** Output MUST be consumed as complete lines only (split on `\n`, trailing `\r`
  removed); a trailing partial line MUST be held until more output arrives or the step ends,
  then processed. Invalid UTF-8 MUST be replaced, not raise.

### Process progress

- **BE-PROG-010** The worker MUST recognise Nextflow task lines in both formats
  `[PROCESS ab/123456] NAME (tag)` (Nextflow ≥ 25) and `[ab/123456] Submitted|Re-submitted|Cached
  process > NAME (tag)`; the tag suffix MUST be stripped to give the process name. A task line
  MUST NOT be parsed as an annotation.
- **BE-PROG-011** The trace file MUST be read incrementally from the last byte offset; the first
  non-empty line is the header; if the file shrinks (rewritten) reading MUST restart from offset 0
  with a new header. A missing file yields no rows.
- **BE-PROG-012** Each task (keyed by trace `hash`, falling back to `task_id`) MUST be in exactly
  one state: `completed` (trace `COMPLETED` or `CACHED`, or a `Cached process` stdout line),
  `failed` (`FAILED`, `ABORTED`, `KILLED`), otherwise `submitted`. The process name comes from the
  trace `process` column, else from `name` with the tag stripped.
- **BE-PROG-013** A step's `processes` value MUST be a list, in first-seen order, of
  `{name, label, submitted, running, completed, failed, total}` where `running` is the number of
  tasks in state `submitted`, `total = submitted = completed + failed + running`. `label` MUST be
  the YAML `processes[].label` for the full name or for its last `:`-segment, else the name.
- **BE-PROG-014** The step row MUST be updated only when counts changed, at most once per worker
  tick, and once more when the step ends.
- **BE-PROG-015** When a job ends in any state other than `success`, tasks still `submitted` MUST
  be counted as `failed` in the final `processes` value.
- **BE-PROG-016** Command steps (`type: command`) MUST have an empty `processes` list.

### Outputs

- **BE-PROG-017** When a job reaches any final state, the worker MUST replace all of the job's
  output rows with the files found under `<job_dir>/output/<output id>` for every YAML output with
  `download: true`. Outputs with `download: false` MUST NOT be listed. If listing fails, the job
  MUST still be finalised.
- **BE-PROG-018** An output path that is a file (or a symlink to a file) MUST give one row; a
  directory MUST be walked recursively in sorted order, without following nested directory
  symlinks, and give one row per file. At most 5 000 files MUST be listed per output.
- **BE-PROG-019** A file MUST be listed only if its fully resolved real path is a regular file
  inside an allowed root: the job directory, or the job's actual Nextflow work directory computed
  exactly as the runner computes it (per-app `work_dir` first, else global `nextflow.work_dir`,
  else `<job_dir>/work`). Broken symlinks and symlinks leaving the roots MUST be skipped silently.
  Each row stores `output_id`, the YAML label, the path relative to `<job_dir>/output/` in POSIX
  form, and the real file's size in bytes.
- **BE-PROG-020** Resolving an output row for download MUST re-validate at request time: the stored
  path MUST be relative, contain no `..`, `.` or empty segments, no NUL and no leading `/` or `\`;
  the resolved real path MUST exist, be a regular file and lie inside an allowed root
  (BE-PROG-019). Otherwise the result is "not found" (no distinction between causes).

### Logs and stream visibility

- **BE-PROG-021** The job log MUST be the tail (last 256 KiB, cut at a line boundary, with a
  `[... N bytes omitted ...]` marker) of `logs/stdout.txt`, followed by a
  `===== <name> (tail) =====` section with the 256 KiB tail of each `*nextflow.log` in name order.
  With neither file present it MUST be the job's `error_message`, else `No log available yet.`
  (active job) or `No log available.` (finished job).
- **BE-PROG-022** `logs/stdout.txt` MUST contain the worker's `[cloudgene] …` lines (step
  heading, the command line, cancel/kill notes, final state) and the full stdout+stderr of each
  Nextflow step.
- **BE-PROG-023** For a command step, a stream (`stdout`, `stderr`) MUST reach the job log, job
  messages or `error_message` only when that stream's flag is `true` in the step. An unflagged
  stream MUST stay only in its per-step file on disk.
- **BE-PROG-024** For a flagged command-step stream: at most 1 MiB per stream MUST be copied into
  the job log (then a truncation note); when the step ends the last 64 KiB MUST become one message
  (`stdout` → `info`, `stderr` → `warning`); on failure the last 4 096 bytes MUST be appended to
  the failure message.
- **BE-PROG-025** A command-step stream that grows beyond 256 MiB MUST stop the step (SIGTERM to
  its process group) and fail the job with a message stating the output limit.
- **BE-PROG-026** The failure message of a Nextflow step MUST be
  `Step "<name>" failed: Nextflow exited with code <rc>.` plus up to 15 non-empty lines starting at
  the first `ERROR ~` in that step's stdout; when the step has `stdout` or `stderr` set, it MUST
  also include the last 4 096 characters of that step's output.
- **BE-PROG-027** Nothing in this area MAY write to a path derived from user-supplied text (job
  name, input values); all paths come from the job id, output ids from the admin-installed YAML,
  and names found on disk.

## Interfaces

Pure functions and classes in `jobs/progress.py` (no database access):

| Name | Contract |
|------|----------|
| `AnnotationParser.feed_line(line) -> [(level, text)]`, `.close()` | BE-PROG-001..004 |
| `parse_annotations(text)` | Whole-text convenience wrapper (feeds and closes). |
| `parse_task_line(line) -> (hash, process, cached) \| None` | BE-PROG-010 |
| `process_name(task_name)` | Strips ` (tag)` suffix. |
| `LineBuffer.feed(text)`, `.flush()` | BE-PROG-009 |
| `TraceReader(path).read() -> [row dict]` | BE-PROG-011 |
| `ProcessTracker(labels).submitted / trace_row / kill_unfinished / counts / changed` | BE-PROG-012..015 |
| `MessageMerger.add(source, messages)` | BE-PROG-006 |
| `read_task_annotations(workdir)` | BE-PROG-005 |

Functions in `jobs/outputs.py`:

| Name | Contract |
|------|----------|
| `collect_outputs(job, definition) -> [JobOutput]` | BE-PROG-017..019 |
| `resolve_output_file(job, output) -> Path \| None` | BE-PROG-020 |
| `safe_relative(rel) -> PurePosixPath \| None` | Lexical check of BE-PROG-020 |
| `read_job_log(job) -> str` | BE-PROG-021 |

Persisted shapes: `JobStep.processes` (BE-PROG-013), `JobMessage{level, text, step}`,
`JobOutput{output_id, label, path, size, download_count}` — field definitions in
[data-model.md](data-model.md); wire shapes (`ProcessProgress`, `JobMessage`, `JobOutput`) in
`schema.yaml` via [api-contract.md](api-contract.md).

Constants: `MAX_MESSAGE_LENGTH = 10000`, `MAX_FILES_PER_OUTPUT = 5000`,
`LOG_TAIL_BYTES = 256 KiB` (`jobs/progress.py`, `jobs/outputs.py`); `COMMAND_MESSAGE_BYTES = 64 KiB`,
`COMMAND_LOG_BYTES = 1 MiB`, `COMMAND_OUTPUT_LIMIT = 256 MiB`, `FAILURE_TAIL_BYTES = 4096`
(`jobs/worker.py:41-44`).

## Behaviour

Per worker tick, for the running Nextflow step:

1. Read new bytes of `logs/stdout.txt` from the step's offset; split into lines.
2. Each line: task line → `tracker.submitted`; otherwise → annotation parser → merger (`stdout`).
3. At step end (`final`): flush the partial line and close any open group.
4. Read new trace rows → `tracker.trace_row`; for rows `COMPLETED`/`FAILED` read the task's
   annotation file → merger (`tasks`). Cached tasks are not re-read.
5. Bulk-insert new messages for the current step; save `processes` if changed.

Per tick for a command step: for each stream, check the 256 MiB limit, copy new bytes of a flagged
stream into `stdout.txt` (once-per-stream header `[cloudgene] --- <stream> of step "<name>" ---`,
1 MiB cap); at step end add the flagged stream tails as messages.

On finish (`_finish`): mark unfinished tasks failed unless success; close step rows; add the final
message; append `[cloudgene] Job <state>: <first line>` to `stdout.txt`; `collect_outputs`; then
set the job's final state. Outputs therefore exist for failed and cancelled jobs too (whatever was
published), and never while a job is running. A restart deletes them (see
[admin-api.md](admin-api.md)).

Output resolution edge cases: a stored path that later becomes a directory, a dangling symlink, or
a file removed by retention cleanup all resolve to "not found". A symlink to another file inside
the job directory is allowed. Nextflow's default `publishDir` mode (symlink into the work dir) is
supported because the work dir is an allowed root.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| BE-PROG-001, 002 | `jobs/tests/test_progress.py::AnnotationParserTest::test_levels`, `::test_value_may_contain_colons`, `::test_unicode_and_invalid` | unit |
| BE-PROG-002 (`info`/`success` names) | `jobs/tests/test_progress.py::AnnotationParserTest::test_info_and_success_names` (planned) | unit |
| BE-PROG-003 | `jobs/tests/test_progress.py::AnnotationParserTest::test_group`, `::test_unterminated_group_flushed_on_close` | unit |
| BE-PROG-004 | `jobs/tests/test_progress.py::AnnotationParserTest::test_message_truncated` (planned) | unit |
| BE-PROG-005, 006 | `jobs/tests/test_progress.py::MergerTest::test_dedup_between_sources`, `::test_read_task_annotations`; `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` | unit |
| BE-PROG-007, 008 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `e2e/tests/test_jobs.py::test_live_progress_multi_process` | unit, e2e |
| BE-PROG-009 | `jobs/tests/test_progress.py::LineBufferTest::test_partial_lines` | unit |
| BE-PROG-010 | `jobs/tests/test_progress.py::TaskLineTest::test_formats` | unit |
| BE-PROG-011 | `jobs/tests/test_progress.py::TraceAndTrackerTest::test_incremental_trace_and_counts`; rewrite case `::test_trace_rewrite_restarts` (planned) | unit |
| BE-PROG-012, 013, 015 | `jobs/tests/test_progress.py::TraceAndTrackerTest::test_incremental_trace_and_counts`, `::test_trace_without_process_column`; `e2e/tests/test_jobs.py::test_live_progress_multi_process` | unit, e2e |
| BE-PROG-014 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` (final value only); write-on-change `::test_processes_saved_only_on_change` (planned) | unit |
| BE-PROG-016 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_taxodactyl_shaped_job` (planned assertion on `processes == []`) | unit |
| BE-PROG-017, 018, 019 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`; `jobs/tests/test_api.py::JobLifecycleApiTest::test_output_traversal_and_foreign_ids`, `::test_a04_per_app_work_dir_is_an_allowed_output_root`, `::test_a04_global_work_dir_still_allowed_without_an_app_override`; `e2e/tests/test_findings_jobs.py::test_a04_per_app_work_dir_is_an_allowed_output_root`; cap and nested-symlink cases `jobs/tests/test_outputs.py::CollectOutputsTest` (planned) | unit, e2e |
| BE-PROG-020 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_output_traversal_and_foreign_ids` | unit |
| BE-PROG-021, 022 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e/tests/test_jobs.py::test_failing_workflow`; empty/fallback text `jobs/tests/test_outputs.py::ReadJobLogTest` (planned) | unit, e2e |
| BE-PROG-023 | `jobs/tests/test_command_steps.py::StreamVisibilityTest::test_hidden_streams_stay_on_disk`, `::test_flagged_streams_are_shown`; `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` | unit, e2e |
| BE-PROG-024 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail`; `e2e/tests/test_command_steps.py::test_failing_command_step_fails_the_job` | unit, e2e |
| BE-PROG-025 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_runaway_output_is_capped` | unit |
| BE-PROG-026 | `jobs/tests/test_worker.py::WorkerFailureTest::test_failed_pipeline`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_nextflow_stdout_flag_adds_output_to_failure_message` | unit |
| BE-PROG-027 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` (job name never in argv/paths) | unit |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| BE-PROG-018 | The 5 000-file cap only breaks the inner per-directory loop; `os.walk` continues into the next directory and appends again, so an output with many sub-directories can list far more than 5 000 files (verified: cap 2 yields 3 over two directories). Truncation is also silent (no message to the user). | `jobs/outputs.py:81-86` | minor |
| BE-PROG-018 | Nested directory symlinks are not descended (`followlinks=False`), so a Nextflow `path` *directory* output published with the default `publishDir` symlink mode inside a folder output is silently omitted. The spec keeps "do not follow" for safety but the omission is invisible to the user. | `jobs/outputs.py:81` | minor |
| BE-PROG-012 | A trace row with neither `hash` nor `task_id` gets key `task-<len(tasks)>`, which changes as tasks are added, so its status updates create new tasks and inflate counts. Cloudgene always requests both columns (`TRACE_FIELDS`), so this only matters for hand-edited configs. | `jobs/progress.py:196` | minor |
| BE-PROG-007 | There is no cap on the number of messages per job. A workflow emitting many annotations grows `job_messages` without bound, and every poll of `jobs_status_retrieve` returns all of them. | `jobs/worker.py:191-199` | minor |
| BE-PROG-005 | `read_task_annotations` opens `workdir` taken verbatim from the trace file without checking it lies inside the allowed roots. Workflows are admin-installed (trusted), so impact is low. | `jobs/worker.py:443-444`, `jobs/progress.py:248-260` | minor |
| BE-PROG-002, 004, 011, 014, 016, 018, 021 | Parts of these requirements have no test (see planned rows above). | — | minor |

## Open questions

1. Nextflow-step stdout is always visible in the job log (BE-PROG-022), while command steps hide
   unflagged streams (BE-PROG-023). Should `stdout:`/`stderr:` flags on a Nextflow step also gate
   what `jobs_log_retrieve` shows, or is the Nextflow console output always public to the owner?
2. The job log includes tails of `nextflow.log`, which can contain resolved config values and
   environment details. Is that acceptable for non-admin owners?
3. `submitted` always equals `total` in `processes` (BE-PROG-013). Keep both fields, or redefine
   `submitted` (e.g. tasks not yet started) once Nextflow exposes that state?
4. `report.html` and `timeline.html` are written to `logs/` but never exposed. Should they become
   downloadable for owners (with the B-04 download rules in [jobs-api.md](jobs-api.md))?
