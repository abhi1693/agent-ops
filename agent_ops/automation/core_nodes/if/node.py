from __future__ import annotations

from automation.catalog.definitions import (
    CatalogNodeDefinition,
    OutputPortDefinition,
    ParameterDefinition,
)
from automation.catalog.validation import (
    raise_definition_error,
    validate_parameter_schema,
)
from automation.core_nodes._conditions import evaluate_condition_block
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


TRUE_PORT = "true"
FALSE_PORT = "false"


def _validate_core_if_config(
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
    conditions_block = config.get("conditions")
    if not isinstance(conditions_block, dict):
        raise_definition_error(f'Node "{node_id}" must define config.conditions as a condition block.')
    raw_conditions = conditions_block.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise_definition_error(f'Node "{node_id}" conditions block must define at least one condition.')
    if len(outgoing_targets_by_source_port.get(TRUE_PORT, [])) != 1:
        raise_definition_error(f'Node "{node_id}" must connect exactly one "{TRUE_PORT}" edge.')
    if len(outgoing_targets_by_source_port.get(FALSE_PORT, [])) != 1:
        raise_definition_error(f'Node "{node_id}" must connect exactly one "{FALSE_PORT}" edge.')
    if outgoing_targets_by_source_port[TRUE_PORT][0] == outgoing_targets_by_source_port[FALSE_PORT][0]:
        raise_definition_error(f'Node "{node_id}" "{TRUE_PORT}" and "{FALSE_PORT}" edges must target different nodes.')


def _execute_if(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    conditions_block = runtime.config["conditions"]
    matched = evaluate_condition_block(runtime, conditions_block)
    output = {
        "matched": matched,
        "condition_count": len(conditions_block.get("conditions") or []),
    }
    selected_port = TRUE_PORT if matched else FALSE_PORT
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        next_port=selected_port,
        output={**output, "next_port": selected_port},
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.if",
    integration_id="core",
    mode="core",
    kind="control",
    label="If",
    description="Routes execution based on a conditional expression.",
    icon="mdi-source-branch",
    default_name="If",
    default_color="#408000",
    subtitle="Conditions",
    node_group=("transform",),
    output_ports=(
        OutputPortDefinition(key=TRUE_PORT, label="True", description="Taken when the condition matches."),
        OutputPortDefinition(key=FALSE_PORT, label="False", description="Taken when the condition does not match."),
    ),
    runtime_validator=_validate_core_if_config,
    runtime_executor=_execute_if,
    parameter_schema=(
        ParameterDefinition(
            key="conditions",
            label="Conditions",
            value_type="json",
            required=True,
            description="Condition block with conditions and combinator.",
            placeholder='{"conditions":[{"leftPath":"trigger.payload.status","operator":"equals","rightValue":"ok"}],"combinator":"and"}',
            rows=5,
            ui_group="input",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
