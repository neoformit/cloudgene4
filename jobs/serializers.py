"""
Serializers for job-related API endpoints
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Job, JobStep, JobMessage, JobDownload
from workflows.models import Workflow

User = get_user_model()


class JobStepSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = JobStep
        fields = ['id', 'name', 'description', 'step_type', 'status', 
                 'started_at', 'completed_at', 'duration', 'order', 'output', 'error_output']
        read_only_fields = fields
    
    def get_duration(self, obj):
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class JobMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobMessage
        fields = ['id', 'message_type', 'message', 'created_at']
        read_only_fields = fields


class JobDownloadSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = JobDownload
        fields = ['id', 'filename', 'file_size', 'file_size_mb', 'download_count', 
                 'created_at', 'expires_at', 'is_expired']
        read_only_fields = fields
    
    def get_file_size_mb(self, obj):
        return round(obj.file_size / (1024 * 1024), 2)
    
    def get_is_expired(self, obj):
        return obj.is_expired()


class JobListSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    duration = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_restart = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = ['id', 'name', 'workflow_name', 'user_username', 'status', 
                 'submitted_at', 'started_at', 'completed_at', 'duration',
                 'priority', 'queue_position', 'can_cancel', 'can_restart']
        read_only_fields = fields
    
    def get_duration(self, obj):
        duration = obj.get_duration()
        return duration.total_seconds() if duration else None
    
    def get_can_cancel(self, obj):
        return obj.can_cancel()
    
    def get_can_restart(self, obj):
        return obj.can_restart()


class JobDetailSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    steps = JobStepSerializer(many=True, read_only=True)
    messages = JobMessageSerializer(many=True, read_only=True)
    downloads = JobDownloadSerializer(many=True, read_only=True)
    duration = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_restart = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = ['id', 'name', 'workflow_name', 'user_username', 'status',
                 'submitted_at', 'started_at', 'completed_at', 'duration',
                 'parameters', 'results', 'logs', 'error_message',
                 'priority', 'queue_position', 'workspace_dir',
                 'steps', 'messages', 'downloads', 'can_cancel', 'can_restart']
        read_only_fields = ['id', 'submitted_at', 'started_at', 'completed_at',
                          'status', 'results', 'logs', 'error_message',
                          'priority', 'queue_position', 'workspace_dir']
    
    def get_duration(self, obj):
        duration = obj.get_duration()
        return duration.total_seconds() if duration else None
    
    def get_can_cancel(self, obj):
        return obj.can_cancel()
    
    def get_can_restart(self, obj):
        return obj.can_restart()


class JobSubmissionSerializer(serializers.ModelSerializer):
    workflow_id = serializers.CharField(write_only=True)
    
    class Meta:
        model = Job
        fields = ['workflow_id', 'name', 'parameters']
    
    def to_internal_value(self, data):
        """
        Handle FormData by converting it to the expected format
        """
        # If data is FormData (multipart form), extract parameters
        if hasattr(data, 'getlist'):
            # This is FormData - extract parameters into a dict
            parameters = {}
            workflow_id = data.get('workflow_id')
            job_name = data.get('job_name')
            
            # Process all fields except special ones
            for key in data.keys():
                if key not in ['workflow_id', 'job_name']:
                    values = data.getlist(key)
                    if len(values) == 1:
                        parameters[key] = values[0]
                    else:
                        parameters[key] = values
            
            # Create structured data
            structured_data = {
                'workflow_id': workflow_id,
                'name': job_name,
                'parameters': parameters
            }
            
            return super().to_internal_value(structured_data)
        
        return super().to_internal_value(data)
    
    def validate_workflow_id(self, value):
        try:
            workflow = Workflow.objects.get(id=value, status='enabled')
        except Workflow.DoesNotExist:
            raise serializers.ValidationError("Workflow not found or disabled")
        
        # Check if user has access to this workflow
        user = self.context['request'].user
        if not workflow.can_access(user):
            raise serializers.ValidationError("You don't have permission to access this workflow")
        
        return value
    
    def validate_parameters(self, value):
        # Ensure value is a dictionary for validation
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                raise serializers.ValidationError("Value must be valid JSON.")
        
        if not isinstance(value, dict):
            raise serializers.ValidationError("Parameters must be a dictionary.")
        
        # Validate parameters against workflow inputs
        workflow_id = self.initial_data.get('workflow_id')
        if workflow_id:
            try:
                workflow = Workflow.objects.get(id=workflow_id)
                # Get workflow parameters from the model
                workflow_params = workflow.parameters.filter(is_input=True)
                
                required_params = [
                    param.parameter_id for param in workflow_params 
                    if param.required
                ]
                
                for param_id in required_params:
                    if param_id not in value or not value[param_id]:
                        raise serializers.ValidationError(
                            f"Required parameter '{param_id}' is missing"
                        )
                
            except Workflow.DoesNotExist:
                pass  # Will be caught by workflow_id validation
        
        return value
    
    def create(self, validated_data):
        workflow_id = validated_data.pop('workflow_id')
        workflow = Workflow.objects.get(id=workflow_id)
        
        job = Job.objects.create(
            workflow=workflow,
            user=self.context['request'].user,
            **validated_data
        )
        
        # Submit job to queue
        from .queue import job_queue
        job_queue.submit_job(job)
        
        return job