from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView

from agent_ops.api.permissions import IsStaffOrScopedReadOnlyUser, IsStaffUser, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from tenancy import filtersets
from tenancy.models import Environment, Organization, Workspace
from users.scopes import (
    get_request_actor_scope,
    scope_environments_queryset,
    scope_organizations_queryset,
    scope_workspaces_queryset,
)

from .serializers import EnvironmentSerializer, OrganizationSerializer, WorkspaceSerializer


class TenancyRootView(APIRootView):
    permission_classes = [TokenPermissions, IsStaffOrScopedReadOnlyUser]

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


class OrganizationViewSet(ModelViewSet):
    serializer_class = OrganizationSerializer
    filterset_class = filtersets.OrganizationFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffOrScopedReadOnlyUser]

    def get_queryset(self):
        queryset = Organization.objects.annotate(
            workspace_count=Count("workspaces", distinct=True),
            environment_count=Count("environments", distinct=True),
        ).order_by("name")
        return scope_organizations_queryset(queryset, get_request_actor_scope(self.request))


class WorkspaceViewSet(ModelViewSet):
    serializer_class = WorkspaceSerializer
    filterset_class = filtersets.WorkspaceFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffOrScopedReadOnlyUser]

    def get_queryset(self):
        queryset = Workspace.objects.select_related("organization").annotate(
            environment_count=Count("environments", distinct=True),
        ).order_by("organization__name", "name")
        return scope_workspaces_queryset(queryset, get_request_actor_scope(self.request))


class EnvironmentViewSet(ModelViewSet):
    serializer_class = EnvironmentSerializer
    filterset_class = filtersets.EnvironmentFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffOrScopedReadOnlyUser]

    def get_queryset(self):
        queryset = Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        )
        return scope_environments_queryset(queryset, get_request_actor_scope(self.request))
