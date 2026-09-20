import logging

from django.apps import AppConfig

logger = logging.getLogger('cloudgene.workflows')


def _prune_deleted_group(sender, instance, **kwargs):
    """A deleted group loses access everywhere: drop its name from settings.yaml apps[].groups."""
    from . import registry
    try:
        registry.prune_group(instance.name)
    except Exception:  # never block the delete (e.g. unreadable settings.yaml)
        logger.exception('Could not remove group %s from workflow access lists', instance.name)


class WorkflowsConfig(AppConfig):
    name = 'workflows'

    def ready(self):
        # Signal wiring only; the registry is synced lazily (never here — unsafe during migrate).
        from django.contrib.auth.models import Group
        from django.db.models.signals import post_delete
        post_delete.connect(_prune_deleted_group, sender=Group,
                            dispatch_uid='workflows.prune_deleted_group')
