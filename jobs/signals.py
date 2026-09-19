"""Remove a job's workspace when its row is deleted (e.g. cascade from a user deletion)."""
import shutil

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core import config as cloudgene_config

from .models import Job


@receiver(post_delete, sender=Job)
def remove_workspace(sender, instance, **kwargs):
    try:
        workspace = cloudgene_config.job_dir(instance.id)
    except ValueError:
        return
    transaction.on_commit(lambda: shutil.rmtree(workspace, ignore_errors=True))
