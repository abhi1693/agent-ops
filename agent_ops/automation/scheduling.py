from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from redis.exceptions import RedisError
from django.db import transaction
from django.utils import timezone

from automation.core_nodes.schedule_trigger.schedules import (
    ScheduleTriggerConfig,
    parse_schedule_datetime,
    parse_schedule_trigger_config,
    resolve_initial_schedule_time,
    serialize_schedule_datetime,
    serialize_schedule_trigger_config,
)
from automation.models import Workflow, WorkflowRun
from automation.primitives import normalize_workflow_definition_nodes
from automation.queue import (
    delete_workflow_run_job,
    enqueue_workflow_run_job_at_now,
    enqueue_workflow_run_job_now,
    get_workflow_queue_name,
)


SCHEDULE_TRIGGER_TYPE = "core.schedule_trigger"


@dataclass(frozen=True)
class WorkflowScheduleSyncResult:
    created_runs: int = 0
    deleted_runs: int = 0
    invalid_nodes: tuple[str, ...] = ()


def _get_schedule_trigger_nodes(workflow: Workflow) -> list[dict]:
    definition = normalize_workflow_definition_nodes(workflow.definition or {})
    nodes = definition.get("nodes", [])
    return [
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == "trigger"
        and node.get("type") == SCHEDULE_TRIGGER_TYPE
    ]


def _get_run_metadata_value(run: WorkflowRun, key: str):
    metadata = run.trigger_metadata if isinstance(run.trigger_metadata, dict) else {}
    return metadata.get(key)


def _get_pending_schedule_runs(*, workflow: Workflow | None = None, workflow_id: int | None = None) -> list[WorkflowRun]:
    queryset = WorkflowRun.objects.filter(
        trigger_mode=SCHEDULE_TRIGGER_TYPE,
        execution_mode=WorkflowRun.ExecutionModeChoices.WORKFLOW,
        status=WorkflowRun.StatusChoices.PENDING,
    ).order_by("created")
    if workflow is not None:
        queryset = queryset.filter(workflow=workflow)
    if workflow_id is not None:
        queryset = queryset.filter(workflow_id=workflow_id)
    return list(queryset)


def _delete_pending_schedule_run(run: WorkflowRun) -> None:
    try:
        delete_workflow_run_job(run)
    except RedisError:
        pass
    run.delete()


def _build_schedule_trigger_metadata(
    *,
    configured_schedule_at: datetime | None,
    interval_minutes: int | None,
    scheduled_for: datetime,
    trigger_node_id: str,
) -> dict:
    schedule = ScheduleTriggerConfig(
        configured_schedule_at=configured_schedule_at,
        interval_minutes=interval_minutes,
    )
    return {
        "configured_schedule_at": serialize_schedule_datetime(configured_schedule_at),
        "interval_minutes": interval_minutes,
        "schedule": serialize_schedule_trigger_config(schedule),
        "scheduled_for": serialize_schedule_datetime(scheduled_for),
        "trigger_node_id": trigger_node_id,
    }


def _create_scheduled_run(
    *,
    workflow: Workflow,
    trigger_node_id: str,
    configured_schedule_at: datetime | None,
    interval_minutes: int | None,
    scheduled_for: datetime,
) -> WorkflowRun:
    from automation.runtime import create_workflow_run

    queue_name = get_workflow_queue_name(WorkflowRun.ExecutionModeChoices.WORKFLOW)
    return create_workflow_run(
        workflow,
        input_data={},
        trigger_mode=SCHEDULE_TRIGGER_TYPE,
        trigger_metadata=_build_schedule_trigger_metadata(
            configured_schedule_at=configured_schedule_at,
            interval_minutes=interval_minutes,
            scheduled_for=scheduled_for,
            trigger_node_id=trigger_node_id,
        ),
        status=WorkflowRun.StatusChoices.PENDING,
        queue_name=queue_name,
    )


def _pending_run_matches_schedule(
    run: WorkflowRun,
    *,
    configured_schedule_at: datetime | None,
    interval_minutes: int | None,
) -> bool:
    return (
        _get_run_metadata_value(run, "configured_schedule_at") == serialize_schedule_datetime(configured_schedule_at)
        and _get_run_metadata_value(run, "interval_minutes") == interval_minutes
    )


