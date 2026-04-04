from __future__ import annotations

from automation.catalog.capabilities import CAPABILITY_TRIGGER_SCHEDULE
from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import _render_runtime_string


def _execute_schedule_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    cron = _render_runtime_string(runtime, "cron", required=True, default_mode="static")
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
            "schedule": {
                "mode": "cron",
                "cron": cron,
            },
        },
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.schedule_trigger",
    integration_id="core",
    mode="core",
    kind="trigger",
    label="Schedule Trigger",
    description="Starts a workflow on a recurring cron schedule.",
    icon="mdi-calendar-clock",
    capabilities=frozenset({CAPABILITY_TRIGGER_SCHEDULE}),
    runtime_executor=_execute_schedule_trigger,
    parameter_schema=(
        ParameterDefinition(
            key="cron",
            label="Cron Expression",
            value_type="string",
            required=True,
            description="Cron expression used to schedule workflow runs.",
            placeholder="0 * * * *",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
