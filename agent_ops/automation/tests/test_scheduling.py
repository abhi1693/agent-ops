from __future__ import annotations

from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import TestCase

from automation.models import Workflow, WorkflowRun
from automation.scheduling import (
    SCHEDULE_TRIGGER_TYPE,
    clear_workflow_schedule_triggers,
    schedule_next_scheduled_workflow_run,
    sync_workflow_schedule_triggers,
)
from tenancy.models import Environment, Organization, Workspace


def _schedule_definition(config: dict | None = None) -> dict:
    return {
        "nodes": [
            {
                "id": "trigger-1",
                "kind": "trigger",
                "type": "core.schedule_trigger",
                "label": "Schedule Trigger",
                "config": config or {"schedule_at": "2026-04-06T10:30", "interval_minutes": 60},
                "position": {"x": 48, "y": 56},
            },
            {
                "id": "response-1",
                "kind": "response",
                "type": "core.response",
                "label": "Done",
                "config": {
                    "template": "{{ trigger.type }} @ {{ trigger.meta.scheduled_for }}",
                },
                "position": {"x": 336, "y": 56},
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "source": "trigger-1",
                "target": "response-1",
            }
        ],
    }


class WorkflowSchedulingTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )

    def _create_workflow(self, *, config: dict | None = None, enabled: bool = True) -> Workflow:
        workflow = Workflow.objects.create(
            environment=self.environment,
            enabled=enabled,
            name="Scheduled workflow",
            definition=_schedule_definition(config),
        )
        clear_workflow_schedule_triggers(workflow_id=workflow.pk)
        return workflow

    def test_sync_workflow_schedule_triggers_creates_future_scheduled_run(self):
        workflow = self._create_workflow(
            config={"schedule_at": "2026-04-06T10:30", "interval_minutes": 120}
        )

        with patch("automation.scheduling.enqueue_workflow_run_job_at_now", side_effect=lambda run, when: run):
            result = sync_workflow_schedule_triggers(workflow)

        self.assertEqual(result.invalid_nodes, ())
        run = WorkflowRun.objects.get(workflow=workflow)
        self.assertEqual(run.status, WorkflowRun.StatusChoices.PENDING)
        self.assertEqual(run.trigger_mode, SCHEDULE_TRIGGER_TYPE)
        self.assertEqual(run.trigger_metadata["trigger_node_id"], "trigger-1")
        self.assertEqual(run.trigger_metadata["interval_minutes"], 120)
        self.assertEqual(run.trigger_metadata["configured_schedule_at"], "2026-04-06T10:30:00+00:00")
        self.assertEqual(run.trigger_metadata["scheduled_for"], "2026-04-06T10:30:00+00:00")

    def test_sync_workflow_schedule_triggers_uses_now_for_interval_only(self):
        workflow = self._create_workflow(config={"interval_minutes": 15})
        fixed_now = datetime(2026, 4, 6, 10, 5, tzinfo=datetime_timezone.utc)

        with patch("automation.scheduling.timezone.now", return_value=fixed_now), patch(
            "automation.scheduling.enqueue_workflow_run_job_now",
            side_effect=lambda run: run,
        ):
            sync_workflow_schedule_triggers(workflow)

        run = WorkflowRun.objects.get(workflow=workflow)
        self.assertEqual(run.trigger_metadata["configured_schedule_at"], None)
        self.assertEqual(run.trigger_metadata["interval_minutes"], 15)
        self.assertEqual(run.trigger_metadata["scheduled_for"], fixed_now.isoformat())

    def test_sync_workflow_schedule_triggers_is_idempotent_for_matching_schedule(self):
        workflow = self._create_workflow(
            config={"schedule_at": "2026-04-06T10:30", "interval_minutes": 120}
        )

        with patch("automation.scheduling.enqueue_workflow_run_job_at_now", side_effect=lambda run, when: run):
            first_result = sync_workflow_schedule_triggers(workflow)
            second_result = sync_workflow_schedule_triggers(workflow)

        self.assertEqual(first_result.invalid_nodes, ())
        self.assertEqual(second_result.invalid_nodes, ())
        self.assertEqual(WorkflowRun.objects.filter(workflow=workflow).count(), 1)

    def test_sync_workflow_schedule_triggers_drops_past_one_off_schedule(self):
        workflow = self._create_workflow(config={"schedule_at": "2026-04-06T10:30"})
        fixed_now = datetime(2026, 4, 6, 10, 31, tzinfo=datetime_timezone.utc)

        with patch("automation.scheduling.timezone.now", return_value=fixed_now):
            result = sync_workflow_schedule_triggers(workflow)

        self.assertEqual(result.invalid_nodes, ())
        self.assertFalse(WorkflowRun.objects.filter(workflow=workflow).exists())

    def test_sync_workflow_schedule_triggers_clears_runs_for_disabled_workflow(self):
        workflow = self._create_workflow(config={"interval_minutes": 30})

        with patch("automation.scheduling.enqueue_workflow_run_job_now", side_effect=lambda run: run):
            sync_workflow_schedule_triggers(workflow)

        workflow.enabled = False
        with patch("automation.scheduling.enqueue_workflow_run_job_now", side_effect=lambda run: run):
            sync_workflow_schedule_triggers(workflow)

        self.assertFalse(WorkflowRun.objects.filter(workflow=workflow).exists())

    def test_schedule_next_scheduled_workflow_run_uses_previous_slot_for_interval(self):
        workflow = self._create_workflow(config={"interval_minutes": 30})
        current_run = WorkflowRun.objects.create(
            workflow=workflow,
            workflow_version=workflow.versions.create(version=1, definition=workflow.definition),
            trigger_mode=SCHEDULE_TRIGGER_TYPE,
            trigger_metadata={
                "trigger_node_id": "trigger-1",
                "configured_schedule_at": None,
                "interval_minutes": 30,
                "scheduled_for": "2026-04-06T10:00:00+00:00",
            },
            status=WorkflowRun.StatusChoices.SUCCEEDED,
            queue_name="default",
            started_at=datetime(2026, 4, 6, 10, 0, tzinfo=datetime_timezone.utc),
            finished_at=datetime(2026, 4, 6, 10, 2, tzinfo=datetime_timezone.utc),
        )

        with patch(
            "automation.scheduling.enqueue_workflow_run_job_at_now",
            side_effect=lambda run, when: run,
        ), patch(
            "automation.scheduling.timezone.now",
            return_value=datetime(2026, 4, 6, 10, 2, tzinfo=datetime_timezone.utc),
        ):
            next_run = schedule_next_scheduled_workflow_run(current_run)

        assert next_run is not None
        self.assertEqual(next_run.trigger_metadata["scheduled_for"], "2026-04-06T10:30:00+00:00")
        self.assertEqual(next_run.trigger_metadata["interval_minutes"], 30)

    def test_schedule_next_scheduled_workflow_run_respects_existing_pending_run(self):
        workflow = self._create_workflow(config={"interval_minutes": 30})
        workflow_version = workflow.versions.create(version=1, definition=workflow.definition)
        current_run = WorkflowRun.objects.create(
            workflow=workflow,
            workflow_version=workflow_version,
            trigger_mode=SCHEDULE_TRIGGER_TYPE,
            trigger_metadata={
                "trigger_node_id": "trigger-1",
                "configured_schedule_at": None,
                "interval_minutes": 30,
                "scheduled_for": "2026-04-06T10:00:00+00:00",
            },
            status=WorkflowRun.StatusChoices.SUCCEEDED,
            queue_name="default",
            started_at=datetime(2026, 4, 6, 10, 0, tzinfo=datetime_timezone.utc),
            finished_at=datetime(2026, 4, 6, 10, 2, tzinfo=datetime_timezone.utc),
        )
        pending_run = WorkflowRun.objects.create(
            workflow=workflow,
            workflow_version=workflow_version,
            trigger_mode=SCHEDULE_TRIGGER_TYPE,
            trigger_metadata={
                "trigger_node_id": "trigger-1",
                "configured_schedule_at": None,
                "interval_minutes": 30,
                "scheduled_for": "2026-04-06T10:30:00+00:00",
            },
            status=WorkflowRun.StatusChoices.PENDING,
            queue_name="default",
        )

        returned_run = schedule_next_scheduled_workflow_run(current_run)
        self.assertEqual(returned_run.pk, pending_run.pk)
