"""
Minimal workflow installer (interim; the T05 registry syncs `apps:` from settings.yaml).

    manage.py install_workflow <app dir | cloudgene.yaml> [--public] [--group G ...] [--disabled]

Validates the definition with ``workflows.definition.load_definition`` and creates/updates the
``Workflow`` cache row (raw YAML + the app dir, stored in ``nextflow_script`` as the YAML path).
"""
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from core import config as cloudgene_config
from workflows.definition import DefinitionError, load_definition
from workflows.models import Workflow


def install_workflow(path, public=False, groups=(), enabled=True) -> Workflow:
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = cloudgene_config.apps_dir() / p
    definition = load_definition(p.resolve())
    wf, _ = Workflow.objects.get_or_create(id=definition.id, defaults={'name': definition.name})
    wf.name = definition.name
    wf.description = definition.description
    wf.version = definition.version or '1.0.0'
    wf.website = definition.website if definition.website.startswith(('http://', 'https://')) else ''
    wf.yaml_config = definition.yaml_text
    wf.nextflow_script = str(definition.source_path)
    wf.public = bool(public)
    wf.status = 'enabled' if enabled else 'disabled'
    wf.save()
    wf.allowed_groups.set([Group.objects.get_or_create(name=g)[0] for g in groups])
    return wf


class Command(BaseCommand):
    help = 'Install or update a workflow from an app directory or cloudgene.yaml'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--public', action='store_true')
        parser.add_argument('--group', action='append', default=[], dest='groups')
        parser.add_argument('--disabled', action='store_true')

    def handle(self, *args, **opts):
        try:
            wf = install_workflow(opts['path'], public=opts['public'], groups=opts['groups'],
                                  enabled=not opts['disabled'])
        except DefinitionError as exc:
            raise CommandError('Invalid workflow definition:\n  ' + '\n  '.join(exc.errors))
        self.stdout.write(f'Installed workflow {wf.id} ({wf.name}) public={wf.public} '
                          f'groups={list(wf.allowed_groups.values_list("name", flat=True))}')
