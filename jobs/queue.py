"""
Job queue management system.

TRANSITIONAL (T01): Celery was removed. Jobs are only queued here (status stays
``pending``); nothing executes them until T03 lands the ``run_worker`` command,
which owns scheduling (plans/SPEC.md §3.3). Limits/pause come from core.config.
"""
import logging
from collections import deque
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Max

from .models import Job
from core import config

logger = logging.getLogger(__name__)


class JobQueue:
    """
    Manages job queue and execution
    """
    
    def __init__(self):
        self._queue = deque()
        self._running_jobs = set()
    
    def submit_job(self, job):
        """
        Submit a job to the queue
        """
        try:
            # Validate job name to fix space handling bug
            if job.name and ' ' in job.name:
                # Replace spaces with underscores to prevent backend errors
                job.name = job.name.replace(' ', '_')
                job.save()
            
            # Check queue limits
            max_queue_size = config.get('server.max_queue_size')
            
            pending_count = Job.objects.filter(status='pending').count()
            
            if pending_count >= max_queue_size:
                raise Exception(f"Queue is full (max size: {max_queue_size})")
            
            # Set job priority and queue position
            job.priority = self.calculate_priority(job)
            job.queue_position = self.get_next_queue_position()
            job.status = 'pending'
            job.save()
            
            logger.info(f"Job {job.id} submitted to queue at position {job.queue_position}")
            
            # Try to start job immediately if possible
            self.process_queue()
            
            return True
            
        except Exception as e:
            job.status = 'failed'
            job.error_message = f"Failed to submit job: {str(e)}"
            job.save()
            logger.error(f"Failed to submit job {job.id}: {e}")
            raise
    
    def process_queue(self):
        """
        No-op until the T03 worker exists: execution is owned by ``run_worker``.
        Jobs remain ``pending``.
        """
        logger.debug('process_queue: no worker-side execution in this build (T03)')

    def start_job(self, job):
        """
        Start a specific job
        """
        with transaction.atomic():
            # Double-check job status to prevent race conditions
            job.refresh_from_db()
            if job.status != 'pending':
                return
            
            job.status = 'running'
            job.started_at = timezone.now()
            job.save()
        
        # Execution is handed to the worker (T03); nothing is dispatched here.
        logger.info(f"Job {job.id} marked running (no executor in this build)")
    
    def cancel_job(self, job_id):
        """
        Cancel a job
        """
        try:
            job = Job.objects.get(id=job_id)
            
            if job.status == 'pending':
                job.status = 'cancelled'
                job.completed_at = timezone.now()
                job.save()
                logger.info(f"Cancelled pending job {job_id}")
                
                # Process queue to potentially start waiting jobs
                self.process_queue()
                
            elif job.status == 'running':
                job.status = 'cancelled'
                job.completed_at = timezone.now()
                job.save()
                logger.info(f"Cancelled running job {job_id}")
                
                # Process queue to start next job
                self.process_queue()
            
            else:
                raise Exception(f"Cannot cancel job in status: {job.status}")
            
            return True
            
        except Job.DoesNotExist:
            raise Exception(f"Job {job_id} not found")
    
    def restart_job(self, job_id):
        """
        Restart a failed or cancelled job
        """
        try:
            job = Job.objects.get(id=job_id)
            
            if not job.can_restart():
                raise Exception(f"Cannot restart job in status: {job.status}")
            
            # Reset job status and timestamps
            job.status = 'pending'
            job.started_at = None
            job.completed_at = None
            job.error_message = ''
            job.logs = ''
            job.queue_position = self.get_next_queue_position()
            job.save()
            
            # Clear previous job steps and messages
            job.steps.all().delete()
            job.messages.all().delete()
            
            logger.info(f"Restarted job {job_id}")
            
            # Try to process queue
            self.process_queue()
            
            return True
            
        except Job.DoesNotExist:
            raise Exception(f"Job {job_id} not found")
    
    def calculate_priority(self, job):
        """
        Calculate job priority based on user and workflow
        """
        priority = 0
        
        # Admin users get higher priority
        if job.user.is_admin_user():
            priority += 10
        
        # Priority can be set based on workflow type
        if hasattr(job.workflow, 'priority'):
            priority += job.workflow.priority
        
        return priority
    
    def get_next_queue_position(self):
        """
        Get the next queue position
        """
        last_position = Job.objects.filter(
            status='pending'
        ).aggregate(
            max_position=Max('queue_position')
        )['max_position']
        
        return (last_position or 0) + 1
    
    def get_queue_status(self):
        """
        Get current queue status
        """
        from django.db.models import Count, Q
        
        status_counts = Job.objects.aggregate(
            pending=Count('id', filter=Q(status='pending')),
            running=Count('id', filter=Q(status='running')),
            completed=Count('id', filter=Q(status='completed')),
            failed=Count('id', filter=Q(status='failed')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )
        
        return {
            'status_counts': status_counts,
            'max_concurrent_jobs': config.get('server.max_running_jobs'),
            'max_queue_size': config.get('server.max_queue_size'),
            'queue_active': not self.is_maintenance_mode(),
        }
    
    def is_maintenance_mode(self):
        """
        Check if server is in maintenance mode
        """
        return config.get('server.maintenance')
    
    def pause_queue(self):
        """
        Pause job processing
        """
        config.set_value('queue.paused', True)
        logger.info("Job queue paused")
    
    def resume_queue(self):
        """
        Resume job processing
        """
        config.set_value('queue.paused', False)
        logger.info("Job queue resumed")
        
        # Process pending jobs
        self.process_queue()
    
    def is_paused(self):
        """
        Check if queue is paused
        """
        return config.get('queue.paused')


# Global queue instance
job_queue = JobQueue()