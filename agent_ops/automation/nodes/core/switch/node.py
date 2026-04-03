from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeDefinition,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    node_node_target_field,
    node_text_field,
    raise_definition_error,
    validate_required_string,
)


def _validate_switch(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    validate_required_string(config, "path", node_id=node_id)
    validate_required_string(config, "case_1_value", node_id=node_id)
    validate_required_string(config, "case_1_target", node_id=node_id)
    validate_required_string(config, "case_2_value", node_id=node_id)
    validate_required_string(config, "case_2_target", node_id=node_id)
    validate_required_string(config, "fallback_target", node_id=node_id)

    targets = (
        ("case_1_target", config["case_1_target"]),
        ("case_2_target", config["case_2_target"]),
        ("fallback_target", config["fallback_target"]),
    )
    target_ids = [target_id for _, target_id in targets]
    if len(set(target_ids)) != len(target_ids):
        raise_definition_error(f'Node "{node_id}" switch targets must be different.')

    for target_name, target_id in targets:
        if target_id not in node_ids:
            raise_definition_error(f'Node "{node_id}" {target_name} "{target_id}" does not exist.')
        if target_id not in outgoing_targets:
            raise_definition_error(
                f'Node "{node_id}" {target_name} "{target_id}" must also be represented by a graph edge.'
            )


def _execute_switch(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    left_value = runtime.get_path_value(runtime.context, runtime.config["path"])
    left_text = "" if left_value is None else str(left_value)

    matched_case = "fallback"
    next_node_id = runtime.config["fallback_target"]
    if left_text == str(runtime.config["case_1_value"]):
        matched_case = "case_1"
        next_node_id = runtime.config["case_1_target"]
    elif left_text == str(runtime.config["case_2_value"]):
        matched_case = "case_2"
        next_node_id = runtime.config["case_2_target"]

    return WorkflowNodeExecutionResult(
        next_node_id=next_node_id,
        output={
            "path": runtime.config["path"],
            "matched_case": matched_case,
            "next_node_id": next_node_id,
            "value": left_value,
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_switch,
    executor=_execute_switch,
)
NODE_DEFINITION = WorkflowNodeDefinition(
    type="core.switch",
    kind="condition",
    display_name="Switch",
    description="Route to one of multiple targets using simple value matching.",
    icon="mdi-call-split",
    catalog_section="flow",
    fields=(
        node_text_field(
            "path",
            "Context path",
            placeholder="trigger.payload.status",
        ),
        node_text_field(
            "case_1_value",
            "Case 1 value",
            placeholder="queued",
        ),
        node_node_target_field("case_1_target", "Case 1 target"),
        node_text_field(
            "case_2_value",
            "Case 2 value",
            placeholder="running",
        ),
        node_node_target_field("case_2_target", "Case 2 target"),
        node_node_target_field("fallback_target", "Fallback target"),
    ),
    validator=NODE_IMPLEMENTATION.validator,
    executor=NODE_IMPLEMENTATION.executor,
)
