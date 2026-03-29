from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView

from agent_ops.api.permissions import IsStaffUser, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from tenancy import filtersets
from tenancy.models import Environment, Organization, Workspace

from .serializers import EnvironmentSerializer, OrganizationSerializer, WorkspaceSerializer


class TenancyRootView(APIRootView):
    permission_classes = [TokenPermissions, IsStaffUser]

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
    queryset = Organization.objects.annotate(
        workspace_count=Count("workspaces", distinct=True),
        environment_count=Count("environments", distinct=True),
    ).order_by("name")
    serializer_class = OrganizationSerializer
    filterset_class = filtersets.OrganizationFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffUser]


class WorkspaceViewSet(ModelViewSet):
    queryset = Workspace.objects.select_related("organization").annotate(
        environment_count=Count("environments", distinct=True),
    ).order_by("organization__name", "name")
    serializer_class = WorkspaceSerializer
    filterset_class = filtersets.WorkspaceFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffUser]


class EnvironmentViewSet(ModelViewSet):
    queryset = Environment.objects.select_related("organization", "workspace").order_by(
        "organization__name", "workspace__name", "name"
    )
    serializer_class = EnvironmentSerializer
    filterset_class = filtersets.EnvironmentFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, IsStaffUser]
