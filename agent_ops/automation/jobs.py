from __future__ import annotations

from automation.models import WorkflowRun
from automation.runtime import execute_workflow_run


def run_workflow_job(run_id: int) -> None:
    run = (
        WorkflowRun.objects.select_related("workflow", "workflow_version")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        return
    execute_workflow_run(run)
