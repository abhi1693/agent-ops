from __future__ import annotations

from automation.catalog.definitions import (
    CatalogNodeDefinition,
    OutputPortDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.catalog.validation import (
    raise_definition_error,
    validate_parameter_schema,
)
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
    operator = str(config.get("operator") or "").strip()
    if operator not in {"exists", "truthy"} and "right_value" not in config:
        raise_definition_error(f'Node "{node_id}" must define config.right_value for operator "{operator}".')
    if len(outgoing_targets_by_source_port.get(TRUE_PORT, [])) != 1:
        raise_definition_error(f'Node "{node_id}" must connect exactly one "{TRUE_PORT}" edge.')
    if len(outgoing_targets_by_source_port.get(FALSE_PORT, [])) != 1:
        raise_definition_error(f'Node "{node_id}" must connect exactly one "{FALSE_PORT}" edge.')
    if outgoing_targets_by_source_port[TRUE_PORT][0] == outgoing_targets_by_source_port[FALSE_PORT][0]:
        raise_definition_error(f'Node "{node_id}" "{TRUE_PORT}" and "{FALSE_PORT}" edges must target different nodes.')


def _execute_if(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    left_value = runtime.get_path_value(runtime.context, runtime.config.get("path"))
    matched = runtime.evaluate_condition(
        runtime.config["operator"],
        left_value,
        runtime.config.get("right_value"),
    )
    selected_port = TRUE_PORT if matched else FALSE_PORT
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        next_port=selected_port,
        output={
            "path": runtime.config.get("path"),
            "operator": runtime.config["operator"],
            "matched": matched,
            "next_port": selected_port,
        },
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.if",
    integration_id="core",
    mode="core",
    kind="control",
    label="If",
    description="Routes execution based on a conditional expression.",
    icon="mdi-source-branch",
    output_ports=(
        OutputPortDefinition(key=TRUE_PORT, label="True", description="Taken when the condition matches."),
        OutputPortDefinition(key=FALSE_PORT, label="False", description="Taken when the condition does not match."),
    ),
    runtime_validator=_validate_core_if_config,
    runtime_executor=_execute_if,
    parameter_schema=(
        ParameterDefinition(
            key="path",
            label="Context Path",
            value_type="string",
            required=True,
            description="Path resolved from the workflow context.",
            placeholder="context.value",
        ),
        ParameterDefinition(
            key="operator",
            label="Operator",
            value_type="string",
            required=True,
            description="Comparison operator.",
            default="equals",
            options=(
                ParameterOptionDefinition(value="equals", label="Equals"),
                ParameterOptionDefinition(value="not_equals", label="Does Not Equal"),
                ParameterOptionDefinition(value="contains", label="Contains"),
                ParameterOptionDefinition(value="exists", label="Exists"),
                ParameterOptionDefinition(value="truthy", label="Is Truthy"),
            ),
        ),
        ParameterDefinition(
            key="right_value",
            label="Compare Against",
            value_type="string",
            required=False,
            description="Value compared against the selected path.",
            placeholder="hello",
            show_if=(
                {"operator": ["equals", "not_equals", "contains"]},
            ),
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
