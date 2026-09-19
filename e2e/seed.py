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
    """Sync the workflow registry from settings.yaml `apps:` (same as `manage.py sync_workflows`,
    which the web process also does lazily on API requests) and fail loudly if a fixture app is
    invalid or missing."""
    from workflows import registry

    from e2e.constants import APPS

    statuses = {s.id: s for s in registry.sync_all()}
    problems = []
    for app_id in APPS:
        st = statuses.get(app_id)
        if st is None:
            problems.append('%s: not listed in settings.yaml apps[]' % app_id)
        elif not st.valid:
            problems.append('%s: invalid: %s' % (app_id, '; '.join(st.errors)))
    if problems:
        raise SystemExit('workflow registry sync failed:\n  ' + '\n  '.join(problems))
    print('workflows synced by the registry: %s' % ', '.join(APPS))


def main(argv):
    _setup()
    steps = argv or ['users', 'workflows']
    for step in steps:
        {'users': seed_users, 'workflows': seed_workflows}[step]()


if __name__ == '__main__':
    main(sys.argv[1:])
