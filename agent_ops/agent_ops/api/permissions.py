from rest_framework.permissions import SAFE_METHODS, BasePermission

from users.models import Token


class TokenPermissions(BasePermission):
    """
    Require authentication and enforce write_enabled for token-authenticated unsafe requests.
    """

    def _verify_write_permission(self, request):
        return bool(request.method in SAFE_METHODS or request.auth.write_enabled)

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if isinstance(request.auth, Token) and not self._verify_write_permission(request):
            return False

        return True

    def has_object_permission(self, request, view, obj):
        if isinstance(request.auth, Token) and not self._verify_write_permission(request):
            return False
        return bool(request.user and request.user.is_authenticated)


class IsStaffUser(BasePermission):
    """
    Restrict access to staff and superusers.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))
