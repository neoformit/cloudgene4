"""Remove a job's workspace when its row is deleted (e.g. cascade from a user deletion).

C-03: the *worker* owns the workspace of any claimed job. Only the worker process actually
knows whether Nextflow is still writing into a running job's directory, so only it may stop
the execution and remove the workspace afterwards. Killing the process group from here (the
web process) assumed web and worker always share a host and could still race the worker's own
writes to the directory (an rmtree run before the execution has actually stopped is undone —
the directory comes back with `work/`, `logs/`, `output/` and `.nextflow/` a moment later); the
worker instead notices the row is gone the next time it tries to write to it (a 0-row update or
DoesNotExist/NotUpdated) and treats that as a designed shutdown path
(``jobs.worker.Execution.vanish`` — kills the process group, waits for it to exit, *then*
removes the workspace; no traceback, see jobs/worker.py). If the job was never claimed
(``JobState.WAITING``, or any already-finished state), nothing is running for it and the web
process removes the workspace immediately.
"""
import logging
import shutil

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core import config as cloudgene_config

from .models import Job, JobState

logger = logging.getLogger('cloudgene.jobs')


@receiver(post_delete, sender=Job)
def remove_workspace(sender, instance, **kwargs):
    # Capture everything we need *now*: Django clears `instance.id` (the pk) once the whole
    # delete() call returns, well before an on_commit callback runs.
    job_id, status = instance.id, instance.status
    try:
        workspace = cloudgene_config.job_dir(job_id)
    except ValueError:
        return

    def _cleanup():
        if status == JobState.RUNNING:
            # A worker may be executing it right now; only the worker may stop it and remove
            # the workspace (jobs.worker.Execution.vanish, triggered from poll_executions).
            logger.info('Job %s deleted while running: leaving the workspace for the worker '
                       'to remove once it stops the execution.', job_id)
            return
        # Never claimed (WAITING) or already finished: nothing is running for it, so it is
        # safe to remove the workspace right away.
        shutil.rmtree(workspace, ignore_errors=True)

    transaction.on_commit(_cleanup)
