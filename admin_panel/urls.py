from django.urls import path

from . import views

urlpatterns = [
    path('api/admin/dashboard/', views.DashboardView.as_view(), name='admin-dashboard'),
    path('api/admin/queue/pause/', views.QueuePauseView.as_view(), name='admin-queue-pause'),
    path('api/admin/queue/resume/', views.QueueResumeView.as_view(), name='admin-queue-resume'),
    path('api/admin/maintenance/enter/', views.MaintenanceEnterView.as_view(),
         name='admin-maintenance-enter'),
    path('api/admin/maintenance/exit/', views.MaintenanceExitView.as_view(),
         name='admin-maintenance-exit'),
    path('api/admin/settings/general/', views.GeneralSettingsView.as_view(),
         name='admin-settings-general'),
    path('api/admin/settings/mail/', views.MailSettingsView.as_view(),
         name='admin-settings-mail'),
    path('api/admin/settings/mail/test/', views.MailTestView.as_view(),
         name='admin-settings-mail-test'),
    path('api/admin/settings/nextflow/', views.NextflowSettingsView.as_view(),
         name='admin-settings-nextflow'),
    path('api/admin/settings/navbar/', views.NavbarSettingsView.as_view(),
         name='admin-settings-navbar'),
    path('api/admin/pages/', views.PageListView.as_view(), name='admin-pages'),
    path('api/admin/pages/<str:slug>/', views.PageDetailView.as_view(), name='admin-page'),
    path('api/admin/logs/', views.LogListView.as_view(), name='admin-logs'),
]
