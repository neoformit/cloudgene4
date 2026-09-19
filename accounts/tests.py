"""
Unit tests for accounts app
"""
import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

from .models import UserToken

User = get_user_model()


class UserModelTest(TestCase):
    """Test cases for the custom User model"""
    
    def setUp(self):
        self.user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'full_name': 'Test User',
            'password': 'TestPass123'
        }
    
    def test_create_user(self):
        """Test creating a user with valid data"""
        user = User.objects.create_user(**self.user_data)
        
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.full_name, 'Test User')
        self.assertTrue(user.check_password('TestPass123'))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
    
    def test_create_superuser(self):
        """Test creating a superuser"""
        user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='AdminPass123',
            full_name='Admin User'
        )
        
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
    
    def test_username_validation(self):
        """Test username validation rules"""
        # Test valid usernames
        self.assertIsNone(User.validate_username('user123'))
        self.assertIsNone(User.validate_username('TestUser'))
        
        # Test invalid usernames
        self.assertIsNotNone(User.validate_username(''))  # Empty
        self.assertIsNotNone(User.validate_username('usr'))  # Too short
        self.assertIsNotNone(User.validate_username('user@test'))  # Invalid chars
        self.assertIsNotNone(User.validate_username('user-123'))  # Invalid chars
    
    def test_email_validation(self):
        """Test email validation rules"""
        # Test valid emails
        self.assertIsNone(User.validate_email('test@example.com'))
        self.assertIsNone(User.validate_email('user.name+tag@domain.co.uk'))
        
        # Test invalid emails
        self.assertIsNotNone(User.validate_email(''))  # Empty
        self.assertIsNotNone(User.validate_email('invalid-email'))  # No @
        self.assertIsNotNone(User.validate_email('user@'))  # No domain
        self.assertIsNotNone(User.validate_email('@domain.com'))  # No user
    
    def test_password_validation(self):
        """Test password validation rules"""
        # Test valid passwords
        self.assertIsNone(User.validate_password('TestPass123', 'TestPass123'))
        
        # Test invalid passwords
        self.assertIsNotNone(User.validate_password('', ''))  # Empty
        self.assertIsNotNone(User.validate_password('short', 'short'))  # Too short
        self.assertIsNotNone(User.validate_password('password', 'different'))  # Mismatch
        self.assertIsNotNone(User.validate_password('NoNumbers', 'NoNumbers'))  # No numbers
        self.assertIsNotNone(User.validate_password('nouppercase123', 'nouppercase123'))  # No uppercase
        self.assertIsNotNone(User.validate_password('NOLOWERCASE123', 'NOLOWERCASE123'))  # No lowercase
    
    def test_has_group(self):
        """Test group membership checking"""
        user = User.objects.create_user(**self.user_data)
        group = Group.objects.create(name='test_group')
        
        self.assertFalse(user.has_group('test_group'))
        
        user.groups.add(group)
        self.assertTrue(user.has_group('test_group'))
        self.assertFalse(user.has_group('nonexistent_group'))
    
    def test_is_admin_user(self):
        """Test admin user detection"""
        user = User.objects.create_user(**self.user_data)
        self.assertFalse(user.is_admin_user())
        
        # Test superuser
        superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='AdminPass123',
            full_name='Admin User'
        )
        self.assertTrue(superuser.is_admin_user())
        
        # Test admin group membership
        admin_group = Group.objects.create(name='admin')
        user.groups.add(admin_group)
        self.assertTrue(user.is_admin_user())
    
    def test_make_admin(self):
        """Test making a user an admin"""
        user = User.objects.create_user(**self.user_data)
        self.assertFalse(user.is_admin_user())
        self.assertFalse(user.is_staff)
        
        user.make_admin()
        
        self.assertTrue(user.is_admin_user())
        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_group('admin'))


class UserTokenTest(TestCase):
    """Test cases for UserToken model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            full_name='Test User',
            password='TestPass123'
        )
    
    def test_create_token(self):
        """Test creating a user token"""
        token = UserToken.objects.create(
            user=self.user,
            token=str(uuid.uuid4()),
            name='test_token'
        )
        
        self.assertEqual(token.user, self.user)
        self.assertEqual(token.name, 'test_token')
        self.assertIsNotNone(token.token)
        self.assertIsNotNone(token.created_at)
        self.assertIsNone(token.expires_at)
        self.assertFalse(token.is_expired())
    
    def test_token_expiration(self):
        """Test token expiration"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Create expired token
        token = UserToken.objects.create(
            user=self.user,
            token=str(uuid.uuid4()),
            name='expired_token',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        
        self.assertTrue(token.is_expired())
        
        # Create non-expired token
        token2 = UserToken.objects.create(
            user=self.user,
            token=str(uuid.uuid4()),
            name='valid_token',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        self.assertFalse(token2.is_expired())


class AuthenticationAPITest(APITestCase):
    """Test cases for authentication API endpoints"""
    
    def setUp(self):
        self.user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'full_name': 'Test User',
            'password': 'TestPass123'
        }
        self.user = User.objects.create_user(**self.user_data)
        self.user.is_active = True
        self.user.save()
    
    def test_user_registration(self):
        """Test user registration via API"""
        url = reverse('register')
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'full_name': 'New User',
            'password': 'NewPass123',
            'password_confirm': 'NewPass123'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertIn('message', response.data)
        
        # Check user was created
        user = User.objects.get(username='newuser')
        self.assertEqual(user.email, 'newuser@example.com')
        self.assertFalse(user.is_active)  # Should require activation
        self.assertIsNotNone(user.activation_key)
    
    def test_user_registration_validation(self):
        """Test registration validation"""
        url = reverse('register')
        
        # Test password mismatch
        data = {
            'username': 'testuser2',
            'email': 'test2@example.com',
            'full_name': 'Test User 2',
            'password': 'TestPass123',
            'password_confirm': 'DifferentPass123'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test duplicate username
        data = {
            'username': 'testuser',  # Already exists
            'email': 'another@example.com',
            'full_name': 'Another User',
            'password': 'TestPass123',
            'password_confirm': 'TestPass123'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_user_login(self):
        """Test user login via API"""
        url = reverse('login')
        data = {
            'username': 'testuser',
            'password': 'TestPass123'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'user'})
        self.assertEqual(response.data['user']['username'], 'testuser')
    
    def test_user_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        url = reverse('login')
        data = {
            'username': 'testuser',
            'password': 'wrongpassword'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_user_logout(self):
        """Test user logout via API"""
        self.client.force_authenticate(user=self.user)
        url = reverse('logout')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
    
    def test_account_activation(self):
        """Test account activation"""
        # Create inactive user
        user = User.objects.create_user(
            username='inactiveuser',
            email='inactive@example.com',
            full_name='Inactive User',
            password='TestPass123'
        )
        user.is_active = False
        user.activation_key = str(uuid.uuid4())
        user.save()
        
        url = reverse('activate_account', kwargs={'activation_key': user.activation_key})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check user is now active
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertIsNone(user.activation_key)
    
    def test_invalid_activation_key(self):
        """Test activation with invalid key"""
        url = reverse('activate_account', kwargs={'activation_key': 'invalid-key'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


class UserViewSetTest(APITestCase):
    """Test cases for User ViewSet"""
    
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
    
    def test_user_list_permission(self):
        """Test user list permissions"""
        url = reverse('user-list')
        
        # Unauthenticated request (may return 401 or 403 depending on authentication backend)
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        
        # Regular user can only see themselves
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['username'], 'testuser')
        
        # Admin user can see all users
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 2)
