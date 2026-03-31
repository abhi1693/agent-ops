from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
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
