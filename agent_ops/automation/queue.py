from __future__ import annotations

from functools import partial

import django_rq
from django.core.exceptions import ValidationError
from django.db import transaction
from django_rq.queues import get_connection
from redis.exceptions import RedisError
from rq import Worker

from automation.models import WorkflowRun

WORKFLOW_QUEUE_HIGH = "high"
WORKFLOW_QUEUE_DEFAULT = "default"
WORKFLOW_QUEUE_LOW = "low"


def get_workflow_queue_name(execution_mode: str) -> str:
    if execution_mode == WorkflowRun.ExecutionModeChoices.NODE_PREVIEW:
        return WORKFLOW_QUEUE_HIGH
    return WORKFLOW_QUEUE_DEFAULT


def get_workers_for_queue(queue_name: str) -> int:
    try:
        return Worker.count(get_connection(queue_name))
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


def enqueue_workflow_run_job(run: WorkflowRun) -> WorkflowRun:
    from automation.jobs import run_workflow_job

    queue = django_rq.get_queue(run.queue_name or WORKFLOW_QUEUE_DEFAULT)
    callback = partial(
        queue.enqueue,
        run_workflow_job,
        run.pk,
        job_id=str(run.job_id),
    )
    transaction.on_commit(callback)
    return run
