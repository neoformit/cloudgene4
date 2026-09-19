"""Seed the E2E database. Run inside the stack env from the repo root:

    python -m e2e.seed users       # groups + admin/alice/bob (after `migrate`)
    python -m e2e.seed workflows   # after the server is up; see fallback below

Idempotent: safe to run repeatedly.
"""
import os
import sys
from pathlib import Path


def _setup():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e2e.e2e_settings')
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
        user = User.objects.filter(username=username).first() or User(username=username)
        user.email = spec['email']
        if hasattr(user, 'full_name'):
            user.full_name = spec['full_name']
        user.is_active = True
        user.is_staff = spec['is_admin']
        user.is_superuser = spec['is_admin']
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
    """Fallback for the pre-registry code base: load each app via `load_sample_workflow` and set
    access rules directly on the Workflow row. Apps the legacy loader can't parse are reported,
    not fatal (e.g. all-inputs uses input types the legacy loader rejects)."""
    import io

    from django.apps import apps as django_apps
    from django.conf import settings
    from django.contrib.auth.models import Group
    from django.core.management import call_command

    from e2e.constants import APPS

    Workflow = django_apps.get_model('workflows', 'Workflow')
    home = Path(settings.CLOUDGENE_HOME)
    for app_id in app_ids:
        yaml_path = home / 'apps' / app_id / 'cloudgene.yaml'
        out = io.StringIO()
        call_command('load_sample_workflow', file=str(yaml_path), stdout=out)
        wf = Workflow.objects.filter(pk=app_id).first()
        if wf is None:
            print('LEGACY-FALLBACK: could not load %s: %s' % (app_id, out.getvalue().strip()))
            continue
        rules = APPS[app_id]
        wf.public = rules['public']
        if hasattr(wf, 'nextflow_script'):
            wf.nextflow_script = str(home / 'apps' / app_id / 'main.nf')
        wf.save()
        wf.allowed_groups.set([Group.objects.get_or_create(name=g)[0] for g in rules['groups']])
        print('LEGACY-FALLBACK: loaded %s (public=%s groups=%s)' % (app_id, rules['public'],
                                                                   rules['groups']))
# end TODO remove after T05 --------------------------------------------------------------------


def main(argv):
    _setup()
    steps = argv or ['users', 'workflows']
    for step in steps:
        {'users': seed_users, 'workflows': seed_workflows}[step]()


if __name__ == '__main__':
    main(sys.argv[1:])
