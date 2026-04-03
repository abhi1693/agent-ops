from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.template import Context, Engine
from django.utils import timezone

from automation.nodes import execute_workflow_node
from automation.auth import resolve_workflow_secret_ref
from automation.workflow_connections import (
    build_auxiliary_connections_by_target,
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
    node_output = execute_workflow_node(
        workflow=workflow,
        node=node,
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
    if node_output is not None:
        return _NodeExecutionResult(
            next_node_id=node_output.next_node_id,
            output=node_output.output,
            response=node_output.response,
            run_status=node_output.run_status,
            terminal=node_output.terminal,
        )

    node_type = node.get("type")
    raise ValidationError({"definition": f'Unsupported node type "{node_type}".'})


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
    snapshot["terminal"] = result.terminal
    if result.response is not None and "response" not in snapshot:
        snapshot["response"] = result.response
    if result.run_status is not None:
        snapshot["run_status"] = result.run_status
    return snapshot


def execute_workflow(
    workflow,
    *,
    input_data: dict[str, Any] | None = None,
    trigger_mode: str = "manual",
    trigger_metadata: dict[str, Any] | None = None,
    actor=None,
    stop_after_node_id: str | None = None,
) -> WorkflowRun:
    input_data = input_data or {}
    secret_paths: set[str] = set()
    secret_values: list[str] = []
    step_results: list[dict[str, Any]] = []

    with transaction.atomic():
        workflow_version = ensure_workflow_version_snapshot(workflow)
        definition = normalize_workflow_definition_nodes(workflow_version.definition or {})
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        nodes_by_id = {node["id"]: node for node in nodes}
        primary_edges, auxiliary_edges = split_workflow_edges(edges)
        adjacency: dict[str, list[str]] = {node["id"]: [] for node in nodes}
        for edge in primary_edges:
            adjacency.setdefault(edge["source"], []).append(edge["target"])
        auxiliary_connections_by_target = build_auxiliary_connections_by_target(
            nodes_by_id=nodes_by_id,
            edges=auxiliary_edges,
        )

        context = _build_execution_context(
            workflow,
            workflow_version=workflow_version,
            input_data=input_data,
            trigger_type=trigger_mode,
            trigger_metadata=trigger_metadata,
        )
        run = WorkflowRun.objects.create(
            workflow=workflow,
            workflow_version=workflow_version,
            trigger_mode=trigger_mode,
            status=WorkflowRun.StatusChoices.RUNNING,
            input_data=input_data,
        )

        try:
            validate_workflow_runtime_definition(nodes=nodes, edges=edges)
            if stop_after_node_id is not None and stop_after_node_id not in nodes_by_id:
                raise ValidationError({"definition": f'Workflow does not define node "{stop_after_node_id}".'})
            trigger_node = next(node for node in nodes if node["kind"] == "trigger")
            current_node_id: str | None = trigger_node["id"]
            max_steps = max(len(nodes) * 4, 1)
            step_count = 0
            response_payload: dict[str, Any] = {}
            run_status = WorkflowRun.StatusChoices.SUCCEEDED
            reached_stop_node = stop_after_node_id is None

            while current_node_id is not None:
                step_count += 1
                if step_count > max_steps:
                    raise ValidationError({"definition": "Workflow execution exceeded the supported step limit."})

                node = nodes_by_id[current_node_id]
                outgoing_targets = adjacency.get(current_node_id, [])
                default_next_node_id = outgoing_targets[0] if outgoing_targets else None
                step_run = WorkflowStepRun.objects.create(
                    run=run,
                    workflow_version=workflow_version,
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
                        workflow=workflow,
                        node=node,
                        next_node_id=default_next_node_id,
                        connected_nodes_by_port=auxiliary_connections_by_target.get(node["id"], {}),
                        context=context,
                        secret_paths=secret_paths,
                        secret_values=secret_values,
                    )
                except ValidationError as exc:
                    step_run.status = WorkflowStepRun.StatusChoices.FAILED
                    step_run.error = _flatten_validation_error(exc)
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
                    raise

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

                if stop_after_node_id is not None and node["id"] == stop_after_node_id:
                    reached_stop_node = True
                    response_payload = {
                        "node_id": node["id"],
                        "label": node.get("label") or node["id"],
                        "response": result.response if result.response is not None else result.output or {},
                        "output": result.output or {},
                        "next_node_id": result.next_node_id,
                        "terminal": result.terminal,
                    }
                    if result.run_status:
                        run_status = result.run_status
                    break

                if result.terminal:
                    response_payload = result.response or {}
                    if result.run_status:
                        run_status = result.run_status
                    break

                current_node_id = result.next_node_id

            if not reached_stop_node:
                raise ValidationError(
                    {"definition": f'Workflow execution did not reach node "{stop_after_node_id}".'}
                )

            if not response_payload:
                response_payload = {
                    "node_id": step_results[-1]["node_id"] if step_results else None,
                    "response": None,
                }

            run.status = run_status
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
            run.step_results = _redact_value(
                step_results,
                secret_paths=secret_paths,
                secret_values=_sorted_secret_values(secret_values),
            )
            run.finished_at = timezone.now()
            run.save(
                update_fields=(
                    "status",
                    "workflow_version",
                    "output_data",
                    "context_data",
                    "step_results",
                    "finished_at",
                    "last_updated",
                )
            )
            return run
        except ValidationError as exc:
            run.status = WorkflowRun.StatusChoices.FAILED
            run.error = _flatten_validation_error(exc)
            run.context_data = _redact_value(
                context,
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
                    "workflow_version",
                    "error",
                    "context_data",
                    "step_results",
                    "finished_at",
                    "last_updated",
                )
            )
            return run


def execute_workflow_node_preview(
    workflow,
    *,
    node_id: str,
    input_data: dict[str, Any] | None = None,
    trigger_mode: str = "manual:node",
    trigger_metadata: dict[str, Any] | None = None,
    actor=None,
) -> WorkflowRun:
    del actor
    input_data = input_data or {}
    secret_paths: set[str] = set()
    secret_values: list[str] = []
    step_results: list[dict[str, Any]] = []

    with transaction.atomic():
        workflow_version = ensure_workflow_version_snapshot(workflow)
        definition = normalize_workflow_definition_nodes(workflow_version.definition or {})
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        nodes_by_id = {node["id"]: node for node in nodes}
        primary_edges, auxiliary_edges = split_workflow_edges(edges)
        adjacency: dict[str, list[str]] = {node["id"]: [] for node in nodes}
        for edge in primary_edges:
            adjacency.setdefault(edge["source"], []).append(edge["target"])
        auxiliary_connections_by_target = build_auxiliary_connections_by_target(
            nodes_by_id=nodes_by_id,
            edges=auxiliary_edges,
        )

        context = _build_execution_context(
            workflow,
            workflow_version=workflow_version,
            input_data=input_data,
            trigger_type=trigger_mode,
            trigger_metadata=trigger_metadata,
        )
        run = WorkflowRun.objects.create(
            workflow=workflow,
            workflow_version=workflow_version,
            trigger_mode=trigger_mode,
            status=WorkflowRun.StatusChoices.RUNNING,
            input_data=input_data,
        )

        try:
            validate_workflow_runtime_definition(nodes=nodes, edges=edges)
            node = nodes_by_id.get(node_id)
            if node is None:
                raise ValidationError({"definition": f'Workflow does not define node "{node_id}".'})

            outgoing_targets = adjacency.get(node_id, [])
            default_next_node_id = outgoing_targets[0] if outgoing_targets else None
            step_run = WorkflowStepRun.objects.create(
                run=run,
                workflow_version=workflow_version,
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
                    workflow=workflow,
                    node=node,
                    next_node_id=default_next_node_id,
                    connected_nodes_by_port=auxiliary_connections_by_target.get(node["id"], {}),
                    context=context,
                    secret_paths=secret_paths,
                    secret_values=secret_values,
                )
            except ValidationError as exc:
                step_run.status = WorkflowStepRun.StatusChoices.FAILED
                step_run.error = _flatten_validation_error(exc)
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
                raise

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

            response_payload = {
                "node_id": node["id"],
                "label": node.get("label") or node["id"],
                "response": result.response if result.response is not None else result.output or {},
                "output": result.output or {},
                "next_node_id": result.next_node_id,
                "terminal": result.terminal,
            }

            run.status = result.run_status or WorkflowRun.StatusChoices.SUCCEEDED
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
            run.step_results = _redact_value(
                step_results,
                secret_paths=secret_paths,
                secret_values=_sorted_secret_values(secret_values),
            )
            run.finished_at = timezone.now()
            run.save(
                update_fields=(
                    "status",
                    "workflow_version",
                    "output_data",
                    "context_data",
                    "step_results",
                    "finished_at",
                    "last_updated",
                )
            )
            return run
        except ValidationError as exc:
            run.status = WorkflowRun.StatusChoices.FAILED
            run.error = _flatten_validation_error(exc)
            run.context_data = _redact_value(
                context,
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
                    "workflow_version",
                    "error",
                    "context_data",
                    "step_results",
                    "finished_at",
                    "last_updated",
                )
            )
            return run
