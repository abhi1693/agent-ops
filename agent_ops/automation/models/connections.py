from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from automation.catalog.services import get_catalog_connection_type
from automation.models.secrets import (
    _derive_scope,
    _get_scope_related_object,
    _validate_json_object,
    _validate_scope_consistency,
    _validate_unique_scope_name,
)
from core.models import PrimaryModel


class WorkflowConnection(PrimaryModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="workflow_connections",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="workflow_connections",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="workflow_connections",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=100)
    integration_id = models.SlugField(max_length=100)
    connection_type = models.CharField(max_length=150)
    credential_secret = models.ForeignKey(
        "automation.Secret",
        on_delete=models.SET_NULL,
        related_name="workflow_connections",
        blank=True,
        null=True,
    )
    enabled = models.BooleanField(default=True)
    auth_config = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("organization__name", "workspace__name", "environment__name", "integration_id", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("environment", "integration_id", "name"),
                condition=models.Q(environment__isnull=False),
                name="automation_workflowconnection_unique_environment_name",
            ),
            models.UniqueConstraint(
                fields=("workspace", "integration_id", "name"),
                condition=models.Q(workspace__isnull=False, environment__isnull=True),
                name="automation_workflowconnection_unique_workspace_name",
            ),
            models.UniqueConstraint(
                fields=("organization", "integration_id", "name"),
                condition=models.Q(workspace__isnull=True, environment__isnull=True),
                name="automation_workflowconnection_unique_organization_name",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("workflowconnection_detail", args=[self.pk])

    @property
    def scope_type(self) -> str:
        if self.environment_id:
            return "Environment"
        if self.workspace_id:
            return "Workspace"
        return "Organization"

    @property
    def scope_label(self) -> str:
        parts = [self.organization.name] if self.organization_id else []
        if self.workspace_id:
            parts.append(self.workspace.name)
        if self.environment_id:
            parts.append(self.environment.name)
        return " / ".join(parts)

    def clean(self):
        super().clean()

        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        _validate_scope_consistency(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        _validate_json_object(self.auth_config, field_name="auth_config")
        _validate_json_object(self.metadata, field_name="metadata")

        if self.organization is None:
            raise ValidationError({"organization": "A connection must be scoped to at least an organization."})

        connection_definition = get_catalog_connection_type(self.connection_type)
        if connection_definition is None:
            raise ValidationError({"connection_type": f'Unknown workflow connection type "{self.connection_type}".'})

        if not self.integration_id:
            self.integration_id = connection_definition.integration_id
        elif self.integration_id != connection_definition.integration_id:
            raise ValidationError(
                {
                    "integration_id": (
                        f'Integration "{self.integration_id}" does not match connection type '
                        f'"{self.connection_type}".'
                    )
                }
            )

        if self.credential_secret_id:
            secret_group = self.credential_secret.secret_group
            if secret_group.organization_id != self.organization_id:
                raise ValidationError(
                    {"credential_secret": "Credential secret must belong to the same organization as the connection."}
                )
            if secret_group.workspace_id != self.workspace_id:
                raise ValidationError(
                    {"credential_secret": "Credential secret must use the same workspace scope as the connection."}
                )
            if secret_group.environment_id != self.environment_id:
                raise ValidationError(
                    {"credential_secret": "Credential secret must use the same environment scope as the connection."}
                )

        _validate_unique_scope_name(
            self,
            queryset=self.__class__.objects.all(),
            filters={
                "organization": self.organization,
                "workspace": self.workspace,
                "environment": self.environment,
                "integration_id": self.integration_id,
                "name": self.name,
            },
            message="A connection with this name already exists for the selected scope and integration.",
        )

    def save(self, *args, **kwargs):
        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return _get_scope_related_object(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
