"""Object-level permissions for tenant management."""
from rest_framework.permissions import BasePermission

from teams.models import TeamMember


class TenantObjectPermission(BasePermission):
    """Re-check tenant access at object level for every detail action."""

    member_actions = {"retrieve", "members", "invite"}
    admin_actions = {"update", "partial_update"}

    @staticmethod
    def _is_platform_admin(user):
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))

    @staticmethod
    def _has_active_role(user, tenant, roles=None):
        memberships = TeamMember.objects.filter(
            tenant=tenant,
            user=user,
            status="active",
        )
        if roles is not None:
            memberships = memberships.filter(role__in=roles)
        return memberships.exists()

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)

        if action in self.admin_actions:
            return self._is_platform_admin(request.user) or self._has_active_role(
                request.user, obj, {"owner"}
            )

        if action == "destroy":
            return self._is_platform_admin(request.user) or self._has_active_role(
                request.user, obj, {"owner"}
            )

        if action in self.member_actions:
            return self._has_active_role(request.user, obj)

        return False
