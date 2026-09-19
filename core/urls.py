from django.urls import path

from . import views

urlpatterns = [
    path('api/health/', views.HealthView.as_view(), name='health'),
]
