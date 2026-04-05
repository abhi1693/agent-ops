from __future__ import annotations

from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.catalog.validation import validate_parameter_schema, validate_terminal
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import _get_runtime_bound_path_value, _render_runtime_string


def _validate_core_response_config(*, config, node_id, outgoing_targets, **_) -> None:
    validate_parameter_schema(
        node_definition=NODE_DEFINITION,
        config=config,
        node_id=node_id,
        node_ids=set(),
        outgoing_targets=outgoing_targets,
    )
    validate_terminal(node_id, outgoing_targets)


def _execute_response(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    if "value_path" in runtime.config and runtime.config.get("value_path") not in (None, ""):
        payload = _get_runtime_bound_path_value(
            runtime,
            _render_runtime_string(runtime, "value_path", default_mode="static"),
        )
    else:
        payload = (
            _render_runtime_string(runtime, "template", default_mode="expression")
            or runtime.node.get("label")
            or runtime.node["id"]
        )
    output = {
        "node_id": runtime.node["id"],
        "response": payload,
    }
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        output=output,
        response=output,
        run_status=runtime.config.get("status", "succeeded"),
        terminal=True,
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.response",
    integration_id="core",
    mode="core",
    kind="output",
    label="Response",
    description="Returns a structured workflow response to the caller.",
    icon="mdi-reply-outline",
    runtime_validator=_validate_core_response_config,
    runtime_executor=_execute_response,
    parameter_schema=(
        ParameterDefinition(
            key="template",
            label="Template",
            value_type="text",
            required=False,
            description="Rendered response body.",
            placeholder="Completed {{ llm.response.text }}",
        ),
        ParameterDefinition(
            key="value_path",
            label="Value Path",
            value_type="string",
            required=False,
            description="Optional direct context lookup instead of rendering the template.",
            placeholder="llm.response",
        ),
        ParameterDefinition(
            key="status",
            label="Status",
            value_type="string",
            required=False,
            description="Terminal run status.",
            default="succeeded",
            options=(
                ParameterOptionDefinition(value="succeeded", label="Succeeded"),
                ParameterOptionDefinition(value="failed", label="Failed"),
            ),
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
