"""Shared serializers / schema helpers (plans/SPEC.md §3.5)."""
from rest_framework import serializers


class MessageSerializer(serializers.Serializer):
    """``{"message": str}`` — generic success payload."""

    message = serializers.CharField()


ERROR_SCHEMA = {
    'type': 'object',
    'required': ['error'],
    'properties': {
        'error': {
            'type': 'object',
            'required': ['message', 'code', 'fields'],
            'properties': {
                'message': {'type': 'string'},
                'code': {'type': 'string'},
                'fields': {
                    'type': 'object',
                    'additionalProperties': {'type': 'array', 'items': {'type': 'string'}},
                },
            },
        },
    },
}


def add_error_envelope(result, generator, request, public):
    """drf-spectacular postprocessing hook: document the error envelope on every operation."""
    result.setdefault('components', {}).setdefault('schemas', {})['Error'] = ERROR_SCHEMA
    ref = {'$ref': '#/components/schemas/Error'}
    for path_item in result.get('paths', {}).values():
        for method, operation in path_item.items():
            if method not in ('get', 'post', 'put', 'patch', 'delete'):
                continue
            operation.setdefault('responses', {}).setdefault('default', {
                'description': 'Error envelope (SPEC §3.5)',
                'content': {'application/json': {'schema': ref}},
            })
    return result
