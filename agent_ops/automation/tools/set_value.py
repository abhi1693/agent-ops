from __future__ import annotations

from .base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _tool_result,
    _validate_required_string,
    tool_text_field,
)


def _validate_set_tool(config: dict, node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)


def _execute_set_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    value = runtime.config.get("value")
    runtime.set_path_value(runtime.context, output_key, value)
    return _tool_result("set", output_key=output_key, value=value)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="set",
    label="Set value",
    description="Write a static value into workflow context.",
    icon="mdi-form-textbox",
    config={"output_key": "tool.output"},
    fields=(
        tool_text_field("output_key", "Save result as", placeholder="tool.output"),
        tool_text_field(
            "value",
            "Value",
            placeholder="static-value",
            help_text="Use advanced runtime JSON for structured values.",
        ),
    ),
    validator=_validate_set_tool,
    executor=_execute_set_tool,
)
