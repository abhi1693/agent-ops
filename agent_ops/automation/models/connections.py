from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from automation.catalog.services import get_catalog_connection_type
from automation.models.secrets import (
    _derive_scope,
    _get_scope_related_object,
    _validate_json_object,
    _validate_scope_consistency,
    _validate_unique_scope_name,
)
from core.models import PrimaryModel


def _validate_secret_reference(*, connection, field_key: str, raw_value):
    if not isinstance(raw_value, dict):
        raise ValidationError(
            {"field_values": f'Connection field "{field_key}" must be a JSON object when using a secret reference.'}
        )

    source = raw_value.get("source", "secret")
    if source != "secret":
        raise ValidationError({"field_values": f'Connection field "{field_key}" must use source "secret".'})

    secret_name = raw_value.get("secret_name")
    if not isinstance(secret_name, str) or not secret_name.strip():
        raise ValidationError({"field_values": f'Connection field "{field_key}" must define a non-empty secret_name.'})

    if not connection.secret_group_id:
        raise ValidationError(
            {
                "secret_group": (
                    f'Connection "{connection.name}" must define a secret group before using secret-backed '
                    f'field "{field_key}".'
                )
            }
        )

    secret = connection.secret_group.get_secret(name=secret_name.strip())
    if secret is None:
        raise ValidationError(
            {
                "field_values": (
                    f'Secret group "{connection.secret_group.name}" does not include secret "{secret_name.strip()}" '
                    f'for field "{field_key}".'
                )
            }
        )

    if not secret.enabled:
        raise ValidationError(
            {
                "field_values": (
                    f'Secret "{secret_name.strip()}" in group "{connection.secret_group.name}" is disabled and '
                    f'cannot be used for field "{field_key}".'
                )
            }
        )


def _validate_typed_connection_field_value(*, field_definition, raw_value: Any):
    if field_definition.value_type in {"string", "text", "url"}:
        if not isinstance(raw_value, str):
            raise ValidationError(
                {"field_values": f'Connection field "{field_definition.key}" must be a string.'}
            )
    elif field_definition.value_type == "integer":
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            raise ValidationError(
                {"field_values": f'Connection field "{field_definition.key}" must be an integer.'}
            )
    elif field_definition.value_type == "number":
        if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
            raise ValidationError(
                {"field_values": f'Connection field "{field_definition.key}" must be a number.'}
            )
    elif field_definition.value_type == "boolean":
        if not isinstance(raw_value, bool):
            raise ValidationError(
                {"field_values": f'Connection field "{field_definition.key}" must be a boolean.'}
            )
    elif field_definition.value_type in {"json", "object"}:
        if not isinstance(raw_value, dict):
            raise ValidationError(
                {"field_values": f'Connection field "{field_definition.key}" must be a JSON object.'}
            )
    elif field_definition.value_type == "string[]":
        if not isinstance(raw_value, list) or not all(isinstance(item, str) for item in raw_value):
            raise ValidationError(
                {"field_values": f'Connection field "{field_definition.key}" must be a list of strings.'}
            )

    if field_definition.options:
        normalized_value = str(raw_value).strip()
        allowed_values = {option.value for option in field_definition.options}
        if normalized_value not in allowed_values:
            raise ValidationError(
                {
                    "field_values": (
                        f'Connection field "{field_definition.key}" must be one of: '
                        f'{", ".join(sorted(allowed_values))}.'
                    )
                }
            )


def _validate_state_field_values(*, connection_definition, state_values: dict[str, Any], field_name: str) -> None:
    unknown_field_keys = set(state_values) - {field.key for field in connection_definition.state_schema}
    if unknown_field_keys:
        raise ValidationError(
            {
                field_name: (
                    f'Connection type "{connection_definition.id}" defines unsupported state keys: '
                    f'{", ".join(sorted(unknown_field_keys))}.'
                )
            }
        )

    for field_definition in connection_definition.state_schema:
        raw_value = state_values.get(field_definition.key)
        if raw_value in (None, "") and field_definition.default not in (None, ""):
            raw_value = field_definition.default
        if raw_value in (None, ""):
            continue

        _validate_typed_connection_field_value(
            field_definition=field_definition,
            raw_value=raw_value,
        )


def _field_value_matches_condition(*, field_values: dict[str, Any], field_key: str | None, values: tuple[str, ...]) -> bool:
    if not field_key:
        return True
    raw_value = field_values.get(field_key)
    if not values:
        return raw_value not in (None, "")
    if not isinstance(raw_value, str):
        return False
    return raw_value in values


