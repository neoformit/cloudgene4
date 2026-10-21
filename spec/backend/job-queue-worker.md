# Job queue and worker

## Purpose

Moves jobs from `waiting` to a final state without depending on web requests. One worker process
per `CLOUDGENE_HOME` (`manage.py run_worker`) claims waiting jobs in submission order up to a
concurrency limit, runs them ([job-runner.md](job-runner.md)), handles cancellation, records a
heartbeat, and on start-up and every tick fails jobs left `running` by a previous worker. This
replaces the original design in which the queue only advanced inside a submit/cancel request and
jobs could stay "pending" forever (K2).

## Scope

Covered:

- `jobs/models.py`: `JobState`, the state fields of `Job` (`status`, `cancel_requested`,
  `submitted_at`, `started_at`, `finished_at`, `pid`, `pgid`, `current_step`, `error_message`,
  `deleted_at`, `purged_at`), `JobStep.status`, `queue_position()`, `can_cancel()`,
  `can_delete()`, `can_restart()`.
- `jobs/worker.py`: `Worker`, `Execution` lifecycle (start, poll, cancel, stop, vanish, finish),
  `fail_job`, `kill_orphan_group`, `retry_on_locked`, `acquire_lock`.
- `jobs/management/commands/run_worker.py`.
- `jobs/services.py`: `cancel_job`, `delete_job`, `restart_job` (state effects only).
- `jobs/signals.py`: workspace removal when a job row is deleted.
- `core/models.py`: `WorkerHeartbeat.beat` (written by the worker).
- How `jobs/management/commands/cleanup_jobs.py` interacts with job states.

Out of scope:

- Process command lines, environment, log files, exit-code messages: [job-runner.md](job-runner.md).
- Progress parsing and output collection on finish: [job-progress-outputs.md](job-progress-outputs.md).
- HTTP endpoints for cancel/delete/restart/status: [jobs-api.md](jobs-api.md), [admin-api.md](admin-api.md).
- `/api/health` and how it judges the heartbeat: [server-pages-mail.md](server-pages-mail.md).
- `cleanup_jobs` options and output: [management-commands.md](management-commands.md).
- Column definitions and migrations: [data-model.md](data-model.md).

## Dependencies

- [configuration.md](configuration.md): `server.max_running_jobs`, `server.max_queue_size`,
  `server.job_retention_days`, `queue.paused`; `core.config.job_dir`, `config_dir`.
- [job-submission.md](job-submission.md): creates `waiting` jobs and their workspace.
- [job-runner.md](job-runner.md): per-step process start and exit handling.
- [job-progress-outputs.md](job-progress-outputs.md): `collect_outputs`, step process counts.
- Operations whose state effects are defined here: `jobs_cancel_create`, `jobs_destroy`,
  `admin_jobs_cancel_create`, `admin_jobs_restart_create`, `jobs_status_retrieve`.

## Requirements

### States

- **BE-QUEUE-001** A job's `status` MUST be one of `waiting`, `running`, `success`, `failed`,
  `cancelled`. `waiting` and `running` are active; the other three are final.
- **BE-QUEUE-002** A job's `status` MUST NOT change except by these transitions:

  | From | To | By | Trigger |
  |------|----|----|---------|
  | (new) | `waiting` | web | submission ([job-submission.md](job-submission.md)) |
  | `waiting` | `running` | worker | claim |
  | `waiting` | `cancelled` | web or worker | cancel of a waiting job |
  | `running` | `success` | worker | last step exited 0 |
  | `running` | `failed` | worker | step failure, setup error, orphan recovery, shutdown |
  | `running` | `cancelled` | worker | `cancel_requested` and process group stopped |
  | `failed`/`cancelled` | `waiting` | web (admin) | restart, only if workspace not purged |

- **BE-QUEUE-003** Every transition into a final state MUST set `finished_at`, clear `pid` and
  `pgid`, and add one job message (`success` / `warning` for cancelled / `error`). For `failed`
  and `cancelled`, `error_message` holds that message; for `success` it is empty.
