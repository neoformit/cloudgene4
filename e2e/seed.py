"""Seed the E2E database. Run inside the stack env from the repo root:

    python -m e2e.seed users       # groups + alice/bob (after `migrate` + `create_admin`)
    python -m e2e.seed workflows   # after the server is up; see fallback below

Idempotent: safe to run repeatedly.
"""
import os
import sys
from pathlib import Path


def _setup():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloudgene_django.settings')
    import django
    django.setup()


def seed_users():
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from e2e.constants import USERS

    User = get_user_model()
    for name in {'admin', 'researchers'}:
        Group.objects.get_or_create(name=name)
    for username, spec in USERS.items():
        if spec['is_admin']:
            continue  # created by `manage.py create_admin` (see stack.py)
        user = User.objects.filter(username=username).first() or User(username=username)
        user.email = spec['email']
        if hasattr(user, 'full_name'):
            user.full_name = spec['full_name']
        user.is_active = True
        user.set_password(spec['password'])
        user.save()
        user.groups.set([Group.objects.get(name=g) for g in spec['groups']])
        print('seeded user %s groups=%s' % (username, spec['groups']))


def seed_workflows():
    """Make sure every fixture app from settings.yaml is installed as a Workflow row.

    Target behaviour (T05): the workflow registry syncs `apps:` from settings.yaml into the DB on
    start-up, so this function finds every row already present and does nothing.
    """
    from django.apps import apps as django_apps

    from e2e.constants import APPS

    Workflow = django_apps.get_model('workflows', 'Workflow')
    missing = [a for a in APPS if not Workflow.objects.filter(pk=a).exists()]
    if not missing:
        print('workflows already installed by the registry: %s' % ', '.join(APPS))
        return
    _legacy_load_workflows(missing)


# TODO remove after T05 ------------------------------------------------------------------------
def _legacy_load_workflows(app_ids):
    """Fallback until the T05 registry syncs `apps:`: install each app with T03's
    `manage.py install_workflow` (validates the definition with workflows.definition)."""
    import io

    from django.conf import settings
    from django.core.management import call_command

    from e2e.constants import APPS

    home = Path(settings.CLOUDGENE_HOME)
    for app_id in app_ids:
        rules = APPS[app_id]
        args = [str(home / 'apps' / app_id)]
        if rules['public']:
            args.append('--public')
        for g in rules['groups']:
            args += ['--group', g]
        out = io.StringIO()
        call_command('install_workflow', *args, stdout=out)
        print('FALLBACK install_workflow: %s' % out.getvalue().strip())
# end TODO remove after T05 --------------------------------------------------------------------


def main(argv):
    _setup()
    steps = argv or ['users', 'workflows']
    for step in steps:
        {'users': seed_users, 'workflows': seed_workflows}[step]()


if __name__ == '__main__':
    main(sys.argv[1:])
