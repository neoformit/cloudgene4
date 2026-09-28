"""Remove a job's workspace when its row is deleted (e.g. cascade from a user deletion).

C-03: if the job was still running, its Nextflow process (and the worker still polling it)
keep writing into the workspace, so an rmtree run before that execution stops is undone —
the directory comes back with `work/`, `logs/`, `output/` and `.nextflow/` a moment later.
So a running job's process group is killed *before* the workspace is removed; the worker
notices the row is gone on its next poll and treats that as a designed shutdown path
(``jobs.worker.Execution.vanish`` — no traceback, see jobs/worker.py).
"""
import logging
import shutil
import time
from types import SimpleNamespace

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core import config as cloudgene_config

from .models import Job, JobState

logger = logging.getLogger('cloudgene.jobs')


@receiver(post_delete, sender=Job)
def remove_workspace(sender, instance, **kwargs):
    # Capture everything we need *now*: Django clears `instance.id` (the pk) once the whole
    # delete() call returns, well before an on_commit callback runs, and a bare "job_id=None"
    # would make kill_orphan_group's /proc match fail silently (nothing gets killed).
    job_id = instance.id
    status, pgid, pid = instance.status, instance.pgid, instance.pid
    try:
        workspace = cloudgene_config.job_dir(job_id)
    except ValueError:
        return

    def _cleanup():
        if status in JobState.ACTIVE and (pgid or pid):
            from .worker import kill_orphan_group  # local import: avoids a signals<->worker cycle
            killed = kill_orphan_group(SimpleNamespace(id=job_id, pgid=pgid, pid=pid))
            logger.info('Job %s deleted while %s: process group killed=%s', job_id, status, killed)
            if killed:
                time.sleep(0.5)   # let the OS finish tearing down the group before we rmtree
        shutil.rmtree(workspace, ignore_errors=True)

    transaction.on_commit(_cleanup)
