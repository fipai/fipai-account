from rest_framework.permissions import BasePermission, SAFE_METHODS


class PublicReadEditorialWrite(BasePermission):
    message = 'Content editing requires an authenticated editorial user.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
