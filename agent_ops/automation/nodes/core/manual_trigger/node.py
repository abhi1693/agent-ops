from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    raise_definition_error,
)


def _validate_manual_trigger(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del config, node_ids
    if len(outgoing_targets) > 1:
        raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')


def _execute_manual_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_manual_trigger,
    executor=_execute_manual_trigger,
)
