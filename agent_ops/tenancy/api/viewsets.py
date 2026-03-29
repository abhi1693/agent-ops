from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView

from agent_ops.api.permissions import ObjectActionPermission, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from tenancy import filtersets
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import (
    assert_object_action_allowed,
    get_action_for_method,
    restrict_queryset,
)

from .serializers import EnvironmentSerializer, OrganizationSerializer, WorkspaceSerializer


class TenancyRootView(APIRootView):
    permission_classes = [TokenPermissions]

    def get_view_name(self):
        return "Tenancy"

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "organizations": reverse("api:tenancy-api:organization-list", request=request),
                "workspaces": reverse("api:tenancy-api:workspace-list", request=request),
                "environments": reverse("api:tenancy-api:environment-list", request=request),
            }
        )


class RestrictedTenancyViewSet(ModelViewSet):
    def validate_saved_object_permissions(self, obj):
        assert_object_action_allowed(
            obj,
            request=self.request,
            action=self.get_permission_action(),
        )
        return obj


class OrganizationViewSet(RestrictedTenancyViewSet):
    serializer_class = OrganizationSerializer
    filterset_class = filtersets.OrganizationFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = Organization.objects.annotate(
            workspace_count=Count("workspaces", distinct=True),
            environment_count=Count("environments", distinct=True),
        ).order_by("name")
        return restrict_queryset(
            queryset,
            request=self.request,
            action=get_action_for_method(self.request.method),
        )


class WorkspaceViewSet(RestrictedTenancyViewSet):
    serializer_class = WorkspaceSerializer
    filterset_class = filtersets.WorkspaceFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = Workspace.objects.select_related("organization").annotate(
            environment_count=Count("environments", distinct=True),
        ).order_by("organization__name", "name")
        return restrict_queryset(
            queryset,
            request=self.request,
            action=get_action_for_method(self.request.method),
        )


class EnvironmentViewSet(RestrictedTenancyViewSet):
    serializer_class = EnvironmentSerializer
    filterset_class = filtersets.EnvironmentFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        )
        return restrict_queryset(
            queryset,
            request=self.request,
            action=get_action_for_method(self.request.method),
        )
