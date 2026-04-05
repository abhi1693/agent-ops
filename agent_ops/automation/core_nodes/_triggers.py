from __future__ import annotations

from typing import Any

from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


def build_trigger_output(
    runtime: WorkflowNodeExecutionContext,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "payload": runtime.context["trigger"]["payload"],
        "trigger_type": runtime.context["trigger"]["type"],
        "trigger_meta": runtime.context["trigger"].get("meta", {}),
    }
    if extra:
        payload.update(extra)
    return payload


def build_trigger_result(
    runtime: WorkflowNodeExecutionContext,
    *,
    extra: dict[str, Any] | None = None,
) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output=build_trigger_output(runtime, extra=extra),
    )


__all__ = ("build_trigger_output", "build_trigger_result")
