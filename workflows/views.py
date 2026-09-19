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
from .serializers import WorkflowSerializer, WorkflowCategorySerializer


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
