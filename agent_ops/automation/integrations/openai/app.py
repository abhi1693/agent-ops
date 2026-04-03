from automation.catalog.capabilities import CAPABILITY_AGENT_MODEL
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
)


OPENAI_CONNECTION = ConnectionTypeDefinition(
    id="openai.api",
    integration_id="openai",
    label="OpenAI API",
    auth_kind="api_key",
    description="Reusable API connection for OpenAI and OpenAI-compatible model endpoints.",
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
