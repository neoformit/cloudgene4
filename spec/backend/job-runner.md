# Job runner

## Purpose

Executes the steps of a claimed job, one process at a time, inside the job workspace. A step is
either a Nextflow run (`nextflow run …` with a generated params file and configuration) or a
command step (`cmd`/`exec`, run as an argv or through `bash -c`). This area defines how the
command line and environment are built, how processes are isolated and killed, which log files
are written, and how an exit status becomes a job result and failure message.

## Scope

Covered:

- `jobs/runner.py`: `prepare_step`, `prepare_command`, `build_env`, `cloudgene_variables`,
  `resolve_binary`, `resolve_script`, `work_dir_for`, `find_bash`, `CLOUDGENE_CONFIG`,
  `app_config_path`, `app_env_path`.
- `jobs/worker.py`: `Execution._start_step`, `_start_command`, `poll`, `_read_command`,
  `_append_job_log`, `_failure_message`, `_command_failure_message`, `_log`.
- `jobs/workflow_bridge.py`: `nextflow_profile`, `nextflow_work_dir`.
- `workflows/template_utils.py`: the values of `cloudgene_variables` for a job.

Out of scope:

- `params.json` content and `$name` substitution/quoting rules:
  [job-submission.md](job-submission.md) (BE-JSUB-028 – BE-JSUB-031).
- Claiming, cancellation flags, grace timing, shutdown, orphan recovery:
  [job-queue-worker.md](job-queue-worker.md).
- Parsing Nextflow output, trace and annotations; collecting outputs; serving the job log:
  [job-progress-outputs.md](job-progress-outputs.md).
- Step definitions (`script`, `revision`, `params`, `cmd`, `bash`, `stdout`, `stderr`, step
  types): [workflow-definition.md](workflow-definition.md).
- Editing the global `nextflow.config` / `nextflow.env` and per-app files:
  [configuration.md](configuration.md), [workflow-registry.md](workflow-registry.md).
- The list and meaning of `CLOUDGENE_*` names shown in the admin UI:
  [workflow-registry.md](workflow-registry.md).

## Dependencies

- [job-submission.md](job-submission.md): `Job.parameters`, workspace layout, variable table,
  `params.json`.
- [job-queue-worker.md](job-queue-worker.md): when a step starts and what happens to the job
  state when it ends or is cancelled.
- [configuration.md](configuration.md): `nextflow.binary`, `nextflow.profile`,
  `nextflow.work_dir`, `CLOUDGENE_HOME/config/nextflow.config`, `CLOUDGENE_HOME/config/nextflow.env`,
  `core.config.parse_env`.
- [workflow-registry.md](workflow-registry.md): per-app `profile`, `work_dir`, `config_path`,
  `env_path` (`registry.get_nextflow_settings`).
- No HTTP operation.

## Requirements

### Steps

- **BE-RUN-001** Steps MUST run one at a time in definition order. A step starts only after the
  previous one exited with status 0. The job succeeds when the last step exits 0.
- **BE-RUN-002** A step whose type is not `nextflow` or `command` MUST fail the job with the step's
  parse error (e.g. a `classname` step) without starting a process.
- **BE-RUN-003** Every step process MUST start in a new session (its own process group), with
  stdin from `/dev/null` and the job workspace as working directory. Its pid and process-group id
  are stored on the job before the next tick.
- **BE-RUN-004** When a step's main process exits, the worker MUST send SIGKILL to its whole
  process group, so no child survives the step.

### Nextflow steps

- **BE-RUN-005** The binary MUST be `nextflow.binary` (default `nextflow`). A value containing `/` is
  used as is; otherwise it is looked up in `PATH`, then in `/usr/local/bin`, else used as is.
- **BE-RUN-006** The command line MUST be, in this order (`P` = `''` for step 1, `step<N>-` for
  step N ≥ 2):

  ```
  <binary> -log <ws>/logs/<P>nextflow.log run <script> [-r <revision>]
    -params-file <ws>/<P>params.json
    [-c CLOUDGENE_HOME/config/nextflow.config] [-c <app nextflow.config>]
    -c <ws>/cloudgene.config [-profile <profile>] -w <work dir>
    -with-trace <ws>/logs/<P>trace.txt -with-report <ws>/logs/<P>report.html
    -with-timeline <ws>/logs/<P>timeline.html -ansi-log false
  ```

  The two optional `-c` files are passed only if they exist. The app file is the registry's
  `config_path`, else `<app dir>/nextflow.config`.
