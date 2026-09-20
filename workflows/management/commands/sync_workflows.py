from django.core.management.base import BaseCommand

from workflows import registry


class Command(BaseCommand):
    help = 'Sync the workflow cache from settings.yaml apps[] (run at deploy / worker start).'

    def handle(self, *args, **opts):
        statuses = registry.sync_all()
        for st in statuses:
            if st.valid:
                state = 'enabled' if st.enabled else 'disabled'
                self.stdout.write(f'{st.id}: {state} ({st.yaml_path})')
            else:
                self.stdout.write(self.style.WARNING(
                    f'{st.id}: INVALID ({st.path})' + ''.join(f'\n  - {e}' for e in st.errors)))
        self.stdout.write(self.style.SUCCESS(f'{len(statuses)} workflow(s) synced.'))
