from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeDefinition,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    node_field_option,
    node_node_target_field,
    node_select_field,
    node_text_field,
    raise_definition_error,
    validate_optional_string,
)


SUPPORTED_CONDITION_OPERATORS = frozenset({"equals", "not_equals", "contains", "exists", "truthy"})


def _validate_if(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    validate_optional_string(config, "path", node_id=node_id)
    operator = config.get("operator")
    if operator not in SUPPORTED_CONDITION_OPERATORS:
        raise_definition_error(
            (
                f'Node "{node_id}" config.operator must be one of: '
                f'{", ".join(sorted(SUPPORTED_CONDITION_OPERATORS))}.'
            )
        )
    if operator not in {"exists", "truthy"} and "right_value" not in config:
        raise_definition_error(f'Node "{node_id}" must define config.right_value for operator "{operator}".')

    true_target = config.get("true_target")
    false_target = config.get("false_target")
    if not isinstance(true_target, str) or not true_target.strip():
        raise_definition_error(f'Node "{node_id}" must define config.true_target.')
    if not isinstance(false_target, str) or not false_target.strip():
        raise_definition_error(f'Node "{node_id}" must define config.false_target.')
    if true_target == false_target:
        raise_definition_error(f'Node "{node_id}" true_target and false_target must be different.')

    for target_name, target_id in (("true_target", true_target), ("false_target", false_target)):
        if target_id not in node_ids:
            raise_definition_error(f'Node "{node_id}" {target_name} "{target_id}" does not exist.')
        if target_id not in outgoing_targets:
            raise_definition_error(
                f'Node "{node_id}" {target_name} "{target_id}" must also be represented by a graph edge.'
            )


def _execute_if(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    left_value = runtime.get_path_value(runtime.context, runtime.config.get("path"))
    matched = runtime.evaluate_condition(
        runtime.config["operator"],
        left_value,
        runtime.config.get("right_value"),
    )
    selected_target = runtime.config["true_target"] if matched else runtime.config["false_target"]
    return WorkflowNodeExecutionResult(
        next_node_id=selected_target,
        output={
            "path": runtime.config.get("path"),
            "operator": runtime.config["operator"],
            "matched": matched,
            "next_node_id": selected_target,
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_if,
    executor=_execute_if,
)
NODE_DEFINITION = WorkflowNodeDefinition(
    type="n8n-nodes-base.if",
    kind="condition",
    display_name="If",
    description="Branch to one of two connected targets using a simple conditional check.",
    icon="mdi-source-branch",
    catalog_section="flow",
    config={"operator": "equals"},
    fields=(
        node_text_field(
            "path",
            "Context path",
            placeholder="trigger.payload.priority",
        ),
        node_select_field(
            "operator",
            "Operator",
            options=(
                node_field_option("equals", "Equals"),
                node_field_option("not_equals", "Does not equal"),
                node_field_option("contains", "Contains"),
                node_field_option("exists", "Exists"),
                node_field_option("truthy", "Is truthy"),
            ),
        ),
        node_text_field(
            "right_value",
            "Compare against",
            placeholder="high",
            help_text="Not used for exists or truthy operators.",
        ),
        node_node_target_field("true_target", "If true, go to"),
        node_node_target_field("false_target", "If false, go to"),
    ),
    validator=NODE_IMPLEMENTATION.validator,
    executor=NODE_IMPLEMENTATION.executor,
)
