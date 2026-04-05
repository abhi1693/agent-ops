from automation.catalog.capabilities import CAPABILITY_AGENT_MODEL
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionHttpAuthDefinition,
    ConnectionHttpHeaderDefinition,
    ConnectionOAuth2Definition,
    ConnectionSlotDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.integrations.openai.client import (
    resolve_openai_chat_model_config,
    validate_openai_chat_model_config,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.catalog.execution import get_runtime_connection_slot_value


OPENAI_CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_DEVICE_AUTH_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
OPENAI_DEVICE_AUTH_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
OPENAI_DEVICE_AUTH_VERIFICATION_URL = "https://auth.openai.com/codex/device"
OPENAI_DEVICE_AUTH_CALLBACK_URL = "https://auth.openai.com/deviceauth/callback"
OPENAI_AUTH_USER_AGENT = "agent-ops-openai-auth/1.0"


def _validate_openai_runtime_config(*, config, node_id, **_) -> None:
    validate_openai_chat_model_config(config, node_id)


def _execute_openai_chat_model(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    resolved_config = resolve_openai_chat_model_config(
        runtime,
        node=runtime.node,
        config=runtime.config,
    )
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "model": resolved_config.model,
            "base_url": resolved_config.base_url,
            "api_type": "openai_compatible",
            "connection_id": get_runtime_connection_slot_value(runtime),
        },
    )


OPENAI_CONNECTION = ConnectionTypeDefinition(
    id="openai.api",
    integration_id="openai",
    label="OpenAI API",
    auth_kind="multi_auth",
    description="Reusable API credential for OpenAI and OpenAI-compatible model endpoints.",
    http_auth=ConnectionHttpAuthDefinition(
        headers=(
            ConnectionHttpHeaderDefinition(
                field_key="api_key",
                header_name="Authorization",
                prefix="Bearer ",
                required=True,
            ),
        ),
        enabled_when_field="auth_mode",
        enabled_when_values=("api_key",),
    ),
    oauth2=ConnectionOAuth2Definition(
        token_url_field="oauth_token_url",
        client_id_field="oauth_client_id",
        client_secret_field="oauth_client_secret",
        account_id_state_key="account_id",
        enabled_when_field="auth_mode",
        enabled_when_values=("oauth2_authorization_code",),
    ),
    field_schema=(
        ParameterDefinition(
            key="auth_mode",
            label="Auth Mode",
            value_type="string",
            required=True,
            description="Authentication mode used for OpenAI requests.",
            default="api_key",
            options=(
                ParameterOptionDefinition(value="api_key", label="API Key"),
                ParameterOptionDefinition(value="oauth2_authorization_code", label="OAuth 2.0"),
            ),
        ),
        ParameterDefinition(
            key="base_url",
            label="API Base URL",
            value_type="url",
            required=True,
            description="Base URL for the OpenAI-compatible API endpoint.",
            default="https://api.openai.com/v1",
            placeholder="https://api.openai.com/v1",
        ),
        ParameterDefinition(
            key="api_key",
            label="API Key",
            value_type="secret_ref",
            required=False,
            description="API key used for authenticated requests.",
            placeholder="OPENAI_API_KEY",
        ),
        ParameterDefinition(
            key="oauth_client_id",
            label="OAuth Client ID",
            value_type="string",
            required=False,
            description="Optional OAuth client override. Leave blank to use the built-in ChatGPT device login client.",
            default=OPENAI_CODEX_OAUTH_CLIENT_ID,
            placeholder=OPENAI_CODEX_OAUTH_CLIENT_ID,
        ),
        ParameterDefinition(
            key="oauth_client_secret",
            label="OAuth Client Secret",
            value_type="secret_ref",
            required=False,
            description="Optional client secret used when refreshing OpenAI OAuth tokens.",
            placeholder="OPENAI_OAUTH_CLIENT_SECRET",
        ),
        ParameterDefinition(
            key="oauth_token_url",
            label="OAuth Token URL",
            value_type="url",
            required=False,
            description="Token endpoint used to refresh OpenAI OAuth tokens.",
            default=OPENAI_OAUTH_TOKEN_URL,
            placeholder=OPENAI_OAUTH_TOKEN_URL,
        ),
    ),
    state_schema=(
        ParameterDefinition(
            key="access_token",
            label="Access Token",
            value_type="string",
            required=False,
            description="Current OAuth access token.",
        ),
        ParameterDefinition(
            key="refresh_token",
            label="Refresh Token",
            value_type="string",
            required=False,
            description="Refresh token used to rotate the OpenAI OAuth access token.",
        ),
        ParameterDefinition(
            key="expires_at",
            label="Expires At",
            value_type="integer",
            required=False,
            description="Unix timestamp when the current access token expires.",
        ),
        ParameterDefinition(
            key="account_id",
            label="Account ID",
            value_type="string",
            required=False,
            description="Optional OpenAI account identifier associated with the OAuth token.",
        ),
    ),
)


APP = IntegrationApp(
    id="openai",
    label="OpenAI",
    description="General-purpose GPT model provider for agent workflows.",
    icon="mdi-brain",
    category_tags=("ai", "models"),
    connection_types=(OPENAI_CONNECTION,),
    actions=(
        CatalogNodeDefinition(
            id="openai.model.chat",
            integration_id="openai",
            mode="action",
            kind="model",
            label="OpenAI",
            description="Runs a chat-completion style OpenAI model within a workflow.",
            icon="mdi-brain",
            resource="chat",
            operation="complete",
            group="Models",
            capabilities=frozenset({CAPABILITY_AGENT_MODEL}),
            connection_type=OPENAI_CONNECTION.id,
            runtime_validator=_validate_openai_runtime_config,
            runtime_executor=_execute_openai_chat_model,
            connection_slots=(
                ConnectionSlotDefinition(
                    key="connection_id",
                    label="Credential for OpenAI",
                    allowed_connection_types=(OPENAI_CONNECTION.id,),
                    required=True,
                    description="Reusable OpenAI credential used for authenticated model requests.",
                ),
            ),
            parameter_schema=(
                ParameterDefinition(
                    key="model",
                    label="Model",
                    value_type="string",
                    required=True,
                    description="OpenAI model identifier to execute.",
                    placeholder="gpt-5.4",
                ),
                ParameterDefinition(
                    key="system_prompt",
                    label="System Prompt",
                    value_type="text",
                    required=False,
                    description="Optional system instructions for the model.",
                ),
                ParameterDefinition(
                    key="temperature",
                    label="Temperature",
                    value_type="number",
                    required=False,
                    description="Sampling temperature for the completion.",
                    default=0.2,
                ),
            ),
            tags=("ai", "llm"),
        ),
    ),
    sort_order=50,
)
