from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    raise_definition_error,
    validate_required_string,
)
from automation.tools.base import _render_runtime_string


def _validate_set(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    validate_required_string(config, "output_key", node_id=node_id)
    if len(outgoing_targets) > 1:
        raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')


def _execute_set(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    value = _render_runtime_string(runtime, "value")
    runtime.set_path_value(runtime.context, output_key, value)
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "tool_name": "set",
            "operation": "set",
            "output_key": output_key,
            "value": value,
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_set,
    executor=_execute_set,
)
