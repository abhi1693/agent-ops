from django.db.models import Q
import django_filters

from automation.models import Secret, SecretGroup, Workflow, WorkflowConnection
from automation.secrets import iter_secrets_providers
from core.filtersets import SearchFilterSet
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


def _provider_choices():
    return sorted(
        (slug, provider.name or slug)
        for slug, provider in iter_secrets_providers()
    )


class SecretFilterSet(SearchFilterSet):
    provider = django_filters.ChoiceFilter(
        choices=_provider_choices(),
        label="Provider",
    )
    enabled = django_filters.BooleanFilter(label="Enabled")
    secret_group = django_filters.ModelChoiceFilter(
        queryset=SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        ),
        label="Secret group",
    )
    organization = django_filters.ModelChoiceFilter(
        field_name="secret_group__organization",
        queryset=Organization.objects.order_by("name"),
        label="Organization",
    )
    workspace = django_filters.ModelChoiceFilter(
        field_name="secret_group__workspace",
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        label="Workspace",
    )
    environment = django_filters.ModelChoiceFilter(
        field_name="secret_group__environment",
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        ),
        label="Environment",
    )

    class Meta:
        model = Secret
        fields = ("q", "provider", "enabled", "secret_group", "organization", "workspace", "environment")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(self, "request", None)
        if request is None:
            return
        self.filters["secret_group"].queryset = restrict_queryset(
            SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "name",
            ),
            request=request,
            action="view",
        )
        self.filters["organization"].queryset = restrict_queryset(
            Organization.objects.order_by("name"),
            request=request,
            action="view",
        )
        self.filters["workspace"].queryset = restrict_queryset(
            Workspace.objects.select_related("organization").order_by("organization__name", "name"),
            request=request,
            action="view",
        )
        self.filters["environment"].queryset = restrict_queryset(
            Environment.objects.select_related("organization", "workspace").order_by(
                "organization__name",
                "workspace__name",
                "name",
            ),
            request=request,
            action="view",
        )

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(provider__icontains=value)
            | Q(secret_group__name__icontains=value)
            | Q(secret_group__organization__name__icontains=value)
            | Q(secret_group__workspace__name__icontains=value)
            | Q(secret_group__environment__name__icontains=value)
        )


class SecretGroupFilterSet(SearchFilterSet):
    organization = django_filters.ModelChoiceFilter(
        queryset=Organization.objects.order_by("name"),
        label="Organization",
    )
    workspace = django_filters.ModelChoiceFilter(
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        label="Workspace",
    )
    environment = django_filters.ModelChoiceFilter(
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        ),
        label="Environment",
    )

    class Meta:
        model = SecretGroup
        fields = ("q", "organization", "workspace", "environment")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(self, "request", None)
        if request is None:
            return
        self.filters["organization"].queryset = restrict_queryset(
            Organization.objects.order_by("name"),
            request=request,
            action="view",
        )
        self.filters["workspace"].queryset = restrict_queryset(
            Workspace.objects.select_related("organization").order_by("organization__name", "name"),
            request=request,
            action="view",
        )
        self.filters["environment"].queryset = restrict_queryset(
            Environment.objects.select_related("organization", "workspace").order_by(
                "organization__name",
                "workspace__name",
                "name",
            ),
            request=request,
            action="view",
        )

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(organization__name__icontains=value)
            | Q(workspace__name__icontains=value)
            | Q(environment__name__icontains=value)
        )


class WorkflowFilterSet(SearchFilterSet):
    enabled = django_filters.BooleanFilter(label="Enabled")
    organization = django_filters.ModelChoiceFilter(
        queryset=Organization.objects.order_by("name"),
        label="Organization",
    )
    workspace = django_filters.ModelChoiceFilter(
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        label="Workspace",
    )
    environment = django_filters.ModelChoiceFilter(
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        ),
        label="Environment",
    )

    class Meta:
        model = Workflow
        fields = ("q", "enabled", "organization", "workspace", "environment")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(self, "request", None)
        if request is None:
            return
        self.filters["organization"].queryset = restrict_queryset(
            Organization.objects.order_by("name"),
            request=request,
            action="view",
        )
        self.filters["workspace"].queryset = restrict_queryset(
            Workspace.objects.select_related("organization").order_by("organization__name", "name"),
            request=request,
            action="view",
        )
        self.filters["environment"].queryset = restrict_queryset(
            Environment.objects.select_related("organization", "workspace").order_by(
                "organization__name",
                "workspace__name",
                "name",
            ),
            request=request,
            action="view",
        )

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(organization__name__icontains=value)
            | Q(workspace__name__icontains=value)
            | Q(environment__name__icontains=value)
        )


class WorkflowConnectionFilterSet(SearchFilterSet):
    enabled = django_filters.BooleanFilter(label="Enabled")
    integration_id = django_filters.CharFilter(label="Integration")
    connection_type = django_filters.CharFilter(label="Connection type")
    organization = django_filters.ModelChoiceFilter(
        queryset=Organization.objects.order_by("name"),
        label="Organization",
    )
    workspace = django_filters.ModelChoiceFilter(
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        label="Workspace",
    )
    environment = django_filters.ModelChoiceFilter(
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        ),
        label="Environment",
    )

    class Meta:
        model = WorkflowConnection
        fields = ("q", "enabled", "integration_id", "connection_type", "organization", "workspace", "environment")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(self, "request", None)
        if request is None:
            return
        self.filters["organization"].queryset = restrict_queryset(
            Organization.objects.order_by("name"),
            request=request,
            action="view",
        )
        self.filters["workspace"].queryset = restrict_queryset(
            Workspace.objects.select_related("organization").order_by("organization__name", "name"),
            request=request,
            action="view",
        )
        self.filters["environment"].queryset = restrict_queryset(
            Environment.objects.select_related("organization", "workspace").order_by(
                "organization__name",
                "workspace__name",
                "name",
            ),
            request=request,
            action="view",
        )

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(integration_id__icontains=value)
            | Q(connection_type__icontains=value)
            | Q(organization__name__icontains=value)
            | Q(workspace__name__icontains=value)
            | Q(environment__name__icontains=value)
        )
