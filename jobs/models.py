import os
import json
import uuid

from core import config as cloudgene_config
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings

User = get_user_model()


class Job(models.Model):
    """
    Represents a job execution in the system
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('waiting', 'Waiting'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, blank=True, help_text="Optional job name")
    workflow = models.ForeignKey('workflows.Workflow', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Job status and timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Job configuration
    parameters = models.JSONField(default=dict, help_text="Input parameters for the job")
    workspace_dir = models.CharField(max_length=500, blank=True)
    nextflow_process_id = models.CharField(max_length=255, blank=True)
    
    # Job results and metadata
    results = models.JSONField(default=dict, blank=True)
    logs = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    # Priority and queue management
    priority = models.IntegerField(default=0)
    queue_position = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'jobs'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status', 'submitted_at']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['workflow', 'status']),
        ]
    
    def __str__(self):
        display_name = self.name or f"Job {self.id}"
        return f"{display_name} - {self.workflow.name} ({self.status})"
    
    def get_workspace_path(self):
        """Get the full path to the job workspace directory"""
        if not self.workspace_dir:
            self.workspace_dir = os.path.join(
                str(cloudgene_config.jobs_dir()),
                str(self.user.id), 
                str(self.id)
            )
            self.save()
        return self.workspace_dir
    
    def get_duration(self):
        """Calculate job duration"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return timezone.now() - self.started_at
        return None
    
    def can_cancel(self):
        """Check if job can be cancelled"""
        return self.status in ['pending', 'running', 'waiting']
    
    def can_restart(self):
        """Check if job can be restarted"""
        return self.status in ['failed', 'cancelled', 'completed']


class JobStep(models.Model):
    """
    Individual steps within a job execution
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='steps')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    step_type = models.CharField(max_length=50)  # e.g., 'nextflow', 'bash', 'docker'
    
    # Step execution details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    order = models.IntegerField(default=0)
    
    # Step configuration and results
    parameters = models.JSONField(default=dict)
    output = models.TextField(blank=True)
    error_output = models.TextField(blank=True)
    
    class Meta:
        db_table = 'job_steps'
        ordering = ['order']
        unique_together = ['job', 'name']
    
    def __str__(self):
        return f"{self.job.name or self.job.id} - {self.name}"


class JobValue(models.Model):
    """
    Parameter values for job inputs and outputs
    """
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='values')
    parameter_id = models.CharField(max_length=255)
    value = models.TextField()
    is_input = models.BooleanField(default=True)
    file_path = models.CharField(max_length=500, blank=True)  # For file/folder parameters
    
    class Meta:
        db_table = 'job_values'
        unique_together = ['job', 'parameter_id', 'is_input']
    
    def __str__(self):
        return f"{self.job} - {self.parameter_id}: {self.value[:50]}"


class JobMessage(models.Model):
    """
    Messages and notifications related to job execution
    """
    MESSAGE_TYPES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('success', 'Success'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'job_messages'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.job} - {self.message_type}: {self.message[:50]}"


class JobDownload(models.Model):
    """
    Downloadable files generated by job execution
    """
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='downloads')
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    download_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'job_downloads'
        ordering = ['filename']
    
    def __str__(self):
        return f"{self.job} - {self.filename}"
    
    def is_expired(self):
        """Check if download link is expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
