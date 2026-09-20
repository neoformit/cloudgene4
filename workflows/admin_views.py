"""
Admin workflow endpoints (SPEC §3.6) — all backed by ``workflows.registry``; the source of
truth is settings.yaml ``apps[]`` (+ per-app files under ``$CLOUDGENE_HOME/apps/<id>/``).

    GET    /api/admin/workflows/                 all apps incl. disabled / invalid
    POST   /api/admin/workflows/install/         {path, enabled?, public?, groups?, copy?}
    POST   /api/admin/workflows/sync/            re-read every app
    GET    /api/admin/workflows/{id}/            one app (+ raw yaml)
    PATCH  /api/admin/workflows/{id}/            {enabled?, public?, groups?}
    DELETE /api/admin/workflows/{id}/            uninstall (files stay on disk)
    POST   /api/admin/workflows/{id}/reload/     re-read cloudgene.yaml
    GET/PUT /api/admin/workflows/{id}/nextflow/  {profile, work_dir, config, env}
"""
from pathlib import Path

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core import config
from core.exceptions import error_response
from core.permissions import IsAdmin

from . import registry
from .models import Workflow
from .template_utils import VARIABLES


class AdminWorkflowSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    version = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    category = serializers.CharField(allow_blank=True)
    path = serializers.CharField(help_text='apps[].path as written in settings.yaml')
    yaml_path = serializers.CharField(allow_blank=True, help_text='Resolved cloudgene.yaml')
    index = serializers.IntegerField(help_text='Position in settings.yaml apps[]')
    enabled = serializers.BooleanField()
    public = serializers.BooleanField()
    groups = serializers.ListField(child=serializers.CharField())
    valid = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    job_count = serializers.IntegerField()


class AdminWorkflowDetailSerializer(AdminWorkflowSerializer):
    yaml = serializers.CharField(allow_blank=True, help_text='Raw cloudgene.yaml')


class AdminWorkflowPatchSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    public = serializers.BooleanField(required=False)
    groups = serializers.ListField(child=serializers.CharField(max_length=150), required=False,
                                   help_text='Group names (created if missing)')


class InstallSerializer(serializers.Serializer):
    path = serializers.CharField(help_text='App dir or cloudgene.yaml (absolute, or relative '
                                           'to $CLOUDGENE_HOME/apps)')
    enabled = serializers.BooleanField(default=True)
    public = serializers.BooleanField(default=False)
    groups = serializers.ListField(child=serializers.CharField(max_length=150), default=list)
    copy = serializers.BooleanField(default=False,
                                    help_text='Copy the app into $CLOUDGENE_HOME/apps/<id>/')


class TemplateVariableSerializer(serializers.Serializer):
    name = serializers.CharField()
    scope = serializers.ChoiceField(choices=['global', 'app', 'job'])
    description = serializers.CharField()


class AppNextflowSerializer(serializers.Serializer):
    profile = serializers.CharField(allow_blank=True, required=False, max_length=255,
                                    help_text="'' = use the global nextflow.profile")
    work_dir = serializers.CharField(allow_blank=True, required=False,
                                     help_text="'' = use the global nextflow.work_dir")
    config = serializers.CharField(allow_blank=True, required=False, trim_whitespace=False,
                                   help_text='Contents of apps/<id>/nextflow.config')
    env = serializers.CharField(allow_blank=True, required=False, trim_whitespace=False,
                                help_text='Contents of apps/<id>/nextflow.env (KEY=VALUE)')
    config_path = serializers.CharField(read_only=True)
    env_path = serializers.CharField(read_only=True)
    variables = TemplateVariableSerializer(many=True, read_only=True)


def _job_counts():
    from django.db.models import Count

    try:
        from jobs.models import Job
        return dict(Job.objects.values_list('workflow_id').annotate(n=Count('id')))
    except Exception:  # pragma: no cover - jobs app changed shape
        return {}


