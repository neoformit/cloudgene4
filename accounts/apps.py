from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # Connects the user_login_failed / user_logged_in receivers (B-01 lockout).
        from . import backends  # noqa: F401
