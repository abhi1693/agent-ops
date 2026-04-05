from __future__ import annotations

from automation.catalog.capabilities import CAPABILITY_TRIGGER_MANUAL
from automation.catalog.definitions import CatalogNodeDefinition
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult

from automation.core_nodes._triggers import build_trigger_result


def _execute_manual_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return build_trigger_result(runtime)


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.manual_trigger",
    integration_id="core",
    mode="core",
    kind="trigger",
    label="Manual Trigger",
    description="Starts a workflow when a user runs it explicitly.",
    icon="mdi-play-circle-outline",
    default_name="Manual Trigger",
    node_group=("trigger",),
    capabilities=frozenset({CAPABILITY_TRIGGER_MANUAL}),
    runtime_executor=_execute_manual_trigger,
)


__all__ = ("NODE_DEFINITION",)
