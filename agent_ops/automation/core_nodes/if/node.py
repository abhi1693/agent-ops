from __future__ import annotations

from automation.catalog.definitions import (
    CatalogNodeDefinition,
    OutputPortDefinition,
    ParameterCollectionOptionDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.catalog.validation import (
    raise_definition_error,
    validate_parameter_schema,
)
from automation.core_nodes._conditions import evaluate_condition_block
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


TRUE_PORT = "true"
FALSE_PORT = "false"


def _build_condition_block(config: dict) -> dict:
    raw_conditions = config.get("conditions")
    if isinstance(raw_conditions, dict):
        raw_values = raw_conditions.get("conditions")
        if isinstance(raw_values, list):
            return {
                "conditions": [item for item in raw_values if isinstance(item, dict)],
                "combinator": str(config.get("combinator") or "and").strip().lower() or "and",
            }

    return {
        "conditions": [],
        "combinator": str(config.get("combinator") or "and").strip().lower() or "and",
    }


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
    conditions_block = _build_condition_block(config)
    raw_conditions = conditions_block.get("conditions")
    if not raw_conditions:
        raise_definition_error(f'Node "{node_id}" conditions block must define at least one condition.')
    if len(outgoing_targets_by_source_port.get(TRUE_PORT, [])) != 1:
        raise_definition_error(f'Node "{node_id}" must connect exactly one "{TRUE_PORT}" edge.')
    if len(outgoing_targets_by_source_port.get(FALSE_PORT, [])) != 1:
        raise_definition_error(f'Node "{node_id}" must connect exactly one "{FALSE_PORT}" edge.')
    if outgoing_targets_by_source_port[TRUE_PORT][0] == outgoing_targets_by_source_port[FALSE_PORT][0]:
        raise_definition_error(f'Node "{node_id}" "{TRUE_PORT}" and "{FALSE_PORT}" edges must target different nodes.')


def _execute_if(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    conditions_block = _build_condition_block(runtime.config)
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
            value_type="object",
            field_type="fixed_collection",
            required=True,
            description="Add one or more conditions that control the true or false branch.",
            ui_group="input",
            collection_options=(
                ParameterCollectionOptionDefinition(
                    key="conditions",
                    label="Condition",
                    multiple=True,
                    fields=(
                        ParameterDefinition(
                            key="leftPath",
                            label="Left Path",
                            value_type="string",
                            required=True,
                            description="Workflow context path to evaluate.",
                            placeholder="trigger.payload.status",
                        ),
                        ParameterDefinition(
                            key="operator",
                            label="Operator",
                            value_type="string",
                            required=True,
                            default="equals",
                            no_data_expression=True,
                            options=(
                                ParameterOptionDefinition(value="equals", label="Equals"),
                                ParameterOptionDefinition(value="not_equals", label="Does not equal"),
                                ParameterOptionDefinition(value="contains", label="Contains"),
                                ParameterOptionDefinition(value="not_contains", label="Does not contain"),
                                ParameterOptionDefinition(value="greater_than", label="Greater than"),
                                ParameterOptionDefinition(value="less_than", label="Less than"),
                                ParameterOptionDefinition(value="starts_with", label="Starts with"),
                                ParameterOptionDefinition(value="ends_with", label="Ends with"),
                                ParameterOptionDefinition(value="is_empty", label="Is empty"),
                                ParameterOptionDefinition(value="not_empty", label="Is not empty"),
                            ),
                        ),
                        ParameterDefinition(
                            key="rightValue",
                            label="Right Value",
                            value_type="string",
                            required=False,
                            placeholder="production",
                            display_options={
                                "show": {
                                    "operator": (
                                        "equals",
                                        "not_equals",
                                        "contains",
                                        "not_contains",
                                        "greater_than",
                                        "less_than",
                                        "starts_with",
                                        "ends_with",
                                    ),
                                },
                            },
                        ),
                    ),
                ),
            ),
        ),
        ParameterDefinition(
            key="combinator",
            label="Match",
            value_type="string",
            required=False,
            description="How multiple conditions should be combined.",
            default="and",
            no_data_expression=True,
            ui_group="advanced",
            options=(
                ParameterOptionDefinition(value="and", label="All conditions"),
                ParameterOptionDefinition(value="or", label="Any condition"),
            ),
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
