"""
Serializers for account endpoints (SPEC §3.4, §3.6).

Privilege fields (``is_staff``, ``is_superuser``, ``is_active``, ``groups``, ``username``) are
never writable by the user themselves (A7): self-service serializers only declare the fields
they accept, unknown input keys are ignored.
"""
from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from core.permissions import ADMIN_GROUP

from . import validation
from .models import User

MSG_USERNAME_TAKEN = 'This username is already taken.'
MSG_EMAIL_TAKEN = 'This e-mail address is already registered.'


def _check(rule, value):
    """Raise a field ValidationError with the message of an ``accounts.validation`` rule."""
    message = rule(value)
    if message:
        raise serializers.ValidationError(message)


def username_taken(username, exclude_pk=None) -> bool:
    qs = User.objects.filter(username__iexact=validation.normalize_username(username))
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def email_taken(email, exclude_pk=None) -> bool:
    qs = User.objects.filter(email__iexact=validation.normalize_email(email))
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


class GroupNamesField(serializers.ListField):
    """Group membership as a list of group names (sorted)."""

    child = serializers.CharField()

    def to_representation(self, value):
        return sorted(g.name for g in value.all())


class UserSerializer(serializers.ModelSerializer):
    """The user as seen by themselves (login, /auth/me, /me)."""

    groups = GroupNamesField(read_only=True)
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'is_active', 'is_admin',
            'groups', 'date_joined', 'last_login',
        ]
        read_only_fields = fields

    def get_is_admin(self, obj) -> bool:
        # Same rule as core.permissions.is_admin, but uses prefetched groups (admin list).
        if obj.is_superuser or obj.is_staff:
            return True
        return any(g.name == ADMIN_GROUP for g in obj.groups.all())


class ProfileSerializer(UserSerializer):
    """``GET /api/me`` — the user plus API-token metadata (never the key itself)."""

    api_token = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['api_token']
        read_only_fields = fields

    @extend_schema_field({'type': 'object', 'nullable': True,
                          'properties': {'created': {'type': 'string', 'format': 'date-time'}}})
    def get_api_token(self, obj):
        token = Token.objects.filter(user=obj).first()
        return {'created': serializers.DateTimeField().to_representation(token.created)} if token else None


class ProfileUpdateSerializer(serializers.Serializer):
    """``PATCH /api/me``. Changing ``email`` or ``password`` requires ``current_password``."""

    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, write_only=True, trim_whitespace=False,
                                     allow_blank=True)
    password_confirm = serializers.CharField(required=False, write_only=True,
                                             trim_whitespace=False, allow_blank=True)
    current_password = serializers.CharField(required=False, write_only=True,
                                             trim_whitespace=False, allow_blank=True)

    def validate_full_name(self, value):
        _check(validation.validate_full_name, value)
        return value.strip()

    def validate_email(self, value):
        _check(validation.validate_email, value)
        value = validation.normalize_email(value)
        if email_taken(value, exclude_pk=self.instance.pk):
            raise serializers.ValidationError(MSG_EMAIL_TAKEN)
        return value

    def validate(self, data):
        user = self.instance
        errors = {}
        password = data.get('password')
        if password:
            message = validation.validate_password(password, data.get('password_confirm'))
            if message:
                errors['password'] = [message]
        elif 'password' in data:
            data.pop('password')  # blank = "don't change"
        changes_email = 'email' in data and data['email'] != user.email
        if (data.get('password') or changes_email):
            current = data.get('current_password') or ''
            if not current:
                errors['current_password'] = ['Please enter your current password.']
            elif not user.check_password(current):
                errors['current_password'] = ['Your current password is not correct.']
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def update(self, user, data):
        if 'full_name' in data:
            user.full_name = data['full_name'].strip()
        if 'email' in data:
            user.email = data['email']
        if data.get('password'):
            user.set_password(data['password'])
        user.save()
        return user


class RegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    full_name = serializers.CharField(allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, allow_blank=True)
    # Optional — clients that confirm locally need not send it
    password_confirm = serializers.CharField(write_only=True, required=False,
                                             allow_blank=True, trim_whitespace=False)

    def validate_username(self, value):
        _check(validation.validate_username, value)
        value = validation.normalize_username(value)
        if username_taken(value):
            raise serializers.ValidationError(MSG_USERNAME_TAKEN)
        return value

    def validate_full_name(self, value):
        _check(validation.validate_full_name, value)
        return value.strip()

    def validate_email(self, value):
        _check(validation.validate_email, value)
        value = validation.normalize_email(value)
        if email_taken(value):
            raise serializers.ValidationError(MSG_EMAIL_TAKEN)
        return value

    def validate_password(self, value):
        # Checked per field (not in validate()) so that all field errors are reported at once.
        confirm = self.initial_data.get('password_confirm')
        _check(lambda v: validation.validate_password(v, confirm or None), value)
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False, allow_blank=True)
    password_confirm = serializers.CharField(required=False, allow_blank=True,
                                             trim_whitespace=False)

    def validate(self, data):
        message = validation.validate_password(data['password'], data.get('password_confirm'))
        if message:
            raise serializers.ValidationError({'password': [message]})
        return data


class PasswordSerializer(serializers.Serializer):
    """Confirmation for destructive self-service actions (``DELETE /api/me``)."""

    password = serializers.CharField(trim_whitespace=False)


class ApiTokenSerializer(serializers.Serializer):
    """``POST /api/me/token`` — the key is only ever returned here, once."""

    token = serializers.CharField(source='key')
    created = serializers.DateTimeField()


# --- Admin ---------------------------------------------------------------------------------

class AdminUserSerializer(UserSerializer):
    """Row of ``GET /api/admin/users``."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['is_superuser', 'activated_at']
        read_only_fields = fields


class AdminUserUpdateSerializer(serializers.Serializer):
    """``PATCH /api/admin/users/{id}``.

    ``groups`` is the complete list of group **names** (replaces membership). The ``admin``
    group is not managed through ``groups`` (it is ignored there and kept as is) — use
    ``is_admin``, which adds/removes the ``admin`` group and ``is_staff`` together.
    """

    groups = serializers.ListField(child=serializers.CharField(), required=False)
    is_active = serializers.BooleanField(required=False)
    is_admin = serializers.BooleanField(required=False)

    def validate_groups(self, names):
        names = sorted({n.strip() for n in names if n.strip()} - {ADMIN_GROUP})
        found = {g.name: g for g in Group.objects.filter(name__in=names)}
        missing = [n for n in names if n not in found]
        if missing:
            raise serializers.ValidationError(f'Unknown group(s): {", ".join(missing)}.')
        return [found[n] for n in names]

    def validate(self, data):
        user = self.instance
        actor = self.context['request'].user
        errors = {}
        if user.pk == actor.pk:
            if data.get('is_active') is False:
                errors['is_active'] = ['You cannot deactivate your own account.']
            if data.get('is_admin') is False:
                errors['is_admin'] = ['You cannot remove your own administrator rights.']
        if data.get('is_admin') is False and user.is_superuser:
            errors['is_admin'] = ['Superusers are always administrators.']
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def update(self, user, data):
        if 'groups' in data:
            keep = list(user.groups.filter(name=ADMIN_GROUP))
            user.groups.set(keep + data['groups'])
        if 'is_active' in data:
            user.is_active = data['is_active']
            if user.is_active:
                user.login_attempts = 0
                user.locked_until = None
        if 'is_admin' in data:
            admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
            if data['is_admin']:
                user.groups.add(admin_group)
                user.is_staff = True
            else:
                user.groups.remove(admin_group)
                user.is_staff = False
        user.save()
        return user


class AdminGroupSerializer(serializers.ModelSerializer):
    """``/api/admin/groups`` — name unique ignoring case; ``member_count`` read-only."""

    name = serializers.CharField(allow_blank=True)
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'member_count']

    def validate_name(self, value):
        _check(validation.validate_group_name, value)
        value = value.strip()
        if Group.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError('A group with this name already exists.')
        return value
