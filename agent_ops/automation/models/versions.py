from __future__ import annotations

import hashlib
import json

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, models, transaction

from automation.primitives import normalize_workflow_definition_nodes
from core.models import ChangeLoggedModel

from .workflows import _get_scope_related_object, _validate_json_object


def _build_snapshot_checksum(*, definition: dict, metadata: dict) -> str:
    payload = json.dumps(
        {
            "definition": definition,
            "metadata": metadata,
        },
        cls=DjangoJSONEncoder,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorkflowVersion(ChangeLoggedModel):
    workflow = models.ForeignKey(
        "automation.Workflow",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField()
    definition_checksum = models.CharField(max_length=64)
    definition = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workflow_id", "-version")
        constraints = (
            models.UniqueConstraint(
                fields=("workflow", "version"),
                name="automation_workflowversion_unique_workflow_version",
            ),
            models.UniqueConstraint(
                fields=("workflow", "definition_checksum"),
                name="automation_workflowversion_unique_workflow_checksum",
            ),
        )
        indexes = (
            models.Index(fields=("workflow", "definition_checksum")),
        )

    def __str__(self) -> str:
        return f"{self.workflow} v{self.version}"

    @property
    def node_count(self) -> int:
        nodes = self.definition.get("nodes", []) if isinstance(self.definition, dict) else []
        return len(nodes)

    def clean(self):
        super().clean()
        _validate_json_object(self.definition, field_name="definition")
        _validate_json_object(self.metadata, field_name="metadata")

    def save(self, *args, **kwargs):
        self.definition_checksum = _build_snapshot_checksum(
            definition=dict(self.definition or {}),
            metadata=dict(self.metadata or {}),
        )
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return _get_scope_related_object(
            organization=self.workflow.organization,
            workspace=self.workflow.workspace,
            environment=self.workflow.environment,
        )


def ensure_workflow_version_snapshot(workflow) -> WorkflowVersion:
    normalized_definition = normalize_workflow_definition_nodes(workflow.definition or {})
    normalized_metadata = dict(workflow.metadata or {})
    definition_checksum = _build_snapshot_checksum(
        definition=normalized_definition,
        metadata=normalized_metadata,
    )

    existing_version = WorkflowVersion.objects.filter(
        workflow=workflow,
        definition_checksum=definition_checksum,
    ).first()
    if existing_version is not None:
        return existing_version

    with transaction.atomic():
        existing_version = WorkflowVersion.objects.select_for_update().filter(
            workflow=workflow,
            definition_checksum=definition_checksum,
        ).first()
        if existing_version is not None:
            return existing_version

        latest_version = (
            WorkflowVersion.objects.select_for_update()
            .filter(workflow=workflow)
            .order_by("-version")
            .first()
        )
        next_version = 1 if latest_version is None else latest_version.version + 1

        try:
            return WorkflowVersion.objects.create(
                workflow=workflow,
                version=next_version,
                definition_checksum=definition_checksum,
                definition=normalized_definition,
                metadata=normalized_metadata,
            )
        except IntegrityError:
            return WorkflowVersion.objects.get(
                workflow=workflow,
                definition_checksum=definition_checksum,
            )
