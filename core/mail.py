"""
Outgoing mail configured from ``settings.yaml`` (``mail.*``) at send time.

    from core.mail import send_mail
    send_mail(subject, body, ['user@example.org'])
"""
from pathlib import Path

from django.conf import settings
from django.core import mail as django_mail

from . import config

BACKENDS = {
    'smtp': 'django.core.mail.backends.smtp.EmailBackend',
    'file': 'django.core.mail.backends.filebased.EmailBackend',
    'console': 'django.core.mail.backends.console.EmailBackend',
}


def get_connection(mail_settings=None, fail_silently=False):
    """Django mail connection for the current (or given) ``mail`` settings section."""
    if settings.EMAIL_BACKEND == 'django.core.mail.backends.locmem.EmailBackend':
        # Django's test runner switched to the in-memory outbox; honour it.
        return django_mail.get_connection(fail_silently=fail_silently)
    m = mail_settings or config.get('mail')
    backend = BACKENDS[m['backend']]
    kwargs = {'fail_silently': fail_silently}
    if m['backend'] == 'smtp':
        kwargs.update(host=m['host'], port=m['port'], username=m['user'] or None,
                      password=m['password'] or None, use_tls=m['use_tls'],
                      use_ssl=m['use_ssl'], timeout=30)
    elif m['backend'] == 'file':
        path = Path(m['file_path'])
        if not path.is_absolute():
            path = config.cloudgene_home() / path
        path.mkdir(parents=True, exist_ok=True)
        kwargs['file_path'] = str(path)
    return django_mail.get_connection(backend, **kwargs)


def from_email():
    return config.get('mail.from_email')


def send_mail(subject, message, recipient_list, *, html_message=None, fail_silently=False):
    """Send one message using the mail settings from settings.yaml."""
    m = config.get('mail')
    return django_mail.send_mail(
        subject, message, m['from_email'], recipient_list,
        html_message=html_message, fail_silently=fail_silently,
        connection=get_connection(m, fail_silently=fail_silently),
    )