- **BE-RUN-007** `<ws>/cloudgene.config` MUST be (re)written before every Nextflow step with trace
  fields `task_id,hash,native_id,process,tag,name,status,exit,workdir,submit,start,complete,duration,realtime`
  and `overwrite = true` for trace, report and timeline. It is passed last, so it wins over
  workflow and admin config for those keys.
- **BE-RUN-008** `<script>` MUST be the step's `script` (default `main.nf`). If that path exists,
  relative to the app directory or absolute, it is passed as an absolute path; otherwise it is
  passed verbatim as a remote pipeline name. `-r` is added only when `revision` is set.
- **BE-RUN-009** `-profile` MUST be the app's `profile`, else `nextflow.profile`; omitted when both are
  empty.
- **BE-RUN-010** The work directory MUST be `<configured>/<job uuid>` when the app's `work_dir` or
  else `nextflow.work_dir` is set (a relative value is under `CLOUDGENE_HOME`), otherwise
  `<ws>/work`. It is created before the step starts.
- **BE-RUN-011** Nextflow's stdout and stderr MUST go, merged, to `<ws>/logs/stdout.txt`, appended
  across steps.

### Command steps

- **BE-RUN-012** With `bash: false`, the argv MUST be the shell-word split of `cmd` with each token
  substituted ([BE-JSUB-030](job-submission.md#requirements)); argv[0] without `/` is resolved
  in the step environment's `PATH`. No shell is involved. An argv that is empty after
  substitution fails the job with `Step "<name>" failed: The command is empty after variable
  substitution`.
- **BE-RUN-013** With `bash: true`, the argv MUST be `[<bash>, -c, <quoted script>]`, where `<bash>`
  is `/bin/bash` if executable, else `bash` from `PATH`.
- **BE-RUN-014** A command step's stdout and stderr MUST go to `<ws>/logs/step<N>-command.stdout.txt`
  and `<ws>/logs/step<N>-command.stderr.txt` (emptied at step start; `N` is 1-based for every
  step).
- **BE-RUN-015** A stream MUST be shown only when its `stdout:`/`stderr:` flag is true: it is copied into
  `logs/stdout.txt` (header `[cloudgene] --- <stream> of step "<name>" ---`, at most 1 MiB per
  stream, then a truncation note naming the step file), and at step end its last 64 KiB becomes a
  job message (stdout: `info`, stderr: `warning`). An unflagged stream stays only in its step
  file.
- **BE-RUN-016** If either captured stream grows beyond 256 MiB, the worker MUST stop the step
  (SIGTERM, grace, SIGKILL) and fail the job with `Step "<name>" failed: its output exceeded 256
  MiB and the command was stopped.`

### Environment

- **BE-RUN-017** The process environment MUST be built in this order, later entries winning: the
  worker's environment; `/usr/local/bin` appended to `PATH` if missing; `KEY=VALUE` lines of
  `CLOUDGENE_HOME/config/nextflow.env`; those of the app's env file (registry `env_path`, else
  `<app dir>/nextflow.env`); the job's `CLOUDGENE_*` variables; `NXF_ANSI_LOG=false`. In env
  files, `#` comments, `export ` and surrounding quotes are allowed, and `$VAR`/`${VAR}` expand
  against the environment built so far (unknown → empty).
- **BE-RUN-018** The job's `CLOUDGENE_*` values MUST come from the job's snapshot (`app_id`,
  `app_name`, `app_version`, `app_dir`), the job (id, name, workspace, submission time) and its
  user (username, e-mail, full name), plus the global service and SMTP values. Env files cannot
  override them.
- **BE-RUN-019** (planned) The environment passed to step processes MUST NOT contain the web
  application's own secrets and connection settings (at least `DJANGO_SECRET_KEY`,
  `DATABASE_URL`, `EMAIL_*` and other `DJANGO_*` variables from `cloudgene.env`).
- **BE-RUN-020** User-supplied text (inputs, job name, file names) MUST reach a step process only
  as a `params.json` value, an argv element, a value quoted per BE-JSUB-030, an environment value,
  or a file under `input/` — never as unquoted shell text or a path segment outside the workspace.

### Exit handling and logs

- **BE-RUN-021** Each step start MUST write to `logs/stdout.txt` the lines `[cloudgene] Step <i>/<n>:
  <name>` (` (command)` for command steps) and `[cloudgene] $ <command>` (shell-quoted argv, or
  the substituted script for `bash: true`). Cancellation, SIGKILL after grace, and the final
  state are logged the same way (`[cloudgene] Job <state>: <first line of message>`).
