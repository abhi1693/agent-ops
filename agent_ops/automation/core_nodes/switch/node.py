from __future__ import annotations

from automation.catalog.definitions import CatalogNodeDefinition, OutputPortDefinition, ParameterDefinition
from automation.catalog.validation import raise_definition_error, validate_parameter_schema
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import _get_runtime_bound_path_value


CASE_1_PORT = "case_1"
CASE_2_PORT = "case_2"
FALLBACK_PORT = "fallback"


def _validate_core_switch_config(
    *,
    config,
    node_id,
    node_ids,
    outgoing_targets,
    outgoing_targets_by_source_port,
    untyped_outgoing_targets,
    **_,
) -> None:
    validate_parameter_schema(
        node_definition=NODE_DEFINITION,
        config=config,
        node_id=node_id,
        node_ids=node_ids,
        outgoing_targets=outgoing_targets,
    )
    for port_key in (CASE_1_PORT, CASE_2_PORT, FALLBACK_PORT):
        if len(outgoing_targets_by_source_port.get(port_key, [])) != 1:
            raise_definition_error(f'Node "{node_id}" must connect exactly one "{port_key}" edge.')
    target_ids = [
        outgoing_targets_by_source_port[CASE_1_PORT][0],
        outgoing_targets_by_source_port[CASE_2_PORT][0],
        outgoing_targets_by_source_port[FALLBACK_PORT][0],
    ]
    if len(set(target_ids)) != len(target_ids):
        raise_definition_error(f'Node "{node_id}" switch targets must be different.')


def _execute_switch(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    left_value = _get_runtime_bound_path_value(runtime, runtime.config["path"])
    left_text = "" if left_value is None else str(left_value)

    matched_case = FALLBACK_PORT
    if left_text == str(runtime.config["case_1_value"]):
        matched_case = CASE_1_PORT
    elif left_text == str(runtime.config["case_2_value"]):
        matched_case = CASE_2_PORT

    return WorkflowNodeExecutionResult(
        next_node_id=None,
        next_port=matched_case,
        output={
            "path": runtime.config["path"],
            "matched_case": matched_case,
            "next_port": matched_case,
            "value": left_value,
        },
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.switch",
    integration_id="core",
    mode="core",
    kind="control",
    label="Switch",
    description="Routes execution across multiple cases using a selected value.",
    icon="mdi-call-split",
    output_ports=(
        OutputPortDefinition(key=CASE_1_PORT, label="Case 1", description="Taken when case 1 matches."),
        OutputPortDefinition(key=CASE_2_PORT, label="Case 2", description="Taken when case 2 matches."),
        OutputPortDefinition(key=FALLBACK_PORT, label="Fallback", description="Taken when no case matches."),
    ),
    runtime_validator=_validate_core_switch_config,
    runtime_executor=_execute_switch,
    parameter_schema=(
        ParameterDefinition(
            key="path",
            label="Context Path",
            value_type="string",
            required=True,
            description="Path resolved from the workflow context.",
            placeholder="trigger.payload.status",
        ),
        ParameterDefinition(
            key="case_1_value",
            label="Case 1 Value",
            value_type="string",
            required=True,
            description="First value to match.",
            placeholder="queued",
        ),
        ParameterDefinition(
            key="case_2_value",
            label="Case 2 Value",
            value_type="string",
            required=True,
            description="Second value to match.",
            placeholder="running",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
