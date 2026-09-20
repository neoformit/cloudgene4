import json
import yaml
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class WorkflowCategory(models.Model):
    """
    Categories for organizing workflows
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'workflow_categories'
        verbose_name_plural = 'Workflow Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Workflow(models.Model):
    """
    Represents a Nextflow workflow that can be executed
    """
    STATUS_CHOICES = [
        ('enabled', 'Enabled'),
        ('disabled', 'Disabled'),
        ('maintenance', 'Maintenance'),
    ]

    id = models.CharField(max_length=255, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50, default='1.0.0')
    website = models.URLField(blank=True)
    category = models.ForeignKey(WorkflowCategory, on_delete=models.CASCADE, null=True, blank=True)
    
    # Workflow configuration
    yaml_config = models.TextField(help_text="YAML configuration for the workflow")
    nextflow_script = models.TextField(blank=True, help_text="Path to the Nextflow script")
    config_file = models.TextField(blank=True, help_text="Path to the Nextflow config file")
    
    # Registry bookkeeping (workflows/registry.py). The row is a *cache* of the app's
    # cloudgene.yaml + its settings.yaml `apps[]` entry, which is the source of truth for
    # enabled/public/groups. Rows with an empty app_path were not created by the registry
    # (e.g. in tests) and are never touched by a sync.
    app_path = models.TextField(blank=True, default='',
                                help_text="Resolved path of the app's cloudgene.yaml")
    errors = models.JSONField(default=list, blank=True,
                              help_text='Validation errors from the last sync (empty = valid)')
    installed = models.BooleanField(default=True,
                                    help_text='False once removed from settings.yaml apps[]')
    synced_at = models.DateTimeField(null=True, blank=True)

    # Status and permissions
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enabled')
    allowed_groups = models.ManyToManyField('auth.Group', blank=True, 
                                          help_text="Groups that can access this workflow")
    public = models.BooleanField(default=False, help_text="Publicly accessible to all users")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'workflows'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    # --- compatibility / convenience -------------------------------------------------

    @property
    def enabled(self):
        return self.status == 'enabled'

    @property
    def app_location(self):
        """Directory of the app (where cloudgene.yaml and the scripts live)."""
        from pathlib import Path
        return str(Path(self.app_path).parent) if self.app_path else ''

    def nextflow_settings(self):
        """Per-app Nextflow settings (see workflows.registry.get_nextflow_settings)."""
        from . import registry
        return registry.get_nextflow_settings(self.id)

    # Former DB columns, now stored in settings.yaml apps[] / $CLOUDGENE_HOME/apps/<id>/.
    @property
    def nextflow_profile(self):
        return self.nextflow_settings()['profile']

    @property
    def working_directory(self):
        return self.nextflow_settings()['work_dir']

    @property
    def nextflow_config(self):
        return self.nextflow_settings()['config']

    @property
    def env_vars(self):
        return self.nextflow_settings()['env']

    def get_config(self):
        """Parse and return the YAML configuration"""
        if not self.yaml_config.strip():
            return {}
        try:
            return yaml.safe_load(self.yaml_config) or {}
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML configuration: {e}")
    
    def get_inputs(self):
        """Get workflow input parameters from configuration"""
        config = self.get_config()
        return config.get('workflow', {}).get('inputs', [])
    
    def get_outputs(self):
        """Get workflow output parameters from configuration"""
        config = self.get_config()
        return config.get('workflow', {}).get('outputs', [])
    
    def get_steps(self):
        """Get workflow steps from configuration"""
        config = self.get_config()
        return config.get('workflow', {}).get('steps', [])
    
    def can_access(self, user):
        """Check if user can access this workflow"""
        if not user.is_authenticated:
            return False
        
        if self.public:
            return True
        
        if user.is_superuser or user.is_admin_user():
            return True
        
        # Check group membership
        user_groups = user.groups.all()
        return self.allowed_groups.filter(id__in=[g.id for g in user_groups]).exists()
