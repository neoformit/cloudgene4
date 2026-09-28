"""
Accounts: session auth, registration/activation, password reset, profile, API token,
and the admin user/group endpoints (SPEC §3.4, §3.6).
"""
import logging
import math
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import config
from core.exceptions import error_response
from core.mail import send_mail
from core.permissions import ADMIN_GROUP, IsAdmin, is_admin
from core.serializers import MessageSerializer

from . import validation
from .models import User, hash_token, new_token
from .serializers import (
    MSG_EMAIL_TAKEN, MSG_USERNAME_TAKEN,
    AdminGroupSerializer, AdminUserSerializer, AdminUserUpdateSerializer, ApiTokenSerializer,
    LoginSerializer, PasswordResetConfirmSerializer, PasswordResetRequestSerializer,
    PasswordSerializer, ProfileSerializer, ProfileUpdateSerializer, RegistrationSerializer,
    UserSerializer,
)

logger = logging.getLogger('cloudgene.accounts')

PASSWORD_RESET_HOURS = 24
MSG_INVALID_LOGIN = 'Invalid username or password.'
MSG_RESET_REQUESTED = ('If an account with this e-mail address exists, '
                       'we have sent a link to reset the password.')


def absolute_url(request, path):
    """Link for e-mails: ``server.url`` if configured, else the request's host."""
    base = (config.get('server.url') or '').rstrip('/')
    return f'{base}{path}' if base else request.build_absolute_uri(path)


def server_name():
    return config.get('server.name') or 'Cloudgene'


# --- Session ---------------------------------------------------------------------------------

