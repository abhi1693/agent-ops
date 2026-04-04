from automation.catalog.capabilities import CAPABILITY_AGENT_MODEL
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionSlotDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
)
from automation.integrations.openai.client import (
    resolve_openai_chat_model_config,
    validate_openai_chat_model_config,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


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
            "connection_id": runtime.config.get("connection_id"),
        },
    )


OPENAI_CONNECTION = ConnectionTypeDefinition(
    id="openai.api",
    integration_id="openai",
    label="OpenAI API",
    auth_kind="api_key",
    description="Reusable API connection for OpenAI and OpenAI-compatible model endpoints.",
    field_schema=(
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
            label="API Key Secret",
            value_type="secret_ref",
            required=True,
            description="Secret reference containing the API key used for requests.",
            placeholder="OPENAI_API_KEY",
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
                    label="Connection",
                    allowed_connection_types=(OPENAI_CONNECTION.id,),
                    required=False,
                    description="Optional reusable OpenAI connection used for authenticated model requests.",
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
