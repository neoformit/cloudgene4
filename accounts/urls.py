from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'groups', views.GroupViewSet, basename='group')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/auth/', include([
        path('login/', views.LoginView.as_view(), name='login'),
        path('logout/', views.LogoutView.as_view(), name='logout'),
        path('me/', views.MeView.as_view(), name='me'),
        path('register/', views.RegisterView.as_view(), name='register'),
        path('activate/<str:activation_key>/', views.ActivateAccountView.as_view(), name='activate_account'),
        path('password-reset/', views.PasswordResetView.as_view(), name='password_reset'),
        path('password-reset-confirm/<str:token>/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    ])),
]