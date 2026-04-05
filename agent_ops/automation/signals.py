from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from automation.models import Workflow
from automation.scheduling import (
    clear_workflow_schedule_triggers,
    sync_workflow_schedule_triggers_for_workflow_id,
)


@receiver(post_save, sender=Workflow)
def sync_workflow_schedules_after_save(sender, instance: Workflow, **kwargs) -> None:
    transaction.on_commit(
        lambda workflow_id=instance.pk: sync_workflow_schedule_triggers_for_workflow_id(workflow_id)
    )


@receiver(post_delete, sender=Workflow)
def clear_workflow_schedules_after_delete(sender, instance: Workflow, **kwargs) -> None:
    transaction.on_commit(
        lambda workflow_id=instance.pk: clear_workflow_schedule_triggers(workflow_id=workflow_id)
    )
