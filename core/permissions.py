"""
The one definition of "admin" (plans/SPEC.md §3.4):
superuser OR is_staff OR member of the group named ``admin``.
"""
from rest_framework import permissions

ADMIN_GROUP = 'admin'


def is_admin(user) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name=ADMIN_GROUP).exists()


class IsAdmin(permissions.BasePermission):
    """Allow only admins (see ``is_admin``)."""

    message = 'Administrator privileges are required.'

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrReadOnly(permissions.BasePermission):
    """Safe methods for everyone; writes for admins only."""

    message = IsAdmin.message

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_admin(request.user)
