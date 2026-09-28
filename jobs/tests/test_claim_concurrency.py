"""T09b bullet 4: the worker's conditional-UPDATE claim (`jobs.worker.Worker.claim`) must be
race-free when two workers run against the same database, not only on SQLite's global writer
lock. SQLite serialises every writer behind one file lock (see settings.py's ``transaction_mode
= 'IMMEDIATE'``), so two threads racing the same UPDATE there never exercise a real DB-level
race — the assertion is only meaningful against a database with real row-level concurrency
(Postgres). A production deployment only ever runs one worker process (the ``fcntl`` lock in
``jobs.worker.acquire_lock``), but the DB-level guarantee must hold regardless: two Django
processes briefly overlapping during a restart/deploy must never both start the same job.
"""
import threading

from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from jobs import worker as worker_mod
from jobs.models import Job, JobState
from jobs.submission import submit_job

from .helpers import TempHomeMixin, make_app, make_user


class ClaimConcurrencyTest(TempHomeMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest(
                'claim race is only meaningful against a database with real row-level '
                'concurrency (Postgres); SQLite serialises every writer behind one lock. '
                'Run against Postgres: scripts/test.sh unit --postgres (plans/TASKS.md T09b).')
        make_app('hello')
        self.user = make_user('alice')

    def _claim_attempt(self, job_id, results, lock):
        try:
            now = timezone.now()
            updated = worker_mod.retry_on_locked(
                Job.objects.filter(pk=job_id, status=JobState.WAITING,
                                   cancel_requested=False).update,
                status=JobState.RUNNING, started_at=now, finished_at=None, updated_at=now)
        finally:
            connections.close_all()
        with lock:
            results.append(updated)

    def test_two_concurrent_claims_never_take_the_same_job(self):
        job = submit_job(self.user, {'workflow': 'hello', 'job_name': 'race'}, {})
        self.assertEqual(job.status, JobState.WAITING)

        n = 8
        barrier = threading.Barrier(n)
        results = []
        results_lock = threading.Lock()

        def attempt():
            barrier.wait()  # line every thread up so the UPDATEs really overlap
            self._claim_attempt(job.pk, results, results_lock)

        threads = [threading.Thread(target=attempt) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(results), n, 'not every thread finished')
        self.assertEqual(sum(results), 1, f'exactly one claim must succeed, got {results}')
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.RUNNING)

    def test_many_jobs_claimed_by_racing_workers_are_each_claimed_exactly_once(self):
        """Closer to the real `Worker.claim()` loop: several waiting jobs, several concurrent
        claimers each trying to grab a batch — no job is ever claimed twice."""
        jobs = [submit_job(self.user, {'workflow': 'hello', 'job_name': f'race-{i}'}, {})
                for i in range(5)]
        job_ids = [j.pk for j in jobs]

        claims = []  # (job_id, worker_index) for every successful claim
        claims_lock = threading.Lock()
        barrier = threading.Barrier(4)

        def worker_run(idx):
            barrier.wait()
            for job_id in job_ids:
                got = self._claim_attempt_bool(job_id)
                if got:
                    with claims_lock:
                        claims.append((job_id, idx))
            connections.close_all()

        threads = [threading.Thread(target=worker_run, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        claimed_job_ids = [c[0] for c in claims]
        self.assertEqual(len(claimed_job_ids), len(set(claimed_job_ids)),
                         f'a job was claimed more than once: {claims}')
        self.assertEqual(set(claimed_job_ids), set(job_ids))
        for job in jobs:
            job.refresh_from_db()
            self.assertEqual(job.status, JobState.RUNNING)

    def _claim_attempt_bool(self, job_id):
        now = timezone.now()
        return bool(worker_mod.retry_on_locked(
            Job.objects.filter(pk=job_id, status=JobState.WAITING,
                               cancel_requested=False).update,
            status=JobState.RUNNING, started_at=now, finished_at=None, updated_at=now))
