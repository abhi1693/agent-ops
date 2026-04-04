from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from automation.catalog.services import get_catalog_connection_type
from automation.models import WorkflowConnection


@dataclass(frozen=True)
class WorkflowResolvedConnection:
    connection: WorkflowConnection
    values: dict[str, Any]
    secret_metas: dict[str, dict[str, str | None]]


def _build_scope_queryset(runtime):
    queryset = WorkflowConnection.objects.select_related(
        "secret_group",
    ).filter(
        organization=runtime.workflow.organization,
        enabled=True,
    )

    if runtime.workflow.environment_id:
        return queryset.filter(
            Q(environment=runtime.workflow.environment)
            | Q(environment__isnull=True, workspace=runtime.workflow.workspace)
            | Q(environment__isnull=True, workspace__isnull=True, organization=runtime.workflow.organization)
        )

    if runtime.workflow.workspace_id:
        return queryset.filter(
            Q(workspace=runtime.workflow.workspace, environment__isnull=True)
            | Q(workspace__isnull=True, environment__isnull=True, organization=runtime.workflow.organization)
        )

    return queryset.filter(
        workspace__isnull=True,
        environment__isnull=True,
    )


def _get_connection(runtime, *, connection_id: str | int | None, expected_connection_type: str | None) -> WorkflowConnection:
    if connection_id in (None, ""):
        raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.connection_id.'})

    queryset = _build_scope_queryset(runtime)

    try:
        connection = queryset.get(pk=connection_id)
    except WorkflowConnection.DoesNotExist as exc:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" references unavailable connection "{connection_id}".'}
        ) from exc

    if expected_connection_type and connection.connection_type != expected_connection_type:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{runtime.node["id"]}" requires connection type "{expected_connection_type}", '
                    f'but received "{connection.connection_type}".'
                )
            }
        )

    return connection


def _resolve_secret_value(runtime, *, connection: WorkflowConnection, field_key: str, secret) -> tuple[str, dict[str, str | None]]:
    secret_value = secret.get_value(obj=runtime.workflow)
    if not isinstance(secret_value, str) or not secret_value:
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{connection.name}" secret "{secret.name}" for field "{field_key}" must resolve '
                    "to a non-empty string."
                )
            }
        )

    runtime.secret_values.append(secret_value)
    return (
        secret_value,
        {
            "name": secret.name,
            "provider": secret.provider,
            "secret_group": secret.secret_group.name if secret.secret_group_id else None,
        },
    )


def resolve_workflow_connection_fields(
    runtime,
    *,
    connection_id: str | int | None,
    expected_connection_type: str | None,
) -> WorkflowResolvedConnection:
    connection = _get_connection(
        runtime,
        connection_id=connection_id,
        expected_connection_type=expected_connection_type,
    )
    connection_definition = get_catalog_connection_type(connection.connection_type)
    if connection_definition is None:
        raise ValidationError(
            {"definition": f'Connection "{connection.name}" uses unknown connection type "{connection.connection_type}".'}
        )

    resolved_values: dict[str, Any] = {}
    secret_metas: dict[str, dict[str, str | None]] = {}
    field_values = connection.field_values or {}

    for field_definition in connection_definition.field_schema:
        raw_value = field_values.get(field_definition.key)

        if field_definition.value_type == "secret_ref":
            if raw_value in (None, ""):
                if field_definition.required:
                    raise ValidationError(
                        {
                            "definition": (
                                f'Connection "{connection.name}" must define secret-backed field '
                                f'"{field_definition.key}".'
                            )
                        }
                    )
                continue

            if not isinstance(raw_value, dict):
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" field "{field_definition.key}" must be a JSON object '
                            "when using a secret reference."
                        )
                    }
                )

            source = raw_value.get("source", "secret")
            if source != "secret":
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" field "{field_definition.key}" must use source '
                            '"secret".'
                        )
                    }
                )

            secret_name = raw_value.get("secret_name")
            if not isinstance(secret_name, str) or not secret_name.strip():
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" field "{field_definition.key}" must define a '
                            "non-empty secret_name."
                        )
                    }
                )
            if connection.secret_group is None:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" must define a secret group before using field '
                            f'"{field_definition.key}".'
                        )
                    }
                )

            secret = connection.secret_group.get_secret(name=secret_name.strip())
            if secret is None or not secret.enabled:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" cannot resolve enabled secret "{secret_name.strip()}" '
                            f'for field "{field_definition.key}".'
                        )
                    }
                )

            secret_value, secret_meta = _resolve_secret_value(
                runtime,
                connection=connection,
                field_key=field_definition.key,
                secret=secret,
            )
            resolved_values[field_definition.key] = secret_value
            secret_metas[field_definition.key] = secret_meta
            continue

        if raw_value in (None, ""):
            raw_value = field_definition.default

        if raw_value in (None, ""):
            if field_definition.required:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" must define field "{field_definition.key}".'
                        )
                    }
                )
            continue

        resolved_values[field_definition.key] = raw_value

    return WorkflowResolvedConnection(
        connection=connection,
        values=resolved_values,
        secret_metas=secret_metas,
    )
