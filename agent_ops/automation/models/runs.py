from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ChangeLoggedModel

from .workflows import _get_scope_related_object


class WorkflowRun(ChangeLoggedModel):
    class ExecutionModeChoices(models.TextChoices):
        WORKFLOW = "workflow", "Workflow"
        NODE_PATH = "node_path", "Node path"
        NODE_PREVIEW = "node_preview", "Node preview"

    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    status_badge_classes = {
        StatusChoices.PENDING: "text-bg-secondary",
        StatusChoices.RUNNING: "text-bg-primary",
        StatusChoices.SUCCEEDED: "text-bg-success",
        StatusChoices.FAILED: "text-bg-danger",
    }

    workflow = models.ForeignKey(
        "automation.Workflow",
        on_delete=models.CASCADE,
        related_name="runs",
    )
    workflow_version = models.ForeignKey(
        "automation.WorkflowVersion",
        on_delete=models.PROTECT,
        related_name="runs",
    )
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="workflow_runs",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="workflow_runs",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="workflow_runs",
        blank=True,
        null=True,
    )
    trigger_mode = models.CharField(max_length=50, default="manual")
    trigger_metadata = models.JSONField(default=dict, blank=True)
    execution_mode = models.CharField(
        max_length=30,
        choices=ExecutionModeChoices.choices,
        default=ExecutionModeChoices.WORKFLOW,
    )
    target_node_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    context_data = models.JSONField(default=dict, blank=True)
    scheduler_state = models.JSONField(default=dict, blank=True)
    step_results = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
    )
    job_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    queue_name = models.CharField(max_length=100, blank=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created",)
        indexes = (
            models.Index(fields=("workflow", "status")),
            models.Index(fields=("organization", "workspace", "environment")),
            models.Index(fields=("status", "execution_mode"), name="automation__status_1ea218_idx"),
        )

    def __str__(self) -> str:
        suffix = self.pk if self.pk is not None else "pending"
        return f"{self.workflow} run {suffix}"

    @property
    def badge_class(self) -> str:
        return self.status_badge_classes.get(self.status, "text-bg-secondary")

    @property
    def scope_label(self) -> str:
        if self.workflow_id:
            return self.workflow.scope_label

        parts = [self.organization.name] if self.organization_id else []
        if self.workspace_id:
            parts.append(self.workspace.name)
        if self.environment_id:
            parts.append(self.environment.name)
        return " / ".join(parts)

    @property
    def step_count(self) -> int:
        return len(self.step_results or [])

    def clean(self):
        super().clean()
        if self.workflow_id is None:
            raise ValidationError({"workflow": "A workflow run must belong to a workflow."})

        if self.workflow_version_id and self.workflow_version.workflow_id != self.workflow_id:
            raise ValidationError({"workflow_version": "Workflow version must belong to the selected workflow."})

        self.organization = self.workflow.organization
        self.workspace = self.workflow.workspace
        self.environment = self.workflow.environment

    def save(self, *args, **kwargs):
        if self.workflow_id is not None:
            self.organization = self.workflow.organization
            self.workspace = self.workflow.workspace
            self.environment = self.workflow.environment
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return _get_scope_related_object(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )


class WorkflowStepRun(ChangeLoggedModel):
    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    run = models.ForeignKey(
        "automation.WorkflowRun",
        on_delete=models.CASCADE,
        related_name="step_runs",
    )
    workflow_version = models.ForeignKey(
        "automation.WorkflowVersion",
        on_delete=models.PROTECT,
        related_name="step_runs",
    )
    sequence = models.PositiveIntegerField()
    node_id = models.CharField(max_length=255)
    node_kind = models.CharField(max_length=50)
    node_type = models.CharField(max_length=255, blank=True)
    label = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("run_id", "sequence")
        indexes = (
            models.Index(fields=("run", "sequence")),
            models.Index(fields=("run", "node_id")),
        )
        constraints = (
            models.UniqueConstraint(
                fields=("run", "sequence"),
                name="automation_workflowsteprun_unique_run_sequence",
            ),
        )

    def __str__(self) -> str:
        return f"{self.run} step {self.sequence}: {self.label}"

    def clean(self):
        super().clean()
        if self.run.workflow_id != self.workflow_version.workflow_id:
            raise ValidationError({"workflow_version": "Step run version must match the parent workflow run."})

    def get_changelog_related_object(self):
        return self.run.get_changelog_related_object()
