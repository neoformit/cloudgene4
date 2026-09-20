from django.core.management.base import BaseCommand, CommandError

from workflows import registry


class Command(BaseCommand):
    help = ('Install a workflow: register the app directory (or its cloudgene.yaml) in '
            'settings.yaml apps[] and sync the workflow cache.')

    def add_arguments(self, parser):
        parser.add_argument('path', help='App directory containing cloudgene.yaml, or the yaml '
                                         'file (relative paths: $CLOUDGENE_HOME/apps, then cwd)')
        parser.add_argument('--public', action='store_true', help='Accessible to every user')
        parser.add_argument('--groups', default='', help='Comma-separated group names')
        parser.add_argument('--disabled', action='store_true', help='Install but keep disabled')
        parser.add_argument('--copy', action='store_true',
                            help='Copy the app into $CLOUDGENE_HOME/apps/<id>/ first')
        parser.add_argument('--replace', action='store_true',
                            help='If the id is already installed, point it at this path')

    def handle(self, *args, **opts):
        import os
        path = opts['path']
        if not os.path.isabs(path) and os.path.exists(path):
            path = os.path.abspath(path)
        groups = [g for g in opts['groups'].split(',') if g.strip()]
        try:
            wf = registry.install(path, public=opts['public'], groups=groups,
                                  enabled=not opts['disabled'], copy=opts['copy'],
                                  replace=opts['replace'])
        except registry.RegistryError as exc:
            detail = ''.join(f'\n  - {e}' for e in exc.errors if e != exc.message)
            raise CommandError(f'{exc.message}{detail}')
        self.stdout.write(self.style.SUCCESS(
            f'Installed {wf.id} ({wf.name} {wf.version}) from {wf.app_path}'))
