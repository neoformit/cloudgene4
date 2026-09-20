"""
Public server endpoints (SPEC §3.6, owned by T05):

    GET /api/server/        name, url, maintenance, navbar (filtered for the viewer), footer_html
    GET /api/pages/{slug}/  {slug, html} from $CLOUDGENE_HOME/pages/<slug>.html
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import config
from .exceptions import error_response
from .permissions import is_admin


class ServerNavbarItemSerializer(serializers.Serializer):
    title = serializers.CharField()
    url = serializers.CharField()
    icon = serializers.CharField(allow_blank=True)
    admin_only = serializers.BooleanField()
    auth_only = serializers.BooleanField()


class ServerInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.CharField(allow_blank=True)
    maintenance = serializers.BooleanField()
    maintenance_message = serializers.CharField(allow_blank=True)
    navbar = ServerNavbarItemSerializer(many=True)
    footer_html = serializers.CharField(allow_blank=True)


class PublicPageSerializer(serializers.Serializer):
    slug = serializers.CharField()
    html = serializers.CharField(allow_blank=True)


def visible_navbar(items, user):
    authenticated = bool(user and user.is_authenticated)
    admin = is_admin(user)
    out = []
    for item in items:
        if item.get('admin_only') and not admin:
            continue
        if item.get('auth_only') and not authenticated:
            continue
        out.append({k: item.get(k, d) for k, d in (('title', ''), ('url', ''), ('icon', ''),
                                                   ('admin_only', False), ('auth_only', False))})
    return out


class ServerInfoView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(operation_id='server_info', responses=ServerInfoSerializer)
    def get(self, request):
        settings = config.load_settings()
        server = settings['server']
        return Response({
            'name': server['name'],
            'url': server['url'],
            'maintenance': server['maintenance'],
            'maintenance_message': server['maintenance_message'],
            'navbar': visible_navbar(settings['navbar'], request.user),
            'footer_html': config.read_page('footer') or '',
        })


class PublicPageView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(operation_id='pages_retrieve', responses=PublicPageSerializer)
    def get(self, request, slug):
        try:
            html = config.read_page(slug)
        except ValueError:  # unsafe slug (traversal etc.) — same answer as a missing page
            html = None
        if html is None:
            return error_response('Page not found.', 'not_found', 404)
        return Response({'slug': slug, 'html': html})
