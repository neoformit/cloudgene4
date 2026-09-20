"""
Unit tests for workflows app
"""
import yaml
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

from .models import Workflow, WorkflowCategory

User = get_user_model()


class WorkflowCategoryTest(TestCase):
    """Test cases for WorkflowCategory model"""
    
    def test_create_category(self):
        """Test creating a workflow category"""
        category = WorkflowCategory.objects.create(
            name='bioinformatics',
            description='Bioinformatics workflows'
        )
        
        self.assertEqual(category.name, 'bioinformatics')
        self.assertEqual(category.description, 'Bioinformatics workflows')
        self.assertIsNotNone(category.created_at)
        self.assertEqual(str(category), 'bioinformatics')


class WorkflowTest(TestCase):
    """Test cases for Workflow model"""
    
    def setUp(self):
        self.category = WorkflowCategory.objects.create(
            name='test',
            description='Test category'
        )
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            full_name='Test User',
            password='TestPass123'
        )
        self.group = Group.objects.create(name='test_group')
        
        self.workflow_config = {
            'id': 'test-workflow',
            'name': 'Test Workflow',
            'description': 'A test workflow',
            'version': '1.0.0',
            'category': 'test',
            'workflow': {
                'steps': [
                    {'name': 'TestStep', 'classname': 'test.TestStep'}
                ],
                'inputs': [
                    {
                        'id': 'input_text',
                        'description': 'Input text',
                        'type': 'text',
                        'required': True
                    }
                ],
                'outputs': [
                    {
                        'id': 'output_file',
                        'description': 'Output file',
                        'type': 'file',
                        'download': True
                    }
                ]
            }
        }
    
    def test_create_workflow(self):
        """Test creating a workflow"""
        workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            description='A test workflow',
            category=self.category,
            yaml_config=yaml.dump(self.workflow_config),
            created_by=self.user
        )
        
        self.assertEqual(workflow.id, 'test-workflow')
        self.assertEqual(workflow.name, 'Test Workflow')
        self.assertEqual(workflow.category, self.category)
        self.assertEqual(workflow.created_by, self.user)
        self.assertEqual(workflow.status, 'enabled')
        self.assertFalse(workflow.public)
        self.assertEqual(str(workflow), 'Test Workflow (v1.0.0)')
    
    def test_get_config(self):
        """Test parsing YAML configuration"""
        workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            yaml_config=yaml.dump(self.workflow_config)
        )
        
        config = workflow.get_config()
        self.assertEqual(config['id'], 'test-workflow')
        self.assertEqual(config['name'], 'Test Workflow')
        self.assertIn('workflow', config)
    
    def test_invalid_yaml_config(self):
        """Test invalid YAML configuration"""
        workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            yaml_config='invalid: yaml: content: ['  # Invalid YAML
        )
        
        with self.assertRaises(ValidationError):
            workflow.get_config()
    
    def test_get_inputs_outputs(self):
        """Test getting workflow inputs and outputs"""
        workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            yaml_config=yaml.dump(self.workflow_config)
        )
        
        inputs = workflow.get_inputs()
        outputs = workflow.get_outputs()
        
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0]['id'], 'input_text')
        self.assertEqual(inputs[0]['type'], 'text')
        
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]['id'], 'output_file')
        self.assertEqual(outputs[0]['type'], 'file')
    
    def test_can_access_public_workflow(self):
        """Test access to public workflow"""
        workflow = Workflow.objects.create(
            id='public-workflow',
            name='Public Workflow',
            yaml_config=yaml.dump(self.workflow_config),
            public=True
        )
        
        # Any authenticated user should be able to access public workflow
        self.assertTrue(workflow.can_access(self.user))
    
    def test_can_access_group_restricted_workflow(self):
        """Test access to group-restricted workflow"""
        workflow = Workflow.objects.create(
            id='restricted-workflow',
            name='Restricted Workflow',
            yaml_config=yaml.dump(self.workflow_config),
            public=False
        )
        workflow.allowed_groups.add(self.group)
        
        # User not in group should not have access
        self.assertFalse(workflow.can_access(self.user))
        
        # User in group should have access
        self.user.groups.add(self.group)
        self.assertTrue(workflow.can_access(self.user))
    
    def test_admin_access(self):
        """Test admin user access to any workflow"""
        workflow = Workflow.objects.create(
            id='admin-test-workflow',
            name='Admin Test Workflow',
            yaml_config=yaml.dump(self.workflow_config),
            public=False
        )
        
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='AdminPass123',
            full_name='Admin User'
        )
        
        self.assertTrue(workflow.can_access(admin_user))
    
    def test_unauthenticated_access(self):
        """Test unauthenticated user access"""
        workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            yaml_config=yaml.dump(self.workflow_config),
            public=True
        )
        
        from django.contrib.auth.models import AnonymousUser
        anonymous_user = AnonymousUser()
        
        self.assertFalse(workflow.can_access(anonymous_user))


