from __future__ import annotations

from automation.nodes.adapters import tool_definition_as_node_implementation
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _render_runtime_string,
    _tool_result,
    _validate_required_string,
    tool_text_field,
    tool_textarea_field,
)


def _validate_template_tool(config: dict, node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    _validate_required_string(config, "template", node_id=node_id)


def _execute_template_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    rendered = (
        _render_runtime_string(runtime, "template", required=True, default_mode="expression")
        or runtime.node.get("label")
        or runtime.node["id"]
    )
    runtime.set_path_value(runtime.context, output_key, rendered)
    return _tool_result("template", output_key=output_key, value=rendered)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="template",
    label="Render template",
    description="Render a template against workflow context and save the result.",
    icon="mdi-text-box-edit-outline",
    config={"output_key": "tool.output"},
    fields=(
        tool_text_field(
            "output_key",
            "Save result as",
            ui_group="result",
            binding="path",
            placeholder="tool.output",
        ),
        tool_textarea_field(
            "template",
            "Template",
            rows=4,
            ui_group="input",
            binding="template",
            placeholder="Service: {{ workflow.scope_label }}",
        ),
    ),
    validator=_validate_template_tool,
    executor=_execute_template_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
