from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Q

from automation.models import WorkflowConnection


@dataclass(frozen=True)
class WorkflowRuntimeConnection:
    connection: WorkflowConnection
    secret_value: str | None
    secret_meta: dict[str, str | None] | None


def resolve_workflow_connection(
    runtime,
    *,
    connection_id: str | int | None,
    expected_connection_type: str | None,
) -> WorkflowRuntimeConnection:
    if connection_id in (None, ""):
        raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.connection_id.'})

    queryset = WorkflowConnection.objects.select_related(
        "credential_secret",
        "credential_secret__secret_group",
    ).filter(
        organization=runtime.workflow.organization,
        enabled=True,
    )

    if runtime.workflow.environment_id:
        queryset = queryset.filter(
            Q(environment=runtime.workflow.environment)
            | Q(environment__isnull=True, workspace=runtime.workflow.workspace)
            | Q(environment__isnull=True, workspace__isnull=True, organization=runtime.workflow.organization)
        )
    elif runtime.workflow.workspace_id:
        queryset = queryset.filter(
            Q(workspace=runtime.workflow.workspace, environment__isnull=True)
            | Q(workspace__isnull=True, environment__isnull=True, organization=runtime.workflow.organization)
        )
    else:
        queryset = queryset.filter(
            workspace__isnull=True,
            environment__isnull=True,
        )

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

    if connection.credential_secret is None:
        return WorkflowRuntimeConnection(connection=connection, secret_value=None, secret_meta=None)

    secret_value = connection.credential_secret.get_value(obj=runtime.workflow)
    if not isinstance(secret_value, str) or not secret_value:
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{connection.name}" secret "{connection.credential_secret.name}" must resolve '
                    "to a non-empty string."
                )
            }
        )
    runtime.secret_values.append(secret_value)
    return WorkflowRuntimeConnection(
        connection=connection,
        secret_value=secret_value,
        secret_meta={
            "name": connection.credential_secret.name,
            "provider": connection.credential_secret.provider,
            "secret_group": (
                connection.credential_secret.secret_group.name
                if connection.credential_secret.secret_group_id
                else None
            ),
        },
    )
