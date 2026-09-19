"""
YAML configuration loader for Cloudgene workflows
"""
import os
import yaml
from django.conf import settings
from django.core.exceptions import ValidationError
from .models import Workflow, WorkflowParameter, WorkflowCategory


class CloudgeneConfigLoader:
    """
    Loads and validates Cloudgene configuration from YAML files
    """
    
    def __init__(self, config_path=None):
        # settings.yaml is owned by core.config; this legacy loader only reads it.
        from core import config as cloudgene_config
        self.config_path = config_path or cloudgene_config.settings_path()
        self.config = None
    
    def load_config(self):
        """Load configuration from YAML file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as file:
                    self.config = yaml.safe_load(file)
            else:
                self.config = self._get_default_config()
            return self.config
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML configuration: {e}")
    
    def save_config(self):
        """Save configuration to YAML file"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as file:
                yaml.dump(self.config, file, default_flow_style=False, indent=2)
        except Exception as e:
            raise ValidationError(f"Failed to save configuration: {e}")
    
    def validate_workflow_config(self, workflow_config):
        """Validate a workflow configuration"""
        required_fields = ['id', 'name', 'workflow']
        
        for field in required_fields:
            if field not in workflow_config:
                raise ValidationError(f"Missing required field: {field}")
        
        # Validate workflow section
        workflow = workflow_config.get('workflow', {})
        if 'steps' not in workflow:
            raise ValidationError("Workflow must have 'steps' section")
        
        # Validate inputs and outputs
        self._validate_parameters(workflow.get('inputs', []), 'input')
        self._validate_parameters(workflow.get('outputs', []), 'output')
        
        return True
    
    def _validate_parameters(self, parameters, param_type):
        """Validate workflow parameters"""
        valid_types = ['file', 'folder', 'text', 'number', 'checkbox', 'list', 'textarea']
        
        for param in parameters:
            if not isinstance(param, dict):
                raise ValidationError(f"Invalid {param_type} parameter format")
            
            if 'id' not in param:
                raise ValidationError(f"Missing 'id' in {param_type} parameter")
            
            if 'type' in param and param['type'] not in valid_types:
                raise ValidationError(f"Invalid parameter type: {param['type']}")
    
    def load_workflow_from_yaml(self, yaml_content):
        """Load workflow from YAML content"""
        try:
            workflow_config = yaml.safe_load(yaml_content)
            self.validate_workflow_config(workflow_config)
            return self._create_workflow_from_config(workflow_config)
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML: {e}")
    
    def _create_workflow_from_config(self, config):
        """Create or update workflow from configuration"""
        # Get or create workflow
        workflow_data = {
            'name': config['name'],
            'description': config.get('description', ''),
            'version': config.get('version', '1.0.0'),
            'website': config.get('website', ''),
            'yaml_config': yaml.dump(config, default_flow_style=False),
        }
        
        # Handle category
        if 'category' in config:
            category, created = WorkflowCategory.objects.get_or_create(
                name=config['category'],
                defaults={'description': f'Category for {config["category"]} workflows'}
            )
            workflow_data['category'] = category
        
        workflow, created = Workflow.objects.update_or_create(
            id=config['id'],
            defaults=workflow_data
        )
        
        # Clear existing parameters
        workflow.parameters.all().delete()
        
        # Add input parameters
        for i, input_param in enumerate(config.get('workflow', {}).get('inputs', [])):
            self._create_parameter(workflow, input_param, True, False, i)
        
        # Add output parameters
        for i, output_param in enumerate(config.get('workflow', {}).get('outputs', [])):
            self._create_parameter(workflow, output_param, False, True, i)
        
        return workflow
    
    def _create_parameter(self, workflow, param_config, is_input, is_output, order):
        """Create a workflow parameter from configuration"""
        WorkflowParameter.objects.create(
            workflow=workflow,
            parameter_id=param_config['id'],
            name=param_config.get('description', param_config['id']),
            description=param_config.get('description', ''),
            parameter_type=param_config.get('type', 'text'),
            required=param_config.get('required', True),
            default_value=param_config.get('value', ''),
            values=param_config.get('values', {}),
            is_input=is_input,
            is_output=is_output,
            order=order,
        )
    
    def _get_default_config(self):
        """Get default configuration"""
        return {
            'server': {
                'name': 'Cloudgene Server',
                'port': 8080,
                'maintenance': False,
                'max_jobs': 10,
                'max_queue_size': 50,
            },
            'navbar': [
                {'title': 'Home', 'url': '/', 'order': 1},
                {'title': 'Jobs', 'url': '/jobs', 'order': 2},
                {'title': 'Admin', 'url': '/admin', 'order': 3, 'admin_only': True},
            ],
            'templates': {
                'home': 'Welcome to Cloudgene',
                'footer': 'Powered by Cloudgene',
            },
            'mail': {
                'smtp_host': '',
                'smtp_port': 587,
                'smtp_user': '',
                'smtp_password': '',
                'from_email': 'noreply@cloudgene.io',
            },
            'nextflow': {
                'binary': 'nextflow',
                'work_dir': '/tmp/nextflow-work',
                'config_file': '',
            },
        }
    
    def get_server_settings(self):
        """Get server settings from configuration"""
        if not self.config:
            self.load_config()
        return self.config.get('server', {})
    
    def get_navbar_items(self):
        """Get navbar items from configuration"""
        if not self.config:
            self.load_config()
        return self.config.get('navbar', [])
    
    def get_mail_settings(self):
        """Get mail settings from configuration"""
        if not self.config:
            self.load_config()
        return self.config.get('mail', {})
    
    def get_nextflow_settings(self):
        """Get Nextflow settings from configuration"""
        if not self.config:
            self.load_config()
        return self.config.get('nextflow', {})