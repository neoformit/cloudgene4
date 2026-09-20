"""
Contract tests for accounts API endpoints.

These tests validate authentication, registration, and user management API contracts.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
# PasswordResetToken is implemented as User model fields

User = get_user_model()


class AuthContractTest(APITestCase):
    """Contract tests for authentication endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            full_name='Test User',
            is_active=True
        )
    
    def test_valid_login_returns_user_and_session(self):
        """Valid credentials start a session and return the user (no token; SPEC §3.4)"""
        data = {
            'username': 'testuser',
            'password': 'TestPass123!'
        }
        
        response = self.client.post('/api/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Verify response has required fields
        self.assertEqual(set(response_data), {'user'})
        self.assertIn('sessionid', response.cookies)
        
        # Verify user object structure
        user_data = response_data['user']
        required_user_fields = ['id', 'username', 'email', 'full_name', 'is_admin']
        for field in required_user_fields:
            self.assertIn(field, user_data)
    
    def test_missing_username_returns_400_with_username_error(self):
        """Missing username should return 400 with username in error"""
        data = {'password': 'TestPass123!'}
        
        response = self.client.post('/api/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('username', response_data['error']['fields'])
    
    def test_missing_password_returns_400_with_password_error(self):
        """Missing password should return 400 with password in error"""
        data = {'username': 'testuser'}
        
        response = self.client.post('/api/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('password', response_data['error']['fields'])
    
    def test_wrong_credentials_returns_400(self):
        """Wrong credentials should return 400"""
        data = {
            'username': 'testuser',
            'password': 'wrongpassword'
        }
        
        response = self.client.post('/api/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_logout_returns_200(self):
        """Authenticated logout should return 200"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post('/api/auth/logout/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RegistrationContractTest(APITestCase):
    """Contract tests for user registration"""
    
    def test_valid_registration_returns_201_with_user(self):
        """Valid registration returns 201 with the (inactive) user; no token"""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'StrongPass123',
            'full_name': 'New User'
        }
        
        response = self.client.post('/api/auth/register/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        self.assertIn('user', response_data)
        self.assertNotIn('token', response_data)
        self.assertFalse(response_data['user']['is_active'])
        
        # Verify user was created
        user = User.objects.get(username='newuser')
        self.assertEqual(user.email, 'new@example.com')
    
    def test_missing_username_returns_400_with_username_error(self):
        """Missing username should return 400 with username in error"""
        data = {
            'email': 'new@example.com',
            'password': 'strongpass123'
        }
        
        response = self.client.post('/api/auth/register/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('username', response_data['error']['fields'])
    
    def test_missing_email_returns_400_with_email_error(self):
        """Missing email should return 400 with email in error"""
        data = {
            'username': 'newuser',
            'password': 'strongpass123'
        }
        
        response = self.client.post('/api/auth/register/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('email', response_data['error']['fields'])
    
    def test_missing_password_returns_400_with_password_error(self):
        """Missing password should return 400 with password in error"""
        data = {
            'username': 'newuser',
            'email': 'new@example.com'
        }
        
        response = self.client.post('/api/auth/register/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('password', response_data['error']['fields'])
    
    def test_invalid_email_format_returns_400_with_email_error(self):
        """Invalid email format should return 400 with email in error"""
        data = {
            'username': 'newuser',
            'email': 'invalid-email',
            'password': 'strongpass123'
        }
        
        response = self.client.post('/api/auth/register/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('email', response_data['error']['fields'])
    
    def test_duplicate_username_returns_400_with_username_error(self):
        """Duplicate username should return 400 with username in error"""
        # Create existing user
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='TestPass123!',
            full_name='Existing User'
        )
        
        data = {
            'username': 'existinguser',  # Duplicate
            'email': 'new@example.com',
            'password': 'strongpass123'
        }
        
        response = self.client.post('/api/auth/register/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('username', response_data['error']['fields'])


class PasswordResetContractTest(APITestCase):
    """Contract tests for password reset endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            full_name='Test User',
            is_active=True
        )
    
    def test_valid_email_returns_200(self):
        """Valid email should return 200"""
        data = {'email': 'test@example.com'}
        
        response = self.client.post('/api/auth/password-reset/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify reset token was created (stored in user.password_reset_token)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.password_reset_token)
    
    def test_missing_email_returns_400_with_email_error(self):
        """Missing email should return 400 with email in error"""
        data = {}
        
        response = self.client.post('/api/auth/password-reset/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('email', response_data['error']['fields'])
    
    def test_unknown_email_returns_same_200(self):
        """Unknown email gets the same answer as a known one (no enumeration, A5)"""
        known = self.client.post('/api/auth/password-reset/', {'email': 'test@example.com'},
                                  format='json')
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'unknown@example.com'},
                                   format='json')
        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(known.json(), unknown.json())


class UserUpdateContractTest(APITestCase):
    """Contract tests for user update endpoints"""
    
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
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='AdminPass123!',
            full_name='Admin User'
        )
        self.admin.make_admin()
    
    def test_user_can_update_own_profile(self):
        """User should be able to update their own profile"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'full_name': 'Updated Name',
            'email': 'updated@example.com'
        }
        
        data['current_password'] = 'TestPass123!'  # e-mail change needs it
        response = self.client.patch('/api/me/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify update was applied
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'Updated Name')
    
    def test_user_cannot_update_another_users_profile(self):
        """Non-admins cannot reach the admin user endpoint"""
        self.client.force_authenticate(user=self.user)
        
        data = {'full_name': 'Hacked Name'}
        
        response = self.client.patch(f'/api/admin/users/{self.other_user.id}/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.other_user.refresh_from_db()
        self.assertNotEqual(self.other_user.full_name, 'Hacked Name')
    
    def test_admin_can_update_any_user(self):
        """Admin should be able to update any user"""
        self.client.force_authenticate(user=self.admin)
        
        data = {'is_active': False}

        response = self.client.patch(f'/api/admin/users/{self.other_user.id}/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class GroupContractTest(APITestCase):
    """Contract tests for group management"""
    
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
    
    def test_admin_can_create_group_with_valid_data(self):
        """Admin should be able to create group with valid data"""
        self.client.force_authenticate(user=self.admin)
        
        data = {'name': 'test-group'}
        
        response = self.client.post('/api/admin/groups/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        
        # Verify response has required fields
        self.assertIn('id', response_data)
        self.assertIn('name', response_data)
        self.assertEqual(response_data['name'], 'test-group')
    
    def test_missing_group_name_returns_400_with_name_error(self):
        """Missing group name should return 400 with name in error"""
        self.client.force_authenticate(user=self.admin)
        
        data = {}
        
        response = self.client.post('/api/admin/groups/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('name', response_data['error']['fields'])
    
    def test_non_admin_cannot_create_group(self):
        """Non-admin user should not be able to create groups"""
        self.client.force_authenticate(user=self.user)
        
        data = {'name': 'test-group'}
        
        response = self.client.post('/api/admin/groups/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)