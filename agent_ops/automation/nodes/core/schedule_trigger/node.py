from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    raise_definition_error,
)


_SUPPORTED_SCHEDULE_MODES = frozenset({"interval", "cron"})
_SUPPORTED_INTERVAL_UNITS = frozenset({"minutes", "hours", "days"})


def _validate_schedule_trigger(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    if len(outgoing_targets) > 1:
        raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')

    mode = config.get("mode", "interval")
    if mode not in _SUPPORTED_SCHEDULE_MODES:
        raise_definition_error(f'Node "{node_id}" config.mode must be one of: cron, interval.')

    if mode == "cron":
        cron_expression = config.get("cron_expression")
        if not isinstance(cron_expression, str) or not cron_expression.strip():
            raise_definition_error(f'Node "{node_id}" must define config.cron_expression for cron mode.')
        return

    interval_unit = config.get("interval_unit", "minutes")
    if interval_unit not in _SUPPORTED_INTERVAL_UNITS:
        raise_definition_error(f'Node "{node_id}" config.interval_unit must be one of: days, hours, minutes.')

    interval_value = config.get("interval_value", "1")
    if isinstance(interval_value, int):
        parsed_interval = interval_value
    elif isinstance(interval_value, str) and interval_value.strip().isdigit():
        parsed_interval = int(interval_value.strip())
    else:
        raise_definition_error(f'Node "{node_id}" config.interval_value must be a positive integer.')

    if parsed_interval <= 0:
        raise_definition_error(f'Node "{node_id}" config.interval_value must be greater than zero.')


def _execute_schedule_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
            "schedule": {
                "mode": runtime.config.get("mode", "interval"),
                "interval_unit": runtime.config.get("interval_unit", "minutes"),
                "interval_value": runtime.config.get("interval_value", "1"),
                "cron_expression": runtime.config.get("cron_expression", ""),
            },
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_schedule_trigger,
    executor=_execute_schedule_trigger,
)
