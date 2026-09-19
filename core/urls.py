from django.urls import path

from . import server_views, views

urlpatterns = [
    path('api/health/', views.HealthView.as_view(), name='health'),
    path('api/server/', server_views.ServerInfoView.as_view(), name='server-info'),
    path('api/pages/<str:slug>/', server_views.PublicPageView.as_view(), name='page'),
]
