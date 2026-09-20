from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.include_root_view = False
router.register(r'jobs', views.JobViewSet, basename='job')

admin_router = DefaultRouter()
admin_router.include_root_view = False
admin_router.register(r'jobs', views.AdminJobViewSet, basename='admin-job')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/admin/', include(admin_router.urls)),
]