class LoginView(APIView):
    """Session login for the SPA (CSRF enforced). Returns the serialized user.

    Failed logins are counted per user; after ``security.max_login_attempts`` failures the
    account is locked for ``security.lockout_duration`` seconds (429, code ``account_locked``).
    Unknown usernames and wrong passwords get the same message. API clients use a token
    (``Authorization: Token <key>``, created on the profile page) instead.

    The lockout itself lives in ``accounts.backends.LockoutModelBackend`` plus the
    ``user_login_failed``/``user_logged_in`` signal receivers (B-01), so it also applies to
    ``/django-admin/login/`` and anything else that calls ``django.contrib.auth.authenticate()``
    — this view only turns the outcome into the SPEC §3.4 error envelope.
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
        username = validation.normalize_username(serializer.validated_data['username'])
        password = serializer.validated_data['password']

        user = authenticate(request, username=username, password=password)
        if user is None:
            # authenticate() already counted this failure (and locked the account if it hit
            # the threshold) via the user_login_failed signal; look the account back up only
            # to word the response (locked vs. plain invalid credentials).
            existing = User.objects.filter(username__iexact=username).first()
            if existing is not None and existing.locked_until:
                existing.refresh_from_db(fields=['locked_until'])
                now = timezone.now()
                if existing.locked_until and existing.locked_until > now:
                    return self._locked(existing, now)
            logger.info('Login failed: invalid credentials for %r', username)
            return error_response(MSG_INVALID_LOGIN, 'invalid_credentials')

        if not user.is_active:
            return error_response(
                'Your account is not active. Please use the activation link we sent you by '
                'e-mail, or contact the administrator.', 'account_inactive', status.HTTP_403_FORBIDDEN)

        login(request, user)  # also updates last_login and resets the lockout counter
        logger.info('Login: %s', user.username)
        return Response({'user': UserSerializer(user).data})

    @staticmethod
    def _locked(user, now):
        seconds = max(1, int((user.locked_until - now).total_seconds()))
        minutes = math.ceil(seconds / 60)
        return error_response(
            f'Too many failed logins. The account is locked for {minutes} '
            f'minute{"s" if minutes != 1 else ""}.',
            'account_locked', status.HTTP_429_TOO_MANY_REQUESTS,
            headers={'Retry-After': str(seconds)})


class LogoutView(APIView):
    """End the session. Always 200 (also when not logged in)."""
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: MessageSerializer})
    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out.'})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    """Current user. Always 200: ``{"authenticated": false, "user": null}`` for anonymous.

    Also sets the ``csrftoken`` cookie (needed when the SPA is served by the Vite dev server).
    """
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


# --- Registration & activation ----------------------------------------------------------------

class RegisterView(APIView):
    """Create an account.

    With ``security.require_activation`` (default) the account is inactive until the link
    from the activation e-mail is used; otherwise it is active immediately and no mail is
    sent. Usernames and e-mails are unique ignoring case.
    """
    permission_classes = [AllowAny]

    @extend_schema(request=RegistrationSerializer,
                   responses={201: inline_serializer('RegisterResponse', {
                       'user': UserSerializer(), 'message': serializers.CharField(),
                       'activation_required': serializers.BooleanField()})})
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        require_activation = bool(config.get('security.require_activation', True))
        raw_key = None
        try:
            with transaction.atomic():
                user = User(username=data['username'], email=data['email'],
                            full_name=data['full_name'])
                user.set_password(data['password'])
                if require_activation:
                    raw_key, user.activation_key = new_token()
                    user.is_active = False
                else:
                    user.is_active = True
                    user.activated_at = timezone.now()
                user.save()
                if require_activation:
                    self._send_activation(request, user, raw_key)
        except IntegrityError:
            # Lost a race against a concurrent registration with the same name/e-mail.
            fields = {}
            if User.objects.filter(username__iexact=data['username']).exists():
                fields['username'] = [MSG_USERNAME_TAKEN]
            if User.objects.filter(email__iexact=data['email']).exists():
                fields['email'] = [MSG_EMAIL_TAKEN]
            raise serializers.ValidationError(fields or {'username': [MSG_USERNAME_TAKEN]})
        except MailError:
            return error_response(
                'We could not send the activation e-mail. Please try again later.',
                'mail_failed', status.HTTP_503_SERVICE_UNAVAILABLE)

        logger.info('Registered user %s (activation %s)', user.username,
                    'pending' if require_activation else 'not required')
        if require_activation:
            message = ('Well done! An e-mail with the activation link has been sent to '
                       'your address.')
        else:
            message = 'Well done! Your account has been created. You can log in now.'
        return Response({'user': UserSerializer(user).data, 'message': message,
                         'activation_required': require_activation},
                        status=status.HTTP_201_CREATED)

    @staticmethod
    def _send_activation(request, user, raw_key):
        name = server_name()
        link = absolute_url(request, f'/activate/{raw_key}')
        try:
            send_mail(
                f'[{name}] Activate your account',
                f'Dear {user.full_name or user.username},\n\n'
                f'thank you for signing up for {name}. Please click the link below to activate '
                f'your account (username: {user.username}).\n\n{link}\n\n'
                f'If you did not sign up, you can ignore this e-mail.\n',
                [user.email])
        except Exception as exc:  # SMTP/file errors
            logger.exception('Activation mail to %s failed', user.email)
            raise MailError() from exc


class MailError(Exception):
    pass


class ActivateAccountView(APIView):
    """Activate an account with the key from the e-mail. Idempotent: using the link again
    after activation answers 200 with ``status: "already_active"``."""
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: inline_serializer('ActivateResponse', {
        'message': serializers.CharField(),
        'status': serializers.ChoiceField(choices=['activated', 'already_active']),
    })})
    def post(self, request, activation_key):
        user = User.objects.filter(activation_key=hash_token(activation_key)).first()
        if user is None:
            return error_response(
                'This activation link is not valid. Please check that you copied the complete '
                'link from the e-mail.', 'invalid_activation_key')
        if user.activated_at is not None:
            return Response({'status': 'already_active',
                             'message': 'Your account is already activated. You can log in.'})
        user.is_active = True
        user.activated_at = timezone.now()
        user.save(update_fields=['is_active', 'activated_at'])
        logger.info('Activated user %s', user.username)
        return Response({'status': 'activated',
                         'message': 'Your account has been activated. You can log in now.'})


# --- Password reset -----------------------------------------------------------------------------

class PasswordResetView(APIView):
    """Request a reset link. Always the same 200 answer (does not reveal whether the e-mail
    is registered). Links are single-use and expire after 24 h; only a hash is stored."""
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetRequestSerializer, responses={200: MessageSerializer})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = validation.normalize_email(serializer.validated_data['email'])
        user = User.objects.filter(email__iexact=email, is_active=True).first() if email else None
        if user is not None:
            raw, hashed = new_token()
            user.password_reset_token = hashed
            user.password_reset_expires = timezone.now() + timedelta(hours=PASSWORD_RESET_HOURS)
            user.save(update_fields=['password_reset_token', 'password_reset_expires'])
            name = server_name()
            link = absolute_url(request, f'/recover/{raw}')
            try:
                send_mail(
                    f'[{name}] Reset your password',
                    f'Dear {user.full_name or user.username},\n\n'
                    f'a password reset was requested for your {name} account '
                    f'(username: {user.username}). Click the link below to choose a new password. '
                    f'The link can be used once and expires in {PASSWORD_RESET_HOURS} hours.\n\n'
                    f'{link}\n\nIf you did not request this, you can ignore this e-mail.\n',
                    [user.email])
            except Exception:
                # Do not reveal the failure (it would reveal that the address exists).
                logger.exception('Password reset mail to %s failed', user.email)
            logger.info('Password reset requested for %s', user.username)
        else:
            logger.info('Password reset requested for unknown/inactive e-mail')
        return Response({'message': MSG_RESET_REQUESTED})


class PasswordResetConfirmView(APIView):
    """Set a new password with a reset token (single use)."""
    permission_classes = [AllowAny]

    @extend_schema(operation_id='auth_password_reset_confirm',
                   request=PasswordResetConfirmSerializer, responses={200: MessageSerializer})
    def post(self, request, token):
        user = User.objects.filter(password_reset_token=hash_token(token)).first()
        if user is None:
            return error_response(
                'This reset link is invalid or has already been used. Please request a new one.',
                'invalid_token')
        if user.password_reset_expires is None or timezone.now() > user.password_reset_expires:
            return error_response('This reset link has expired. Please request a new one.',
                                  'expired_token')
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['password'])
        user.password_reset_token = None
        user.password_reset_expires = None
        user.login_attempts = 0
        user.locked_until = None
        user.save()
        # B-02: a credential created before the reset must not survive it.
        Token.objects.filter(user=user).delete()
        logger.info('Password reset completed for %s', user.username)
        return Response({'message': 'Your password has been changed. You can log in now.'})


# --- Profile ------------------------------------------------------------------------------------

def _other_admins_exist(user) -> bool:
    return User.objects.filter(is_active=True).exclude(pk=user.pk).filter(
        Q(is_superuser=True) | Q(is_staff=True) | Q(groups__name=ADMIN_GROUP)).exists()


class ProfileView(APIView):
    """``/api/me``: own profile. PATCH ``full_name``, ``email``, ``password`` (+ optional
    ``password_confirm``); changing e-mail or password requires ``current_password``.
    DELETE deletes the account (body ``{"password"}``) and ends the session."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ProfileSerializer})
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    @extend_schema(request=ProfileUpdateSerializer, responses={200: ProfileSerializer})
    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({'email': [MSG_EMAIL_TAKEN]})
        if serializer.validated_data.get('password'):
            if isinstance(request.successful_authenticator, SessionAuthentication):
                # Keep this session valid after the password hash changed (others are logged out).
                update_session_auth_hash(request._request, user)
            # B-02: a credential created before the password change must not survive it.
            Token.objects.filter(user=user).delete()
        return Response(ProfileSerializer(user).data)

    @extend_schema(request=PasswordSerializer, responses={200: MessageSerializer})
    def delete(self, request):
        serializer = PasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['password']):
            raise serializers.ValidationError({'password': ['Your password is not correct.']})
        if is_admin(user) and not _other_admins_exist(user):
            return error_response('You are the only administrator; this account cannot be '
                                  'deleted.', 'last_admin')
        username = user.username
        logout(request)
        user.delete()
        logger.info('User %s deleted their account', username)
        return Response({'message': 'Your account has been deleted.'})


