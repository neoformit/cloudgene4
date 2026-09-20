"""Serializers for the admin panel API (SPEC §3.6)."""
from rest_framework import serializers

from .models import SystemLog


# --- settings -----------------------------------------------------------------------------

class GeneralSettingsSerializer(serializers.Serializer):
    """``server.*`` keys of settings.yaml. PUT accepts any subset (others unchanged)."""

    name = serializers.CharField(max_length=100, required=False)
    url = serializers.CharField(max_length=500, allow_blank=True, required=False)
    max_running_jobs = serializers.IntegerField(min_value=1, required=False)
    max_queue_size = serializers.IntegerField(min_value=0, required=False)
    job_retention_days = serializers.IntegerField(min_value=0, required=False)
    max_upload_mb = serializers.IntegerField(min_value=1, required=False)
    maintenance = serializers.BooleanField(required=False)
    maintenance_message = serializers.CharField(max_length=2000, allow_blank=True,
                                                required=False)

    def validate_url(self, value):
        value = value.strip()
        if value and not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError('Must start with http:// or https://.')
        return value.rstrip('/')


class MailSettingsSerializer(serializers.Serializer):
    """``mail.*``. ``password`` is write-only: never returned; empty/absent = unchanged
    (use ``clear_password: true`` to remove it). ``password_set`` tells whether one exists."""

    backend = serializers.ChoiceField(choices=['smtp', 'file', 'console'], required=False)
    file_path = serializers.CharField(max_length=500, required=False)
    host = serializers.CharField(max_length=255, allow_blank=True, required=False)
    port = serializers.IntegerField(min_value=1, max_value=65535, required=False)
    user = serializers.CharField(max_length=255, allow_blank=True, required=False)
    password = serializers.CharField(max_length=255, allow_blank=True, required=False,
                                     write_only=True, trim_whitespace=False)
    clear_password = serializers.BooleanField(required=False, write_only=True)
    password_set = serializers.BooleanField(read_only=True)
    use_tls = serializers.BooleanField(required=False)
    use_ssl = serializers.BooleanField(required=False)
    from_email = serializers.EmailField(required=False)

    def validate(self, attrs):
        if attrs.get('use_tls') and attrs.get('use_ssl'):
            raise serializers.ValidationError({'use_ssl': ['TLS and SSL are mutually exclusive.']})
        return attrs


class MailTestSerializer(serializers.Serializer):
    to = serializers.EmailField(required=False,
                                help_text="Recipient (default: the admin's own e-mail)")


class MailTestResultSerializer(serializers.Serializer):
    message = serializers.CharField()
    to = serializers.EmailField()


class NextflowSettingsSerializer(serializers.Serializer):
    """``nextflow.*`` plus the global config files."""

    binary = serializers.CharField(max_length=500, required=False)
    profile = serializers.CharField(max_length=255, allow_blank=True, required=False)
    work_dir = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    config = serializers.CharField(allow_blank=True, required=False, trim_whitespace=False,
                                   help_text='Contents of config/nextflow.config')
    env = serializers.CharField(allow_blank=True, required=False, trim_whitespace=False,
                                help_text='Contents of config/nextflow.env (KEY=VALUE lines)')
    variables = serializers.ListField(child=serializers.DictField(), read_only=True)


class NavbarItemSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=100)
    url = serializers.CharField(max_length=500)
    icon = serializers.CharField(max_length=100, allow_blank=True, required=False, default='')
    admin_only = serializers.BooleanField(required=False, default=False)
    auth_only = serializers.BooleanField(required=False, default=False)


class NavbarSerializer(serializers.Serializer):
    navbar = NavbarItemSerializer(many=True)


# --- pages --------------------------------------------------------------------------------

class PageSummarySerializer(serializers.Serializer):
    slug = serializers.CharField()
    size = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    deletable = serializers.BooleanField()


class PageSerializer(serializers.Serializer):
    slug = serializers.CharField(read_only=True)
    html = serializers.CharField(allow_blank=True, trim_whitespace=False)
    deletable = serializers.BooleanField(read_only=True)


# --- dashboard / queue --------------------------------------------------------------------

class WorkerStatusSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    last_seen = serializers.DateTimeField(allow_null=True)
    age_seconds = serializers.FloatField(allow_null=True)
    pid = serializers.IntegerField(allow_null=True)


class QueueStatusSerializer(serializers.Serializer):
    paused = serializers.BooleanField()
    maintenance = serializers.BooleanField()
    maintenance_message = serializers.CharField(allow_blank=True)
    running = serializers.IntegerField()
    waiting = serializers.IntegerField()
    max_running = serializers.IntegerField()
    max_queue = serializers.IntegerField()
    worker = WorkerStatusSerializer()


class MaintenanceRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000, required=False, allow_blank=True,
                                    help_text='New banner text (optional)')


class JobCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    waiting = serializers.IntegerField()
    running = serializers.IntegerField()
    success = serializers.IntegerField()
    failed = serializers.IntegerField()
    cancelled = serializers.IntegerField()


class UserCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    admins = serializers.IntegerField()


class WorkflowCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    enabled = serializers.IntegerField()
    disabled = serializers.IntegerField()
    invalid = serializers.IntegerField()


class RefSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class UserRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class RecentJobSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    state = serializers.CharField()
    workflow = RefSerializer()
    user = UserRefSerializer()
    submitted_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class DashboardSerializer(serializers.Serializer):
    queue = QueueStatusSerializer()
    jobs = JobCountsSerializer()
    users = UserCountsSerializer()
    workflows = WorkflowCountsSerializer()
    recent_jobs = RecentJobSerializer(many=True)


# --- logs ---------------------------------------------------------------------------------

class SystemLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, allow_null=True,
                                     default=None)

    class Meta:
        model = SystemLog
        fields = ['id', 'timestamp', 'level', 'component', 'logger', 'message', 'username',
                  'metadata']
        read_only_fields = fields
