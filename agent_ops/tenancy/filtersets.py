from django.db.models import Q
import django_filters

from core.filtersets import SearchFilterSet
from tenancy.models import Environment, Organization, Workspace


class OrganizationFilterSet(SearchFilterSet):
    class Meta:
        model = Organization
        fields = ("q",)

    def search_queryset(self, queryset, value):
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class WorkspaceFilterSet(SearchFilterSet):
    organization = django_filters.ModelChoiceFilter(
        queryset=Organization.objects.order_by("name"),
        label="Organization",
    )

    class Meta:
        model = Workspace
        fields = ("q", "organization")

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(organization__name__icontains=value)
        )


class EnvironmentFilterSet(SearchFilterSet):
    organization = django_filters.ModelChoiceFilter(
        field_name="workspace__organization",
        queryset=Organization.objects.order_by("name"),
        label="Organization",
    )
    workspace = django_filters.ModelChoiceFilter(
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        label="Workspace",
    )

    class Meta:
        model = Environment
        fields = ("q", "organization", "workspace")

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(workspace__name__icontains=value)
            | Q(workspace__organization__name__icontains=value)
        )
