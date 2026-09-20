import hashlib
import secrets

from django.contrib.auth.models import AbstractUser, Group, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from . import validation


def hash_token(raw: str) -> str:
    """One-way hash for single-use secrets sent by e-mail (activation / password reset)."""
    return hashlib.sha256((raw or '').encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """``(raw, hashed)`` — the raw value goes into the e-mail link, only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


class UserManager(DjangoUserManager):
    """Case-insensitive username lookup (usernames are unique ignoring case, K1)."""

    def get_by_natural_key(self, username):
        return self.get(username__iexact=validation.normalize_username(username))

    @classmethod
    def normalize_email(cls, email):
        return validation.normalize_email(email)


class User(AbstractUser):
    """Cloudgene user.

    Username and e-mail are unique **ignoring case** (DB constraints on ``Lower(...)``);
    e-mail is stored lower-cased and stripped, username stripped (``save`` normalises).
    """

    full_name = models.CharField(max_length=255, blank=True, default='')
    # sha256 of the activation key sent by e-mail; kept after activation so that re-clicking
    # the link can answer "already activated" (see ``activated_at``).
    activation_key = models.CharField(max_length=255, blank=True, null=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    # sha256 of the single-use password reset token
    password_reset_token = models.CharField(max_length=255, blank=True, null=True)
    password_reset_expires = models.DateTimeField(null=True, blank=True)
    # login lockout (security.max_login_attempts / security.lockout_duration)
    locked_until = models.DateTimeField(null=True, blank=True)
    login_attempts = models.IntegerField(default=0)

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'full_name']

    class Meta:
        db_table = 'users'
        constraints = [
            models.UniqueConstraint(Lower('username'), name='users_username_ci_unique'),
            models.UniqueConstraint(Lower('email'), name='users_email_ci_unique'),
        ]

    def save(self, *args, **kwargs):
        self.username = validation.normalize_username(self.username)
        self.email = validation.normalize_email(self.email)
        super().save(*args, **kwargs)

    def has_group(self, group_name):
        return self.groups.filter(name=group_name).exists()

    def is_admin_user(self):
        """Single definition of admin: ``core.permissions.is_admin``."""
        from core.permissions import is_admin
        return is_admin(self)

    def make_admin(self):
        admin_group, _ = Group.objects.get_or_create(name='admin')
        self.groups.add(admin_group)
        self.is_staff = True
        self.save()

    def clean(self):
        super().clean()
        errors = {}
        for field, check in (('username', validation.validate_username),
                             ('email', validation.validate_email),
                             ('full_name', validation.validate_full_name)):
            message = check(getattr(self, field))
            if message:
                errors[field] = message
        if errors:
            raise ValidationError(errors)

    # Kept for callers of the old API; the rules live in accounts.validation.
    validate_username = staticmethod(validation.validate_username)
    validate_email = staticmethod(validation.validate_email)
    validate_password = staticmethod(validation.validate_password)
