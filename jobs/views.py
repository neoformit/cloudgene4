"""
API views for job management
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import Http404, HttpResponse, FileResponse
from django.db.models import Q

from core.exceptions import error_response
from .models import Job, JobDownload
from .serializers import (
    JobListSerializer, JobDetailSerializer, JobSubmissionSerializer
)
from .queue import job_queue


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to only allow owners of a job or admins to access it
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_admin_user():
            return True
        return obj.user == request.user


class JobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing jobs
    """
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        elif self.action == 'create':
            return JobSubmissionSerializer
        else:
            return JobDetailSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = Job.objects.select_related('workflow', 'user').prefetch_related(
            'steps', 'messages', 'downloads'
        )
        
        # Admins can see all jobs, users can only see their own
        if not user.is_admin_user():
            queryset = queryset.filter(user=user)
        
        # Filter by status if requested
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by workflow if requested
        workflow_filter = self.request.query_params.get('workflow')
        if workflow_filter:
            queryset = queryset.filter(workflow_id=workflow_filter)
        
        return queryset.order_by('-submitted_at')
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a job"""
        job = self.get_object()
        
        try:
            job_queue.cancel_job(str(job.id))
            return Response({'message': 'Job cancelled successfully'})
        except Exception as e:
            return error_response(str(e), 'invalid_state')
    
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """Restart a failed or cancelled job"""
        job = self.get_object()
        
        try:
            job_queue.restart_job(str(job.id))
            serializer = self.get_serializer(job)
            return Response(serializer.data)
        except Exception as e:
            return error_response(str(e), 'invalid_state')
    
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Get job logs"""
        job = self.get_object()
        return Response({
            'job_id': str(job.id),
            'logs': job.logs,
            'error_message': job.error_message
        })
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Get list of downloadable files"""
        job = self.get_object()
        downloads = job.downloads.all()
        
        from .serializers import JobDownloadSerializer
        serializer = JobDownloadSerializer(downloads, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='download/(?P<download_id>[^/.]+)')
    def download_file(self, request, pk=None, download_id=None):
        """Download a specific file"""
        job = self.get_object()
        download = get_object_or_404(JobDownload, job=job, id=download_id)
        
        if download.is_expired():
            return error_response('Download link has expired', 'gone', status.HTTP_410_GONE)
        
        try:
            # Increment download count
            download.download_count += 1
            download.save()
            
            # Return file
            return FileResponse(
                open(download.file_path, 'rb'),
                as_attachment=True,
                filename=download.filename
            )
        except FileNotFoundError:
            return error_response('File not found', 'not_found', status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def queue_status(self, request):
        """Get queue status information"""
        queue_status = job_queue.get_queue_status()
        return Response(queue_status)
    
    @action(detail=False, methods=['post'])
    def pause_queue(self, request):
        """Pause job queue (admin only)"""
        if not request.user.is_admin_user():
            return error_response('Admin permission required', 'permission_denied',
                                  status.HTTP_403_FORBIDDEN)
        
        job_queue.pause_queue()
        return Response({'message': 'Queue paused'})
    
    @action(detail=False, methods=['post'])
    def resume_queue(self, request):
        """Resume job queue (admin only)"""
        if not request.user.is_admin_user():
            return error_response('Admin permission required', 'permission_denied',
                                  status.HTTP_403_FORBIDDEN)
        
        job_queue.resume_queue()
        return Response({'message': 'Queue resumed'})
    
    def create(self, request, *args, **kwargs):
        """Submit a new job"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            job = serializer.save()
            response_serializer = JobDetailSerializer(job)
            return Response(
                response_serializer.data, 
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return error_response(f'Failed to submit job: {str(e)}', 'submission_failed')
