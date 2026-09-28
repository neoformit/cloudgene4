import logging

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import config
from .exceptions import json_error
from .models import WorkerHeartbeat

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Liveness/readiness: database reachable + worker heartbeat.

    Returns 200 when the database is reachable (the worker being down is reported but
    does not make the web process unhealthy), 503 otherwise.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id='health',
        responses={
            (200, 'application/json'): inline_serializer('Health', {
                'status': serializers.ChoiceField(choices=['ok', 'degraded', 'error']),
                'db': inline_serializer('HealthDb', {'ok': serializers.BooleanField()}),
                'worker': inline_serializer('HealthWorker', {
                    'ok': serializers.BooleanField(),
                    'last_seen': serializers.DateTimeField(allow_null=True),
                    'age_seconds': serializers.FloatField(allow_null=True),
                    'pid': serializers.IntegerField(allow_null=True),
                }),
                'config': inline_serializer('HealthConfig', {
                    'ok': serializers.BooleanField(),
                    'errors': serializers.ListField(child=serializers.CharField()),
                }),
            }),
        },
    )
    def get(self, request):
        db_ok = True
        worker = {'ok': False, 'last_seen': None, 'age_seconds': None, 'pid': None}
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            worker = WorkerHeartbeat.status()
        except Exception:
            logger.exception('Health check: database error')
            db_ok = False
        cfg = config.config_status()
        cfg_errors = [f'{key}: {msg}' for key, msgs in cfg['errors'].items() for msg in msgs]
        if not db_ok:
            state = 'error'
        elif not worker['ok'] or not cfg['ok']:
            state = 'degraded'
        else:
            state = 'ok'
        if worker['last_seen'] is not None:
            worker['last_seen'] = worker['last_seen'].isoformat()
        return Response(
            {'status': state, 'db': {'ok': db_ok}, 'worker': worker,
             'config': {'ok': cfg['ok'], 'errors': cfg_errors}},
            status=200 if db_ok else 503,
        )


_MISSING_BUILD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Cloudgene</title></head>
<body style="font-family: sans-serif; margin: 3rem">
<h1>Cloudgene</h1>
<p>The frontend has not been built yet. Run:</p>
<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p>The API is available under <a href="/api/schema/swagger-ui/">/api/</a>.</p>
</body></html>
"""


@ensure_csrf_cookie
def spa_index(request, *args, **kwargs):
    """Serve the built SPA (static/frontend/index.html) for every non-API route.

    Sets the ``csrftoken`` cookie so the SPA can send ``X-CSRFToken``.
    """
    try:
        html = settings.SPA_INDEX_FILE.read_text(encoding='utf-8')
    except FileNotFoundError:
        return HttpResponse(_MISSING_BUILD, status=503)
    response = HttpResponse(html)
    response['Cache-Control'] = 'no-cache'
    return response


def api_not_found(request, *args, **kwargs):
    return json_error(request, 'Not found.', 'not_found', 404)


def csrf_failure(request, reason=''):
    """CSRF_FAILURE_VIEW: JSON envelope for API paths, plain text elsewhere."""
    if request.path.startswith('/api/'):
        return json_error(request, f'CSRF Failed: {reason}', 'csrf_failed', 403)
    return HttpResponse(f'CSRF verification failed: {reason}', status=403,
                        content_type='text/plain')
