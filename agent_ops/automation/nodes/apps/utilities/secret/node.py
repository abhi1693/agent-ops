from __future__ import annotations

from automation.nodes.adapters import tool_definition_as_node_implementation
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _tool_result,
    _validate_optional_secret_group_id,
    _validate_required_string,
    tool_text_field,
)


def _validate_secret_tool(config: dict, node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    _validate_required_string(config, "secret_name", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)


def _execute_secret_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    secret = runtime.resolve_scoped_secret(
        runtime.workflow,
        secret_name=runtime.config["secret_name"],
        secret_group_id=runtime.config.get("secret_group_id"),
    )
    value = secret.get_value(obj=runtime.workflow)
    runtime.set_path_value(runtime.context, output_key, value)
    runtime.secret_paths.add(output_key)
    if isinstance(value, str):
        runtime.secret_values.append(value)
    return _tool_result(
        "secret",
        output_key=output_key,
        secret={
            "name": secret.name,
            "provider": secret.provider,
            "secret_group": secret.secret_group.name if secret.secret_group_id else None,
        },
    )


TOOL_DEFINITION = WorkflowToolDefinition(
    name="secret",
    label="Resolve secret",
    description="Resolve a scoped secret and store the redacted value path in context.",
    icon="mdi-key-variant",
    config={"output_key": "credentials.value"},
    fields=(
        tool_text_field("output_key", "Save result as", placeholder="credentials.openai"),
        tool_text_field(
            "secret_name",
            "Secret name",
            placeholder="OPENAI_API_KEY",
        ),
        tool_text_field(
            "secret_group_id",
            "Secret group",
            placeholder="Use workflow secret group",
            help_text="Optional. Override the workflow secret group for this node with a scoped secret group ID.",
        ),
    ),
    validator=_validate_secret_tool,
    executor=_execute_secret_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
