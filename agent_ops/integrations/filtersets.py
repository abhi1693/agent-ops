from django.db.models import Q
import django_filters

from core.filtersets import SearchFilterSet
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from integrations.secrets import iter_secrets_providers
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
        model = Secret
        fields = ("q", "provider", "enabled", "organization", "workspace", "environment")

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
            | Q(provider__icontains=value)
            | Q(organization__name__icontains=value)
            | Q(workspace__name__icontains=value)
            | Q(environment__name__icontains=value)
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


class SecretGroupAssignmentFilterSet(SearchFilterSet):
    secret_group = django_filters.ModelChoiceFilter(
        queryset=SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        ),
        label="Secret Group",
    )
    secret = django_filters.ModelChoiceFilter(
        queryset=Secret.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        ),
        label="Secret",
    )
    required = django_filters.BooleanFilter(label="Required")
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
        model = SecretGroupAssignment
        fields = ("q", "secret_group", "secret", "required", "organization", "workspace", "environment")

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
        self.filters["secret"].queryset = restrict_queryset(
            Secret.objects.select_related("organization", "workspace", "environment").order_by(
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
            Q(key__icontains=value)
            | Q(secret_group__name__icontains=value)
            | Q(secret__name__icontains=value)
            | Q(organization__name__icontains=value)
            | Q(workspace__name__icontains=value)
            | Q(environment__name__icontains=value)
        )
