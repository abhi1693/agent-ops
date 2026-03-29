from copy import deepcopy

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView
from rest_framework.views import APIView

from agent_ops.api.permissions import IsStaffUser, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from users import filtersets
from users.models import Group, Membership, ObjectPermission, Token, User
from users.preferences import DEFAULT_USER_PREFERENCES

from .serializers import (
    GroupSerializer,
    MembershipSerializer,
    ObjectPermissionSerializer,
    TokenSerializer,
    UserSerializer,
)


def _deep_merge(base, overlay):
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _get_user_config_data(user):
    return _deep_merge(DEFAULT_USER_PREFERENCES, user.get_config().data)


class UsersRootView(APIRootView):
    def get_view_name(self):
        return "Users"

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "users": reverse("api:users-api:user-list", request=request),
                "groups": reverse("api:users-api:group-list", request=request),
                "memberships": reverse("api:users-api:membership-list", request=request),
                "permissions": reverse("api:users-api:objectpermission-list", request=request),
                "tokens": reverse("api:users-api:token-list", request=request),
                "config": reverse("api:users-api:config", request=request),
            }
        )


class UserViewSet(ModelViewSet):
    queryset = User.objects.prefetch_related(
        "groups",
        "memberships__organization",
        "memberships__workspace",
        "memberships__environment",
        "object_permissions",
        "user_permissions__content_type",
    ).order_by("username")
    serializer_class = UserSerializer
    filterset_class = filtersets.UserFilterSet
    ordering_fields = ("username", "email", "date_joined", "last_login")
    permission_classes = [TokenPermissions, IsStaffUser]


class GroupViewSet(ModelViewSet):
    queryset = Group.objects.prefetch_related(
        "permissions__content_type",
        "object_permissions",
    ).order_by("name")
    serializer_class = GroupSerializer
    filterset_class = filtersets.GroupFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffUser]


class MembershipViewSet(ModelViewSet):
    queryset = Membership.objects.select_related(
        "user",
        "organization",
        "workspace",
        "environment",
    ).prefetch_related(
        "groups",
        "object_permissions",
    ).order_by(
        "user__username",
        "organization__name",
        "workspace__name",
        "environment__name",
    )
    serializer_class = MembershipSerializer
    filterset_class = filtersets.MembershipFilterSet
    ordering_fields = ("user__username", "organization__name", "workspace__name", "environment__name")
    permission_classes = [TokenPermissions, IsStaffUser]


class ObjectPermissionViewSet(ModelViewSet):
    queryset = ObjectPermission.objects.prefetch_related(
        "content_types",
        "groups",
        "memberships",
        "users",
    ).order_by("name")
    serializer_class = ObjectPermissionSerializer
    filterset_class = filtersets.ObjectPermissionFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffUser]


class TokenViewSet(ModelViewSet):
    serializer_class = TokenSerializer
    filterset_class = filtersets.TokenFilterSet
    ordering_fields = ("created", "expires", "last_used")
    permission_classes = [TokenPermissions]

    def get_queryset(self):
        return self.request.user.tokens.select_related(
            "user",
            "scope_membership__organization",
            "scope_membership__workspace",
            "scope_membership__environment",
        ).order_by("-created")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserConfigView(APIView):
    permission_classes = [TokenPermissions]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(_get_user_config_data(request.user))

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request):
        if not isinstance(request.data, dict):
            raise serializers.ValidationError("Request body must be a JSON object.")

        user_config = request.user.get_config()
        user_config.data = _deep_merge(user_config.data, request.data)
        user_config.save()
        return Response(_get_user_config_data(request.user))
