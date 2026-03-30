from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ChangeLoggedModel

from .workflows import _get_scope_related_object


class WorkflowRun(ChangeLoggedModel):
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
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    context_data = models.JSONField(default=dict, blank=True)
    step_results = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created",)
        indexes = (
            models.Index(fields=("workflow", "status")),
            models.Index(fields=("organization", "workspace", "environment")),
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
