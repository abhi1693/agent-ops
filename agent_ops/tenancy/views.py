from django.db.models import Count

from core.generic_views import (
    ObjectChangeLogView,
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from tenancy import filtersets, tables
from tenancy.forms import EnvironmentForm, OrganizationForm, WorkspaceForm
from tenancy.mixins import (
    RestrictedObjectChangeLogMixin,
    RestrictedObjectDeleteMixin,
    RestrictedObjectEditMixin,
    RestrictedObjectListMixin,
    RestrictedObjectViewMixin,
)
from tenancy.models import Environment, Organization, Workspace


class OrganizationListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Organization.objects.all()
    table = tables.OrganizationTable
    filterset = filtersets.OrganizationFilterSet
    template_name = "tenancy/organization_list.html"

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .annotate(
                workspace_count=Count("workspaces", distinct=True),
                environment_count=Count("environments", distinct=True),
            )
            .order_by("name")
        )
        return queryset


class OrganizationDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Organization
    template_name = "tenancy/organization_detail.html"

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related(
            "workspaces",
            "environments__workspace",
        ).annotate(
            workspace_count=Count("workspaces", distinct=True),
            environment_count=Count("environments", distinct=True),
        )
        return queryset


class OrganizationChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Organization
    queryset = Organization.objects.order_by("name")


class OrganizationCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Organization
    form_class = OrganizationForm
    success_message = "Organization created."


class OrganizationUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Organization
    form_class = OrganizationForm
    success_message = "Organization updated."


class OrganizationDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Organization
    success_message = "Organization deleted."


class WorkspaceListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Workspace.objects.select_related("organization")
    table = tables.WorkspaceTable
    filterset = filtersets.WorkspaceFilterSet
    template_name = "tenancy/workspace_list.html"

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .select_related("organization")
            .annotate(environment_count=Count("environments", distinct=True))
            .order_by("organization__name", "name")
        )
        return queryset


class WorkspaceDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Workspace
    template_name = "tenancy/workspace_detail.html"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("organization").prefetch_related(
            "environments"
        ).annotate(
            environment_count=Count("environments", distinct=True),
        )
        return queryset


class WorkspaceChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Workspace
    queryset = Workspace.objects.select_related("organization").order_by("organization__name", "name")


class WorkspaceCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workspace
    form_class = WorkspaceForm
    success_message = "Workspace created."


class WorkspaceUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workspace
    form_class = WorkspaceForm
    success_message = "Workspace updated."


class WorkspaceDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Workspace
    success_message = "Workspace deleted."


class EnvironmentListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Environment.objects.select_related("organization", "workspace")
    table = tables.EnvironmentTable
    filterset = filtersets.EnvironmentFilterSet
    template_name = "tenancy/environment_list.html"

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .select_related("organization", "workspace")
            .order_by("organization__name", "workspace__name", "name")
        )
        return queryset


class EnvironmentDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Environment
    template_name = "tenancy/environment_detail.html"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("organization", "workspace")
        return queryset


class EnvironmentChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Environment
    queryset = Environment.objects.select_related("organization", "workspace").order_by(
        "organization__name",
        "workspace__name",
        "name",
    )


class EnvironmentCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Environment
    form_class = EnvironmentForm
    success_message = "Environment created."


class EnvironmentUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Environment
    form_class = EnvironmentForm
    success_message = "Environment updated."


class EnvironmentDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Environment
    success_message = "Environment deleted."