class ApiTokenView(APIView):
    """``/api/me/token``: POST creates (or regenerates) the API token and returns the key
    once; DELETE revokes it."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: ApiTokenSerializer})
    def post(self, request):
        with transaction.atomic():
            Token.objects.filter(user=request.user).delete()
            token = Token.objects.create(user=request.user)
        logger.info('API token created for %s', request.user.username)
        return Response(ApiTokenSerializer(token).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: MessageSerializer})
    def delete(self, request):
        deleted, _ = Token.objects.filter(user=request.user).delete()
        if deleted:
            logger.info('API token revoked for %s', request.user.username)
        return Response({'message': 'API token revoked.' if deleted else 'No API token.'})


# --- Admin --------------------------------------------------------------------------------------

@extend_schema(parameters=[
    OpenApiParameter('search', OpenApiTypes.STR, description='Username, e-mail or full name contains'),
    OpenApiParameter('group', OpenApiTypes.STR, description='Only members of this group (name)'),
    OpenApiParameter('is_active', OpenApiTypes.BOOL),
])
class AdminUserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                       viewsets.GenericViewSet):
    """Admin user management. PATCH ``{groups: [names], is_active, is_admin}``."""
    permission_classes = [IsAdmin]
    serializer_class = AdminUserSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = User.objects.prefetch_related('groups').order_by('username')
        if self.action != 'list':
            return qs
        params = self.request.query_params
        search = (params.get('search') or '').strip()
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search)
                           | Q(full_name__icontains=search))
        group = (params.get('group') or '').strip()
        if group:
            qs = qs.filter(groups__name=group)
        active = params.get('is_active')
        if active in ('true', 'false', '1', '0'):
            qs = qs.filter(is_active=active in ('true', '1'))
        return qs.distinct()

    @extend_schema(request=AdminUserUpdateSerializer, responses={200: AdminUserSerializer})
    def partial_update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True,
                                               context={'request': request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
        logger.info('Admin %s updated user %s: %s', request.user.username, user.username,
                    {k: (sorted(g.name for g in v) if k == 'groups' else v)
                     for k, v in serializer.validated_data.items()})
        user = self.get_queryset().get(pk=user.pk)
        return Response(AdminUserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            return error_response('You cannot delete your own account here; use your profile.',
                                  'cannot_delete_self')
        username = user.username
        user.delete()
        logger.info('Admin %s deleted user %s', request.user.username, username)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminGroupViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                        mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Groups (for workflow access). List is **not paginated** (a plain array)."""
    permission_classes = [IsAdmin]
    serializer_class = AdminGroupSerializer
    pagination_class = None

    def get_queryset(self):
        return Group.objects.annotate(member_count=Count('user', distinct=True)).order_by('name')

    def perform_create(self, serializer):
        group = serializer.save()
        group.member_count = 0
        logger.info('Admin %s created group %s', self.request.user.username, group.name)

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        if group.name == ADMIN_GROUP:
            return error_response('The admin group cannot be deleted.', 'protected_group')
        name = group.name
        group.delete()
        logger.info('Admin %s deleted group %s', request.user.username, name)
        return Response(status=status.HTTP_204_NO_CONTENT)
