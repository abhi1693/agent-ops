from django import forms

from automation.catalog.loader import get_workflow_catalog
from automation.catalog.services import (
    WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE,
    workflow_definition_supports_catalog_designer,
)
from automation.models import Secret, SecretGroup, Workflow
from automation.models import WorkflowConnection
from automation.primitives import normalize_workflow_definition_nodes
from automation.secrets import iter_secrets_providers
from core.form_widgets import apply_standard_widget_classes
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


def _connection_type_choices(current_value=None):
    choices = sorted(
        (
            connection_type.id,
            f"{app.label} · {connection_type.label}",
        )
        for app in get_workflow_catalog()["integration_apps"].values()
        for connection_type in app.connection_types
    )
    if current_value and all(slug != current_value for slug, _label in choices):
        choices.append((current_value, current_value))
    return choices


def _configure_scope_fields(form, request):
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

    form.fields["organization"].queryset = organization_qs
    form.fields["workspace"].queryset = workspace_qs
    form.fields["environment"].queryset = environment_qs
    if "secret_group" in form.fields:
        secret_group_qs = SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        if request is not None:
            secret_group_qs = restrict_queryset(secret_group_qs, request=request, action="view")
        form.fields["secret_group"].queryset = secret_group_qs


class SecretForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Secret",
            "fields": (
                "secret_group",
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
    secret_group = forms.ModelChoiceField(queryset=SecretGroup.objects.none())

    class Meta:
        model = Secret
        fields = (
            "secret_group",
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

        secret_group_qs = SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        if request is not None:
            secret_group_qs = restrict_queryset(secret_group_qs, request=request, action="view")
            if not self.instance.pk:
                initial_secret_group = request.GET.get("secret_group")
                if initial_secret_group and initial_secret_group.isdigit():
                    self.fields["secret_group"].initial = int(initial_secret_group)

        self.fields["secret_group"].queryset = secret_group_qs
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
        _configure_scope_fields(self, request)
        apply_standard_widget_classes(self)


class WorkflowForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Workflow",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "secret_group",
                "name",
                "description",
                "enabled",
            ),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)
    secret_group = forms.ModelChoiceField(queryset=SecretGroup.objects.none(), required=False)

    class Meta:
        model = Workflow
        fields = (
            "organization",
            "workspace",
            "environment",
            "secret_group",
            "name",
            "description",
            "enabled",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        _configure_scope_fields(self, request)
        apply_standard_widget_classes(self)


class WorkflowDesignerForm(forms.ModelForm):
    definition = forms.JSONField(widget=forms.HiddenInput())

    class Meta:
        model = Workflow
        fields = ("definition",)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and getattr(self.instance, "pk", None):
            self.initial["definition"] = normalize_workflow_definition_nodes(self.instance.definition)
        apply_standard_widget_classes(self)

    def clean_definition(self):
        definition = self.cleaned_data["definition"]
        normalized_definition = normalize_workflow_definition_nodes(definition)
        if not workflow_definition_supports_catalog_designer(normalized_definition):
            raise forms.ValidationError(WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE)
        return normalized_definition


class WorkflowRunForm(forms.Form):
    input_data = forms.JSONField(
        required=False,
        initial=dict,
        widget=forms.Textarea,
        help_text="Manual trigger payload. Available during execution as trigger.payload.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["input_data"].widget.attrs["rows"] = 8
        apply_standard_widget_classes(self)


class WorkflowConnectionForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Workflow Connection",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "name",
                "description",
                "connection_type",
                "credential_secret",
                "enabled",
            ),
        },
        {
            "title": "Configuration",
            "description": "Store provider-specific connection settings and metadata as JSON objects.",
            "fields": ("auth_config", "metadata"),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)
    credential_secret = forms.ModelChoiceField(queryset=Secret.objects.none(), required=False)
    connection_type = forms.ChoiceField(choices=())
    auth_config = forms.JSONField(required=False, initial=dict, widget=forms.Textarea)
    metadata = forms.JSONField(required=False, initial=dict, widget=forms.Textarea)

    class Meta:
        model = WorkflowConnection
        fields = (
            "organization",
            "workspace",
            "environment",
            "name",
            "description",
            "connection_type",
            "credential_secret",
            "enabled",
            "auth_config",
            "metadata",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        _configure_scope_fields(self, request)
        self.fields["connection_type"].choices = _connection_type_choices(self.instance.connection_type or None)
        self.fields["credential_secret"].queryset = Secret.objects.select_related(
            "secret_group__organization",
            "secret_group__workspace",
            "secret_group__environment",
        ).order_by(
            "secret_group__organization__name",
            "secret_group__workspace__name",
            "secret_group__environment__name",
            "secret_group__name",
            "name",
        )
        if request is not None:
            self.fields["credential_secret"].queryset = restrict_queryset(
                self.fields["credential_secret"].queryset,
                request=request,
                action="view",
            )
            if not self.instance.pk:
                initial_environment = request.GET.get("environment")
                if initial_environment and initial_environment.isdigit():
                    self.fields["environment"].initial = int(initial_environment)
        self.fields["auth_config"].widget.attrs["rows"] = 6
        self.fields["metadata"].widget.attrs["rows"] = 6
        apply_standard_widget_classes(self)
