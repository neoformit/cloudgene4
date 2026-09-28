"""
Jobs API (plans/SPEC.md §3.6).

User endpoints (owner-or-admin object access; other users get 404):
    GET    /api/jobs/?state=&page=        own jobs, deleted excluded
    POST   /api/jobs/                     multipart submission (jobs/submission.py)
    GET    /api/jobs/{id}/                detail (steps, messages, outputs, inputs)
    GET    /api/jobs/{id}/status/         light payload for polling
    POST   /api/jobs/{id}/cancel/
    DELETE /api/jobs/{id}/                finished jobs only; removes the workspace
    GET    /api/jobs/{id}/log/            text/plain
    GET    /api/jobs/{id}/outputs/{file_id}/   file download
Admin endpoints:
    GET  /api/admin/jobs/?state=&user=&workflow=&search=
    POST /api/admin/jobs/{id}/cancel/   POST /api/admin/jobs/{id}/restart/
"""
import logging

from django.db.models import F, Q
from django.http import FileResponse, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import error_response
from core.permissions import IsAdmin, is_admin

from . import services
from .models import Job, JobOutput, JobState
from .outputs import read_job_log, resolve_output_file
from .serializers import (JobDetailSerializer, JobListSerializer, JobStatusSerializer,
                          JobSubmitRequestSerializer)
from .submission import SubmissionError, submit_job

logger = logging.getLogger('cloudgene.jobs')

STATE_PARAM = OpenApiParameter('state', str, enum=list(JobState.ALL),
                               description='Filter by state (comma-separated list allowed)')


def _filter_state(queryset, request):
    raw = request.query_params.get('state')
    if not raw:
        return queryset
    states = [s.strip() for s in raw.split(',') if s.strip()]
    bad = [s for s in states if s not in JobState.ALL]
    if bad:
        raise ValidationError({'state': [f'Unknown state "{bad[0]}". Use one of: {", ".join(JobState.ALL)}.']})
    return queryset.filter(status__in=states)


def _action_error(exc):
    return error_response(exc.message, exc.code, exc.status)


class JobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = JobDetailSerializer
    lookup_value_regex = '[0-9a-fA-F-]{32,36}'

    def get_queryset(self):
        user = self.request.user
        qs = Job.objects.visible().select_related('user', 'workflow')
        if self.action == 'list' or not is_admin(user):
            qs = qs.filter(user=user)
        if self.action == 'list':
            qs = _filter_state(qs, self.request)
        elif self.action in ('retrieve', 'status'):
            qs = qs.prefetch_related('steps', 'messages', 'outputs')
        return qs.order_by('-submitted_at', 'id')

    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        if self.action == 'status':
            return JobStatusSerializer
        return JobDetailSerializer

    @extend_schema(parameters=[STATE_PARAM])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request={'multipart/form-data': JobSubmitRequestSerializer,
                            'application/json': JobSubmitRequestSerializer},
                   responses={201: JobDetailSerializer})
    def create(self, request):
        try:
            job = submit_job(request.user, request.data, request.FILES)
        except SubmissionError as exc:
            return error_response(exc.message, exc.code, exc.status, fields=exc.fields)
        logger.info('Job %s submitted (workflow=%s)', job.id, job.app_id,
                   extra={'user': request.user})
        return Response(JobDetailSerializer(job, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    def destroy(self, request, pk=None):
        job = self.get_object()
        try:
            services.delete_job(job)
        except services.JobActionError as exc:
            return _action_error(exc)
        logger.info('Job %s deleted', job.id, extra={'user': request.user})
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=JobStatusSerializer)
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        return Response(JobStatusSerializer(self.get_object()).data)

    @extend_schema(request=None, responses=JobDetailSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        job = self.get_object()
        try:
            job = services.cancel_job(job, by_admin=job.user_id != request.user.id)
        except services.JobActionError as exc:
            return _action_error(exc)
        logger.info('Job %s cancelled', job.id, extra={'user': request.user})
        return Response(JobDetailSerializer(job).data)

    @extend_schema(responses={(200, 'text/plain'): OpenApiTypes.STR})
    @action(detail=True, methods=['get'], url_path='log', url_name='log')
    def log(self, request, pk=None):
        job = self.get_object()
        return HttpResponse(read_job_log(job), content_type='text/plain; charset=utf-8')

    @extend_schema(responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY,
                              404: OpenApiResponse(description='Not found')})
    @action(detail=True, methods=['get'], url_path=r'outputs/(?P<file_id>\d+)',
            url_name='output-download')
    def output_download(self, request, pk=None, file_id=None):
        job = self.get_object()
        output = JobOutput.objects.filter(job=job, pk=file_id).first()
        path = resolve_output_file(job, output) if output else None
        if path is None:
            return error_response('File not found.', 'not_found', status.HTTP_404_NOT_FOUND)
        JobOutput.objects.filter(pk=output.pk).update(download_count=F('download_count') + 1)
        inline = request.query_params.get('inline') in ('1', 'true')
        return FileResponse(open(path, 'rb'), as_attachment=not inline, filename=output.name)


class AdminJobViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """All users' jobs for admins (deleted jobs excluded)."""
    permission_classes = [IsAdmin]
    serializer_class = JobListSerializer
    lookup_value_regex = '[0-9a-fA-F-]{32,36}'

    def get_queryset(self):
        qs = Job.objects.visible().select_related('user', 'workflow').order_by('-submitted_at', 'id')
        if self.action != 'list':
            return qs
        qs = _filter_state(qs, self.request)
        params = self.request.query_params
        if params.get('user'):
            value = params['user']
            qs = qs.filter(user_id=int(value)) if value.isdigit() else qs.filter(user__username__iexact=value)
        if params.get('workflow'):
            qs = qs.filter(app_id=params['workflow'])
        if params.get('search'):
            term = params['search']
            qs = qs.filter(Q(name__icontains=term) | Q(user__username__icontains=term)
                           | Q(app_name__icontains=term) | Q(id__istartswith=term))
        return qs

    @extend_schema(parameters=[
        STATE_PARAM,
        OpenApiParameter('user', str, description='User id or username'),
        OpenApiParameter('workflow', str, description='Workflow id'),
        OpenApiParameter('search', str, description='Job name / username / workflow / id prefix'),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=JobDetailSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        try:
            job = services.cancel_job(self.get_object(), by_admin=True)
        except services.JobActionError as exc:
            return _action_error(exc)
        logger.info('Job %s cancelled by admin', job.id, extra={'user': request.user})
        return Response(JobDetailSerializer(job).data)

    @extend_schema(request=None, responses=JobDetailSerializer)
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        try:
            job = services.restart_job(self.get_object())
        except services.JobActionError as exc:
            return _action_error(exc)
        logger.info('Job %s restarted by admin', job.id, extra={'user': request.user})
        return Response(JobDetailSerializer(job).data)
