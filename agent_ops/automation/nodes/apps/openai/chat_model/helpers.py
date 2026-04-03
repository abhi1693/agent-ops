from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeDefinition,
    WorkflowNodeExecutionResult,
    node_field_option,
    node_select_field,
    node_text_field,
    node_textarea_field,
    WorkflowNodeImplementation,
)
from automation.nodes.apps.openai.client import validate_openai_chat_model_config


def build_openai_compatible_chat_model_implementation(*, api_type: str) -> WorkflowNodeImplementation:
    def _validate_chat_model_node(
        config: dict,
        node_id: str,
        outgoing_targets: list[str],
        node_ids: set[str],
    ) -> None:
        del outgoing_targets, node_ids
        validate_openai_chat_model_config(config, node_id)

    def _execute_chat_model_node(runtime) -> WorkflowNodeExecutionResult:
        return WorkflowNodeExecutionResult(
            next_node_id=runtime.next_node_id,
            output={
                "model": runtime.config.get("model"),
                "base_url": runtime.config.get("base_url"),
                "api_type": api_type,
            },
        )

    return WorkflowNodeImplementation(
        validator=_validate_chat_model_node,
        executor=_execute_chat_model_node,
    )


def build_openai_compatible_chat_model_definition(
    *,
    api_type: str,
    node_type: str,
    details: str,
    display_name: str,
    icon: str,
    app_id: str,
    app_label: str,
    app_description: str,
    app_icon: str,
    base_url: str,
    default_model: str,
    model_options: tuple[tuple[str, str], ...],
    custom_model_placeholder: str,
) -> WorkflowNodeDefinition:
    implementation = build_openai_compatible_chat_model_implementation(api_type=api_type)
    return WorkflowNodeDefinition(
        type=node_type,
        kind="tool",
        display_name=display_name,
        description=details,
        icon=icon,
        app_id=app_id,
        app_label=app_label,
        app_description=app_description,
        app_icon=app_icon,
        config={
            "base_url": base_url,
            "model": default_model,
            "custom_model": "",
        },
        fields=(
            node_text_field(
                "base_url",
                "API base URL",
                placeholder=base_url,
            ),
            node_select_field(
                "model",
                "Model preset",
                options=tuple(
                    node_field_option(value, label)
                    for value, label in model_options
                ),
            ),
            node_text_field(
                "custom_model",
                "Custom model ID",
                placeholder=custom_model_placeholder,
                help_text=(
                    "Optional advanced override. If set, this exact model ID is used "
                    "instead of the selected preset."
                ),
            ),
            node_text_field(
                "secret_name",
                "Secret name",
                placeholder=f"{api_type.upper()}_API_KEY",
            ),
            node_text_field(
                "secret_group_id",
                "Secret group",
                placeholder="Use workflow secret group",
                help_text=(
                    "Optional. Override the workflow secret group for this node with "
                    "a scoped secret group ID."
                ),
            ),
            node_text_field(
                "temperature",
                "Temperature",
                placeholder="0.2",
            ),
            node_text_field(
                "max_tokens",
                "Max tokens",
                placeholder="800",
            ),
            node_textarea_field(
                "extra_body_json",
                "Extra body JSON",
                rows=5,
                placeholder='{"response_format": {"type": "json_object"}}',
                help_text=(
                    "Optional provider-specific fields merged into the request body "
                    "after prompts and model."
                ),
            ),
        ),
        validator=implementation.validator,
        executor=implementation.executor,
    )
