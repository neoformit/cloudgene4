from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import admin_views, views

router = DefaultRouter()
router.register(r'workflows', views.WorkflowViewSet, basename='workflow')
router.register(r'categories', views.WorkflowCategoryViewSet, basename='category')

urlpatterns = [
    path('api/', include(router.urls)),
    # Admin (T05) — workflows/admin_views.py
    path('api/admin/workflows/', admin_views.AdminWorkflowListView.as_view(),
         name='admin-workflow-list'),
    path('api/admin/workflows/install/', admin_views.AdminWorkflowInstallView.as_view(),
         name='admin-workflow-install'),
    path('api/admin/workflows/sync/', admin_views.AdminWorkflowSyncView.as_view(),
         name='admin-workflow-sync'),
    path('api/admin/workflows/<str:workflow_id>/', admin_views.AdminWorkflowDetailView.as_view(),
         name='admin-workflow-detail'),
    path('api/admin/workflows/<str:workflow_id>/reload/',
         admin_views.AdminWorkflowReloadView.as_view(), name='admin-workflow-reload'),
    path('api/admin/workflows/<str:workflow_id>/nextflow/',
         admin_views.AdminWorkflowNextflowView.as_view(), name='admin-workflow-nextflow'),
]
