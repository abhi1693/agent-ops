from django import forms

from automation.catalog.loader import get_workflow_catalog
from automation.catalog.services import (
    WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE,
    workflow_definition_supports_catalog_designer,
)
from automation.integrations.openai.app import OPENAI_CODEX_OAUTH_CLIENT_ID, OPENAI_OAUTH_TOKEN_URL
from automation.models import Secret, SecretGroup, Workflow
from automation.models import WorkflowConnection, WorkflowConnectionState
from automation.primitives import canonicalize_workflow_definition, normalize_workflow_definition_nodes
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
            self.initial["definition"] = canonicalize_workflow_definition(self.instance.definition)
        apply_standard_widget_classes(self)

    def clean_definition(self):
        definition = self.cleaned_data["definition"]
        normalized_definition = normalize_workflow_definition_nodes(definition)
        if not workflow_definition_supports_catalog_designer(normalized_definition):
            raise forms.ValidationError(WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE)
        return canonicalize_workflow_definition(definition)


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
                "secret_group",
                "enabled",
            ),
        },
        {
            "title": "Configuration",
            "description": "Store typed connection field values and metadata as JSON objects.",
            "fields": ("field_values", "state_values", "metadata"),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)
    secret_group = forms.ModelChoiceField(queryset=SecretGroup.objects.none(), required=False)
    connection_type = forms.ChoiceField(choices=())
    field_values = forms.JSONField(required=False, initial=dict, widget=forms.Textarea)
    state_values = forms.JSONField(required=False, initial=dict, widget=forms.Textarea)
    metadata = forms.JSONField(required=False, initial=dict, widget=forms.Textarea)
    openai_auth_mode = forms.ChoiceField(
        required=False,
        choices=(
            ("api_key", "API Key"),
            ("oauth2_authorization_code", "OAuth 2.0"),
        ),
        label="Auth Mode",
    )
    openai_base_url = forms.URLField(required=False, label="API Base URL")
    openai_api_key_secret_name = forms.CharField(required=False, label="API Key Secret Name")
    openai_oauth_client_id = forms.CharField(required=False, label="OAuth Client ID")
    openai_oauth_client_secret_name = forms.CharField(required=False, label="OAuth Client Secret Name")
    openai_oauth_token_url = forms.URLField(required=False, label="OAuth Token URL")

    class Meta:
        model = WorkflowConnection
        fields = (
            "organization",
            "workspace",
            "environment",
            "name",
            "description",
            "connection_type",
            "secret_group",
            "enabled",
            "field_values",
            "metadata",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.uses_structured_openai_editor = False
        _configure_scope_fields(self, request)
        self.fields["connection_type"].choices = _connection_type_choices(self.instance.connection_type or None)
        self.fields["secret_group"].queryset = SecretGroup.objects.select_related(
            "organization",
            "workspace",
            "environment",
        ).order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        if request is not None:
            self.fields["secret_group"].queryset = restrict_queryset(
                self.fields["secret_group"].queryset,
                request=request,
                action="view",
            )
            if not self.instance.pk:
                initial_environment = request.GET.get("environment")
                if initial_environment and initial_environment.isdigit():
                    self.fields["environment"].initial = int(initial_environment)
                initial_secret_group = request.GET.get("secret_group")
                if initial_secret_group and initial_secret_group.isdigit():
                    self.fields["secret_group"].initial = int(initial_secret_group)
                initial_connection_type = request.GET.get("connection_type")
                if initial_connection_type:
                    self.fields["connection_type"].initial = initial_connection_type
                initial_field_values = request.GET.get("field_values")
                if initial_field_values:
                    try:
                        self.fields["field_values"].initial = forms.JSONField().to_python(initial_field_values)
                    except forms.ValidationError:
                        pass
        self.fields["field_values"].widget.attrs["rows"] = 8
        current_state = getattr(self.instance, "state", None)
        if current_state is not None:
            self.fields["state_values"].initial = current_state.state_values
        self.fields["state_values"].widget.attrs["rows"] = 6
        self.fields["metadata"].widget.attrs["rows"] = 6
        self._configure_openai_fields()
        apply_standard_widget_classes(self)

    def save(self, commit=True):
        connection = super().save(commit=commit)
        if not commit:
            return connection

        if "state_values" in self.data:
            state_values = self.cleaned_data.get("state_values") or {}
        else:
            current_state = getattr(connection, "state", None)
            state_values = current_state.state_values if current_state is not None else {}
        state, _ = WorkflowConnectionState.objects.get_or_create(connection=connection)
        state.state_values = state_values
        state.full_clean()
        state.save()
        return connection

    def clean(self):
        cleaned_data = super().clean()

        if (cleaned_data.get("connection_type") or self.instance.connection_type) != "openai.api":
            return cleaned_data

        structured_field_names = (
            "openai_auth_mode",
            "openai_base_url",
            "openai_api_key_secret_name",
            "openai_oauth_client_id",
            "openai_oauth_client_secret_name",
            "openai_oauth_token_url",
        )
        if not any(field_name in self.data for field_name in structured_field_names):
            return cleaned_data

        auth_mode = (cleaned_data.get("openai_auth_mode") or "api_key").strip() or "api_key"
        base_url = (cleaned_data.get("openai_base_url") or "https://api.openai.com/v1").strip()
        api_key_secret_name = (cleaned_data.get("openai_api_key_secret_name") or "").strip()
        oauth_client_id = (
            cleaned_data.get("openai_oauth_client_id") or ""
        ).strip()
        oauth_client_secret_name = (cleaned_data.get("openai_oauth_client_secret_name") or "").strip()
        oauth_token_url = (
            cleaned_data.get("openai_oauth_token_url") or OPENAI_OAUTH_TOKEN_URL
        ).strip()

        field_values = {
            "auth_mode": auth_mode,
            "base_url": base_url,
        }

        if auth_mode == "api_key":
            if not api_key_secret_name:
                self.add_error("openai_api_key_secret_name", "Enter a secret name from the selected secret group.")
            else:
                field_values["api_key"] = {
                    "source": "secret",
                    "secret_name": api_key_secret_name,
                }
        elif auth_mode == "oauth2_authorization_code":
            field_values["oauth_client_id"] = oauth_client_id or OPENAI_CODEX_OAUTH_CLIENT_ID
            field_values["oauth_token_url"] = oauth_token_url
            if oauth_client_secret_name:
                field_values["oauth_client_secret"] = {
                    "source": "secret",
                    "secret_name": oauth_client_secret_name,
                }
        else:
            self.add_error("openai_auth_mode", "Select a supported authentication mode.")

        cleaned_data["field_values"] = field_values
        return cleaned_data

    def _configure_openai_fields(self) -> None:
        connection_type = self._effective_connection_type()
        if connection_type != "openai.api":
            return

        self.uses_structured_openai_editor = True
        field_values = self._effective_field_values()
        available_secret_names = self._selected_secret_names()
        available_secret_label = ", ".join(available_secret_names) if available_secret_names else "No secrets available yet"

        self.fieldsets = (
            {
                "title": "Workflow Connection",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "secret_group",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved OpenAI credential without editing raw JSON.",
                "fields": (
                    "openai_auth_mode",
                    "openai_base_url",
                    "openai_api_key_secret_name",
                    "openai_oauth_client_id",
                    "openai_oauth_client_secret_name",
                    "openai_oauth_token_url",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )

        self.fields["openai_auth_mode"].initial = field_values.get("auth_mode") or "api_key"
        self.fields["openai_auth_mode"].help_text = (
            "Choose whether requests use a secret-backed API key or the ChatGPT device login flow."
        )
        self.fields["openai_base_url"].initial = field_values.get("base_url") or "https://api.openai.com/v1"
        self.fields["openai_base_url"].help_text = "OpenAI-compatible API base URL."
        self.fields["openai_base_url"].widget.attrs["placeholder"] = "https://api.openai.com/v1"
        self.fields["openai_api_key_secret_name"].initial = self._secret_name_from_ref(field_values.get("api_key"))
        self.fields["openai_api_key_secret_name"].help_text = (
            "Enter a secret name from the selected secret group for API key authentication. "
            f"Available secrets: {available_secret_label}."
        )
        oauth_client_id = field_values.get("oauth_client_id") or ""
        self.fields["openai_oauth_client_id"].initial = (
            ""
            if oauth_client_id == OPENAI_CODEX_OAUTH_CLIENT_ID
            else oauth_client_id
        )
        self.fields["openai_oauth_client_id"].help_text = (
            "Optional override. Leave blank to use OpenAI's built-in ChatGPT device login client."
        )
        self.fields["openai_oauth_client_secret_name"].initial = self._secret_name_from_ref(
            field_values.get("oauth_client_secret")
        )
        self.fields["openai_oauth_client_secret_name"].help_text = (
            "Optional secret name from the selected secret group for the OAuth client secret. "
            f"Available secrets: {available_secret_label}."
        )
        self.fields["openai_oauth_token_url"].initial = (
            field_values.get("oauth_token_url") or OPENAI_OAUTH_TOKEN_URL
        )
        self.fields["openai_oauth_token_url"].help_text = "Token endpoint used to refresh OpenAI device-login tokens."
        self.fields["openai_oauth_token_url"].widget.attrs["placeholder"] = OPENAI_OAUTH_TOKEN_URL

    def _effective_connection_type(self) -> str:
        if self.is_bound:
            return (self.data.get("connection_type") or self.instance.connection_type or "").strip()
        return (
            self.initial.get("connection_type")
            or self.fields["connection_type"].initial
            or self.instance.connection_type
            or ""
        ).strip()

    def _effective_field_values(self) -> dict:
        if self.is_bound:
            raw_field_values = self.data.get("field_values")
            if raw_field_values:
                try:
                    return forms.JSONField().to_python(raw_field_values)
                except forms.ValidationError:
                    pass
        initial = self.initial.get("field_values")
        if isinstance(initial, dict) and initial:
            return initial
        return self.instance.field_values or {}

    def _selected_secret_names(self) -> list[str]:
        secret_group_id = None
        if self.is_bound:
            secret_group_id = self.data.get("secret_group")
        if not secret_group_id:
            secret_group_id = self.initial.get("secret_group") or self.fields["secret_group"].initial
        if not secret_group_id and self.instance.secret_group_id:
            secret_group_id = self.instance.secret_group_id
        if not secret_group_id:
            return []
        try:
            secret_group_id = int(secret_group_id)
        except (TypeError, ValueError):
            return []
        secret_group = self.fields["secret_group"].queryset.filter(pk=secret_group_id).first()
        if secret_group is None:
            return []
        return list(secret_group.secrets.filter(enabled=True).order_by("name").values_list("name", flat=True))

    @staticmethod
    def _secret_name_from_ref(raw_value) -> str:
        if isinstance(raw_value, dict):
            secret_name = raw_value.get("secret_name")
            if isinstance(secret_name, str):
                return secret_name
        return ""
