"""
Create (or update) an administrator account. Idempotent.

    python manage.py create_admin --username admin --email admin@example.org --password Admin1234

The password may also come from $CLOUDGENE_ADMIN_PASSWORD; if neither is given a
random one is generated and printed. Existing users keep their password unless
--password / $CLOUDGENE_ADMIN_PASSWORD is given.
"""
import os
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from core.permissions import ADMIN_GROUP


class Command(BaseCommand):
    help = 'Create or update an administrator account (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--email', default='admin@localhost')
        parser.add_argument('--full-name', default='Administrator')
        parser.add_argument('--password', default=None)

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        password = opts['password'] or os.environ.get('CLOUDGENE_ADMIN_PASSWORD')
        user = User.objects.filter(username__iexact=opts['username']).first()
        created = user is None
        generated = None
        if created:
            if not password:
                generated = password = secrets.token_urlsafe(12) + 'A1a'
            user = User(username=opts['username'], email=opts['email'].lower(),
                        full_name=opts['full_name'])
        if password:
            user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.activation_key = None
        user.save()
        group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        user.groups.add(group)

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} admin user "{user.username}"'))
        if generated:
            self.stdout.write(f'Generated password: {generated}')
