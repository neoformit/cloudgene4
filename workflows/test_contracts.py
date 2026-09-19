"""
Contract tests for workflows API endpoints.

These tests validate workflow listing, detail views, and admin settings API contracts.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Workflow, WorkflowCategory, WorkflowParameter

User = get_user_model()


class WorkflowListContractTest(APITestCase):
    """Contract tests for workflow listing"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            full_name='Test User'
        )
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='AdminPass123!',
            full_name='Admin User'
        )
        self.admin.make_admin()
        
        # Create test group and assign to user
        self.test_group = Group.objects.create(name='test-group')
        self.user.groups.add(self.test_group)
        
        # Create public workflow
        self.public_workflow = Workflow.objects.create(
            id='public-workflow',
            name='Public Workflow',
            description='A public workflow',
            status='enabled',
            public=True,
            yaml_config='workflow:\n  name: Public Workflow'
        )
        
        # Create group-restricted workflow
        self.private_workflow = Workflow.objects.create(
            id='private-workflow',
            name='Private Workflow',
            description='A group-restricted workflow',
            status='enabled',
            public=False,
            yaml_config='workflow:\n  name: Private Workflow'
        )
        self.private_workflow.allowed_groups.add(self.test_group)
        
        # Create disabled workflow
        self.disabled_workflow = Workflow.objects.create(
            id='disabled-workflow',
            name='Disabled Workflow',
            status='disabled',
            public=True,
            yaml_config='workflow:\n  name: Disabled Workflow'
        )
    
    def test_workflow_list_response_structure(self):
        """Workflow list should have proper pagination structure"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/workflows/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Check if response has results (paginated) or is direct list
        workflows = response_data.get('results', response_data)
        self.assertIsInstance(workflows, list)
        
        # Verify each workflow has required fields
        if workflows:
            workflow = workflows[0]
            required_fields = [
                'id', 'name', 'status', 'inputs', 'outputs',
                'description', 'version', 'public'
            ]
            for field in required_fields:
                self.assertIn(field, workflow)
    
    def test_unauthenticated_user_sees_only_public_workflows(self):
        """Unauthenticated users should only see public, enabled workflows"""
        response = self.client.get('/api/workflows/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        workflows = response_data.get('results', response_data)
        
        # Should only see public workflow
        workflow_ids = [w['id'] for w in workflows]
        self.assertIn('public-workflow', workflow_ids)
        self.assertNotIn('private-workflow', workflow_ids)
        self.assertNotIn('disabled-workflow', workflow_ids)
    
    def test_authenticated_user_sees_accessible_workflows(self):
        """Authenticated users should see public workflows and group-accessible ones"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/workflows/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        workflows = response_data.get('results', response_data)
        
        workflow_ids = [w['id'] for w in workflows]
        self.assertIn('public-workflow', workflow_ids)
        self.assertIn('private-workflow', workflow_ids)  # User is in test-group
        self.assertNotIn('disabled-workflow', workflow_ids)  # Disabled workflows hidden
    
    def test_admin_sees_all_enabled_workflows(self):
        """Admin users should see all enabled workflows"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/workflows/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        workflows = response_data.get('results', response_data)
        
        workflow_ids = [w['id'] for w in workflows]
        self.assertIn('public-workflow', workflow_ids)
        self.assertIn('private-workflow', workflow_ids)
        self.assertNotIn('disabled-workflow', workflow_ids)  # Still hidden even for admin


class WorkflowDetailContractTest(APITestCase):
    """Contract tests for workflow detail view"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            full_name='Test User'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='TestPass123!',
            full_name='Other User'
        )
        
        # Create test group and add user to it
        self.test_group = Group.objects.create(name='test-group')
        self.user.groups.add(self.test_group)
        
        # Inputs/outputs come from the definition (cloudgene.yaml), SPEC §4
        self.workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            description='A test workflow',
            version='1.0.0',
            status='enabled',
            public=False,
            yaml_config=(
                'id: test-workflow\nname: Test Workflow\nworkflow:\n'
                '  steps: [{script: main.nf}]\n'
                '  inputs:\n    - {id: input_param, description: Input Parameter, type: text}\n'
                '  outputs:\n    - {id: output_param, description: Output Parameter, type: file}\n'
            ),
        )
        self.workflow.allowed_groups.add(self.test_group)

    def test_workflow_detail_response_has_required_fields(self):
        """Workflow detail should have all required fields"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/workflows/test-workflow/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        required_fields = [
            'id', 'name', 'description', 'version',
            'inputs', 'outputs', 'status', 'public', 'definition_errors'
        ]
        
        for field in required_fields:
            self.assertIn(field, response_data)
    
    def test_inputs_contains_only_input_parameters(self):
        """inputs field should only contain parameters with is_input=True"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/workflows/test-workflow/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        inputs = response_data['inputs']
        self.assertIsInstance(inputs, list)
        
        # Should only contain input parameter
        input_ids = [param['id'] for param in inputs]
        self.assertIn('input_param', input_ids)
        self.assertNotIn('output_param', input_ids)
    
    def test_outputs_contains_only_output_parameters(self):
        """outputs field should only contain parameters with is_output=True"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/workflows/test-workflow/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        outputs = response_data['outputs']
        self.assertIsInstance(outputs, list)
        
        # Should only contain output parameter
        output_ids = [param['id'] for param in outputs]
        self.assertIn('output_param', output_ids)
        self.assertNotIn('input_param', output_ids)
    
    def test_non_member_user_gets_404_for_private_workflow(self):
        """Non-group member should get 404 for group-restricted workflow"""
        self.client.force_authenticate(user=self.other_user)
        
        response = self.client.get('/api/workflows/test-workflow/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_unauthenticated_user_gets_404_for_private_workflow(self):
        """Unauthenticated user should get 404 for private workflow"""
        response = self.client.get('/api/workflows/test-workflow/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class WorkflowSettingsContractTest(APITestCase):
    """Contract tests for admin workflow settings"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            full_name='Test User'
        )
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='AdminPass123!',
            full_name='Admin User'
        )
        self.admin.make_admin()
        
        # Create test groups
        self.group1 = Group.objects.create(name='group1')
        self.group2 = Group.objects.create(name='group2')
        
        # Create workflow
        self.workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            description='A test workflow',
            status='enabled',
            public=False,
            yaml_config='workflow:\n  name: Test Workflow'
        )
        self.workflow.allowed_groups.add(self.group1)
    
    def test_admin_can_get_workflow_settings(self):
        """Admin should be able to get workflow settings"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/workflows/test-workflow/settings/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Verify settings fields are present
        settings_fields = [
            'id', 'name', 'description', 'status', 'public', 'allowed_groups',
            'nextflow_profile', 'working_directory', 'env_vars', 'nextflow_config'
        ]
        
        for field in settings_fields:
            self.assertIn(field, response_data)
    
    def test_admin_can_update_workflow_settings(self):
        """Admin should be able to update workflow settings"""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'public': True,
            'nextflow_profile': 'docker',
            'working_directory': '/tmp/work'
        }
        
        response = self.client.patch('/api/admin/workflows/test-workflow/settings/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify update was applied
        self.workflow.refresh_from_db()
        self.assertTrue(self.workflow.public)
        self.assertEqual(self.workflow.nextflow_profile, 'docker')
        self.assertEqual(self.workflow.working_directory, '/tmp/work')
    
    def test_admin_can_update_allowed_groups(self):
        """Admin should be able to update allowed groups"""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'allowed_group_names': ['group1', 'group2']
        }
        
        response = self.client.patch('/api/admin/workflows/test-workflow/settings/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify groups were updated
        group_names = list(self.workflow.allowed_groups.values_list('name', flat=True))
        self.assertIn('group1', group_names)
        self.assertIn('group2', group_names)
    
    def test_non_admin_cannot_access_workflow_settings(self):
        """Non-admin user should not be able to access workflow settings"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/workflows/test-workflow/settings/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_non_admin_cannot_update_workflow_settings(self):
        """Non-admin user should not be able to update workflow settings"""
        self.client.force_authenticate(user=self.user)
        
        data = {'public': True}
        
        response = self.client.patch('/api/admin/workflows/test-workflow/settings/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)