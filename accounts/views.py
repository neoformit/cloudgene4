"""
Authentication and user management views
"""
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from core.exceptions import error_response
from core.serializers import MessageSerializer
from core.permissions import IsAdmin
from .serializers import (
    UserSerializer, UserRegistrationSerializer, GroupSerializer,
    LoginSerializer, PasswordResetSerializer
)

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user management
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_admin_user():
            return User.objects.all()
        return User.objects.filter(id=self.request.user.id)


class GroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for group management
    """
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        if self.request.user.is_admin_user():
            return Group.objects.all()
        return Group.objects.none()


class LoginView(APIView):
    """Session login for the SPA (CSRF enforced). Returns the serialized user.

    API clients should use a token (``Authorization: Token <key>``) instead.
    """
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer,
                   responses={200: inline_serializer('LoginResponse', {'user': UserSerializer()})})
    def post(self, request):
        # Anonymous requests are not CSRF-checked by SessionAuthentication; a login
        # form must be (login CSRF), so enforce it explicitly.
        SessionAuthentication().enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        login(request, user)
        return Response({'user': UserSerializer(user).data})


class LogoutView(APIView):
    """End the session. Always 200 (also when not logged in)."""
    permission_classes = [AllowAny]

    @extend_schema(request=None,
                   responses={200: MessageSerializer})
    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out.'})


class MeView(APIView):
    """Current user. Always 200: ``{"authenticated": false, "user": null}`` for anonymous."""
    permission_classes = [AllowAny]

    @extend_schema(responses={200: inline_serializer('Me', {
        'authenticated': serializers.BooleanField(),
        'user': UserSerializer(allow_null=True),
    })})
    def get(self, request):
        user = request.user
        if user is not None and user.is_authenticated:
            return Response({'authenticated': True, 'user': UserSerializer(user).data})
        return Response({'authenticated': False, 'user': None})


class RegisterView(APIView):
    """
    User registration view
    """
    permission_classes = [AllowAny]

    @extend_schema(request=UserRegistrationSerializer,
                   responses={201: inline_serializer('RegisterResponse', {
                       'user': UserSerializer(), 'message': serializers.CharField()})})
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            activation_url = request.build_absolute_uri(
                f'/activate/{user.activation_key}'
            )
            send_mail(
                subject='Activate your Cloudgene account',
                message=(
                    f'Hi {user.full_name or user.username},\n\n'
                    f'Click the link below to activate your account.\n\n'
                    f'{activation_url}\n\n'
                    f'If you did not register for Cloudgene, '
                    f'you can ignore this email.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            return Response({
                'user': UserSerializer(user).data,
                'message': (
                    'Registration successful. '
                    'Please check your email for activation instructions.'
                ),
            }, status=status.HTTP_201_CREATED)
        raise serializers.ValidationError(serializer.errors)


class ActivateAccountView(APIView):
    """
    Account activation view
    """
    permission_classes = [AllowAny]

    @extend_schema(responses={200: MessageSerializer})
    def get(self, request, activation_key):
        try:
            user = User.objects.get(
                activation_key=activation_key, is_active=False
            )
            user.is_active = True
            user.activation_key = None
            user.save()
            return Response({'message': 'Account activated successfully'})
        except User.DoesNotExist:
            return error_response('Invalid activation key.', 'invalid_activation_key')


class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetSerializer, responses={200: MessageSerializer})
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)

        import uuid
        user = User.objects.get(email=serializer.validated_data['email'])
        user.password_reset_token = str(uuid.uuid4())
        user.password_reset_expires = (
            timezone.now() + timezone.timedelta(hours=24)
        )
        user.save()

        reset_url = request.build_absolute_uri(
            f'/recover/{user.password_reset_token}'
        )
        send_mail(
            subject='Reset your Cloudgene password',
            message=(
                f'Hi {user.full_name or user.username},\n\n'
                f'Click the link below to reset your password. '
                f'This link expires in 24 hours.\n\n'
                f'{reset_url}\n\n'
                f'If you did not request a password reset, '
                f'you can ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return Response({'message': 'Password reset email sent'})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=inline_serializer('PasswordResetConfirm', {
        'password': serializers.CharField()}), responses={200: MessageSerializer})
    def post(self, request, token):
        try:
            user = User.objects.get(password_reset_token=token)
        except User.DoesNotExist:
            return error_response('Invalid or expired reset link.', 'invalid_token')

        if (
            user.password_reset_expires is None
            or timezone.now() > user.password_reset_expires
        ):
            return error_response('This reset link has expired.', 'expired_token')

        password = request.data.get('password', '')
        error = User.validate_password(password)
        if error:
            raise serializers.ValidationError({'password': [error]})

        user.set_password(password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.save()

        return Response({'message': 'Password reset successful'})
