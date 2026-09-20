from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

admin_router = SimpleRouter()
admin_router.register(r'users', views.AdminUserViewSet, basename='admin-user')
admin_router.register(r'groups', views.AdminGroupViewSet, basename='admin-group')

urlpatterns = [
    path('api/auth/', include([
        path('login/', views.LoginView.as_view(), name='login'),
        path('logout/', views.LogoutView.as_view(), name='logout'),
        path('me/', views.MeView.as_view(), name='me'),
        path('register/', views.RegisterView.as_view(), name='register'),
        path('activate/<str:activation_key>/', views.ActivateAccountView.as_view(),
             name='activate_account'),
        path('password-reset/', views.PasswordResetView.as_view(), name='password_reset'),
        path('password-reset/<str:token>/', views.PasswordResetConfirmView.as_view(),
             name='password_reset_confirm'),
    ])),
    path('api/me/', views.ProfileView.as_view(), name='profile'),
    path('api/me/token/', views.ApiTokenView.as_view(), name='profile_token'),
    path('api/admin/', include(admin_router.urls)),
]
