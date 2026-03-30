from __future__ import annotations

from .base import WorkflowToolDefinition, WorkflowToolExecutionContext, _tool_result, _validate_optional_string


def _validate_passthrough_tool(config: dict, node_id: str) -> None:
    _validate_optional_string(config, "tool_name", node_id=node_id)


def _execute_passthrough_tool(runtime: WorkflowToolExecutionContext) -> dict:
    return _tool_result("passthrough")


TOOL_DEFINITION = WorkflowToolDefinition(
    name="passthrough",
    label="Passthrough",
    description="No-op tool that keeps the workflow moving without changing context.",
    icon="mdi-arrow-right",
    validator=_validate_passthrough_tool,
    executor=_execute_passthrough_tool,
)
