"""
Contract tests for jobs API endpoints.

These tests ensure the API contract is correctly implemented and responses
match expected shapes, catching integration bugs between frontend and backend.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from workflows.models import Workflow, WorkflowCategory, WorkflowParameter
from .models import Job

User = get_user_model()


class JobSubmissionJSONContractTest(APITestCase):
    """Contract tests for JSON job submission"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', 
            email='test@example.com', 
            password='Testpass123',
            full_name='Test User'
        )
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com', 
            password='Admin123',
            full_name='Admin User'
        )
        self.admin.make_admin()
        
        # Create test workflow
        self.workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            description='Test workflow for contract testing',
            status='enabled',
            public=True,
            yaml_config='workflow:\n  name: Test Workflow'
        )
        
        # Create workflow parameters
        self.required_param = WorkflowParameter.objects.create(
            workflow=self.workflow,
            parameter_id='required_param',
            name='Required Parameter',
            parameter_type='text',
            required=True,
            is_input=True
        )
        
        self.optional_param = WorkflowParameter.objects.create(
            workflow=self.workflow,
            parameter_id='optional_param', 
            name='Optional Parameter',
            parameter_type='text',
            required=False,
            is_input=True
        )
    
    def test_valid_json_submission_creates_job(self):
        """Valid JSON payload should create job with correct fields"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'test-workflow',
            'name': 'test-job',
            'parameters': {
                'required_param': 'test-value'
            }
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify response has required fields
        response_data = response.json()
        required_fields = ['id', 'name', 'status', 'parameters', 'workflow_name', 'user_username']
        for field in required_fields:
            self.assertIn(field, response_data)
        
        # Verify job was created correctly
        job = Job.objects.get(id=response_data['id'])
        self.assertEqual(job.name, 'test-job')
        self.assertEqual(job.workflow_id, 'test-workflow')
        self.assertEqual(job.parameters['required_param'], 'test-value')
    
    def test_missing_workflow_id_returns_400_with_field_error(self):
        """Missing workflow_id should return 400 with workflow_id in error"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'name': 'test-job',
            'parameters': {'required_param': 'value'}
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('workflow_id', response_data)
    
    def test_unknown_workflow_id_returns_400_with_workflow_id_error(self):
        """Unknown workflow_id should return 400 with workflow_id error"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'nonexistent-workflow',
            'name': 'test-job',
            'parameters': {'required_param': 'value'}
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('workflow_id', response_data)
    
    def test_missing_required_parameter_returns_400_with_parameters_error(self):
        """Missing required parameter should return 400 with parameters error"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'test-workflow',
            'name': 'test-job',
            'parameters': {}  # Missing required_param
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('parameters', response_data)
        self.assertIn('required_param', str(response_data['parameters']))
    
    def test_invalid_json_in_parameters_returns_400_with_parameters_error(self):
        """Invalid JSON string in parameters should return 400 with clear error message"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'test-workflow',
            'name': 'test-job',
            'parameters': '{invalid: json syntax}'  # Invalid JSON string
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('parameters', response_data)
        self.assertIn('Value must be valid JSON', str(response_data['parameters']))
    
    def test_non_dict_parameters_returns_400_with_parameters_error(self):
        """Non-dictionary parameters value should return 400 with clear error message"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'test-workflow',
            'name': 'test-job',
            'parameters': 'not a dict or json'  # String that's not JSON
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('parameters', response_data)

    def test_unauthenticated_user_returns_401(self):
        """Unauthenticated request should return 401"""
        data = {
            'workflow_id': 'test-workflow',
            'name': 'test-job',
            'parameters': {'required_param': 'value'}
        }
        
        response = self.client.post('/api/jobs/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class JobSubmissionFormDataContractTest(APITestCase):
    """Contract tests for FormData job submission"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com', 
            password='Testpass123',
            full_name='Test User'
        )
        
        self.workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            status='enabled',
            public=True,
            yaml_config='workflow:\n  name: Test Workflow'
        )
        
        self.required_param = WorkflowParameter.objects.create(
            workflow=self.workflow,
            parameter_id='text_param',
            name='Text Parameter',
            parameter_type='text',
            required=True,
            is_input=True
        )
    
    def test_valid_formdata_submission_creates_job(self):
        """Valid FormData should create job correctly"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'test-workflow',
            'job_name': 'formdata-test-job',
            'text_param': 'test-value'
        }
        
        response = self.client.post('/api/jobs/', data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        response_data = response.json()
        job = Job.objects.get(id=response_data['id'])
        
        # Verify FormData fields extracted correctly
        self.assertEqual(job.name, 'formdata-test-job')
        self.assertEqual(job.workflow_id, 'test-workflow')
        self.assertEqual(job.parameters['text_param'], 'test-value')
    
    def test_missing_required_param_in_formdata_returns_400(self):
        """Missing required param in FormData should return 400 with parameters error"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'workflow_id': 'test-workflow',
            'job_name': 'test-job'
            # Missing text_param
        }
        
        response = self.client.post('/api/jobs/', data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('parameters', response_data)


class JobActionContractTest(APITestCase):
    """Contract tests for job actions (cancel, restart)"""
    
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
            password='Testpass123',
            full_name='Other User'
        )
        
        self.workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            status='enabled',
            public=True
        )
        
        self.job = Job.objects.create(
            workflow=self.workflow,
            user=self.user,
            name='test-job',
            status='pending',
            parameters={}
        )
    
    def test_cancel_own_pending_job_returns_200(self):
        """User can cancel their own pending job"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post(f'/api/jobs/{self.job.id}/cancel/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIn('message', response_data)
    
    def test_cancel_other_users_job_returns_403(self):
        """User cannot cancel another user's job"""
        self.client.force_authenticate(user=self.other_user)
        
        response = self.client.post(f'/api/jobs/{self.job.id}/cancel/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class JobResponseShapeTest(APITestCase):
    """Test job response contains all required fields"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            full_name='Test User'
        )
        
        self.workflow = Workflow.objects.create(
            id='test-workflow',
            name='Test Workflow',
            status='enabled',
            public=True
        )
        
        self.job = Job.objects.create(
            workflow=self.workflow,
            user=self.user,
            name='test-job',
            status='pending',
            parameters={'test_param': 'value'}
        )
    
    def test_job_detail_response_has_required_fields(self):
        """GET /api/jobs/{id}/ response has all required fields"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get(f'/api/jobs/{self.job.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        required_fields = [
            'id', 'name', 'status', 'parameters', 'steps', 
            'messages', 'downloads', 'can_cancel', 'can_restart',
            'workflow_name', 'user_username', 'submitted_at'
        ]
        
        for field in required_fields:
            self.assertIn(field, response_data, f"Missing required field: {field}")
        
        # Verify field types
        self.assertIsInstance(response_data['steps'], list)
        self.assertIsInstance(response_data['messages'], list)
        self.assertIsInstance(response_data['downloads'], list)
        self.assertIsInstance(response_data['can_cancel'], bool)
        self.assertIsInstance(response_data['can_restart'], bool)
        self.assertIsInstance(response_data['parameters'], dict)