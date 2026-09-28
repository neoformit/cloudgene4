"""
Global DRF exception handler producing the error envelope of plans/SPEC.md §3.5::

    {"error": {"message": str, "code": str, "fields": {field: [str, ...]}}}

``fields`` is always present (empty dict when not a validation error). Non-field
validation errors (``non_field_errors`` / ``detail``) become the message only.
"""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import RequestDataTooBig, SuspiciousOperation, TooManyFieldsSent, TooManyFilesSent
from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger('cloudgene.api')

NON_FIELD_KEYS = ('non_field_errors', 'detail', '__all__')


def error_body(message, code='error', fields=None):
    return {'error': {'message': str(message), 'code': str(code), 'fields': fields or {}}}


def error_response(message, code='error', status_code=400, fields=None, headers=None):
    """Build an envelope Response from inside a view (for errors not raised as exceptions)."""
    return Response(error_body(message, code, fields), status=status_code, headers=headers)


def _flatten(detail, prefix=''):
    """ErrorDetail tree -> {dotted.field: [messages]}."""
    out = {}
    if isinstance(detail, dict):
        for key, value in detail.items():
            name = f'{prefix}.{key}' if prefix else str(key)
            for k, v in _flatten(value, name).items():
                out.setdefault(k, []).extend(v)
    elif isinstance(detail, list):
        if all(not isinstance(item, (dict, list)) for item in detail):
            out[prefix] = [str(item) for item in detail]
        else:
            for i, item in enumerate(detail):
                name = f'{prefix}[{i}]' if prefix else f'[{i}]'
                for k, v in _flatten(item, name).items():
                    out.setdefault(k, []).extend(v)
    else:
        out[prefix] = [str(detail)]
    return out


def _first_code(detail):
    if isinstance(detail, dict):
        for value in detail.values():
            return _first_code(value)
    if isinstance(detail, list) and detail:
        return _first_code(detail[0])
    return getattr(detail, 'code', None)


def _validation_envelope(detail):
    flat = _flatten(detail)
    non_field = []
    for key in NON_FIELD_KEYS:
        non_field.extend(flat.pop(key, []))
    if '' in flat:
        non_field.extend(flat.pop(''))
    if non_field:
        message = non_field[0]
    elif flat:
        field, messages = next(iter(flat.items()))
        message = f'{field}: {messages[0]}' if messages else 'Invalid input.'
    else:
        message = 'Invalid input.'
    code = 'invalid' if flat else (_first_code(detail) or 'invalid')
    return error_body(message, code, flat)


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    # A-02: request parsing (accessing request.data/.FILES) can raise these Django
    # SuspiciousOperation subclasses before any DRF exception ever sees the request; without a
    # mapping here they fall through to the unhandled-error 500 below.
    if isinstance(exc, (TooManyFilesSent, TooManyFieldsSent)):
        logger.warning('Rejected oversized request: %s', exc)
        return Response(
            error_body('Too many files were included in this request.', 'upload_too_large'),
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if isinstance(exc, RequestDataTooBig):
        logger.warning('Rejected oversized request: %s', exc)
        return Response(
            error_body('The request is too large.', 'upload_too_large'),
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if isinstance(exc, SuspiciousOperation):
        logger.warning('Rejected suspicious request: %s', exc)
        return Response(error_body(str(exc) or 'Bad request.', 'invalid'),
                        status=status.HTTP_400_BAD_REQUEST)

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled error: log with traceback, never leak internals to the client.
        view = context.get('view')
        logger.exception('Unhandled API error in %s', view.__class__.__name__ if view else '?')
        return Response(
            error_body('Internal server error.', 'server_error'),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        response.data = _validation_envelope(exc.detail)
        return response

    detail = getattr(exc, 'detail', None)
    if isinstance(detail, (dict, list)):
        body = _validation_envelope(detail)
        body['error']['code'] = getattr(exc, 'default_code', body['error']['code'])
        response.data = body
        return response

    code = getattr(detail, 'code', None) or getattr(exc, 'default_code', 'error')
    message = str(detail) if detail is not None else str(exc)
    if isinstance(exc, exceptions.PermissionDenied) and message.startswith('CSRF Failed'):
        code = 'csrf_failed'
    response.data = error_body(message, code)
    return response


def json_error(request, message, code, status_code):
    """Plain-Django JSON error in the envelope format (for non-DRF views)."""
    return JsonResponse(error_body(message, code), status=status_code)
