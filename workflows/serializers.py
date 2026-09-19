"""
Serializers for workflow-related API endpoints
"""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import Workflow, WorkflowCategory


class WorkflowCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowCategory
        fields = ['id', 'name', 'description', 'created_at']


class InputValueSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()


class WorkflowInputSerializer(serializers.Serializer):
    """One run-form input (SPEC §4); built from the parsed definition, not a DB table."""
    id = serializers.CharField()
    type = serializers.CharField()
    label = serializers.CharField()
    value = serializers.JSONField(allow_null=True, help_text='Typed default')
    values = InputValueSerializer(many=True)
    checkbox_values = serializers.DictField(allow_null=True)
    required = serializers.BooleanField()
    visible = serializers.BooleanField()
    help = serializers.CharField(allow_blank=True)
    details = serializers.CharField(allow_blank=True)
    accept = serializers.CharField(allow_blank=True)
    min = serializers.FloatField(allow_null=True)
    max = serializers.FloatField(allow_null=True)
    write_file = serializers.CharField(allow_blank=True)
    serialize = serializers.BooleanField()


class WorkflowOutputSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    label = serializers.CharField()
    download = serializers.BooleanField()
    serialize = serializers.BooleanField()


class WorkflowSerializer(serializers.ModelSerializer):
    """Public workflow (list/detail) incl. the typed run-form schema from cloudgene.yaml."""
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    author = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    inputs = serializers.SerializerMethodField()
    outputs = serializers.SerializerMethodField()
    definition_errors = serializers.SerializerMethodField()
    max_upload_mb = serializers.SerializerMethodField()

    class Meta:
        model = Workflow
        fields = ['id', 'name', 'description', 'version', 'website', 'author', 'logo',
                  'category_name', 'status', 'public', 'inputs', 'outputs', 'definition_errors',
                  'max_upload_mb']
        read_only_fields = fields

    def _definition(self, obj):
        cache = self.context.setdefault('_definitions', {})
        if obj.pk not in cache:
            from jobs import workflow_bridge
            from .definition import DefinitionError
            try:
                cache[obj.pk] = (workflow_bridge.get_definition(obj), [])
            except DefinitionError as exc:
                cache[obj.pk] = (None, exc.errors)
        return cache[obj.pk]

    def get_author(self, obj) -> str:
        d, _ = self._definition(obj)
        return d.author if d else ''

    def get_logo(self, obj) -> str:
        d, _ = self._definition(obj)
        return d.logo if d else ''

    @extend_schema_field(WorkflowInputSerializer(many=True))
    def get_inputs(self, obj):
        d, _ = self._definition(obj)
        return [p.to_dict() for p in d.inputs] if d else []

    @extend_schema_field(WorkflowOutputSerializer(many=True))
    def get_outputs(self, obj):
        d, _ = self._definition(obj)
        return [o.to_dict() for o in d.outputs] if d else []

    def get_definition_errors(self, obj) -> list[str]:
        return self._definition(obj)[1]

    def get_max_upload_mb(self, obj) -> int:
        from core import config as cloudgene_config
        return int(cloudgene_config.get('server.max_upload_mb', 1024) or 1024)


class WorkflowSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for admin workflow settings, including Nextflow configuration
    """
    category_name = serializers.CharField(source='category.name', read_only=True)
    allowed_groups = serializers.StringRelatedField(many=True, read_only=True)
    allowed_group_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False,
        help_text="List of group names to assign to this workflow"
    )
    
    class Meta:
        model = Workflow
        fields = ['id', 'name', 'description', 'version', 'website', 'category_name',
                 'status', 'public', 'created_at', 'updated_at', 'allowed_groups', 'allowed_group_names',
                 'nextflow_profile', 'working_directory', 'env_vars', 'nextflow_config']
        read_only_fields = ['id', 'created_at', 'updated_at', 'category_name', 'allowed_groups']
    
    def update(self, instance, validated_data):
        # Handle allowed_group_names separately
        group_names = validated_data.pop('allowed_group_names', None)
        
        # Update other fields
        instance = super().update(instance, validated_data)
        
        # Update group membership if provided
        if group_names is not None:
            from django.contrib.auth.models import Group
            groups = Group.objects.filter(name__in=group_names)
            instance.allowed_groups.set(groups)
        
        return instance