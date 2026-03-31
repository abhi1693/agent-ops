from __future__ import annotations

import json

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    raise_definition_error,
)


def _validate_stop_and_error(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    if outgoing_targets:
        raise_definition_error(f'Node "{node_id}" is terminal and cannot have outgoing edges.')

    error_type = config.get("error_type", "errorMessage")
    if error_type not in {"errorMessage", "errorObject"}:
        raise_definition_error(f'Node "{node_id}" config.error_type must be one of: errorMessage, errorObject.')

    if error_type == "errorMessage":
        error_message = config.get("error_message")
        if not isinstance(error_message, str) or not error_message.strip():
            raise_definition_error(f'Node "{node_id}" must define config.error_message.')
        return

    error_object = config.get("error_object")
    if not isinstance(error_object, str) or not error_object.strip():
        raise_definition_error(f'Node "{node_id}" must define config.error_object.')
    try:
        parsed_object = json.loads(error_object)
    except json.JSONDecodeError as exc:
        raise_definition_error(f'Node "{node_id}" config.error_object must be valid JSON: {exc.msg}.')
    if not isinstance(parsed_object, dict):
        raise_definition_error(f'Node "{node_id}" config.error_object must decode to a JSON object.')


def _execute_stop_and_error(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    error_type = runtime.config.get("error_type", "errorMessage")
    if error_type == "errorObject":
        payload = json.loads(runtime.config["error_object"])
    else:
        payload = {
            "message": runtime.config.get("error_message") or "An error occurred.",
        }

    output = {
        "node_id": runtime.node["id"],
        "response": payload,
    }
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        output=output,
        response=output,
        run_status="failed",
        terminal=True,
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_stop_and_error,
    executor=_execute_stop_and_error,
)
