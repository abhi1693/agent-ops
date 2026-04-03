from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    raise_definition_error,
    validate_optional_string,
)
from automation.tools.base import _render_runtime_string


SUPPORTED_RESPONSE_STATUSES = frozenset({"succeeded", "failed"})


def _validate_response(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    validate_optional_string(config, "template", node_id=node_id)
    validate_optional_string(config, "value_path", node_id=node_id)
    status = config.get("status", "succeeded")
    if status not in SUPPORTED_RESPONSE_STATUSES:
        raise_definition_error(
            f'Node "{node_id}" config.status must be one of: {", ".join(sorted(SUPPORTED_RESPONSE_STATUSES))}.'
        )
    if outgoing_targets:
        raise_definition_error(f'Node "{node_id}" is terminal and cannot have outgoing edges.')


def _execute_response(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    if "value_path" in runtime.config:
        payload = runtime.get_path_value(
            runtime.context,
            _render_runtime_string(runtime, "value_path", default_mode="static"),
        )
    else:
        template = (
            _render_runtime_string(runtime, "template", default_mode="expression")
            or runtime.node.get("label")
            or runtime.node["id"]
        )
        payload = template

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


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_response,
    executor=_execute_response,
)