def enqueue_scheduled_workflow_run_once(
    *,
    workflow: Workflow,
    trigger_node_id: str,
    schedule: ScheduleTriggerConfig,
    now: datetime | None = None,
) -> WorkflowRun | None:
    reference_time = now or timezone.now()
    pending_runs = [
        run
        for run in _get_pending_schedule_runs(workflow=workflow)
        if _get_run_metadata_value(run, "trigger_node_id") == trigger_node_id
    ]

    for extra_run in pending_runs[1:]:
        _delete_pending_schedule_run(extra_run)

    existing_run = pending_runs[0] if pending_runs else None
    if existing_run is not None and _pending_run_matches_schedule(
        existing_run,
        configured_schedule_at=schedule.configured_schedule_at,
        interval_minutes=schedule.interval_minutes,
    ):
        return existing_run

    if existing_run is not None:
        _delete_pending_schedule_run(existing_run)

    scheduled_for = resolve_initial_schedule_time(schedule=schedule, now=reference_time)
    if schedule.configured_schedule_at is not None and scheduled_for <= reference_time:
        return None

    with transaction.atomic():
        run = _create_scheduled_run(
            workflow=workflow,
            trigger_node_id=trigger_node_id,
            configured_schedule_at=schedule.configured_schedule_at,
            interval_minutes=schedule.interval_minutes,
            scheduled_for=scheduled_for,
        )

    try:
        if scheduled_for <= reference_time:
            enqueue_workflow_run_job_now(run)
        else:
            enqueue_workflow_run_job_at_now(run, scheduled_for)
    except RedisError:
        run.delete()
        raise
    return run


def sync_workflow_schedule_triggers(workflow: Workflow) -> WorkflowScheduleSyncResult:
    invalid_nodes: list[str] = []
    created_runs = 0
    desired_node_ids: set[str] = set()

    if workflow.enabled:
        for node in _get_schedule_trigger_nodes(workflow):
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                continue

            try:
                schedule = parse_schedule_trigger_config(node.get("config") or {})
            except ValueError:
                invalid_nodes.append(node_id)
                continue

            desired_node_ids.add(node_id)
            created_run = enqueue_scheduled_workflow_run_once(
                workflow=workflow,
                trigger_node_id=node_id,
                schedule=schedule,
            )
            if created_run is not None:
                created_runs += 1

    deleted_runs = 0
    for run in _get_pending_schedule_runs(workflow=workflow):
        trigger_node_id = _get_run_metadata_value(run, "trigger_node_id")
        if not workflow.enabled or trigger_node_id not in desired_node_ids:
            _delete_pending_schedule_run(run)
            deleted_runs += 1

    return WorkflowScheduleSyncResult(
        created_runs=created_runs,
        deleted_runs=deleted_runs,
        invalid_nodes=tuple(invalid_nodes),
    )


def sync_workflow_schedule_triggers_for_workflow_id(workflow_id: int) -> WorkflowScheduleSyncResult:
    workflow = (
        Workflow.objects.select_related("organization", "workspace", "environment")
        .filter(pk=workflow_id)
        .first()
    )
    if workflow is None:
        clear_workflow_schedule_triggers(workflow_id=workflow_id)
        return WorkflowScheduleSyncResult()

    try:
        return sync_workflow_schedule_triggers(workflow)
    except RedisError:
        clear_workflow_schedule_triggers(workflow_id=workflow_id)
        return WorkflowScheduleSyncResult()


def clear_workflow_schedule_triggers(*, workflow_id: int) -> int:
    deleted_runs = 0
    for run in _get_pending_schedule_runs(workflow_id=workflow_id):
        _delete_pending_schedule_run(run)
        deleted_runs += 1
    return deleted_runs


def schedule_next_scheduled_workflow_run(run: WorkflowRun) -> WorkflowRun | None:
    if run.trigger_mode != SCHEDULE_TRIGGER_TYPE:
        return None

    interval_minutes = _get_run_metadata_value(run, "interval_minutes")
    if not isinstance(interval_minutes, int) or interval_minutes < 1:
        return None

    trigger_node_id = _get_run_metadata_value(run, "trigger_node_id")
    if not isinstance(trigger_node_id, str) or not trigger_node_id:
        return None

    existing_pending_run = next(
        (
            pending_run
            for pending_run in _get_pending_schedule_runs(workflow=run.workflow)
            if _get_run_metadata_value(pending_run, "trigger_node_id") == trigger_node_id
        ),
        None,
    )
    if existing_pending_run is not None:
        return existing_pending_run

    scheduled_for = parse_schedule_datetime(_get_run_metadata_value(run, "scheduled_for"))
    base_time = scheduled_for or run.started_at or run.created
    next_scheduled_for = max(
        base_time + timedelta(minutes=interval_minutes),
        timezone.now() + timedelta(minutes=1),
    )

    with transaction.atomic():
        next_run = _create_scheduled_run(
            workflow=run.workflow,
            trigger_node_id=trigger_node_id,
            configured_schedule_at=parse_schedule_datetime(_get_run_metadata_value(run, "configured_schedule_at")),
            interval_minutes=interval_minutes,
            scheduled_for=next_scheduled_for,
        )

    try:
        enqueue_workflow_run_job_at_now(next_run, next_scheduled_for)
    except RedisError:
        next_run.delete()
        raise
    return next_run
