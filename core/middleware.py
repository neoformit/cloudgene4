from django.urls import Resolver404, get_resolver

API_NOT_FOUND = 'api-not-found'  # url_name of the JSON 404 catch-all for /api/


def _resolves(resolver, path):
    try:
        match = resolver.resolve(path)
    except Resolver404:
        return False
    return match.url_name != API_NOT_FOUND


class ApiTrailingSlashMiddleware:
    """Accept ``/api/...`` paths with or without the trailing slash.

    Canonical API paths end with ``/`` (DRF router style, and what ``schema.yaml``
    documents). Clients may omit it: ``POST /api/auth/login`` is routed internally to
    ``/api/auth/login/`` instead of Django's APPEND_SLASH redirect (which cannot
    preserve a POST body).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith('/api/') and not path.endswith('/'):
            resolver = get_resolver()
            if not _resolves(resolver, path) and _resolves(resolver, path + '/'):
                request.path_info = path + '/'
                request.path = request.path + '/'
        return self.get_response(request)
