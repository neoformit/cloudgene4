"""
Contract tests for admin panel API endpoints.

These tests validate admin dashboard, server settings, templates, navbar items,
system logs, and counters API contracts.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase
from rest_framework import status
from .models import ServerSettings, Template, NavbarItem, SystemLog, Counter
from workflows.models import Workflow
from jobs.models import Job

User = get_user_model()


class AdminDashboardContractTest(APITestCase):
    """Contract tests for admin dashboard endpoint"""
    
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
        
        # Create test data
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
        
        self.log = SystemLog.objects.create(
            level='info',
            message='Test log message',
            component='test',
            user=self.user
        )
    
    def test_admin_can_access_dashboard(self):
        """Admin should be able to access dashboard with statistics"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/dashboard/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Verify dashboard structure
        required_fields = ['statistics', 'recent_jobs', 'recent_logs']
        for field in required_fields:
            self.assertIn(field, response_data)
        
        # Verify statistics structure
        stats = response_data['statistics']
        self.assertIn('jobs', stats)
        self.assertIn('users', stats)
        self.assertIn('workflows', stats)
        
        # Verify job statistics
        job_stats = stats['jobs']
        job_stat_fields = ['total', 'pending', 'running', 'completed', 'failed', 'cancelled']
        for field in job_stat_fields:
            self.assertIn(field, job_stats)
        
        # Verify user statistics
        user_stats = stats['users']
        user_stat_fields = ['total', 'active', 'staff']
        for field in user_stat_fields:
            self.assertIn(field, user_stats)
        
        # Verify workflow statistics
        workflow_stats = stats['workflows']
        workflow_stat_fields = ['total', 'enabled', 'disabled']
        for field in workflow_stat_fields:
            self.assertIn(field, workflow_stats)
        
        # Verify recent jobs structure
        recent_jobs = response_data['recent_jobs']
        self.assertIsInstance(recent_jobs, list)
        
        # Verify recent logs structure
        recent_logs = response_data['recent_logs']
        self.assertIsInstance(recent_logs, list)
    
    def test_non_admin_cannot_access_dashboard(self):
        """Non-admin user should not be able to access dashboard"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/dashboard/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ServerSettingsContractTest(APITestCase):
    """Contract tests for server settings management"""
    
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
        
        self.setting = ServerSettings.objects.create(
            name='test_setting',
            value='test_value',
            description='Test setting',
            setting_type='string',
            category='general'
        )
    
    def test_admin_can_list_server_settings(self):
        """Admin should be able to list server settings"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/server-settings/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Check if response has results (paginated) or is direct list
        settings = response_data.get('results', response_data)
        self.assertIsInstance(settings, list)
        
        if settings:
            setting = settings[0]
            required_fields = ['id', 'name', 'value', 'description', 'setting_type', 'category']
            for field in required_fields:
                self.assertIn(field, setting)
    
    def test_admin_can_create_server_setting(self):
        """Admin should be able to create server setting"""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'name': 'new_setting',
            'value': 'new_value',
            'description': 'New test setting',
            'setting_type': 'string',
            'category': 'general'
        }
        
        response = self.client.post('/api/admin/server-settings/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify setting was created
        setting = ServerSettings.objects.get(name='new_setting')
        self.assertEqual(setting.value, 'new_value')
    
    def test_admin_can_update_server_setting(self):
        """Admin should be able to update server setting"""
        self.client.force_authenticate(user=self.admin)
        
        data = {'value': 'updated_value'}
        
        response = self.client.patch(f'/api/admin/server-settings/{self.setting.id}/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify update was applied
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, 'updated_value')
    
    def test_missing_name_returns_400_with_name_error(self):
        """Missing name should return 400 with name in error"""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'value': 'test_value',
            'setting_type': 'string'
        }
        
        response = self.client.post('/api/admin/server-settings/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('name', response_data)
    
    def test_non_admin_cannot_access_server_settings(self):
        """Non-admin user should not be able to access server settings"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/server-settings/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TemplateContractTest(APITestCase):
    """Contract tests for template management"""
    
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
        
        self.template = Template.objects.create(
            name='test_template',
            content='<h1>Test Template</h1>',
            description='Test template',
            template_type='page'
        )
    
    def test_anyone_can_list_templates(self):
        """Any user should be able to list templates"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/templates/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        templates = response_data.get('results', response_data)
        self.assertIsInstance(templates, list)
        
        if templates:
            template = templates[0]
            required_fields = ['id', 'name', 'content', 'description', 'template_type', 'created_at', 'updated_at']
            for field in required_fields:
                self.assertIn(field, template)
    
    def test_admin_can_create_template(self):
        """Admin should be able to create template"""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'name': 'new_template',
            'content': '<h1>New Template</h1>',
            'description': 'New test template',
            'template_type': 'page'
        }
        
        response = self.client.post('/api/admin/templates/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify template was created
        template = Template.objects.get(name='new_template')
        self.assertEqual(template.content, '<h1>New Template</h1>')
    
    def test_non_admin_cannot_create_template(self):
        """Non-admin user should not be able to create template"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'name': 'unauthorized_template',
            'content': '<h1>Unauthorized</h1>',
            'template_type': 'page'
        }
        
        response = self.client.post('/api/admin/templates/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_admin_can_update_template(self):
        """Admin should be able to update template"""
        self.client.force_authenticate(user=self.admin)
        
        data = {'content': '<h1>Updated Template</h1>'}
        
        response = self.client.patch(f'/api/admin/templates/{self.template.id}/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify update was applied
        self.template.refresh_from_db()
        self.assertEqual(self.template.content, '<h1>Updated Template</h1>')


class NavbarItemContractTest(APITestCase):
    """Contract tests for navbar item management"""
    
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
        
        self.navbar_item = NavbarItem.objects.create(
            title='Test Link',
            url='/test/',
            icon='test-icon',
            order=1,
            visible=True
        )
    
    def test_anyone_can_list_navbar_items(self):
        """Any user should be able to list navbar items"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/navbar-items/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        navbar_items = response_data.get('results', response_data)
        self.assertIsInstance(navbar_items, list)
        
        if navbar_items:
            item = navbar_items[0]
            required_fields = ['id', 'title', 'url', 'icon', 'order', 'visible', 'admin_only']
            for field in required_fields:
                self.assertIn(field, item)
    
    def test_admin_can_create_navbar_item(self):
        """Admin should be able to create navbar item"""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'title': 'New Link',
            'url': '/new/',
            'icon': 'new-icon',
            'order': 2,
            'visible': True
        }
        
        response = self.client.post('/api/admin/navbar-items/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify navbar item was created
        item = NavbarItem.objects.get(title='New Link')
        self.assertEqual(item.url, '/new/')
    
    def test_non_admin_cannot_create_navbar_item(self):
        """Non-admin user should not be able to create navbar item"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'title': 'Unauthorized Link',
            'url': '/unauthorized/',
            'order': 3
        }
        
        response = self.client.post('/api/admin/navbar-items/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SystemLogContractTest(APITestCase):
    """Contract tests for system log viewing"""
    
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
        
        self.log = SystemLog.objects.create(
            level='info',
            message='Test log message',
            component='test',
            user=self.user,
            metadata={'key': 'value'}
        )
    
    def test_admin_can_list_system_logs(self):
        """Admin should be able to list system logs"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/system-logs/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        logs = response_data.get('results', response_data)
        self.assertIsInstance(logs, list)
        
        if logs:
            log = logs[0]
            required_fields = ['id', 'timestamp', 'level', 'message', 'component', 'metadata']
            for field in required_fields:
                self.assertIn(field, log)
    
    def test_admin_can_filter_logs_by_level(self):
        """Admin should be able to filter logs by level"""
        # Create additional logs
        SystemLog.objects.create(level='error', message='Error message', component='test')
        SystemLog.objects.create(level='warning', message='Warning message', component='test')
        
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/system-logs/?level=error')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        logs = response_data.get('results', response_data)
        
        # Should only return error logs
        for log in logs:
            self.assertEqual(log['level'], 'error')
    
    def test_admin_can_filter_logs_by_component(self):
        """Admin should be able to filter logs by component"""
        # Create log with different component
        SystemLog.objects.create(level='info', message='Job message', component='jobs')
        
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/system-logs/?component=jobs')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        logs = response_data.get('results', response_data)
        
        # Should only return jobs component logs
        for log in logs:
            self.assertEqual(log['component'], 'jobs')
    
    def test_non_admin_cannot_access_system_logs(self):
        """Non-admin user should not be able to access system logs"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/system-logs/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CounterContractTest(APITestCase):
    """Contract tests for counter viewing"""
    
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
        
        self.counter = Counter.objects.create(
            name='test_counter',
            value=100,
            description='Test counter'
        )
    
    def test_admin_can_list_counters(self):
        """Admin should be able to list counters"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/admin/counters/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        counters = response_data.get('results', response_data)
        self.assertIsInstance(counters, list)
        
        if counters:
            counter = counters[0]
            required_fields = ['id', 'name', 'value', 'description', 'last_updated']
            for field in required_fields:
                self.assertIn(field, counter)
    
    def test_admin_can_get_counter_detail(self):
        """Admin should be able to get counter detail"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get(f'/api/admin/counters/{self.counter.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        self.assertEqual(response_data['name'], 'test_counter')
        self.assertEqual(response_data['value'], 100)
    
    def test_non_admin_cannot_access_counters(self):
        """Non-admin user should not be able to access counters"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/admin/counters/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)