class WorkflowAPITest(APITestCase):
    """Test cases for Workflow API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            full_name='Test User',
            password='TestPass123'
        )
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='AdminPass123',
            full_name='Admin User'
        )
        
        self.category = WorkflowCategory.objects.create(
            name='test',
            description='Test category'
        )
        
        self.group = Group.objects.create(name='test_group')
        self.user.groups.add(self.group)
        
        # Create public workflow
        self.public_workflow = Workflow.objects.create(
            id='public-workflow',
            name='Public Workflow',
            description='A public workflow',
            category=self.category,
            yaml_config='test: config',
            public=True,
            status='enabled'
        )
        
        # Create group-restricted workflow
        self.restricted_workflow = Workflow.objects.create(
            id='restricted-workflow',
            name='Restricted Workflow',
            description='A restricted workflow',
            category=self.category,
            yaml_config='test: config',
            public=False,
            status='enabled'
        )
        self.restricted_workflow.allowed_groups.add(self.group)
        
        # Create disabled workflow
        self.disabled_workflow = Workflow.objects.create(
            id='disabled-workflow',
            name='Disabled Workflow',
            description='A disabled workflow',
            category=self.category,
            yaml_config='test: config',
            status='disabled'
        )
    
    def test_workflow_list_unauthenticated(self):
        """Test workflow list without authentication"""
        url = reverse('workflow-list')
        response = self.client.get(url)
        
        # Anonymous users may browse, but only public + enabled workflows
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [w['id'] for w in response.data['results']]
        self.assertNotIn(self.restricted_workflow.id, ids)
        self.assertNotIn(self.disabled_workflow.id, ids)
    
    def test_workflow_list_authenticated(self):
        """Test workflow list with authentication"""
        self.client.force_authenticate(user=self.user)
        url = reverse('workflow-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should see public and accessible restricted workflows, but not disabled
        workflow_ids = [w['id'] for w in response.data['results']]
        self.assertIn('public-workflow', workflow_ids)
        self.assertIn('restricted-workflow', workflow_ids)
        self.assertNotIn('disabled-workflow', workflow_ids)
    
    def test_workflow_list_admin(self):
        """Test workflow list as admin"""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('workflow-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Admin should see all enabled workflows
        workflow_ids = [w['id'] for w in response.data['results']]
        self.assertIn('public-workflow', workflow_ids)
        self.assertIn('restricted-workflow', workflow_ids)
        self.assertNotIn('disabled-workflow', workflow_ids)
    
    def test_workflow_detail(self):
        """Test workflow detail endpoint"""
        self.client.force_authenticate(user=self.user)
        url = reverse('workflow-detail', kwargs={'pk': 'public-workflow'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], 'public-workflow')
        self.assertEqual(response.data['name'], 'Public Workflow')
    
    def test_workflow_list_category_filter(self):
        """Test workflow list with category filter"""
        self.client.force_authenticate(user=self.user)
        url = reverse('workflow-list') + '?category=test'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # All returned workflows should be in test category
        for workflow in response.data['results']:
            self.assertEqual(workflow['category_name'], 'test')
    
    def test_category_list(self):
        """Test workflow category list"""
        self.client.force_authenticate(user=self.user)
        url = reverse('category-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)
        
        category_names = [c['name'] for c in response.data['results']]
        self.assertIn('test', category_names)
