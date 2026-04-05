from django import forms

from automation.catalog.loader import get_workflow_catalog
from automation.catalog.services import (
    WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE,
    workflow_definition_supports_catalog_designer,
)
from automation.integrations.openai.app import OPENAI_CODEX_OAUTH_CLIENT_ID, OPENAI_OAUTH_TOKEN_URL
from automation.models import Workflow, WorkflowConnection, WorkflowConnectionState
from automation.primitives import canonicalize_workflow_definition, normalize_workflow_definition_nodes
from core.form_widgets import apply_standard_widget_classes
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


def _connection_type_choices(current_value=None):
    choices = sorted(
        (
            connection_type.id,
            f"{app.label} · {connection_type.label}",
        )
        for app in get_workflow_catalog()["integration_apps"].values()
        for connection_type in app.connection_types
        if connection_type.id != "webhook.shared_secret" or connection_type.id == current_value
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


class WorkflowForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Workflow",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "name",
                "description",
                "enabled",
            ),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)

    class Meta:
        model = Workflow
        fields = (
            "organization",
            "workspace",
            "environment",
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
            "title": "Credential",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "name",
                "description",
                "connection_type",
                "enabled",
            ),
        },
        {
            "title": "Configuration",
            "description": "Store the encrypted connection payload directly on the connection record.",
            "fields": ("data", "state_values", "metadata"),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)
    connection_type = forms.ChoiceField(choices=())
    data = forms.JSONField(required=False, initial=dict, widget=forms.Textarea)
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
    openai_api_key = forms.CharField(required=False, label="API Key", widget=forms.PasswordInput(render_value=False))
    openai_oauth_client_id = forms.CharField(required=False, label="OAuth Client ID")
    openai_oauth_client_secret = forms.CharField(
        required=False,
        label="OAuth Client Secret",
        widget=forms.PasswordInput(render_value=False),
    )
    openai_oauth_token_url = forms.URLField(required=False, label="OAuth Token URL")
    prometheus_base_url = forms.URLField(required=False, label="API Base URL")
    prometheus_bearer_token = forms.CharField(
        required=False,
        label="Bearer Token",
        widget=forms.PasswordInput(render_value=False),
    )
    elasticsearch_base_url = forms.URLField(required=False, label="API Base URL")
    elasticsearch_auth_scheme = forms.ChoiceField(
        required=False,
        choices=(
            ("ApiKey", "ApiKey"),
            ("Bearer", "Bearer"),
        ),
        label="Auth Scheme",
    )
    elasticsearch_auth_token = forms.CharField(
        required=False,
        label="Auth Token",
        widget=forms.PasswordInput(render_value=False),
    )
    github_webhook_secret = forms.CharField(
        required=False,
        label="Webhook Secret",
        widget=forms.PasswordInput(render_value=False),
    )
    webhook_basic_username = forms.CharField(required=False, label="Username")
    webhook_basic_password = forms.CharField(
        required=False,
        label="Password",
        widget=forms.PasswordInput(render_value=False),
    )
    webhook_header_auth_name = forms.CharField(required=False, label="Name")
    webhook_header_auth_value = forms.CharField(
        required=False,
        label="Value",
        widget=forms.PasswordInput(render_value=False),
    )
    webhook_jwt_key_type = forms.ChoiceField(
        required=False,
        choices=(
            ("passphrase", "Passphrase"),
            ("pemKey", "PEM Key"),
        ),
        label="Key Type",
    )
    webhook_jwt_secret = forms.CharField(
        required=False,
        label="Secret",
        widget=forms.PasswordInput(render_value=False),
    )
    webhook_jwt_public_key = forms.CharField(
        required=False,
        label="Public Key",
        widget=forms.Textarea,
    )
    webhook_jwt_algorithm = forms.ChoiceField(
        required=False,
        choices=(
            ("HS256", "HS256"),
            ("HS384", "HS384"),
            ("HS512", "HS512"),
            ("RS256", "RS256"),
            ("RS384", "RS384"),
            ("RS512", "RS512"),
            ("ES256", "ES256"),
            ("ES384", "ES384"),
            ("ES512", "ES512"),
            ("PS256", "PS256"),
            ("PS384", "PS384"),
            ("PS512", "PS512"),
            ("none", "none"),
        ),
        label="Algorithm",
    )

    class Meta:
        model = WorkflowConnection
        fields = (
            "organization",
            "workspace",
            "environment",
            "name",
            "description",
            "connection_type",
            "enabled",
            "data",
            "metadata",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.structured_connection_editor = None
        self._pending_data_values: dict | None = None
        self.popup_mode = request is not None and (request.GET.get("popup") or request.POST.get("popup")) == "1"
        _configure_scope_fields(self, request)
        self.fields["connection_type"].choices = _connection_type_choices(self.instance.connection_type or None)
        if request is not None:
            if not self.instance.pk:
                initial_environment = request.GET.get("environment")
                if initial_environment and initial_environment.isdigit():
                    self.fields["environment"].initial = int(initial_environment)
                initial_connection_type = request.GET.get("connection_type")
                if initial_connection_type:
                    self.fields["connection_type"].initial = initial_connection_type
                initial_data_values = request.GET.get("data")
                if initial_data_values:
                    try:
                        self.fields["data"].initial = forms.JSONField().to_python(initial_data_values)
                    except forms.ValidationError:
                        pass
        if self.instance.pk:
            self.fields["data"].initial = self.instance.get_data_values()
        self.fields["data"].widget.attrs["rows"] = 8
        current_state = getattr(self.instance, "state", None)
        if current_state is not None:
            self.fields["state_values"].initial = current_state.state_values
        self.fields["state_values"].widget.attrs["rows"] = 6
        self.fields["metadata"].widget.attrs["rows"] = 6
        self._configure_structured_connection_fields()
        if self.popup_mode:
            self._configure_popup_mode()
        apply_standard_widget_classes(self)

    def save(self, commit=True):
        if self._pending_data_values is not None:
            self.instance.set_data_values(self._pending_data_values)
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

        connection_type = (cleaned_data.get("connection_type") or self.instance.connection_type or "").strip()

        if connection_type == "openai.api":
            return self._clean_openai_data(cleaned_data)

        if connection_type == "prometheus.api":
            return self._clean_prometheus_data(cleaned_data)

        if connection_type == "elasticsearch.api":
            return self._clean_elasticsearch_data(cleaned_data)

        if connection_type == "github.oauth2":
            return self._clean_github_data(cleaned_data)
        if connection_type == "webhook.basic_auth":
            return self._clean_webhook_basic_auth_data(cleaned_data)
        if connection_type in {"webhook.header_auth", "webhook.shared_secret"}:
            return self._clean_webhook_header_auth_data(cleaned_data)
        if connection_type == "webhook.jwt_auth":
            return self._clean_webhook_jwt_auth_data(cleaned_data)

        self._pending_data_values = cleaned_data.get("data") or {}
        self.instance.set_data_values(self._pending_data_values)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_openai_data(self, cleaned_data):
        if not self._has_any_posted_fields(
            "openai_auth_mode",
            "openai_base_url",
            "openai_api_key",
            "openai_oauth_client_id",
            "openai_oauth_client_secret",
            "openai_oauth_token_url",
        ):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        auth_mode = (cleaned_data.get("openai_auth_mode") or "api_key").strip() or "api_key"
        base_url = (cleaned_data.get("openai_base_url") or "https://api.openai.com/v1").strip()
        api_key = (cleaned_data.get("openai_api_key") or "").strip()
        oauth_client_id = (
            cleaned_data.get("openai_oauth_client_id") or ""
        ).strip()
        oauth_client_secret = (cleaned_data.get("openai_oauth_client_secret") or "").strip()
        oauth_token_url = (
            cleaned_data.get("openai_oauth_token_url") or OPENAI_OAUTH_TOKEN_URL
        ).strip()
        data_values = self._effective_data_values()

        normalized_data = {
            "auth_mode": auth_mode,
            "base_url": base_url,
        }

        if auth_mode == "api_key":
            if api_key:
                normalized_data["api_key"] = api_key
            elif not data_values.get("api_key"):
                self.add_error("openai_api_key", "Enter an API key.")
        elif auth_mode == "oauth2_authorization_code":
            normalized_data["oauth_client_id"] = oauth_client_id or OPENAI_CODEX_OAUTH_CLIENT_ID
            normalized_data["oauth_token_url"] = oauth_token_url
            if oauth_client_secret:
                normalized_data["oauth_client_secret"] = oauth_client_secret
            elif data_values.get("oauth_client_secret"):
                normalized_data["oauth_client_secret"] = data_values["oauth_client_secret"]
        else:
            self.add_error("openai_auth_mode", "Select a supported authentication mode.")

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_prometheus_data(self, cleaned_data):
        if not self._has_any_posted_fields("prometheus_base_url", "prometheus_bearer_token"):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        data_values = self._effective_data_values()
        base_url = (cleaned_data.get("prometheus_base_url") or "").strip()
        bearer_token = (cleaned_data.get("prometheus_bearer_token") or "").strip()

        if not base_url:
            self.add_error("prometheus_base_url", "Enter an API base URL.")

        normalized_data = {"base_url": base_url}
        self._copy_secret_value(
            normalized_data=normalized_data,
            normalized_key="bearer_token",
            incoming_value=bearer_token,
            existing_values=data_values,
        )

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_elasticsearch_data(self, cleaned_data):
        if not self._has_any_posted_fields(
            "elasticsearch_base_url",
            "elasticsearch_auth_scheme",
            "elasticsearch_auth_token",
        ):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        data_values = self._effective_data_values()
        base_url = (cleaned_data.get("elasticsearch_base_url") or "").strip()
        auth_scheme = (cleaned_data.get("elasticsearch_auth_scheme") or "ApiKey").strip() or "ApiKey"
        auth_token = (cleaned_data.get("elasticsearch_auth_token") or "").strip()

        if not base_url:
            self.add_error("elasticsearch_base_url", "Enter an API base URL.")

        normalized_data = {
            "base_url": base_url,
            "auth_scheme": auth_scheme,
        }
        self._copy_secret_value(
            normalized_data=normalized_data,
            normalized_key="auth_token",
            incoming_value=auth_token,
            existing_values=data_values,
        )

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_github_data(self, cleaned_data):
        if not self._has_any_posted_fields("github_webhook_secret"):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        data_values = self._effective_data_values()
        webhook_secret = (cleaned_data.get("github_webhook_secret") or "").strip()

        normalized_data: dict[str, str] = {}
        self._copy_secret_value(
            normalized_data=normalized_data,
            normalized_key="webhook_secret",
            incoming_value=webhook_secret,
            existing_values=data_values,
        )

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_webhook_basic_auth_data(self, cleaned_data):
        if not self._has_any_posted_fields("webhook_basic_username", "webhook_basic_password"):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        data_values = self._effective_data_values()
        username = (cleaned_data.get("webhook_basic_username") or "").strip()
        password = (cleaned_data.get("webhook_basic_password") or "").strip()

        if not username:
            self.add_error("webhook_basic_username", "Enter a username.")

        normalized_data = {"username": username}
        self._copy_secret_value(
            normalized_data=normalized_data,
            normalized_key="password",
            incoming_value=password,
            existing_values=data_values,
        )
        if "password" not in normalized_data:
            self.add_error("webhook_basic_password", "Enter a password.")

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_webhook_header_auth_data(self, cleaned_data):
        if not self._has_any_posted_fields("webhook_header_auth_name", "webhook_header_auth_value"):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        data_values = self._effective_data_values()
        header_name = (cleaned_data.get("webhook_header_auth_name") or "").strip()
        header_value = (cleaned_data.get("webhook_header_auth_value") or "").strip()
        use_legacy_fields = (cleaned_data.get("connection_type") or self.instance.connection_type) == "webhook.shared_secret"

        if not header_name:
            self.add_error("webhook_header_auth_name", "Enter a name.")

        normalized_data = (
            {"header_name": header_name}
            if use_legacy_fields
            else {"name": header_name}
        )
        self._copy_secret_value(
            normalized_data=normalized_data,
            normalized_key="secret_value" if use_legacy_fields else "value",
            incoming_value=header_value,
            existing_values=data_values,
        )
        if ("secret_value" if use_legacy_fields else "value") not in normalized_data:
            self.add_error("webhook_header_auth_value", "Enter a value.")

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _clean_webhook_jwt_auth_data(self, cleaned_data):
        if not self._has_any_posted_fields(
            "webhook_jwt_key_type",
            "webhook_jwt_secret",
            "webhook_jwt_public_key",
            "webhook_jwt_algorithm",
        ):
            self._pending_data_values = cleaned_data.get("data") or {}
            self.instance.set_data_values(self._pending_data_values)
            cleaned_data["data"] = self.instance.data
            return cleaned_data

        data_values = self._effective_data_values()
        key_type = (cleaned_data.get("webhook_jwt_key_type") or "passphrase").strip() or "passphrase"
        algorithm = (cleaned_data.get("webhook_jwt_algorithm") or "HS256").strip() or "HS256"
        secret = (cleaned_data.get("webhook_jwt_secret") or "").strip()
        public_key = (cleaned_data.get("webhook_jwt_public_key") or "").strip()

        normalized_data = {
            "key_type": key_type,
            "algorithm": algorithm,
        }

        if key_type == "passphrase":
            self._copy_secret_value(
                normalized_data=normalized_data,
                normalized_key="secret",
                incoming_value=secret,
                existing_values=data_values,
            )
            if "secret" not in normalized_data:
                self.add_error("webhook_jwt_secret", "Enter a secret.")
        elif key_type == "pemKey":
            self._copy_secret_value(
                normalized_data=normalized_data,
                normalized_key="public_key",
                incoming_value=public_key,
                existing_values=data_values,
            )
            if "public_key" not in normalized_data:
                self.add_error("webhook_jwt_public_key", "Enter a public key.")
        else:
            self.add_error("webhook_jwt_key_type", "Select a supported key type.")

        self._pending_data_values = normalized_data
        self.instance.set_data_values(normalized_data)
        cleaned_data["data"] = self.instance.data
        return cleaned_data

    def _configure_structured_connection_fields(self) -> None:
        connection_type = self._effective_connection_type()
        if connection_type == "openai.api":
            self._configure_openai_fields()
            return
        if connection_type == "prometheus.api":
            self._configure_prometheus_fields()
            return
        if connection_type == "elasticsearch.api":
            self._configure_elasticsearch_fields()
            return
        if connection_type == "github.oauth2":
            self._configure_github_fields()
            return
        if connection_type == "webhook.basic_auth":
            self._configure_webhook_basic_auth_fields()
            return
        if connection_type in {"webhook.header_auth", "webhook.shared_secret"}:
            self._configure_webhook_header_auth_fields()
            return
        if connection_type == "webhook.jwt_auth":
            self._configure_webhook_jwt_auth_fields()
            return

    def _hide_field(self, field_name: str) -> None:
        if field_name in self.fields:
            self.fields[field_name].widget = forms.HiddenInput()

    def _is_field_hidden(self, field_name: str) -> bool:
        return isinstance(self.fields[field_name].widget, forms.HiddenInput)

    def _configure_popup_mode(self) -> None:
        for field_name in (
            "organization",
            "workspace",
            "environment",
            "description",
            "enabled",
            "metadata",
            "state_values",
        ):
            self._hide_field(field_name)

        if self.instance.pk or self._effective_connection_type():
            self._hide_field("connection_type")

        visible_identity_fields = tuple(
            field_name
            for field_name in ("name", "connection_type")
            if field_name in self.fields and not self._is_field_hidden(field_name)
        )

        minimal_fieldsets = []
        if visible_identity_fields:
            minimal_fieldsets.append(
                {
                    "title": "",
                    "fields": visible_identity_fields,
                }
            )

        if self.structured_connection_editor:
            for fieldset in self.fieldsets:
                if fieldset.get("title") == "Credentials":
                    minimal_fieldsets.append(
                        {
                            "title": "Credentials",
                            "description": "",
                            "fields": fieldset.get("fields", ()),
                        }
                    )
                    break
        else:
            minimal_fieldsets.append(
                {
                    "title": "Credentials",
                    "description": "",
                    "fields": ("data",),
                }
            )

        self.fieldsets = tuple(minimal_fieldsets)

    def _configure_openai_fields(self) -> None:
        self.structured_connection_editor = "openai"

        data_values = self._effective_data_values()

        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved OpenAI credential without editing raw JSON.",
                "fields": (
                    "openai_auth_mode",
                    "openai_base_url",
                    "openai_api_key",
                    "openai_oauth_client_id",
                    "openai_oauth_client_secret",
                    "openai_oauth_token_url",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )

        self.fields["openai_auth_mode"].initial = data_values.get("auth_mode") or "api_key"
        self.fields["openai_auth_mode"].help_text = "Choose whether requests use an API key or the ChatGPT device login flow."
        self.fields["openai_base_url"].initial = data_values.get("base_url") or "https://api.openai.com/v1"
        self.fields["openai_base_url"].help_text = "OpenAI-compatible API base URL."
        self.fields["openai_base_url"].widget.attrs["placeholder"] = "https://api.openai.com/v1"
        self.fields["openai_api_key"].help_text = (
            "Stored encrypted on this connection. Leave blank when editing to keep the saved API key."
            if data_values.get("api_key")
            else "Stored encrypted on this connection."
        )
        oauth_client_id = data_values.get("oauth_client_id") or ""
        self.fields["openai_oauth_client_id"].initial = (
            ""
            if oauth_client_id == OPENAI_CODEX_OAUTH_CLIENT_ID
            else oauth_client_id
        )
        self.fields["openai_oauth_client_id"].help_text = (
            "Optional override. Leave blank to use OpenAI's built-in ChatGPT device login client."
        )
        self.fields["openai_oauth_client_secret"].help_text = (
            "Stored encrypted on this connection. Leave blank when editing to keep the saved client secret."
            if data_values.get("oauth_client_secret")
            else "Optional client secret stored encrypted on this connection."
        )
        self.fields["openai_oauth_token_url"].initial = (
            data_values.get("oauth_token_url") or OPENAI_OAUTH_TOKEN_URL
        )
        self.fields["openai_oauth_token_url"].help_text = "Token endpoint used to refresh OpenAI device-login tokens."
        self.fields["openai_oauth_token_url"].widget.attrs["placeholder"] = OPENAI_OAUTH_TOKEN_URL

    def _configure_prometheus_fields(self) -> None:
        self.structured_connection_editor = "prometheus"
        data_values = self._effective_data_values()
        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved Prometheus credential without editing raw JSON.",
                "fields": (
                    "prometheus_base_url",
                    "prometheus_bearer_token",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )
        self.fields["prometheus_base_url"].initial = data_values.get("base_url") or ""
        self.fields["prometheus_base_url"].help_text = "Prometheus-compatible API base URL."
        self.fields["prometheus_base_url"].widget.attrs["placeholder"] = "https://prometheus.example.com"
        self.fields["prometheus_bearer_token"].help_text = (
            "Stored encrypted on this connection. Leave blank when editing to keep the saved bearer token."
            if data_values.get("bearer_token")
            else "Optional bearer token stored encrypted on this connection."
        )

    def _configure_elasticsearch_fields(self) -> None:
        self.structured_connection_editor = "elasticsearch"
        data_values = self._effective_data_values()
        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved Elasticsearch credential without editing raw JSON.",
                "fields": (
                    "elasticsearch_base_url",
                    "elasticsearch_auth_scheme",
                    "elasticsearch_auth_token",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )
        self.fields["elasticsearch_base_url"].initial = data_values.get("base_url") or ""
        self.fields["elasticsearch_base_url"].help_text = "Elasticsearch-compatible API base URL."
        self.fields["elasticsearch_base_url"].widget.attrs["placeholder"] = "https://elastic.example.com"
        self.fields["elasticsearch_auth_scheme"].initial = data_values.get("auth_scheme") or "ApiKey"
        self.fields["elasticsearch_auth_scheme"].help_text = "Authorization scheme applied to the stored auth token."
        self.fields["elasticsearch_auth_token"].help_text = (
            "Stored encrypted on this connection. Leave blank when editing to keep the saved auth token."
            if data_values.get("auth_token")
            else "Optional auth token stored encrypted on this connection."
        )

    def _configure_github_fields(self) -> None:
        self.structured_connection_editor = "github"
        data_values = self._effective_data_values()
        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved GitHub credential without editing raw JSON.",
                "fields": ("github_webhook_secret",),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )
        self.fields["github_webhook_secret"].help_text = (
            "Stored encrypted on this connection. Leave blank when editing to keep the saved webhook secret."
            if data_values.get("webhook_secret")
            else "Optional webhook signing secret stored encrypted on this connection."
        )

    def _configure_webhook_basic_auth_fields(self) -> None:
        self.structured_connection_editor = "webhook_basic_auth"
        data_values = self._effective_data_values()
        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved Basic Auth credential without editing raw JSON.",
                "fields": (
                    "webhook_basic_username",
                    "webhook_basic_password",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )
        self.fields["webhook_basic_username"].initial = data_values.get("username") or ""
        self.fields["webhook_basic_username"].widget.attrs["placeholder"] = "admin"
        self.fields["webhook_basic_username"].help_text = ""
        self.fields["webhook_basic_password"].help_text = ""

    def _configure_webhook_header_auth_fields(self) -> None:
        self.structured_connection_editor = "webhook_header_auth"
        data_values = self._effective_data_values()
        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved Header Auth credential without editing raw JSON.",
                "fields": (
                    "webhook_header_auth_name",
                    "webhook_header_auth_value",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )
        self.fields["webhook_header_auth_name"].initial = (
            data_values.get("name") or data_values.get("header_name") or "X-Webhook-Secret"
        )
        self.fields["webhook_header_auth_name"].widget.attrs["placeholder"] = "X-Webhook-Secret"
        self.fields["webhook_header_auth_name"].help_text = ""
        self.fields["webhook_header_auth_value"].help_text = ""

    def _configure_webhook_jwt_auth_fields(self) -> None:
        self.structured_connection_editor = "webhook_jwt_auth"
        data_values = self._effective_data_values()
        self.fieldsets = (
            {
                "title": "Credential",
                "fields": (
                    "organization",
                    "workspace",
                    "environment",
                    "name",
                    "description",
                    "connection_type",
                    "enabled",
                ),
            },
            {
                "title": "Credentials",
                "description": "Configure the saved JWT Auth credential without editing raw JSON.",
                "fields": (
                    "webhook_jwt_key_type",
                    "webhook_jwt_secret",
                    "webhook_jwt_public_key",
                    "webhook_jwt_algorithm",
                ),
            },
            {
                "title": "Advanced",
                "description": "Optional metadata attached to this connection record.",
                "fields": ("metadata",),
            },
        )
        self.fields["webhook_jwt_key_type"].initial = data_values.get("key_type") or "passphrase"
        self.fields["webhook_jwt_key_type"].help_text = ""
        self.fields["webhook_jwt_secret"].help_text = ""
        self.fields["webhook_jwt_public_key"].help_text = ""
        self.fields["webhook_jwt_public_key"].widget.attrs["rows"] = 6
        self.fields["webhook_jwt_public_key"].widget.attrs["placeholder"] = "-----BEGIN PUBLIC KEY-----"
        self.fields["webhook_jwt_algorithm"].initial = data_values.get("algorithm") or "HS256"
        self.fields["webhook_jwt_algorithm"].help_text = ""

    def _has_any_posted_fields(self, *field_names: str) -> bool:
        return any(field_name in self.data for field_name in field_names)

    def _copy_secret_value(self, *, normalized_data: dict, normalized_key: str, incoming_value: str, existing_values: dict) -> None:
        if incoming_value:
            normalized_data[normalized_key] = incoming_value
            return
        existing_value = existing_values.get(normalized_key)
        if existing_value:
            normalized_data[normalized_key] = existing_value

    def _effective_connection_type(self) -> str:
        if self.is_bound:
            return (self.data.get("connection_type") or self.instance.connection_type or "").strip()
        return (
            self.initial.get("connection_type")
            or self.fields["connection_type"].initial
            or self.instance.connection_type
            or ""
        ).strip()

    def _effective_data_values(self) -> dict:
        if self.is_bound:
            raw_data_values = self.data.get("data")
            if raw_data_values:
                try:
                    parsed = forms.JSONField().to_python(raw_data_values)
                    if isinstance(parsed, dict):
                        return parsed
                except forms.ValidationError:
                    pass
        initial = self.initial.get("data")
        if isinstance(initial, dict) and initial:
            return initial
        if self.instance.pk:
            return self.instance.get_data_values()
        return {}
