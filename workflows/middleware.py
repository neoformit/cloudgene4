import logging

from . import registry

logger = logging.getLogger('cloudgene.workflows')


class WorkflowSyncMiddleware:
    """Lazily re-sync the workflow cache (``registry.sync_if_changed``) on API requests.

    Cheap when nothing changed (a few ``stat`` calls). Hand edits of settings.yaml ``apps[]``
    or of an installed cloudgene.yaml are therefore picked up by the next API request.
    Failures are logged and never break the request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            try:
                registry.sync_if_changed()
            except Exception:
                logger.exception('Workflow sync failed')
        return self.get_response(request)