- **BE-RUN-022** A Nextflow step exiting non-zero MUST fail the job with `Step "<name>" failed:
  Nextflow exited with code <rc>.`, followed by up to 15 non-blank lines starting at the first
  `ERROR ~` in this step's part of `logs/stdout.txt`, and — only if the step's `stdout` or `stderr`
  flag is set — `Output (last lines):` and the last 4096 characters of that output.
- **BE-RUN-023** A command step exiting non-zero MUST fail the job with `Step "<name>" failed (exit
  code <rc>).`, or `(killed by signal <SIGNAME>).` for a signal, followed for each flagged stream
  by `<stream> (last lines):` and its last 4096 bytes.
- **BE-RUN-024** If the process cannot be started, the job MUST fail with `Could not start Nextflow
  (<binary>): <error>` or `Step "<name>" failed: could not start command "<argv0>": <error>`.
- **BE-RUN-025** The files a job writes MUST be exactly those listed under Interfaces; no file
  outside the workspace is written except the Nextflow work directory when configured outside it.

## Interfaces

Python: `runner.prepare_step(job, definition, index, *, binary, profile, work_dir, app_dir) →
PreparedStep(command, env, cwd, stdout_path, trace_path, log_path, params_path)`;
`runner.prepare_command(job, definition, index, *, app_dir) → PreparedCommand(argv, env, cwd,
stdout_path, stderr_path, display)` (raises `ValueError` for an empty argv);
`runner.build_env(job, definition, app_dir, base_env=None)`; `runner.resolve_binary(configured)`.

Constants (`jobs/worker.py`): `COMMAND_MESSAGE_BYTES = 64 KiB`, `COMMAND_LOG_BYTES = 1 MiB`,
`COMMAND_OUTPUT_LIMIT = 256 MiB`, `FAILURE_TAIL_BYTES = 4096`.

Workspace files written while running (`P` as in BE-RUN-006):

| Path (under `CLOUDGENE_HOME/jobs/<uuid>/`) | Writer | Content |
|---|---|---|
| `params.json`, `step<N>-params.json` | runner | Nextflow params (BE-JSUB-031) |
| `cloudgene.config` | runner | trace/report/timeline config (BE-RUN-007) |
| `logs/stdout.txt` | Nextflow + worker | merged Nextflow output, `[cloudgene]` lines, flagged command output |
| `logs/<P>nextflow.log` | Nextflow | `-log` file |
| `logs/<P>trace.txt`, `logs/<P>report.html`, `logs/<P>timeline.html` | Nextflow | trace / report / timeline |
| `logs/step<N>-command.stdout.txt`, `…stderr.txt` | command step | full captured streams |
| `output/<output id>` | runner (dirs), workflow | outputs; folder outputs pre-created |
| `work/`, `.nextflow/` | Nextflow | when no work dir is configured |

Environment variables set for every step: everything in BE-RUN-017, including
`CLOUDGENE_SERVICE_NAME`, `CLOUDGENE_SERVICE_URL`, `CLOUDGENE_SMTP_HOST`, `CLOUDGENE_SMTP_PORT`,
`CLOUDGENE_SMTP_USER`, `CLOUDGENE_SMTP_PASSWORD`, `CLOUDGENE_SMTP_SENDER`,
`CLOUDGENE_WORKSPACE_TYPE` (`local`), `CLOUDGENE_WORKSPACE_HOME`, `CLOUDGENE_APP_ID`,
`CLOUDGENE_APP_NAME`, `CLOUDGENE_APP_VERSION`, `CLOUDGENE_APP_LOCATION`, `CLOUDGENE_JOB_ID`,
`CLOUDGENE_JOB_NAME`, `CLOUDGENE_JOB_LOCATION`, `CLOUDGENE_JOB_SUBMITTED_ON`,
`CLOUDGENE_USER_NAME`, `CLOUDGENE_USER_EMAIL`, `CLOUDGENE_USER_FULL_NAME`, `NXF_ANSI_LOG`.

## Behaviour

