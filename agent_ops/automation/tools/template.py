from __future__ import annotations

from .base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _tool_result,
    _validate_required_string,
    tool_text_field,
    tool_textarea_field,
)


def _validate_template_tool(config: dict, node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    _validate_required_string(config, "template", node_id=node_id)


def _execute_template_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    template = runtime.config.get("template") or runtime.node.get("label") or runtime.node["id"]
    rendered = runtime.render_template(str(template), runtime.context)
    runtime.set_path_value(runtime.context, output_key, rendered)
    return _tool_result("template", output_key=output_key, value=rendered)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="template",
    label="Render template",
    description="Render a template against workflow context and save the result.",
    icon="mdi-text-box-edit-outline",
    config={"output_key": "tool.output"},
    fields=(
        tool_text_field("output_key", "Save result as", placeholder="tool.output"),
        tool_textarea_field(
            "template",
            "Template",
            rows=4,
            placeholder="Service: {{ workflow.scope_label }}",
        ),
    ),
    validator=_validate_template_tool,
    executor=_execute_template_tool,
)
