from __future__ import annotations

from automation.catalog.capabilities import CAPABILITY_TRIGGER_SCHEDULE
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ParameterDefinition,
)
from automation.catalog.validation import raise_definition_error, validate_parameter_schema
from automation.core_nodes._triggers import build_trigger_result
from automation.core_nodes.schedule_trigger.schedules import (
    parse_schedule_trigger_config,
    serialize_schedule_trigger_config,
    validate_schedule_config,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


def _validate_schedule_trigger_config(*, config, node_id, outgoing_targets, **_) -> None:
    validate_parameter_schema(
        node_definition=NODE_DEFINITION,
        config=config,
        node_id=node_id,
        node_ids=set(),
        outgoing_targets=outgoing_targets,
    )
    try:
        validate_schedule_config(config)
    except ValueError as exc:
        raise_definition_error(f'Node "{node_id}" {exc}')


def _execute_schedule_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    try:
        schedule = parse_schedule_trigger_config(runtime.config)
    except ValueError as exc:
        raise_definition_error(f'Node "{runtime.node["id"]}" {exc}')
        raise AssertionError("unreachable") from exc

    return build_trigger_result(
        runtime,
        extra={
            "schedule": serialize_schedule_trigger_config(schedule),
        },
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.schedule_trigger",
    integration_id="core",
    mode="core",
    kind="trigger",
    label="Schedule Trigger",
    description="Starts a workflow on a delayed or recurring interval schedule.",
    icon="mdi-calendar-clock",
    default_name="Schedule Trigger",
    subtitle='={{config.interval_minutes || config.schedule_at || "schedule"}}',
    node_group=("trigger",),
    capabilities=frozenset({CAPABILITY_TRIGGER_SCHEDULE}),
    runtime_validator=_validate_schedule_trigger_config,
    runtime_executor=_execute_schedule_trigger,
    parameter_schema=(
        ParameterDefinition(
            key="schedule_at",
            label="Schedule At",
            field_type="datetime",
            value_type="string",
            required=False,
            description="Initial time to enqueue the workflow.",
            placeholder="2026-04-06T10:30",
            ui_group="input",
        ),
        ParameterDefinition(
            key="interval_minutes",
            label="Interval Minutes",
            value_type="integer",
            required=False,
            description="Re-enqueue the workflow at this interval after each run finishes.",
            help_text='If set without "Schedule At", the first run is scheduled immediately.',
            ui_group="input",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
