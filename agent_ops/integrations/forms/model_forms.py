from django import forms

from core.form_widgets import apply_standard_widget_classes
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from integrations.secrets import iter_secrets_providers
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


def _provider_choices(current_value=None):
    choices = sorted(
        (slug, provider.name or slug)
        for slug, provider in iter_secrets_providers()
    )
    if current_value and all(slug != current_value for slug, _label in choices):
        choices.append((current_value, current_value))
    return choices


class SecretForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Secret",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "name",
                "description",
                "provider",
                "enabled",
            ),
        },
        {
            "title": "Retrieval",
            "description": "Store provider-specific lookup parameters and metadata here, not the secret value itself.",
            "fields": ("parameters", "metadata", "expires"),
        },
    )
    provider = forms.ChoiceField(choices=())
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)

    class Meta:
        model = Secret
        fields = (
            "organization",
            "workspace",
            "environment",
            "name",
            "description",
            "provider",
            "parameters",
            "metadata",
            "enabled",
            "expires",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider"].choices = _provider_choices(self.instance.provider or None)

        organization_qs = Organization.objects.order_by("name")
        workspace_qs = Workspace.objects.select_related("organization").order_by("organization__name", "name")
        environment_qs = Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        )
        if request is not None:
            organization_qs = restrict_queryset(organization_qs, request=request, action="view")
            workspace_qs = restrict_queryset(workspace_qs, request=request, action="view")
            environment_qs = restrict_queryset(environment_qs, request=request, action="view")

        self.fields["organization"].queryset = organization_qs
        self.fields["workspace"].queryset = workspace_qs
        self.fields["environment"].queryset = environment_qs
        self.fields["parameters"].widget.attrs["rows"] = 6
        self.fields["metadata"].widget.attrs["rows"] = 6
        apply_standard_widget_classes(self)


class SecretGroupForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Secret Group",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "name",
                "description",
            ),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)

    class Meta:
        model = SecretGroup
        fields = (
            "organization",
            "workspace",
            "environment",
            "name",
            "description",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        organization_qs = Organization.objects.order_by("name")
        workspace_qs = Workspace.objects.select_related("organization").order_by("organization__name", "name")
        environment_qs = Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        )
        if request is not None:
            organization_qs = restrict_queryset(organization_qs, request=request, action="view")
            workspace_qs = restrict_queryset(workspace_qs, request=request, action="view")
            environment_qs = restrict_queryset(environment_qs, request=request, action="view")

        self.fields["organization"].queryset = organization_qs
        self.fields["workspace"].queryset = workspace_qs
        self.fields["environment"].queryset = environment_qs
        apply_standard_widget_classes(self)


class SecretGroupAssignmentForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Assignment",
            "description": "Attach a secret to a group under a stable key or role.",
            "fields": (
                "secret_group",
                "secret",
                "key",
                "required",
                "order",
            ),
        },
    )
    secret_group = forms.ModelChoiceField(queryset=SecretGroup.objects.none())
    secret = forms.ModelChoiceField(queryset=Secret.objects.none())

    class Meta:
        model = SecretGroupAssignment
        fields = (
            "secret_group",
            "secret",
            "key",
            "required",
            "order",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        secret_group_qs = SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        secret_qs = Secret.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        if request is not None:
            secret_group_qs = restrict_queryset(secret_group_qs, request=request, action="view")
            secret_qs = restrict_queryset(secret_qs, request=request, action="view")

            if not self.instance.pk:
                initial_secret_group = request.GET.get("secret_group")
                if initial_secret_group and initial_secret_group.isdigit():
                    self.fields["secret_group"].initial = int(initial_secret_group)

        self.fields["secret_group"].queryset = secret_group_qs
        self.fields["secret"].queryset = secret_qs
        apply_standard_widget_classes(self)
