from __future__ import annotations

from functools import partial

import django_rq
from django.core.exceptions import ValidationError
from django.db import transaction
from django_rq.queues import get_connection
from redis.exceptions import RedisError
from rq import Worker

WORKFLOW_QUEUE_HIGH = "high"
WORKFLOW_QUEUE_DEFAULT = "default"
WORKFLOW_QUEUE_LOW = "low"


def get_workflow_queue_name(execution_mode: str) -> str:
    return WORKFLOW_QUEUE_DEFAULT


def get_workers_for_queue(queue_name: str) -> int:
    try:
        connection = get_connection(queue_name)
        return sum(
            1
            for worker in Worker.all(connection=connection)
            if queue_name in worker.queue_names()
        )
    except RedisError:
        return 0


def ensure_workers_for_queue(queue_name: str) -> None:
    if get_workers_for_queue(queue_name) > 0:
        return
    raise ValidationError(
        {
            "execution": (
                f'Unable to queue workflow execution because no RQ worker is servicing the "{queue_name}" queue.'
            )
        }
    )


def enqueue_workflow_run_job_now(run: WorkflowRun) -> WorkflowRun:
    from automation.jobs import run_workflow_job

    queue = django_rq.get_queue(run.queue_name or WORKFLOW_QUEUE_DEFAULT)
    queue.enqueue(
        run_workflow_job,
        run.pk,
        job_id=str(run.job_id),
    )
    return run


def enqueue_workflow_run_job(run: WorkflowRun) -> WorkflowRun:
    callback = partial(
        enqueue_workflow_run_job_now,
        run,
    )
    transaction.on_commit(callback)
    return run


def enqueue_workflow_run_job_at_now(run: WorkflowRun, scheduled_for) -> WorkflowRun:
    from automation.jobs import run_workflow_job

    queue = django_rq.get_queue(run.queue_name or WORKFLOW_QUEUE_DEFAULT)
    queue.enqueue_at(
        scheduled_for,
        run_workflow_job,
        run.pk,
        job_id=str(run.job_id),
    )
    return run


def enqueue_workflow_run_job_at(run: WorkflowRun, scheduled_for) -> WorkflowRun:
    callback = partial(
        enqueue_workflow_run_job_at_now,
        run,
        scheduled_for,
    )
    transaction.on_commit(callback)
    return run


def delete_workflow_run_job(run: WorkflowRun) -> None:
    queue = django_rq.get_queue(run.queue_name or WORKFLOW_QUEUE_DEFAULT)
    job = queue.fetch_job(str(run.job_id))
    if job is None:
        return
    job.delete()
