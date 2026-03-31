from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.nodes.adapters import tool_definition_as_node_implementation
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _tool_result,
    _validate_required_string,
    tool_text_field,
)


def _validate_secret_tool(config: dict, node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    _validate_required_string(config, "name", node_id=node_id)
    provider = config.get("provider")
    if provider is not None and (not isinstance(provider, str) or not provider.strip()):
        raise ValidationError({"definition": f'Node "{node_id}" config.provider must be a non-empty string.'})


def _execute_secret_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    secret = runtime.resolve_scoped_secret(
        runtime.workflow,
        name=runtime.config["name"],
        provider=runtime.config.get("provider"),
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
        tool_text_field("name", "Secret name", placeholder="OPENAI_API_KEY"),
        tool_text_field(
            "provider",
            "Secret provider",
            placeholder="environment-variable",
            help_text="Optional. Leave blank to search all enabled providers in scope.",
        ),
    ),
    validator=_validate_secret_tool,
    executor=_execute_secret_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
