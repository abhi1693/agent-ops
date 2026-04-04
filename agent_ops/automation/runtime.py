from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.template import Context, Engine
from django.utils import timezone

from automation.catalog.runtime import execute_catalog_runtime_node
from automation.catalog.services import get_catalog_node
from automation.queue import (
    enqueue_workflow_run_job,
    ensure_workers_for_queue,
    get_workflow_queue_name,
)
from automation.runtime_types import WorkflowNodeExecutionContext
from automation.auth import resolve_workflow_secret_ref
from automation.workflow_connections import (
    build_auxiliary_connections_by_target,
    get_edge_source_port,
    split_workflow_edges,
)
from automation.models.runs import WorkflowRun, WorkflowStepRun
from automation.models.versions import ensure_workflow_version_snapshot
from automation.primitives import (
    normalize_workflow_definition_nodes,
    validate_workflow_runtime_definition,
)


_TEMPLATE_ENGINE = Engine(debug=False)
_REDACTED_VALUE = "[redacted secret]"


@dataclass
class _NodeExecutionResult:
    next_node_id: str | None
    next_port: str | None = None
    output: dict[str, Any] | None = None
    response: Any = None
    run_status: str | None = None
    terminal: bool = False


def _flatten_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        parts = []
        for field, messages in error.message_dict.items():
            parts.append(f"{field}: {' '.join(messages)}")
        return " ".join(parts)
    return " ".join(error.messages)


def _render_template(template: str, context: dict[str, Any]) -> str:
    compiled = _TEMPLATE_ENGINE.from_string(template)
    return compiled.render(Context(context)).strip()


def _split_path(path: str) -> list[str]:
    return [segment for segment in path.split(".") if segment]


def _get_path_value(data: Any, path: str | None) -> Any:
    if not path:
        return data

    current = data
    for segment in _split_path(path):
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(current, list):
            try:
                index = int(segment)
            except (TypeError, ValueError):
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


def _set_path_value(data: dict[str, Any], path: str, value: Any) -> None:
    current = data
    segments = _split_path(path)
    if not segments:
        raise ValidationError({"definition": "Runtime output_key cannot be empty."})

    for segment in segments[:-1]:
        nested = current.get(segment)
        if not isinstance(nested, dict):
            nested = {}
            current[segment] = nested
        current = nested

    current[segments[-1]] = value


