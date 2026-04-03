from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeDefinition,
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
NODE_DEFINITION = WorkflowNodeDefinition(
    type="n8n-nodes-base.manualTrigger",
    kind="trigger",
    display_name="Manual Trigger",
    description="Start a workflow manually from the UI or API, following n8n's starter trigger pattern.",
    icon="mdi-play-circle-outline",
    app_description="Core workflow nodes, runtime primitives, and n8n-style built-in blocks available in the designer.",
    app_icon="mdi-toy-brick-outline",
    validator=NODE_IMPLEMENTATION.validator,
    executor=NODE_IMPLEMENTATION.executor,
)