- **BE-QUEUE-004** Step rows (`JobStep.status`) MUST follow the job: the running step ends as
  `success`/`failed`/`cancelled`; on any non-success end, steps not yet started become
  `cancelled`.
- **BE-QUEUE-005** `queue_position()` MUST return the 1-based rank of a waiting job by
  (`submitted_at`, `id`) among all waiting jobs, and `null` for any other state.

### Claiming and limits

- **BE-QUEUE-006** The worker claims waiting jobs in (`submitted_at`, `id`) order, skipping jobs
  with `cancel_requested`. A claim is one conditional update (`status=waiting AND
  cancel_requested=false` → `running`, `started_at=now`); a job whose update affects no row is
  skipped. Two workers racing for the same job MUST NOT both claim it.
- **BE-QUEUE-007** The worker MUST NOT run more than `server.max_running_jobs` (minimum 1) jobs at once. Settings are
  re-read every tick, so a change to `max_running_jobs` or `queue.paused` applies without a
  restart.
- **BE-QUEUE-008** While `queue.paused` is true the worker MUST claim nothing; running jobs continue
  and cancellations are still processed.
- **BE-QUEUE-009** (K2) The queue MUST advance without any web request: when a running job ends,
  the next waiting job is claimed by the worker within one tick (default 1 s).