def _redact_value(
    value: Any,
    *,
    path: str = "",
    secret_paths: set[str],
    secret_values: list[str],
) -> Any:
    if path and path in secret_paths:
        return _REDACTED_VALUE

    if isinstance(value, dict):
        return {
            key: _redact_value(
                item,
                path=f"{path}.{key}" if path else key,
                secret_paths=secret_paths,
                secret_values=secret_values,
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _redact_value(
                item,
                path=f"{path}.{index}" if path else str(index),
                secret_paths=secret_paths,
                secret_values=secret_values,
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, str):
        redacted = value
        for secret_value in secret_values:
            if secret_value:
                redacted = redacted.replace(secret_value, _REDACTED_VALUE)
        return redacted

    return value


def _resolve_scoped_secret(
    workflow,
    *,
    secret_name: str,
    secret_group_id=None,
    required: bool = True,
):
    return resolve_workflow_secret_ref(
        workflow,
        secret_name=secret_name,
        secret_group_id=secret_group_id,
        error_field="definition",
        required=required,
    )


def _evaluate_condition(operator: str, left_value: Any, right_value: Any) -> bool:
    if operator == "equals":
        return left_value == right_value
    if operator == "not_equals":
        return left_value != right_value
    if operator == "contains":
        if left_value is None:
            return False
        try:
            return right_value in left_value
        except TypeError:
            return False
    if operator == "exists":
        return left_value is not None
    if operator == "truthy":
        return bool(left_value)
    raise ValidationError({"definition": f'Unsupported condition operator "{operator}".'})


def _build_execution_context(
    workflow,
    *,
    workflow_version=None,
    input_data: dict[str, Any],
    trigger_type: str,
    trigger_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "workflow": {
            "id": workflow.pk,
            "name": workflow.name,
            "scope_label": workflow.scope_label,
            "version_id": workflow_version.pk if workflow_version is not None else None,
            "version": workflow_version.version if workflow_version is not None else None,
        },
        "trigger": {
            "type": trigger_type,
            "payload": input_data,
            "meta": trigger_metadata or {},
        },
        "messages": [],
    }


def _execute_node(
    *,
    workflow,
    node: dict[str, Any],
    next_node_id: str | None,
    connected_nodes_by_port: dict[str, list[dict[str, Any]]],
    context: dict[str, Any],
    secret_paths: set[str],
    secret_values: list[str],
) -> _NodeExecutionResult:
    node_type = node.get("type")
    catalog_definition = get_catalog_node(node_type) if isinstance(node_type, str) else None
    if catalog_definition is None:
        raise ValidationError({"definition": f'Unsupported node type "{node_type}".'})
    catalog_node_output = execute_catalog_runtime_node(
        WorkflowNodeExecutionContext(
            workflow=workflow,
            node=node,
            config=node.get("config") or {},
            next_node_id=next_node_id,
            connected_nodes_by_port=connected_nodes_by_port,
            context=context,
            secret_paths=secret_paths,
            secret_values=secret_values,
            render_template=_render_template,
            get_path_value=_get_path_value,
            set_path_value=_set_path_value,
            resolve_scoped_secret=_resolve_scoped_secret,
            evaluate_condition=_evaluate_condition,
        )
    )
    if catalog_node_output is None:
        raise ValidationError({"definition": f'Catalog node type "{node_type}" has no native runtime executor.'})
    return _NodeExecutionResult(
        next_node_id=catalog_node_output.next_node_id,
        next_port=catalog_node_output.next_port,
        output=catalog_node_output.output,
        response=catalog_node_output.response,
        run_status=catalog_node_output.run_status,
        terminal=catalog_node_output.terminal,
    )


def _sorted_secret_values(secret_values: list[str]) -> list[str]:
    return sorted(secret_values, key=len, reverse=True)


def _build_step_input_snapshot(*, context: dict[str, Any], next_node_id: str | None) -> dict[str, Any]:
    return {
        "context": context,
        "next_node_id": next_node_id,
    }


def _build_step_output_snapshot(
    *,
    result: _NodeExecutionResult,
) -> dict[str, Any]:
    snapshot = dict(result.output or {})
    snapshot["next_node_id"] = result.next_node_id
    if result.next_port is not None:
        snapshot["next_port"] = result.next_port
    snapshot["terminal"] = result.terminal
    if result.response is not None and "response" not in snapshot:
        snapshot["response"] = result.response
    if result.run_status is not None:
        snapshot["run_status"] = result.run_status
    return snapshot


def _build_scheduler_state_payload(
    *,
    ready_node_ids: list[str],
    active_node_ids: set[str],
    activated_node_ids: set[str],
    completed_node_ids: set[str],
    failed_node_ids: set[str],
    skipped_node_ids: set[str],
    selected_predecessors: dict[str, set[str]],
    skipped_predecessors: dict[str, set[str]],
) -> dict[str, Any]:
    return {
        "ready_node_ids": list(ready_node_ids),
        "active_node_ids": sorted(active_node_ids),
        "activated_node_ids": sorted(activated_node_ids),
        "completed_node_ids": sorted(completed_node_ids),
        "failed_node_ids": sorted(failed_node_ids),
        "skipped_node_ids": sorted(skipped_node_ids),
        "selected_predecessors": {
            node_id: sorted(predecessors)
            for node_id, predecessors in sorted(selected_predecessors.items())
            if predecessors
        },
        "skipped_predecessors": {
            node_id: sorted(predecessors)
            for node_id, predecessors in sorted(skipped_predecessors.items())
            if predecessors
        },
    }


def _update_run_scheduler_state(
    run: WorkflowRun,
    *,
    ready_node_ids: list[str],
    active_node_ids: set[str],
    activated_node_ids: set[str],
    completed_node_ids: set[str],
    failed_node_ids: set[str],
    skipped_node_ids: set[str],
    selected_predecessors: dict[str, set[str]],
    skipped_predecessors: dict[str, set[str]],
) -> dict[str, Any]:
    scheduler_state = _build_scheduler_state_payload(
        ready_node_ids=ready_node_ids,
        active_node_ids=active_node_ids,
        activated_node_ids=activated_node_ids,
        completed_node_ids=completed_node_ids,
        failed_node_ids=failed_node_ids,
        skipped_node_ids=skipped_node_ids,
        selected_predecessors=selected_predecessors,
        skipped_predecessors=skipped_predecessors,
    )
    run.scheduler_state = scheduler_state
    return scheduler_state


def _persist_run_scheduler_state(run: WorkflowRun) -> None:
    run.save(update_fields=("scheduler_state", "last_updated"))


def _get_default_next_node_id(outgoing_targets: list[str]) -> str | None:
    if len(outgoing_targets) == 1:
        return outgoing_targets[0]
    return None


def _resolve_selected_targets(
    *,
    result: _NodeExecutionResult,
    outgoing_targets: list[str],
    outgoing_targets_by_source_port: dict[str, list[str]],
) -> list[str]:
    if result.terminal:
        return []
    if result.next_node_id:
        return [result.next_node_id]
    if result.next_port is not None:
        return list(outgoing_targets_by_source_port.get(result.next_port, []))
    if outgoing_targets:
        return list(outgoing_targets)
    return []


def _initialize_workflow_run(
    workflow,
    *,
    input_data: dict[str, Any] | None,
    trigger_mode: str,
    trigger_metadata: dict[str, Any] | None,
    actor,
    execution_mode: str,
    target_node_id: str | None = None,
    status: str = WorkflowRun.StatusChoices.PENDING,
    queue_name: str = "",
) -> WorkflowRun:
    workflow_version = ensure_workflow_version_snapshot(workflow)
    return WorkflowRun.objects.create(
        workflow=workflow,
        workflow_version=workflow_version,
        trigger_mode=trigger_mode,
        trigger_metadata=trigger_metadata or {},
        execution_mode=execution_mode,
        target_node_id=target_node_id or "",
        status=status,
        input_data=input_data or {},
        requested_by=actor,
        queue_name=queue_name,
    )


def _load_runtime_definition(
    run: WorkflowRun,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, list[str]],
    dict[str, dict[str, list[str]]],
    dict[str, dict[str, list[dict[str, Any]]]],
]:
    definition = normalize_workflow_definition_nodes(run.workflow_version.definition or {})
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    nodes_by_id = {node["id"]: node for node in nodes}
    primary_edges, auxiliary_edges = split_workflow_edges(edges)
    adjacency: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    primary_targets_by_source_port: dict[str, dict[str, list[str]]] = {node["id"]: {} for node in nodes}
    for edge in primary_edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
        source_port = get_edge_source_port(edge)
        if source_port is not None:
            primary_targets_by_source_port.setdefault(edge["source"], {}).setdefault(source_port, []).append(
                edge["target"]
            )
    auxiliary_connections_by_target = build_auxiliary_connections_by_target(
        nodes_by_id=nodes_by_id,
        edges=auxiliary_edges,
    )
    return (
        definition,
        nodes,
        nodes_by_id,
        adjacency,
        primary_targets_by_source_port,
        auxiliary_connections_by_target,
    )


def _record_step_failure(
    *,
    step_run: WorkflowStepRun,
    default_next_node_id: str | None,
    error: ValidationError,
    secret_paths: set[str],
    secret_values: list[str],
) -> None:
    step_run.status = WorkflowStepRun.StatusChoices.FAILED
    step_run.error = _flatten_validation_error(error)
    step_run.output_data = _redact_value(
        {
            "result": {},
            "next_node_id": default_next_node_id,
            "terminal": False,
        },
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    step_run.finished_at = timezone.now()
    step_run.save(
        update_fields=(
            "status",
            "error",
            "output_data",
            "finished_at",
            "last_updated",
        )
    )


def _record_step_success(
    *,
    step_run: WorkflowStepRun,
    node: dict[str, Any],
    result: _NodeExecutionResult,
    step_results: list[dict[str, Any]],
    secret_paths: set[str],
    secret_values: list[str],
) -> None:
    step_run.status = WorkflowStepRun.StatusChoices.SUCCEEDED
    step_run.output_data = _redact_value(
        _build_step_output_snapshot(result=result),
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    step_run.finished_at = timezone.now()
    step_run.save(
        update_fields=(
            "status",
            "output_data",
            "finished_at",
            "last_updated",
        )
    )
    step_results.append(
        {
            "node_id": node["id"],
            "kind": node["kind"],
            "type": node.get("type"),
            "label": node.get("label") or node["id"],
            "result": result.output or {},
        }
    )


def _build_node_response_payload(node: dict[str, Any], result: _NodeExecutionResult) -> dict[str, Any]:
    return {
        "node_id": node["id"],
        "label": node.get("label") or node["id"],
        "response": result.response if result.response is not None else result.output or {},
        "output": result.output or {},
        "next_node_id": result.next_node_id,
        "next_port": result.next_port,
        "terminal": result.terminal,
    }


def _finalize_workflow_run_success(
    *,
    run: WorkflowRun,
    run_status: str,
    response_payload: dict[str, Any],
    context: dict[str, Any],
    scheduler_state: dict[str, Any],
    step_results: list[dict[str, Any]],
    secret_paths: set[str],
    secret_values: list[str],
) -> WorkflowRun:
    run.status = run_status
    run.error = ""
    run.output_data = _redact_value(
        response_payload,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.context_data = _redact_value(
        context,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.scheduler_state = _redact_value(
        scheduler_state,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.step_results = _redact_value(
        step_results,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.finished_at = timezone.now()
    run.save(
        update_fields=(
            "status",
            "error",
            "output_data",
            "context_data",
            "scheduler_state",
            "step_results",
            "finished_at",
            "last_updated",
        )
    )
    return run


def _finalize_workflow_run_failure(
    *,
    run: WorkflowRun,
    error: Exception,
    context: dict[str, Any],
    scheduler_state: dict[str, Any],
    step_results: list[dict[str, Any]],
    secret_paths: set[str],
    secret_values: list[str],
) -> WorkflowRun:
    message = _flatten_validation_error(error) if isinstance(error, ValidationError) else str(error)
    run.status = WorkflowRun.StatusChoices.FAILED
    run.error = message
    run.context_data = _redact_value(
        context,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.scheduler_state = _redact_value(
        scheduler_state,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.step_results = _redact_value(
        step_results,
        secret_paths=secret_paths,
        secret_values=_sorted_secret_values(secret_values),
    )
    run.finished_at = timezone.now()
    run.save(
        update_fields=(
            "status",
            "error",
            "context_data",
            "scheduler_state",
            "step_results",
            "finished_at",
            "last_updated",
        )
    )
    return run


def execute_workflow_run(run: WorkflowRun) -> WorkflowRun:
    secret_paths: set[str] = set()
    secret_values: list[str] = []
    step_results: list[dict[str, Any]] = []

    if run.workflow_version_id is None:
        run.workflow_version = ensure_workflow_version_snapshot(run.workflow)
        run.save(update_fields=("workflow_version", "last_updated"))

    (
        definition,
        nodes,
        nodes_by_id,
        adjacency,
        primary_targets_by_source_port,
        auxiliary_connections_by_target,
    ) = _load_runtime_definition(run)
    context = _build_execution_context(
        run.workflow,
        workflow_version=run.workflow_version,
        input_data=run.input_data or {},
        trigger_type=run.trigger_mode,
        trigger_metadata=run.trigger_metadata or {},
    )
    ready_node_ids: list[str] = []
    active_node_ids: set[str] = set()
    activated_node_ids: set[str] = set()
    completed_node_ids: set[str] = set()
    failed_node_ids: set[str] = set()
    skipped_node_ids: set[str] = set()
    selected_predecessors: dict[str, set[str]] = {}
    skipped_predecessors: dict[str, set[str]] = {}
    incoming_predecessors: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    for source_id, target_ids in adjacency.items():
        for target_id in target_ids:
            incoming_predecessors.setdefault(target_id, set()).add(source_id)

    scheduler_state = _update_run_scheduler_state(
        run,
        ready_node_ids=ready_node_ids,
        active_node_ids=active_node_ids,
        activated_node_ids=activated_node_ids,
        completed_node_ids=completed_node_ids,
        failed_node_ids=failed_node_ids,
        skipped_node_ids=skipped_node_ids,
        selected_predecessors=selected_predecessors,
        skipped_predecessors=skipped_predecessors,
    )
    run.status = WorkflowRun.StatusChoices.RUNNING
    run.error = ""
    run.finished_at = None
    run.output_data = {}
    run.context_data = {}
    run.scheduler_state = scheduler_state
    run.step_results = []
    run.save(
        update_fields=(
            "status",
            "error",
            "finished_at",
            "output_data",
            "context_data",
            "scheduler_state",
            "step_results",
            "last_updated",
        )
    )

    try:
        validate_workflow_runtime_definition(nodes=nodes, edges=definition.get("edges", []))
        target_node_id = run.target_node_id or None
        if target_node_id is not None and target_node_id not in nodes_by_id:
            raise ValidationError({"definition": f'Workflow does not define node "{target_node_id}".'})

        if run.execution_mode == WorkflowRun.ExecutionModeChoices.NODE_PREVIEW:
            node = nodes_by_id[target_node_id]
            outgoing_targets = adjacency.get(node["id"], [])
            default_next_node_id = _get_default_next_node_id(outgoing_targets)
            activated_node_ids.add(node["id"])
            active_node_ids.add(node["id"])
            scheduler_state = _update_run_scheduler_state(
                run,
                ready_node_ids=ready_node_ids,
                active_node_ids=active_node_ids,
                activated_node_ids=activated_node_ids,
                completed_node_ids=completed_node_ids,
                failed_node_ids=failed_node_ids,
                skipped_node_ids=skipped_node_ids,
                selected_predecessors=selected_predecessors,
                skipped_predecessors=skipped_predecessors,
            )
            _persist_run_scheduler_state(run)

            with transaction.atomic():
                step_run = WorkflowStepRun.objects.create(
                    run=run,
                    workflow_version=run.workflow_version,
                    sequence=1,
                    node_id=node["id"],
                    node_kind=node["kind"],
                    node_type=node.get("type") or "",
                    label=node.get("label") or node["id"],
                    status=WorkflowStepRun.StatusChoices.RUNNING,
                    input_data=_redact_value(
                        _build_step_input_snapshot(
                            context=context,
                            next_node_id=default_next_node_id,
                        ),
                        secret_paths=secret_paths,
                        secret_values=_sorted_secret_values(secret_values),
                    ),
                )
                try:
                    result = _execute_node(
                        workflow=run.workflow,
                        node=node,
                        next_node_id=default_next_node_id,
                        connected_nodes_by_port=auxiliary_connections_by_target.get(node["id"], {}),
                        context=context,
                        secret_paths=secret_paths,
                        secret_values=secret_values,
                    )
                except ValidationError as exc:
                    active_node_ids.discard(node["id"])
                    failed_node_ids.add(node["id"])
                    scheduler_state = _update_run_scheduler_state(
                        run,
                        ready_node_ids=ready_node_ids,
                        active_node_ids=active_node_ids,
                        activated_node_ids=activated_node_ids,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        skipped_node_ids=skipped_node_ids,
                        selected_predecessors=selected_predecessors,
                        skipped_predecessors=skipped_predecessors,
                    )
                    _persist_run_scheduler_state(run)
                    _record_step_failure(
                        step_run=step_run,
                        default_next_node_id=default_next_node_id,
                        error=exc,
                        secret_paths=secret_paths,
                        secret_values=secret_values,
                    )
                    raise

                active_node_ids.discard(node["id"])
                completed_node_ids.add(node["id"])
                scheduler_state = _update_run_scheduler_state(
                    run,
                    ready_node_ids=ready_node_ids,
                    active_node_ids=active_node_ids,
                    activated_node_ids=activated_node_ids,
                    completed_node_ids=completed_node_ids,
                    failed_node_ids=failed_node_ids,
                    skipped_node_ids=skipped_node_ids,
                    selected_predecessors=selected_predecessors,
                    skipped_predecessors=skipped_predecessors,
                )
                _persist_run_scheduler_state(run)
                _record_step_success(
                    step_run=step_run,
                    node=node,
                    result=result,
                    step_results=step_results,
                    secret_paths=secret_paths,
                    secret_values=secret_values,
                )
            return _finalize_workflow_run_success(
                run=run,
                run_status=result.run_status or WorkflowRun.StatusChoices.SUCCEEDED,
                response_payload=_build_node_response_payload(node, result),
                context=context,
                scheduler_state=scheduler_state,
                step_results=step_results,
                secret_paths=secret_paths,
                secret_values=secret_values,
            )

        trigger_node = next(node for node in nodes if node["kind"] == "trigger")
        ready_node_ids.append(trigger_node["id"])
        activated_node_ids.add(trigger_node["id"])
        scheduler_state = _update_run_scheduler_state(
            run,
            ready_node_ids=ready_node_ids,
            active_node_ids=active_node_ids,
            activated_node_ids=activated_node_ids,
            completed_node_ids=completed_node_ids,
            failed_node_ids=failed_node_ids,
            skipped_node_ids=skipped_node_ids,
            selected_predecessors=selected_predecessors,
            skipped_predecessors=skipped_predecessors,
        )
        _persist_run_scheduler_state(run)
        max_steps = max(len(nodes) * 4, 1)
        step_count = 0
        response_payload: dict[str, Any] = {}
        run_status = WorkflowRun.StatusChoices.SUCCEEDED
        reached_stop_node = run.execution_mode != WorkflowRun.ExecutionModeChoices.NODE_PATH

        while ready_node_ids:
            step_count += 1
            if step_count > max_steps:
                raise ValidationError({"definition": "Workflow execution exceeded the supported step limit."})

            current_node_id = ready_node_ids.pop(0)
            if current_node_id in completed_node_ids or current_node_id in failed_node_ids:
                continue

            active_node_ids.add(current_node_id)
            scheduler_state = _update_run_scheduler_state(
                run,
                ready_node_ids=ready_node_ids,
                active_node_ids=active_node_ids,
                activated_node_ids=activated_node_ids,
                completed_node_ids=completed_node_ids,
                failed_node_ids=failed_node_ids,
                skipped_node_ids=skipped_node_ids,
                selected_predecessors=selected_predecessors,
                skipped_predecessors=skipped_predecessors,
            )
            _persist_run_scheduler_state(run)
            node = nodes_by_id[current_node_id]
            outgoing_targets = adjacency.get(current_node_id, [])
            default_next_node_id = _get_default_next_node_id(outgoing_targets)
            should_break = False

            with transaction.atomic():
                step_run = WorkflowStepRun.objects.create(
                    run=run,
                    workflow_version=run.workflow_version,
                    sequence=step_count,
                    node_id=node["id"],
                    node_kind=node["kind"],
                    node_type=node.get("type") or "",
                    label=node.get("label") or node["id"],
                    status=WorkflowStepRun.StatusChoices.RUNNING,
                    input_data=_redact_value(
                        _build_step_input_snapshot(
                            context=context,
                            next_node_id=default_next_node_id,
                        ),
                        secret_paths=secret_paths,
                        secret_values=_sorted_secret_values(secret_values),
                    ),
                )
                try:
                    result = _execute_node(
                        workflow=run.workflow,
                        node=node,
                        next_node_id=default_next_node_id,
                        connected_nodes_by_port=auxiliary_connections_by_target.get(node["id"], {}),
                        context=context,
                        secret_paths=secret_paths,
                        secret_values=secret_values,
                    )
                except ValidationError as exc:
                    active_node_ids.discard(current_node_id)
                    failed_node_ids.add(current_node_id)
                    scheduler_state = _update_run_scheduler_state(
                        run,
                        ready_node_ids=ready_node_ids,
                        active_node_ids=active_node_ids,
                        activated_node_ids=activated_node_ids,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        skipped_node_ids=skipped_node_ids,
                        selected_predecessors=selected_predecessors,
                        skipped_predecessors=skipped_predecessors,
                    )
                    _persist_run_scheduler_state(run)
                    _record_step_failure(
                        step_run=step_run,
                        default_next_node_id=default_next_node_id,
                        error=exc,
                        secret_paths=secret_paths,
                        secret_values=secret_values,
                    )
                    raise

                active_node_ids.discard(current_node_id)
                completed_node_ids.add(current_node_id)
                _record_step_success(
                    step_run=step_run,
                    node=node,
                    result=result,
                    step_results=step_results,
                    secret_paths=secret_paths,
                    secret_values=secret_values,
                )

                selected_targets = {
                    target_id
                    for target_id in _resolve_selected_targets(
                        result=result,
                        outgoing_targets=outgoing_targets,
                        outgoing_targets_by_source_port=primary_targets_by_source_port.get(current_node_id, {}),
                    )
                    if target_id in nodes_by_id
                }
                for target_id in selected_targets:
                    activated_node_ids.add(target_id)
                    selected_predecessors.setdefault(target_id, set()).add(current_node_id)

                for target_id in outgoing_targets:
                    if target_id not in selected_targets:
                        skipped_predecessors.setdefault(target_id, set()).add(current_node_id)

                for target_id in selected_targets:
                    active_predecessors = incoming_predecessors.get(target_id, set()).intersection(activated_node_ids)
                    unresolved_predecessors = {
                        predecessor_id
                        for predecessor_id in active_predecessors
                        if predecessor_id
                        not in selected_predecessors.get(target_id, set()).union(
                            skipped_predecessors.get(target_id, set())
                        )
                    }
                    if unresolved_predecessors:
                        continue
                    if (
                        target_id not in ready_node_ids
                        and target_id not in active_node_ids
                        and target_id not in completed_node_ids
                        and target_id not in failed_node_ids
                    ):
                        ready_node_ids.append(target_id)

                if run.execution_mode == WorkflowRun.ExecutionModeChoices.NODE_PATH and node["id"] == target_node_id:
                    reached_stop_node = True
                    response_payload = _build_node_response_payload(node, result)
                    if result.run_status:
                        run_status = result.run_status
                    skipped_node_ids.update(ready_node_ids)
                    skipped_node_ids.update(activated_node_ids - completed_node_ids - active_node_ids - failed_node_ids)
                    scheduler_state = _update_run_scheduler_state(
                        run,
                        ready_node_ids=[],
                        active_node_ids=active_node_ids,
                        activated_node_ids=activated_node_ids,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        skipped_node_ids=skipped_node_ids,
                        selected_predecessors=selected_predecessors,
                        skipped_predecessors=skipped_predecessors,
                    )
                    _persist_run_scheduler_state(run)
                    should_break = True
                elif result.terminal:
                    response_payload = result.response or {}
                    if result.run_status:
                        run_status = result.run_status
                    skipped_node_ids.update(ready_node_ids)
                    skipped_node_ids.update(activated_node_ids - completed_node_ids - active_node_ids - failed_node_ids)
                    scheduler_state = _update_run_scheduler_state(
                        run,
                        ready_node_ids=[],
                        active_node_ids=active_node_ids,
                        activated_node_ids=activated_node_ids,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        skipped_node_ids=skipped_node_ids,
                        selected_predecessors=selected_predecessors,
                        skipped_predecessors=skipped_predecessors,
                    )
                    _persist_run_scheduler_state(run)
                    should_break = True
                else:
                    scheduler_state = _update_run_scheduler_state(
                        run,
                        ready_node_ids=ready_node_ids,
                        active_node_ids=active_node_ids,
                        activated_node_ids=activated_node_ids,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        skipped_node_ids=skipped_node_ids,
                        selected_predecessors=selected_predecessors,
                        skipped_predecessors=skipped_predecessors,
                    )
                    _persist_run_scheduler_state(run)

            if should_break:
                break

        if not reached_stop_node:
            raise ValidationError(
                {"definition": f'Workflow execution did not reach node "{target_node_id}".'}
            )

        if not response_payload:
            response_payload = {
                "node_id": step_results[-1]["node_id"] if step_results else None,
                "response": None,
            }

        return _finalize_workflow_run_success(
            run=run,
            run_status=run_status,
            response_payload=response_payload,
            context=context,
            scheduler_state=scheduler_state,
            step_results=step_results,
            secret_paths=secret_paths,
            secret_values=secret_values,
        )
    except Exception as exc:
        scheduler_state = _update_run_scheduler_state(
            run,
            ready_node_ids=ready_node_ids,
            active_node_ids=active_node_ids,
            activated_node_ids=activated_node_ids,
            completed_node_ids=completed_node_ids,
            failed_node_ids=failed_node_ids,
            skipped_node_ids=skipped_node_ids,
            selected_predecessors=selected_predecessors,
            skipped_predecessors=skipped_predecessors,
        )
        return _finalize_workflow_run_failure(
            run=run,
            error=exc,
            context=context,
            scheduler_state=scheduler_state,
            step_results=step_results,
            secret_paths=secret_paths,
            secret_values=secret_values,
        )


def enqueue_workflow(
    workflow,
    *,
    input_data: dict[str, Any] | None = None,
    trigger_mode: str = "manual",
    trigger_metadata: dict[str, Any] | None = None,
    actor=None,
    execution_mode: str = WorkflowRun.ExecutionModeChoices.WORKFLOW,
    target_node_id: str | None = None,
) -> WorkflowRun:
    queue_name = get_workflow_queue_name(execution_mode)
    ensure_workers_for_queue(queue_name)
    with transaction.atomic():
        run = _initialize_workflow_run(
            workflow,
            input_data=input_data,
            trigger_mode=trigger_mode,
            trigger_metadata=trigger_metadata,
            actor=actor,
            execution_mode=execution_mode,
            target_node_id=target_node_id,
            queue_name=queue_name,
        )
        enqueue_workflow_run_job(run)
    return run


def execute_workflow(
    workflow,
    *,
    input_data: dict[str, Any] | None = None,
    trigger_mode: str = "manual",
    trigger_metadata: dict[str, Any] | None = None,
    actor=None,
    stop_after_node_id: str | None = None,
) -> WorkflowRun:
    execution_mode = (
        WorkflowRun.ExecutionModeChoices.NODE_PATH
        if stop_after_node_id is not None
        else WorkflowRun.ExecutionModeChoices.WORKFLOW
    )
    run = _initialize_workflow_run(
        workflow,
        input_data=input_data,
        trigger_mode=trigger_mode,
        trigger_metadata=trigger_metadata,
        actor=actor,
        execution_mode=execution_mode,
        target_node_id=stop_after_node_id,
    )
    return execute_workflow_run(run)


def execute_workflow_node_preview(
    workflow,
    *,
    node_id: str,
    input_data: dict[str, Any] | None = None,
    trigger_mode: str = "manual:node",
    trigger_metadata: dict[str, Any] | None = None,
    actor=None,
) -> WorkflowRun:
    run = _initialize_workflow_run(
        workflow,
        input_data=input_data,
        trigger_mode=trigger_mode,
        trigger_metadata=trigger_metadata,
        actor=actor,
        execution_mode=WorkflowRun.ExecutionModeChoices.NODE_PREVIEW,
        target_node_id=node_id,
    )
    return execute_workflow_run(run)
