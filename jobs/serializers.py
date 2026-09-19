"""
Response serializers for the jobs API (plans/SPEC.md §3.6). Submission is validated in
``jobs/submission.py`` against the workflow definition; ``JobSubmitRequestSerializer`` only
documents the multipart request for the OpenAPI schema.
"""
from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Job, JobMessage, JobOutput, JobState, JobStep


class ProcessProgressSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    submitted = serializers.IntegerField()
    running = serializers.IntegerField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    total = serializers.IntegerField()


class JobStepSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source='status')
    processes = ProcessProgressSerializer(many=True)

    class Meta:
        model = JobStep
        fields = ['id', 'order', 'name', 'state', 'started_at', 'finished_at', 'processes']
        read_only_fields = fields


class JobMessageSerializer(serializers.ModelSerializer):
    step = serializers.IntegerField(source='step_id', allow_null=True)

    class Meta:
        model = JobMessage
        fields = ['id', 'level', 'text', 'step', 'created_at']
        read_only_fields = fields


class JobOutputSerializer(serializers.ModelSerializer):
    name = serializers.CharField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = JobOutput
        fields = ['id', 'output_id', 'label', 'name', 'path', 'size', 'download_count', 'url']
        read_only_fields = fields

    def get_url(self, obj) -> str:
        return reverse('job-output-download', kwargs={'pk': str(obj.job_id), 'file_id': obj.id})


class JobInputSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    type = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    files = serializers.ListField(child=serializers.DictField(), help_text='[{name, size}] for uploads')


class JobListSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source='status', help_text='waiting|running|success|failed|cancelled')
    workflow_id = serializers.CharField(source='app_id')
    workflow_name = serializers.CharField(source='app_name')
    workflow_version = serializers.CharField(source='app_version')
    user = serializers.CharField(source='user.username')
    user_id = serializers.IntegerField()
    queue_position = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_restart = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = ['id', 'name', 'state', 'workflow_id', 'workflow_name', 'workflow_version',
                  'user', 'user_id', 'submitted_at', 'started_at', 'finished_at',
                  'duration_seconds', 'queue_position', 'cancel_requested', 'expires_at',
                  'purged_at', 'can_cancel', 'can_delete', 'can_restart']
        read_only_fields = fields

    def get_queue_position(self, obj) -> int | None:
        return obj.queue_position()

    def get_duration_seconds(self, obj) -> float | None:
        return obj.duration_seconds()

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_expires_at(self, obj):
        return obj.expires_at()

    def get_can_cancel(self, obj) -> bool:
        return obj.can_cancel()

    def get_can_delete(self, obj) -> bool:
        return obj.can_delete()

    def get_can_restart(self, obj) -> bool:
        """Restart is an admin action (``POST /api/admin/jobs/{id}/restart``)."""
        return obj.can_restart()


class JobStatusSerializer(JobListSerializer):
    """Light payload polled by the job page every 2 s while the job is active."""
    steps = JobStepSerializer(many=True)
    messages = JobMessageSerializer(many=True)
    outputs_count = serializers.SerializerMethodField()

    class Meta(JobListSerializer.Meta):
        fields = JobListSerializer.Meta.fields + ['updated_at', 'error_message', 'steps', 'messages',
                                                  'outputs_count']
        read_only_fields = fields

    def get_outputs_count(self, obj) -> int:
        return obj.outputs.count()


class JobDetailSerializer(JobStatusSerializer):
    inputs = serializers.SerializerMethodField()
    outputs = JobOutputSerializer(many=True)
    log_url = serializers.SerializerMethodField()

    class Meta(JobStatusSerializer.Meta):
        fields = JobStatusSerializer.Meta.fields + ['inputs', 'outputs', 'log_url']
        read_only_fields = fields

    def get_log_url(self, obj) -> str:
        return reverse('job-log', kwargs={'pk': str(obj.id)})

    @extend_schema_field(JobInputSerializer(many=True))
    def get_inputs(self, obj):
        from . import workflow_bridge
        try:
            definition = workflow_bridge.definition_from_yaml(obj.workflow_yaml)
        except Exception:
            return [{'id': k, 'label': k, 'type': 'text', 'value': v, 'files': []}
                    for k, v in (obj.parameters or {}).items()]
        out = []
        for p in definition.value_inputs:
            if not p.visible or p.id not in (obj.parameters or {}):
                continue
            value = obj.parameters[p.id]
            files = [{'name': f.get('name'), 'size': f.get('size')}
                     for f in (obj.uploads or {}).get(p.id, [])]
            if p.is_file:
                value = ', '.join(f['name'] for f in files)
            elif p.type == 'textarea' and p.write_file:
                value = p.write_file
            elif p.type in ('list', 'radio'):
                value = next((v['label'] for v in p.values if v['key'] == value), value)
            out.append({'id': p.id, 'label': p.label, 'type': p.type, 'value': value, 'files': files})
        return out


class JobSubmitRequestSerializer(serializers.Serializer):
    workflow = serializers.CharField(help_text='Workflow id')
    job_name = serializers.CharField(required=False, allow_blank=True, max_length=255,
                                     help_text='Optional free-text name (default: "<workflow> <date>")')
    # Additional fields: one per workflow input id (files as multipart file parts).


class JobDeletedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    deleted = serializers.BooleanField()


STATE_CHOICES = list(JobState.ALL)
