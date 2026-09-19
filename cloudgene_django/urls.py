from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from core import views as core_views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/auth/token/', obtain_auth_token, name='api_token_auth'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(), name='swagger-ui'),
    path('', include('core.urls')),
    path('', include('accounts.urls')),
    path('', include('workflows.urls')),
    path('', include('jobs.urls')),
    path('', include('admin_panel.urls')),
    # Unknown /api/ paths → JSON 404 envelope (never the SPA)
    re_path(r'^api(/.*)?$', core_views.api_not_found, name='api-not-found'),
    # SPA catch-all — must be last; serves static/frontend/index.html
    re_path(r'^(?!static/)(?!django-admin/).*$', core_views.spa_index, name='spa'),
]