def _row(st: registry.AppStatus, job_counts=None, with_yaml=False) -> dict:
    meta = st.meta
    cached = None
    if meta is None:
        cached = Workflow.objects.filter(pk=st.id).first()
    data = {
        'id': st.id,
        'name': meta.name if meta else (cached.name if cached else st.id),
        'version': meta.version if meta else (cached.version if cached else ''),
        'description': meta.description if meta else '',
        'category': meta.category if meta else '',
        'path': st.path,
        'yaml_path': st.yaml_path,
        'index': st.index,
        'enabled': st.enabled,
        'public': st.public,
        'groups': st.groups,
        'valid': st.valid,
        'errors': st.errors,
        'warnings': st.warnings,
        'job_count': (job_counts or {}).get(st.id, 0),
    }
    if with_yaml:
        data['yaml'] = config.read_text(Path(st.yaml_path)) if st.yaml_path else ''
    return data


def _registry_error(exc: registry.RegistryError, field='path'):
    fields = {field: exc.errors} if exc.errors and exc.status == 400 else None
    return error_response(exc.message, exc.code, exc.status, fields=fields)


def _nextflow_payload(app_id):
    data = registry.get_nextflow_settings(app_id)
    data['variables'] = [{'name': n, 'scope': s, 'description': d} for n, s, d in VARIABLES]
    return data


class AdminWorkflowListView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_workflows_list',
                   responses=AdminWorkflowSerializer(many=True))
    def get(self, request):
        counts = _job_counts()
        return Response([_row(st, counts) for st in registry.list_apps()])


class AdminWorkflowInstallView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_workflows_install', request=InstallSerializer,
                   responses={201: AdminWorkflowDetailSerializer})
    def post(self, request):
        ser = InstallSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            wf = registry.install(**ser.validated_data)
            st = registry.get_status(wf.id)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        except ValueError as exc:
            return error_response(str(exc), 'invalid', 400)
        return Response(_row(st, _job_counts(), with_yaml=True), status=201)


class AdminWorkflowSyncView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_workflows_sync', request=None,
                   responses=AdminWorkflowSerializer(many=True))
    def post(self, request):
        counts = _job_counts()
        return Response([_row(st, counts) for st in registry.sync_all()])


class AdminWorkflowDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_workflows_retrieve',
                   responses=AdminWorkflowDetailSerializer)
    def get(self, request, workflow_id):
        try:
            st = registry.get_status(workflow_id)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        return Response(_row(st, _job_counts(), with_yaml=True))

    @extend_schema(operation_id='admin_workflows_update', request=AdminWorkflowPatchSerializer,
                   responses=AdminWorkflowDetailSerializer)
    def patch(self, request, workflow_id):
        ser = AdminWorkflowPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            st = registry.update_access(workflow_id, **ser.validated_data)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        return Response(_row(st, _job_counts(), with_yaml=True))

    @extend_schema(operation_id='admin_workflows_uninstall', responses={204: None})
    def delete(self, request, workflow_id):
        try:
            registry.uninstall(workflow_id)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        return Response(status=204)


class AdminWorkflowReloadView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_workflows_reload', request=None,
                   responses=AdminWorkflowDetailSerializer)
    def post(self, request, workflow_id):
        try:
            st = registry.reload(workflow_id)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        return Response(_row(st, _job_counts(), with_yaml=True))


class AdminWorkflowNextflowView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_workflows_nextflow_retrieve',
                   responses=AppNextflowSerializer)
    def get(self, request, workflow_id):
        try:
            registry.get_status(workflow_id)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        return Response(_nextflow_payload(workflow_id))

    @extend_schema(operation_id='admin_workflows_nextflow_update', request=AppNextflowSerializer,
                   responses=AppNextflowSerializer)
    def put(self, request, workflow_id):
        try:
            registry.get_status(workflow_id)
        except registry.RegistryError as exc:
            return _registry_error(exc)
        ser = AppNextflowSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            registry.set_nextflow_settings(
                workflow_id, profile=d.get('profile'), work_dir=d.get('work_dir'),
                config_text=d.get('config'), env_text=d.get('env'))
        except registry.RegistryError as exc:
            return _registry_error(exc)
        return Response(_nextflow_payload(workflow_id))
