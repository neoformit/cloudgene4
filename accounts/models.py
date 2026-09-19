import re
from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class User(AbstractUser):
    """
    Custom user model based on the original Cloudgene User class
    """
    full_name = models.CharField(max_length=255, blank=True, default='')
    activation_key = models.CharField(max_length=255, blank=True, null=True)
    password_reset_token = models.CharField(
        max_length=255, blank=True, null=True
    )
    password_reset_expires = models.DateTimeField(null=True, blank=True)
    api_token = models.CharField(max_length=255, blank=True, default='')
    last_login_date = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    login_attempts = models.IntegerField(default=0)
    api_token_expires_on = models.DateTimeField(null=True, blank=True)
    accessed_by_api = models.BooleanField(default=False)
    
    # Override to use email as username
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'full_name']

    class Meta:
        db_table = 'users'

    def has_group(self, group_name):
        """Check if user belongs to a specific group"""
        return self.groups.filter(name=group_name).exists()

    def is_admin_user(self):
        """Check if user is an admin (single definition: core.permissions.is_admin)"""
        from core.permissions import is_admin
        return is_admin(self)

    def make_admin(self):
        """Make user an admin"""
        admin_group, created = Group.objects.get_or_create(name='admin')
        self.groups.add(admin_group)
        self.is_staff = True
        self.save()

    def clean(self):
        """Validate user data"""
        super().clean()
        
        # Validate username
        if self.username:
            error = self.validate_username(self.username)
            if error:
                raise ValidationError({'username': error})
        
        # Validate email
        if self.email:
            error = self.validate_email(self.email)
            if error:
                raise ValidationError({'email': error})
        
        # Validate full name
        if not self.full_name:
            raise ValidationError({'full_name': 'The full name is required.'})

    @staticmethod
    def validate_username(username):
        """Validate username according to Cloudgene rules"""
        if not username:
            return "The username is required."
        
        if len(username) < 4:
            return "The username must contain at least four characters."
        
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            return "Your username is not valid. Only characters A-Z, a-z and digits 0-9 are acceptable."
        
        return None

    @staticmethod
    def validate_email(email):
        """Validate email format"""
        if not email:
            return "E-Mail is required."
        
        # More flexible email pattern
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return "Please enter a valid mail address."
        
        return None

    @staticmethod
    def validate_password(password, confirm_password=None):
        """Validate password according to Cloudgene rules"""
        if confirm_password is not None and password != confirm_password:
            return "Please check your passwords."
        
        if not password:
            return "Password is required."
        
        if len(password) < 6:
            return "Password must contain at least six characters!"
        
        if not re.search(r'[0-9]', password):
            return "Password must contain at least one number (0-9)!"
        
        if not re.search(r'[a-z]', password):
            return "Password must contain at least one lowercase letter (a-z)!"
        
        if not re.search(r'[A-Z]', password):
            return "Password must contain at least one uppercase letter (A-Z)!"
        
        return None


class UserGroup(models.Model):
    """
    Custom group model for workflow access control
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_groups'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class UserToken(models.Model):
    """
    API tokens for users
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_tokens')
    token = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'user_tokens'
        ordering = ['-created_at']
    
    def is_expired(self):
        """Check if token is expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def __str__(self):
        return f"{self.name} - {self.user.username}"
