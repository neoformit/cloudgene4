"""
The job worker: ``python manage.py run_worker [--once] [--interval 1.0] [--grace 10]``.

Single instance per CLOUDGENE_HOME (fcntl lock on ``config/worker.lock``). SIGTERM/SIGINT stop
it gracefully: no new jobs are claimed and running Nextflow process groups are terminated
(jobs are marked failed). ``--once`` processes the queue until it is idle, then exits.
"""
import logging
import signal

from django.core.management.base import BaseCommand, CommandError

from jobs.worker import CANCEL_GRACE_SECONDS, Worker, acquire_lock

logger = logging.getLogger('cloudgene.worker')


class Command(BaseCommand):
    help = 'Run the job worker (scheduler + Nextflow executor)'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true',
                            help='Run until no job is running or claimable, then exit')
        parser.add_argument('--interval', type=float, default=1.0, help='Tick interval in seconds')
        parser.add_argument('--grace', type=float, default=CANCEL_GRACE_SECONDS,
                            help='Seconds between SIGTERM and SIGKILL when cancelling')
        parser.add_argument('--timeout', type=float, default=3600, help='Max seconds for --once')

    def handle(self, *args, **opts):
        lock = acquire_lock()
        if lock is None:
            raise CommandError('Another worker is already running for this CLOUDGENE_HOME.')
        worker = Worker(tick_seconds=opts['interval'], grace=opts['grace'])
        try:
            if opts['once']:
                worker.drain(timeout=opts['timeout'])
                return
            signal.signal(signal.SIGTERM, worker.request_stop)
            signal.signal(signal.SIGINT, worker.request_stop)
            self.stdout.write(f'Worker started (interval {opts["interval"]}s). Stop with Ctrl+C.')
            self.stdout.flush()
            worker.run_forever()
            self.stdout.write('Worker stopped.')
        finally:
            lock.close()