def _get_effective_connection_field_value(*, field_values: dict[str, Any], field_definition) -> Any:
    raw_value = field_values.get(field_definition.key)
    if raw_value in (None, "") and field_definition.default not in (None, ""):
        return field_definition.default
    return raw_value


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
    secret_group = models.ForeignKey(
        "automation.SecretGroup",
        on_delete=models.SET_NULL,
        related_name="workflow_connections_by_group",
        blank=True,
        null=True,
    )
    enabled = models.BooleanField(default=True)
    field_values = models.JSONField(default=dict, blank=True)
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
        _validate_json_object(self.field_values, field_name="field_values")
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

        if self.secret_group_id:
            secret_group = self.secret_group
            if secret_group.organization_id != self.organization_id:
                raise ValidationError(
                    {"secret_group": "Connection secret group must belong to the same organization as the connection."}
                )
            if secret_group.workspace_id != self.workspace_id:
                raise ValidationError(
                    {"secret_group": "Connection secret group must use the same workspace scope as the connection."}
                )
            if secret_group.environment_id != self.environment_id:
                raise ValidationError(
                    {"secret_group": "Connection secret group must use the same environment scope as the connection."}
                )

        unknown_field_keys = set(self.field_values) - {field.key for field in connection_definition.field_schema}
        if unknown_field_keys:
            raise ValidationError(
                {
                    "field_values": (
                        f'Connection "{self.name}" defines unsupported field keys for type '
                        f'"{self.connection_type}": {", ".join(sorted(unknown_field_keys))}.'
                    )
                }
            )

        for field_definition in connection_definition.field_schema:
            raw_value = _get_effective_connection_field_value(
                field_values=self.field_values,
                field_definition=field_definition,
            )

            if field_definition.required and raw_value in (None, ""):
                raise ValidationError(
                    {
                        "field_values": (
                            f'Connection "{self.name}" must define field "{field_definition.key}" for type '
                            f'"{self.connection_type}".'
                        )
                    }
                )

            if raw_value in (None, ""):
                continue

            if field_definition.value_type == "secret_ref":
                _validate_secret_reference(
                    connection=self,
                    field_key=field_definition.key,
                    raw_value=raw_value,
                )
                continue

            _validate_typed_connection_field_value(
                field_definition=field_definition,
                raw_value=raw_value,
            )

        if connection_definition.http_auth and _field_value_matches_condition(
            field_values=self.field_values,
            field_key=connection_definition.http_auth.enabled_when_field,
            values=connection_definition.http_auth.enabled_when_values,
        ):
            required_field_keys = {
                header.field_key
                for header in connection_definition.http_auth.headers
                if header.required
            }
            if connection_definition.http_auth.basic_username_field:
                required_field_keys.add(connection_definition.http_auth.basic_username_field)
            if connection_definition.http_auth.basic_password_field:
                required_field_keys.add(connection_definition.http_auth.basic_password_field)
            for field_key in sorted(required_field_keys):
                field_definition = next(
                    (field for field in connection_definition.field_schema if field.key == field_key),
                    None,
                )
                raw_value = (
                    _get_effective_connection_field_value(field_values=self.field_values, field_definition=field_definition)
                    if field_definition is not None
                    else self.field_values.get(field_key)
                )
                if raw_value in (None, ""):
                    raise ValidationError(
                        {
                            "field_values": (
                                f'Connection "{self.name}" must define field "{field_key}" when its configured '
                                "HTTP auth mode is active."
                            )
                        }
                    )

        if connection_definition.oauth2 and _field_value_matches_condition(
            field_values=self.field_values,
            field_key=connection_definition.oauth2.enabled_when_field,
            values=connection_definition.oauth2.enabled_when_values,
        ):
            required_oauth_keys = [connection_definition.oauth2.token_url_field]
            if connection_definition.oauth2.client_id_field:
                required_oauth_keys.append(connection_definition.oauth2.client_id_field)
            for field_key in required_oauth_keys:
                field_definition = next(
                    (field for field in connection_definition.field_schema if field.key == field_key),
                    None,
                )
                raw_value = (
                    _get_effective_connection_field_value(field_values=self.field_values, field_definition=field_definition)
                    if field_definition is not None
                    else self.field_values.get(field_key)
                )
                if raw_value in (None, ""):
                    raise ValidationError(
                        {
                            "field_values": (
                                f'Connection "{self.name}" must define field "{field_key}" when its configured '
                                "OAuth mode is active."
                            )
                        }
                    )

        if self.pk and hasattr(self, "state"):
            self.state.full_clean(exclude={"connection"})

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


class WorkflowConnectionState(PrimaryModel):
    connection = models.OneToOneField(
        "automation.WorkflowConnection",
        on_delete=models.CASCADE,
        related_name="state",
    )
    state_values = models.JSONField(default=dict, blank=True)
    last_refreshed = models.DateTimeField(blank=True, null=True)

    changelog_exclude_fields = ("state_values",)

    class Meta:
        ordering = ("connection__name",)

    def __str__(self) -> str:
        return f"{self.connection.name} state"

    def get_absolute_url(self):
        return self.connection.get_absolute_url()

    def get_changelog_related_object(self):
        return self.connection

    @property
    def summary(self) -> dict[str, Any]:
        state_values = self.state_values or {}
        return {
            "has_access_token": bool(state_values.get("access_token")),
            "has_refresh_token": bool(state_values.get("refresh_token")),
            "expires_at": state_values.get("expires_at"),
            "account_id": state_values.get("account_id"),
            "last_refreshed": self.last_refreshed.isoformat() if self.last_refreshed else None,
        }

    def mark_refreshed(self) -> None:
        self.last_refreshed = timezone.now()

    def clean(self):
        super().clean()
        _validate_json_object(self.state_values, field_name="state_values")

        if not self.connection_id:
            raise ValidationError({"connection": "Connection state must reference a workflow connection."})

        connection_definition = get_catalog_connection_type(self.connection.connection_type)
        if connection_definition is None:
            raise ValidationError(
                {"connection": f'Unknown workflow connection type "{self.connection.connection_type}".'}
            )

        _validate_state_field_values(
            connection_definition=connection_definition,
            state_values=self.state_values,
            field_name="state_values",
        )
