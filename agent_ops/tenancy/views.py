from django.db.models import Count

from core.generic_views import ObjectDeleteView, ObjectEditView, ObjectListView, ObjectView
from core.mixins import StaffRequiredMixin
from tenancy import filtersets, tables
from tenancy.forms import EnvironmentForm, OrganizationForm, WorkspaceForm
from tenancy.mixins import StaffOrScopedUserRequiredMixin
from tenancy.models import Environment, Organization, Workspace
from users.scopes import (
    get_request_actor_scope,
    scope_environments_queryset,
    scope_organizations_queryset,
    scope_workspaces_queryset,
)


class OrganizationListView(StaffOrScopedUserRequiredMixin, ObjectListView):
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
        return scope_organizations_queryset(queryset, get_request_actor_scope(request))


class OrganizationDetailView(StaffOrScopedUserRequiredMixin, ObjectView):
    model = Organization
    template_name = "tenancy/organization_detail.html"

    def get_queryset(self):
        queryset = Organization.objects.prefetch_related(
            "workspaces",
            "environments__workspace",
        ).annotate(
            workspace_count=Count("workspaces", distinct=True),
            environment_count=Count("environments", distinct=True),
        )
        return scope_organizations_queryset(queryset, get_request_actor_scope(self.request))


class OrganizationCreateView(StaffRequiredMixin, ObjectEditView):
    model = Organization
    form_class = OrganizationForm
    success_message = "Organization created."


class OrganizationUpdateView(StaffRequiredMixin, ObjectEditView):
    model = Organization
    form_class = OrganizationForm
    success_message = "Organization updated."


class OrganizationDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = Organization
    success_message = "Organization deleted."


class WorkspaceListView(StaffOrScopedUserRequiredMixin, ObjectListView):
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
        return scope_workspaces_queryset(queryset, get_request_actor_scope(request))


class WorkspaceDetailView(StaffOrScopedUserRequiredMixin, ObjectView):
    model = Workspace
    template_name = "tenancy/workspace_detail.html"

    def get_queryset(self):
        queryset = Workspace.objects.select_related("organization").prefetch_related(
            "environments"
        ).annotate(
            environment_count=Count("environments", distinct=True),
        )
        return scope_workspaces_queryset(queryset, get_request_actor_scope(self.request))


class WorkspaceCreateView(StaffRequiredMixin, ObjectEditView):
    model = Workspace
    form_class = WorkspaceForm
    success_message = "Workspace created."


class WorkspaceUpdateView(StaffRequiredMixin, ObjectEditView):
    model = Workspace
    form_class = WorkspaceForm
    success_message = "Workspace updated."


class WorkspaceDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = Workspace
    success_message = "Workspace deleted."


class EnvironmentListView(StaffOrScopedUserRequiredMixin, ObjectListView):
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
        return scope_environments_queryset(queryset, get_request_actor_scope(request))


class EnvironmentDetailView(StaffOrScopedUserRequiredMixin, ObjectView):
    model = Environment
    template_name = "tenancy/environment_detail.html"

    def get_queryset(self):
        queryset = Environment.objects.select_related("organization", "workspace")
        return scope_environments_queryset(queryset, get_request_actor_scope(self.request))


class EnvironmentCreateView(StaffRequiredMixin, ObjectEditView):
    model = Environment
    form_class = EnvironmentForm
    success_message = "Environment created."


class EnvironmentUpdateView(StaffRequiredMixin, ObjectEditView):
    model = Environment
    form_class = EnvironmentForm
    success_message = "Environment updated."


class EnvironmentDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = Environment
    success_message = "Environment deleted."
