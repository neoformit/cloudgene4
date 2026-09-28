"""Authentication shared by every login surface — the SPA API *and* the Django admin (B-01).

Before this, the lockout (``security.max_login_attempts`` / ``security.lockout_duration``) was
implemented only inside ``accounts.views.LoginView``, so ``/django-admin/login/`` (which calls
Django's own ``authenticate()``) never saw it: a locked account's correct password still worked
there, and its wrong passwords never counted.

``LockoutModelBackend`` is now the sole entry in ``AUTHENTICATION_BACKENDS``, so *every* call to
``django.contrib.auth.authenticate()`` — the SPA's ``LoginView`` included — goes through it:

- while an account is locked, the backend refuses it outright, correct password or not;
- once the lock has expired, it is cleared before the attempt is evaluated;
- counting failures and setting the lock happens in the ``user_login_failed`` receiver below,
  which Django fires whenever *every* backend returned ``None`` — so a wrong password anywhere
  counts, whichever view or form triggered it;
- ``user_logged_in`` resets the counter on any successful login, from any surface.
"""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

from core import config

from . import validation

logger = logging.getLogger('cloudgene.accounts')


class LockoutModelBackend(ModelBackend):
    """``ModelBackend``, but a locked account cannot authenticate at all — not even with the
    correct password. Whether the password is *actually* active-account-worthy is still decided
    by the caller (``LoginView`` / the admin's ``AuthenticationForm``); this backend only decides
    "is this account currently locked, and does the password match".
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            user = User._default_manager.get_by_natural_key(username)
        except User.DoesNotExist:
            # Same cost as a real check, so an unknown username isn't distinguishable by timing.
            User().set_password(password)
            return None
        now = timezone.now()
        if user.locked_until:
            if user.locked_until > now:
                return None  # locked: refuse outright, correct password or not
            # the lock has expired: clear it before evaluating this attempt
            User.objects.filter(pk=user.pk).update(login_attempts=0, locked_until=None)
            user.login_attempts, user.locked_until = 0, None
        if user.check_password(password):
            return user
        return None


@receiver(user_login_failed)
def count_failed_login(sender, credentials, request=None, **kwargs):
    """Count one failed attempt toward the lockout, keyed on the (case-insensitive) username,
    whichever login surface it came from. Fired by ``django.contrib.auth.authenticate()`` only
    when no backend returned a user (unknown user, locked account, or wrong password).
    """
    User = get_user_model()
    username = credentials.get('username') or credentials.get(User.USERNAME_FIELD)
    if not username:
        return
    user = User.objects.filter(
        username__iexact=validation.normalize_username(username)).first()
    if user is None:
        return  # nothing to lock for an unknown user
    now = timezone.now()
    if user.locked_until and user.locked_until > now:
        return  # already locked; do not extend the lock or double-count
    max_attempts = config.get('security.max_login_attempts') or 0
    duration = config.get('security.lockout_duration') or 0
    User.objects.filter(pk=user.pk).update(login_attempts=F('login_attempts') + 1)
    user.refresh_from_db(fields=['login_attempts'])
    logger.info('Login failed: wrong password for %s (%d)', user.username, user.login_attempts)
    if max_attempts and user.login_attempts >= max_attempts and duration:
        user.locked_until = now + timedelta(seconds=duration)
        User.objects.filter(pk=user.pk).update(locked_until=user.locked_until)
        logger.warning('Login: account %s locked for %ss after %d failed logins',
                        user.username, duration, user.login_attempts)


@receiver(user_logged_in)
def reset_login_attempts(sender, user, request=None, **kwargs):
    """Any successful login (SPA or Django admin) clears the counter/lock."""
    User = get_user_model()
    if user.login_attempts or user.locked_until:
        User.objects.filter(pk=user.pk).update(login_attempts=0, locked_until=None)
        user.login_attempts, user.locked_until = 0, None