Step start (`Execution._start_step`): mark the step row `running` and `Job.current_step`; for an
unsupported step fail at once; build the prepared step (creates `logs/`, output paths, work dir,
params and config files); log the header and command; check the job row still exists; spawn;
store pid/pgid. If the row vanished at any point, the worker's vanish path applies
([BE-QUEUE-023](job-queue-worker.md#requirements)).

Poll (each tick): read new output (progress, [job-progress-outputs.md](job-progress-outputs.md));
for command steps copy flagged streams and check the output cap; apply cancellation
([BE-QUEUE-019](job-queue-worker.md#requirements)); if the process exited, SIGKILL the group, read
the remaining output, then:

| Condition | Result |
|-----------|--------|
| output cap exceeded | `failed`, BE-RUN-016 message |
| SIGTERM was sent for cancellation | `cancelled`, `Job cancelled.` |
| rc = 0, more steps | next step starts in the same tick |
| rc = 0, last step | `success`, `Job completed successfully.` |
| rc ≠ 0 | `failed`, BE-RUN-022 / BE-RUN-023 message |

Paths that come from the workflow author (`script`, `cmd`, config files) are trusted admin input;
values from users are constrained as in BE-RUN-020 and
[job-submission.md](job-submission.md#requirements).

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| 001 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_multi_step_and_remote_script`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_taxodactyl_shaped_job`, `::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit |
| 002 | `jobs/tests/test_worker.py::WorkerFailureTest::test_unsupported_step_fails_with_clear_message` | unit |
| 003, 004 | `jobs/tests/test_worker.py::WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_cancel_during_long_command_kills_the_process_group`; `jobs/tests/test_worker.py::test_children_killed_after_normal_exit` (planned, BE-RUN-004) | unit |
| 005, 024 | `jobs/tests/test_worker.py::WorkerFailureTest::test_missing_binary`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_missing_executable` | unit |
| 006, 008, 009, 010 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_env_files_profile_and_app_config`, `::test_multi_step_and_remote_script`; `jobs/tests/test_api.py::JobLifecycleApiTest::test_a04_per_app_work_dir_is_an_allowed_output_root`; `e2e/tests/test_findings_jobs.py::test_a04_per_app_work_dir_is_an_allowed_output_root` | unit, e2e |
| 007 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs` (trace parsed) | unit |
| 011, 021 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_list_detail_status_log_and_download`; `e2e/tests/test_jobs.py::test_live_progress_multi_process` | unit, e2e |
| 012, 013, 020 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_injection_is_literal_in_both_modes`, `SubstitutionTest` (all); `e2e/tests/test_command_steps.py::test_command_steps_run_and_show_output` | unit, e2e |
| 014, 015 | `jobs/tests/test_command_steps.py::StreamVisibilityTest::test_hidden_streams_stay_on_disk`, `::test_flagged_streams_are_shown` | unit |
| 016 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_runaway_output_is_capped` | unit |
| 017, 018 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_env_files_profile_and_app_config`; `jobs/tests/test_command_steps.py::SubstitutionTest::test_build_variables` | unit |
| 019 | `jobs/tests/test_worker.py::test_server_secrets_not_in_step_env` (planned) | unit |
| 022 | `jobs/tests/test_worker.py::WorkerFailureTest::test_failed_pipeline`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_nextflow_stdout_flag_adds_output_to_failure_message`; `e2e/tests/test_jobs.py::test_failing_workflow` | unit, e2e |
| 023 | `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail`; `e2e/tests/test_command_steps.py::test_failing_command_step_fails_the_job` | unit, e2e |
| 025 | `jobs/tests/test_worker.py::test_only_workspace_files_written` (planned) | unit |

## Known gaps

| Req | What the code does | Where | Severity |
|-----|--------------------|-------|----------|
| BE-RUN-019 | The step environment starts from the worker's full `os.environ`. Under systemd that is `cloudgene.env`, so every Nextflow and command process (including remote pipelines and their containers' env passthrough) gets `DJANGO_SECRET_KEY`, `DATABASE_URL` with the DB password, and mail settings. | `jobs/runner.py:118`; `deploy/systemd/cloudgene-worker.service:11` | major |
| BE-RUN-022 | A Nextflow process killed by a signal is reported as `Nextflow exited with code -9` instead of naming the signal as command steps do. | `jobs/worker.py:545` | minor |
| BE-RUN-008 | When the snapshot's app directory no longer exists (workflow uninstalled), `main.nf` is passed as a remote pipeline name and Nextflow fails with a confusing "cannot find project" error instead of a clear message. | `jobs/runner.py:103-109` | minor |
| BE-RUN-004, 025 | No test checks that children are killed after a normal exit, or that nothing is written outside the workspace. | `jobs/tests/test_worker.py` | minor |

## Open questions

- `CLOUDGENE_SMTP_PASSWORD` is passed to every step on purpose (Cloudgene 3 compatibility). Should
  it stay, or be opt-in per workflow?
- Step-1 Nextflow files have no prefix while command-step files are always `step<N>-`. Should the
  naming be unified (it affects log viewers in [job-progress-outputs.md](job-progress-outputs.md))?