- **BE-QUEUE-010** The waiting-queue size limit (`server.max_queue_size`) is enforced at
  submission ([BE-JSUB-005](job-submission.md#requirements)); the worker MUST NOT reject a job
  for queue size.

### Worker process

- **BE-QUEUE-011** Only one worker may run per `CLOUDGENE_HOME`: it MUST hold an exclusive
  non-blocking `flock` on `CLOUDGENE_HOME/config/worker.lock` (file content: its pid). A second
  `run_worker` exits with `CommandError` `Another worker is already running for this
  CLOUDGENE_HOME.` (exit status 1) and touches no job.
- **BE-QUEUE-012** Every tick the worker MUST upsert `WorkerHeartbeat` row `default` with
  `last_seen=now`, `pid`, `hostname`, `started_at` and `info` =
  `{running, paused, max_running_jobs}`. A heartbeat older than 30 s means the worker is down.
- **BE-QUEUE-013** A tick runs these phases in order: heartbeat, orphan reconcile, poll running
  executions, cancel flagged waiting jobs, claim (skipped when paused or stopping). An error in
  one phase MUST be logged and MUST NOT stop the other phases. A SQLite "database is locked"
  error is retried up to 3 times (backoff 0.05 s, doubling) before the phase gives up until the
  next tick; other errors are not retried.
- **BE-QUEUE-014** On SIGTERM or SIGINT the worker MUST stop claiming, finish the current tick,
  then for each running job send SIGTERM to its process group, wait up to min(grace, 5) s,
  send SIGKILL, and mark the job `failed` with `The worker was shut down while this job was
  running; the job was stopped.` It then releases the lock and exits 0.
- **BE-QUEUE-015** `run_worker --once` MUST run ticks until nothing runs and nothing is claimable
  (or the queue is paused), or `--timeout` seconds (default 3600) pass; jobs still running then
  are stopped as in BE-QUEUE-014. Options: `--interval` (tick seconds, default 1.0), `--grace`
  (SIGTERM→SIGKILL seconds, default 10).
- **BE-QUEUE-028** Whenever the worker changes anything that `jobs_status_retrieve` returns
  (job state, `current_step`, a step's state or `processes`, or a new job message), it MUST also
  set `Job.updated_at` to the current time, so that `updated_at` changes whenever the status
  payload changes. (planned) The job page's poller uses `updated_at` for change detection
  ([../frontend/job-detail.md](../frontend/job-detail.md) FE-JDET-010).

### Recovery (K2)

- **BE-QUEUE-016** At start-up and on every tick, every `running` job that this worker is not
  executing is an orphan. The worker MUST mark it `failed` with `The worker was restarted while
  this job was running; the job was stopped.` (running step → `failed`, waiting steps →
  `cancelled`) and keep its workspace.
- **BE-QUEUE-017** For an orphan, the worker sends SIGKILL to the stored process group only if
  that group is alive and one of its processes has the job id in its command line or
  environment. A process group reused by an unrelated process MUST NOT be signalled.

### Cancellation

- **BE-QUEUE-018** Cancelling a `waiting` job MUST set it `cancelled` at once (with
  `cancel_requested=true`, `finished_at`, message `Job cancelled.` or `Job cancelled by an
  administrator.`). If the worker claimed it in the meantime, the running path applies.
- **BE-QUEUE-019** Cancelling a `running` job MUST only set `cancel_requested=true` and add
  `Cancellation requested.` (or `… by an administrator.`) once. Within one tick the worker sends
  SIGTERM to the job's process group; after the grace period (default 10 s) it sends SIGKILL.
  When the step process has exited the job becomes `cancelled` with message `Job cancelled.`,
  whatever its exit code.
- **BE-QUEUE-020** A `waiting` job with `cancel_requested=true` MUST NOT be claimed; the worker sets
  it `cancelled` with `Job cancelled.`
- **BE-QUEUE-021** Cancelling a job in a final state MUST fail with 409, code `invalid_state`,
  message `The job is already <state>.`

### Failure while starting

- **BE-QUEUE-022** If the job's stored workflow snapshot does not parse, the job MUST become
  `failed` with `The workflow definition is invalid: <reason>`. Any other error while starting
  gives `The job could not be started: <reason>`; an unexpected error while polling gives
  `Internal error while running the job: <reason>` after the process group is stopped.
- **BE-QUEUE-023** If a claimed or running job's row is deleted (e.g. its user is deleted), the
  worker MUST kill the job's process group, wait for it to exit, remove the workspace and forget
  the job, logging at INFO without a traceback. For a deleted job that is not running, the web
  process removes the workspace after the transaction commits.

### Restart, delete, retention

- **BE-QUEUE-024** Admin restart MUST be allowed only for `failed`/`cancelled` jobs whose workspace is
  not purged or deleted (else 409 `invalid_state` / `workspace_removed`) and whose workflow is
  still installed and enabled (else 409 `workflow_unavailable`). It removes `output/`, `logs/`,
  `work/`, `.nextflow/`, all `*params.json` and `cloudgene.config`, keeps `input/`, deletes
  steps, messages and outputs, re-snapshots the current workflow YAML and app dir, and sets
  `waiting` with a new `submitted_at` (end of the queue).
- **BE-QUEUE-025** Delete MUST be allowed only for final-state jobs (else 409 `invalid_state`,
  `Only finished jobs can be deleted. Cancel the job first.`). It sets `deleted_at` and
  `purged_at`, removes output rows and the workspace; the row stays.
- **BE-QUEUE-026** Retention cleanup MUST only remove workspaces of final-state jobs (finished
  more than `server.job_retention_days` ago, or deleted), and of directories under `jobs/` named
  like a UUID that have no job row and are at least one hour old. It MUST NOT touch active jobs.
- **BE-QUEUE-027** (planned) Removing a job's workspace (delete, retention, vanish) MUST also
  remove its Nextflow work directory when `nextflow.work_dir` or a per-app `work_dir` places it
  outside the workspace.

## Interfaces

Command:

```
python manage.py run_worker [--once] [--interval 1.0] [--grace 10] [--timeout 3600]
```

Exit status: 0 on normal stop; 1 with `Another worker is already running for this
CLOUDGENE_HOME.` when the lock is held. Logger: `cloudgene.worker`.

Constants (`jobs/worker.py`): `CANCEL_GRACE_SECONDS = 10`, `ORPHAN_MESSAGE`, `SHUTDOWN_MESSAGE`,
`LOCK_RETRY_ATTEMPTS = 3`, `LOCK_RETRY_BACKOFF = 0.05`. `WorkerHeartbeat.STALE_AFTER = 30 s`.

Files: `CLOUDGENE_HOME/config/worker.lock`.

Python: `jobs.services.cancel_job(job, by_admin)`, `delete_job(job)`, `restart_job(job)`,
`queue_summary()` (`{paused, maintenance, running, waiting, max_running, max_queue}` for the
admin dashboard); errors are `JobActionError(message, code, status=409)`.

## Behaviour

State machine:

```
             claim                 last step rc=0
 waiting ──────────► running ──────────────────────► success
    │                  │  │ step fails / setup error / orphan / shutdown
    │ cancel           │  └──────────────────────────► failed ──┐
    ▼                  │ cancel_requested + group gone          │ admin restart
 cancelled ◄───────────┘                                        │ (not purged)
    └───────────────────────── admin restart ──────► waiting ◄──┘
```

Tick (default every 1 s): load settings (on error, defaults) → heartbeat → reconcile orphans →
poll each execution (vanished rows first, then progress, cancellation, exit) → cancel flagged
waiting jobs → claim `max_running_jobs − executions` jobs unless paused or stopping. A claimed
job is launched in the same tick; if its setup fails it is failed at once and does not hold a
slot.

The worker keeps its executions in memory only. Any restart therefore turns every `running` job
into an orphan, which BE-QUEUE-016 fails; jobs are never re-run automatically. Each step runs in
its own process group, so killing the worker (even SIGKILL) leaves Nextflow running until the next
worker kills it.

Retention interplay: `cleanup_jobs` (daily timer) only removes final-state workspaces and sets
`purged_at`; a purged job cannot be restarted. The worker removes a workspace only on vanish
(BE-QUEUE-023). A brand-new submission's directory without a row yet is protected by the one-hour
age rule.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| 001, 002, 003, 004 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_job_runs_to_success_with_progress_messages_and_outputs`, `WorkerFailureTest::test_failed_pipeline`, `WorkerCancelTest::test_cancel_running_kills_process_tree`; `jobs/tests/test_command_steps.py::CommandStepWorkerTest::test_failing_command_fails_job_with_exit_code_and_stderr_tail` | unit |
| 005 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_queue_positions` | unit |
| 006 | `jobs/tests/test_claim_concurrency.py::ClaimConcurrencyTest::test_two_concurrent_claims_never_take_the_same_job`, `::test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once` (Postgres only) | unit |
| 007, 009 | `jobs/tests/test_worker.py::WorkerQueueTest::test_max_running_and_queue_advances_without_requests`; `e2e/tests/test_queue.py::test_queue_limits_and_advances_after_cancel` | unit, e2e |
| 008 | `jobs/tests/test_worker.py::WorkerQueueTest::test_paused_queue_claims_nothing`; `e2e/tests/test_queue.py::test_pause_and_resume_queue` | unit, e2e |
| 010 | see [job-submission.md](job-submission.md#acceptance-tests) BE-JSUB-005 | — |
| 011, 015 | `jobs/tests/test_worker.py::RunWorkerCommandTest::test_once_and_single_instance_lock` | unit |
| 012 | `jobs/tests/test_worker.py::WorkerQueueTest::test_heartbeat` | unit |
| 013 | `jobs/tests/test_worker.py::TickPhaseIsolationTest` (both tests), `RetryOnLockedTest` (all tests) | unit |
| 014 | `jobs/tests/test_worker.py::ShutdownTest::test_shutdown_stops_running_jobs`; `run_worker` signal path: `jobs/tests/test_worker.py::RunWorkerCommandTest::test_sigterm_stops_gracefully` (planned) | unit |
| 016, 017 | `jobs/tests/test_worker.py::OrphanTest::test_orphan_running_job_is_failed_and_its_group_killed`, `::test_foreign_process_group_is_not_killed`; `e2e/tests/test_queue.py::test_worker_restart_fails_orphans_and_queue_continues` | unit, e2e |
| 018, 021, 025 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_waiting_and_delete_rules`; `e2e/tests/test_jobs.py::test_cancel_waiting_and_delete_finished` | unit, e2e |
| 019 | `jobs/tests/test_api.py::JobLifecycleApiTest::test_cancel_running_sets_flag`; `jobs/tests/test_worker.py::WorkerCancelTest::test_cancel_running_kills_process_tree`, `::test_sigkill_after_grace`; `e2e/tests/test_jobs.py::test_cancel_running_job_from_job_page` | unit, e2e |
| 020 | `jobs/tests/test_worker.py::WorkerCancelTest::test_waiting_cancel_race_handled_by_worker` | unit |
| 022 | `jobs/tests/test_worker.py::WorkerFailureTest::test_invalid_snapshot`; internal-error path: `jobs/tests/test_worker.py::WorkerFailureTest::test_poll_error_fails_job` (planned) | unit |
| 023 | `jobs/tests/test_worker.py::DeletedWhileRunningTest` (all tests); `jobs/tests/test_api.py::CleanupCommandTest::test_deleting_a_user_removes_job_workspaces` | unit |
| 024 | `jobs/tests/test_api.py::AdminJobsApiTest::test_restart`, `::test_restart_needs_enabled_workflow` | unit |
| 026 | `jobs/tests/test_api.py::CleanupCommandTest::test_retention` | unit |
| 027 | `jobs/tests/test_api.py::CleanupCommandTest::test_external_work_dir_removed` (planned) | unit |
| 028 | `jobs/tests/test_worker.py::WorkerSuccessTest::test_progress_bumps_updated_at` (planned): `updated_at` advances after a step start, a `processes` change and a new message | unit |

## Known gaps

| Req | What the code does | Where | Severity |
|-----|--------------------|-------|----------|
| BE-QUEUE-027 | With `nextflow.work_dir` or a per-app `work_dir` set, Nextflow work goes to `<work_dir>/<job uuid>`; delete, restart, retention and vanish only remove `CLOUDGENE_HOME/jobs/<uuid>`, so work directories (often the largest data) are never removed. | `jobs/runner.py:146-152`; `jobs/services.py:251`, `:267-268`; `jobs/management/commands/cleanup_jobs.py:341-348`; `jobs/worker.py:406` | major |
| BE-QUEUE-028 | During a run the worker updates `current_step` with `QuerySet.update()` (bypasses `auto_now`), saves step `processes` with `update_fields=['processes']` on the `JobStep` row, and adds messages with `bulk_create`; none of these touches `Job.updated_at`, which changes only on claim and finish. A poller comparing `updated_at` sees no change for the whole run. | `jobs/worker.py:219-220`, `jobs/worker.py:449-453`, `jobs/worker.py:191-199` | major |
| BE-QUEUE-011, 016 | The single-worker lock is a host-local `flock`. Two workers on different hosts sharing one database would each treat the other's running jobs as orphans and fail them every tick. | `jobs/worker.py:617-624`, `:807-823` | minor |
| BE-QUEUE-019 | When a running job finishes between the web process reading it and the cancel update, the update matches no row but `Cancellation requested.` is still added to a finished job. | `jobs/services.py:236-239` | minor |
| BE-QUEUE-014 | Shutdown stops running jobs one after another, each up to ~10 s (5 s grace + 5 s wait); with more than ~12 running jobs this exceeds `TimeoutStopSec=120` in `deploy/systemd/cloudgene-worker.service`, and systemd kills the worker mid-shutdown (jobs then recovered as orphans). | `jobs/worker.py:372-386`, `:798-801` | minor |
| BE-QUEUE-015 | `--once` installs no SIGTERM/SIGINT handler; a signal kills the worker without stopping its jobs (recovered later as orphans). | `jobs/management/commands/run_worker.py:286-288` | minor |
| BE-QUEUE-006 | The concurrency tests repeat the claim UPDATE instead of calling `Worker.claim`, and are skipped on SQLite (the default test database). | `jobs/tests/test_claim_concurrency.py:23-45` | minor |
| BE-QUEUE-014, 022 | No test drives `run_worker` with a real SIGTERM, or an exception inside `Execution.poll`. | `jobs/tests/test_worker.py` | minor |

## Open questions

- Should orphaned jobs (worker restart) be re-queued instead of failed when no step had started
  a process yet (e.g. a crash right after claim)?
- Should the web UI or the submit response warn when the worker heartbeat is stale, since jobs
  then wait with no visible reason?
- `management-commands.md` (CMD) also lists `run_worker` and `cleanup_jobs`; this file defines
  their job-state behaviour and CMD should link here rather than restate it.
