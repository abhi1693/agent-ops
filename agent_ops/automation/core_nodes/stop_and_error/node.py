from __future__ import annotations

from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition
from automation.catalog.validation import validate_parameter_schema, validate_terminal
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import _render_runtime_string


def _validate_core_stop_and_error_config(*, config, node_id, outgoing_targets, **_) -> None:
    validate_parameter_schema(
        node_definition=NODE_DEFINITION,
        config=config,
        node_id=node_id,
        node_ids=set(),
        outgoing_targets=outgoing_targets,
    )
    validate_terminal(node_id, outgoing_targets)


def _execute_stop_and_error(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    payload = {
        "message": _render_runtime_string(runtime, "message", default_mode="expression")
        or "An error occurred.",
    }
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        output=payload,
        response=payload,
        run_status="failed",
        terminal=True,
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.stop_and_error",
    integration_id="core",
    mode="core",
    kind="control",
    label="Stop And Error",
    description="Stops execution immediately and emits an explicit workflow failure.",
    icon="mdi-alert-circle-outline",
    default_name="Stop And Error",
    node_group=("transform",),
    runtime_validator=_validate_core_stop_and_error_config,
    runtime_executor=_execute_stop_and_error,
    parameter_schema=(
        ParameterDefinition(
            key="message",
            label="Error Message",
            value_type="string",
            required=True,
            description="Message surfaced in the workflow run error output.",
            placeholder="The selected deployment environment is not allowed.",
            ui_group="input",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
