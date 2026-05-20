from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from rest_framework.authtoken.views import obtain_auth_token
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/auth/token/', obtain_auth_token, name='api_token_auth'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(), name='swagger-ui'),
    path('', include('accounts.urls')),
    path('', include('workflows.urls')),
    path('', include('jobs.urls')),
    path('', include('admin_panel.urls')),
    # SPA catch-all — must be last; serves frontend/index.html for all non-API routes
    re_path(r'^(?!api/)(?!static/).*$', TemplateView.as_view(template_name='index.html')),
]
