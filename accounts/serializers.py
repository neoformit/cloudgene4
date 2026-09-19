"""
Serializers for account-related API endpoints
"""
import uuid

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group

from .models import User, UserToken


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'is_active',
            'is_staff', 'is_admin', 'date_joined', 'last_login', 'groups',
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']

    def get_is_admin(self, obj) -> bool:
        return obj.is_admin_user()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    # Optional — clients that validate locally need not send it
    password_confirm = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = User
        fields = [
            'username', 'email', 'full_name', 'password', 'password_confirm',
        ]

    def validate(self, data):
        password = data['password']
        password_confirm = data.get('password_confirm', password)

        password_error = User.validate_password(password, password_confirm)
        if password_error:
            raise serializers.ValidationError({'password': password_error})

        username_error = User.validate_username(data['username'])
        if username_error:
            raise serializers.ValidationError({'username': username_error})

        email_error = User.validate_email(data['email'])
        if email_error:
            raise serializers.ValidationError({'email': email_error})

        # Check for duplicate email
        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError({'email': 'A user with this email address already exists.'})

        # Check for duplicate username
        if User.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError({'username': 'A user with this username already exists.'})

        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password')

        user = User.objects.create_user(password=password, **validated_data)
        user.activation_key = str(uuid.uuid4())
        user.is_active = False
        user.save()

        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if not user.is_active:
                    raise serializers.ValidationError(
                        'User account is disabled.'
                    )
                data['user'] = user
            else:
                raise serializers.ValidationError(
                    'Invalid username or password.'
                )
        else:
            raise serializers.ValidationError(
                'Must include username and password.'
            )

        return data


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                'No user found with this email address.'
            )
        return value


class UserTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserToken
        fields = [
            'id', 'name', 'token', 'created_at', 'expires_at', 'last_used',
        ]
        read_only_fields = ['id', 'token', 'created_at', 'last_used']
