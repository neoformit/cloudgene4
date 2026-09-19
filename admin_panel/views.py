"""
Admin panel views
"""
from rest_framework import viewsets

from core.permissions import IsAdmin, IsAdminOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Count, Q
from django.contrib.auth import get_user_model

from .models import ServerSettings, Template, NavbarItem, SystemLog, Counter
from .serializers import (
    ServerSettingsSerializer, TemplateSerializer, NavbarItemSerializer,
    SystemLogSerializer, CounterSerializer,
)
from jobs.models import Job
from workflows.models import Workflow

User = get_user_model()


class ServerSettingsViewSet(viewsets.ModelViewSet):
    queryset = ServerSettings.objects.all()
    serializer_class = ServerSettingsSerializer
    permission_classes = [IsAdmin]


class TemplateViewSet(viewsets.ModelViewSet):
    """Readable by anyone; writable by admins only."""
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [IsAdminOrReadOnly]


class NavbarItemViewSet(viewsets.ModelViewSet):
    """Readable by anyone; writable by admins only."""
    queryset = NavbarItem.objects.all()
    serializer_class = NavbarItemSerializer
    permission_classes = [IsAdminOrReadOnly]


class SystemLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SystemLog.objects.all()
    serializer_class = SystemLogSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = SystemLog.objects.all()
        level = self.request.query_params.get('level')
        if level:
            queryset = queryset.filter(level=level)
        component = self.request.query_params.get('component')
        if component:
            queryset = queryset.filter(component=component)
        return queryset.order_by('-timestamp')


class CounterViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Counter.objects.all()
    serializer_class = CounterSerializer
    permission_classes = [IsAdmin]


class AdminDashboardView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        job_stats = Job.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            running=Count('id', filter=Q(status='running')),
            completed=Count('id', filter=Q(status='completed')),
            failed=Count('id', filter=Q(status='failed')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )

        user_stats = User.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            staff=Count('id', filter=Q(is_staff=True)),
        )

        workflow_stats = Workflow.objects.aggregate(
            total=Count('id'),
            enabled=Count('id', filter=Q(status='enabled')),
            disabled=Count('id', filter=Q(status='disabled')),
        )

        recent_jobs = Job.objects.select_related(
            'workflow', 'user'
        ).order_by('-submitted_at')[:10]

        from jobs.serializers import JobListSerializer
        recent_jobs_data = JobListSerializer(recent_jobs, many=True).data

        recent_logs = SystemLog.objects.order_by('-timestamp')[:10]
        recent_logs_data = SystemLogSerializer(recent_logs, many=True).data

        return Response({
            'statistics': {
                'jobs': job_stats,
                'users': user_stats,
                'workflows': workflow_stats,
            },
            'recent_jobs': recent_jobs_data,
            'recent_logs': recent_logs_data,
        })
