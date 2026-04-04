from __future__ import annotations

from automation.catalog.capabilities import CAPABILITY_TRIGGER_MANUAL
from automation.catalog.definitions import CatalogNodeDefinition
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


def _execute_manual_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
        },
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.manual_trigger",
    integration_id="core",
    mode="core",
    kind="trigger",
    label="Manual Trigger",
    description="Starts a workflow when a user runs it explicitly.",
    icon="mdi-play-circle-outline",
    capabilities=frozenset({CAPABILITY_TRIGGER_MANUAL}),
    runtime_executor=_execute_manual_trigger,
)


__all__ = ("NODE_DEFINITION",)
