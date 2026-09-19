"""
Workflow management views
"""
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from core.permissions import IsAdmin, is_admin
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework.exceptions import ValidationError
from .models import Workflow, WorkflowCategory
from .serializers import WorkflowSerializer, WorkflowCategorySerializer, WorkflowSettingsSerializer


class WorkflowViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for browsing workflows.
    Unauthenticated users see only public workflows.
    Authenticated users also see workflows for their groups.
    Admins see all enabled workflows.
    """
    serializer_class = WorkflowSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user = self.request.user
        queryset = Workflow.objects.filter(status='enabled')

        if user is None or not user.is_authenticated:
            queryset = queryset.filter(public=True)
        elif not is_admin(user):
            queryset = queryset.filter(
                Q(public=True) |
                Q(allowed_groups__in=user.groups.all())
            ).distinct()

        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__name=category)

        return queryset.order_by('name')


class WorkflowCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkflowCategory.objects.all()
    serializer_class = WorkflowCategorySerializer
    permission_classes = [AllowAny]


class WorkflowAdminViewSet(viewsets.ModelViewSet):
    """
    Admin ViewSet for managing workflow settings
    """
    queryset = Workflow.objects.all()
    serializer_class = WorkflowSettingsSerializer
    permission_classes = [IsAdmin]


class WorkflowSettingsAPIView(APIView):
    """
    API view for workflow settings management
    """
    permission_classes = [IsAdmin]
    
    def get(self, request, workflow_id):
        """Get workflow settings"""
        workflow = get_object_or_404(Workflow, id=workflow_id)
        serializer = WorkflowSettingsSerializer(workflow)
        return Response(serializer.data)
    
    def patch(self, request, workflow_id):
        """Update workflow settings"""
        workflow = get_object_or_404(Workflow, id=workflow_id)
        serializer = WorkflowSettingsSerializer(workflow, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        
        raise ValidationError(serializer.errors)
