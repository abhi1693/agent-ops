from rest_framework.permissions import SAFE_METHODS, BasePermission

from users.models import Token
from users.restrictions import (
    get_action_for_method,
    has_model_action_permission,
    is_object_action_allowed,
    resolve_restriction_scope,
)
from users.scopes import get_request_actor_scope


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

        get_request_actor_scope(request)

        if isinstance(request.auth, Token) and not self._verify_write_permission(request):
            return False

        return True

    def has_object_permission(self, request, view, obj):
        get_request_actor_scope(request)
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


class IsStaffOrScopedReadOnlyUser(BasePermission):
    """
    Permit full access for staff and read-only access for authenticated users with
    an active tenant scope.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        if request.method not in SAFE_METHODS:
            return False
        return get_request_actor_scope(request) is not None

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


def _get_view_model(view):
    serializer_class = getattr(view, "serializer_class", None)
    if serializer_class is not None:
        meta = getattr(serializer_class, "Meta", None)
        if meta is not None and getattr(meta, "model", None) is not None:
            return meta.model

    queryset = getattr(view, "queryset", None)
    if queryset is not None:
        return queryset.model

    return None


class ObjectActionPermission(BasePermission):
    """
    Enforce action-aware access to a model using actor scope restrictions and
    object-permission constraints.
    """

    def _verify_write_permission(self, request):
        return bool(request.method in SAFE_METHODS or request.auth.write_enabled)

    def _get_permission_action(self, request, view):
        view_action = getattr(view, "get_permission_action", None)
        if callable(view_action):
            return view_action()
        return get_action_for_method(request.method)

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        actor_scope = resolve_restriction_scope(request=request)
        if actor_scope is None:
            return False

        if isinstance(request.auth, Token) and not self._verify_write_permission(request):
            return False

        model = _get_view_model(view)
        if model is None:
            return actor_scope.is_staff or request.method in SAFE_METHODS

        action = self._get_permission_action(request, view)
        return has_model_action_permission(
            model,
            actor_scope=actor_scope,
            action=action,
        )

    def has_object_permission(self, request, view, obj):
        if isinstance(request.auth, Token) and not self._verify_write_permission(request):
            return False

        action = self._get_permission_action(request, view)
        return is_object_action_allowed(
            obj,
            request=request,
            action=action,
        )
