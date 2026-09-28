import os

from django.urls import Resolver404, get_resolver

from core.exceptions import error_body
from django.http import JsonResponse

API_NOT_FOUND = 'api-not-found'  # url_name of the JSON 404 catch-all for /api/

# QA_FINDINGS I-4: DATA_UPLOAD_MAX_MEMORY_SIZE only rejects a JSON/urlencoded body *after*
# reading it all into memory (Django's HttpRequest.body checks the limit once the full body has
# been read), so an oversized non-multipart API body still costs a full read (~2.7s for 11 MB on
# this host) before being rejected. Multipart uploads are unaffected (streamed, bounded by
# server.max_upload_mb in jobs/submission.py) and are exempted below.
JSON_BODY_MAX_BYTES = int(os.environ.get('API_JSON_BODY_MAX_MB', '10')) * 1024 * 1024


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


class JsonBodySizeLimitMiddleware:
    """Reject an oversized non-multipart ``/api/`` request body by ``Content-Length`` alone,
    before Django reads it into memory (QA_FINDINGS I-4). Multipart (file upload) requests are
    exempt — those are streamed and bounded by ``server.max_upload_mb`` elsewhere."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('/api/'):
            content_type = request.META.get('CONTENT_TYPE', '')
            if 'multipart/form-data' not in content_type:
                try:
                    length = int(request.META.get('CONTENT_LENGTH') or 0)
                except (TypeError, ValueError):
                    length = 0
                if length > JSON_BODY_MAX_BYTES:
                    return JsonResponse(
                        error_body(
                            'The request body is too large (max %d MB).'
                            % (JSON_BODY_MAX_BYTES // (1024 * 1024)),
                            'upload_too_large',
                        ),
                        status=413,
                    )
        return self.get_response(request)
