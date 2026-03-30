from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from integrations.models import Secret, SecretGroup, SecretGroupAssignment


def _workflow_scope_candidates(workflow) -> list[dict[str, Any]]:
    scope_candidates = []
    if workflow.environment_id:
        scope_candidates.append({"environment": workflow.environment})
    if workflow.workspace_id:
        scope_candidates.append({"workspace": workflow.workspace, "environment__isnull": True})
    if workflow.organization_id:
        scope_candidates.append(
            {
                "organization": workflow.organization,
                "workspace__isnull": True,
                "environment__isnull": True,
            }
        )
    return scope_candidates


def get_workflow_secret_groups_queryset(workflow):
    scope_candidates = _workflow_scope_candidates(workflow)
    if not scope_candidates:
        return SecretGroup.objects.none()

    scope_query = Q()
    for scope_filter in scope_candidates:
        scope_query |= Q(**scope_filter)

    return (
        SecretGroup.objects.filter(scope_query)
        .select_related("organization", "workspace", "environment")
        .order_by("organization__name", "workspace__name", "environment__name", "name")
    )


def list_workflow_secret_group_options(workflow) -> list[dict[str, str]]:
    options = [{"value": "", "label": "No secret group"}]
    for secret_group in get_workflow_secret_groups_queryset(workflow):
        label = secret_group.name
        if secret_group.scope_label:
            label = f"{secret_group.name} ({secret_group.scope_label})"
        options.append({"value": str(secret_group.pk), "label": label})
    return options


def resolve_workflow_secret_group(workflow, *, secret_group_id: str | int | None, error_field: str) -> SecretGroup | None:
    if secret_group_id in (None, ""):
        return None

    try:
        secret_group_pk = int(secret_group_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError({error_field: f'Secret group "{secret_group_id}" is not a valid identifier.'}) from exc

    secret_group = get_workflow_secret_groups_queryset(workflow).filter(pk=secret_group_pk).first()
    if secret_group is None:
        raise ValidationError(
            {error_field: f'Secret group "{secret_group_id}" is not available in this workflow scope.'}
        )
    return secret_group


def resolve_workflow_secret(
    workflow,
    *,
    name: str,
    provider: str | None = None,
    secret_group_id: str | int | None = None,
    error_field: str = "definition",
) -> Secret:
    secret_group = resolve_workflow_secret_group(
        workflow,
        secret_group_id=secret_group_id,
        error_field=error_field,
    )
    if secret_group is not None:
        assignments = SecretGroupAssignment.objects.filter(
            secret_group=secret_group,
            secret__enabled=True,
        ).select_related("secret")
        if provider:
            assignments = assignments.filter(secret__provider=provider)

        assignment = assignments.filter(key=name).order_by("order", "key").first()
        if assignment is not None:
            return assignment.secret

        assignment = assignments.filter(secret__name=name).order_by("order", "key").first()
        if assignment is not None:
            return assignment.secret

        if provider:
            raise ValidationError(
                {
                    error_field: (
                        f'No enabled secret matching "{name}" with provider "{provider}" '
                        f'is assigned to secret group "{secret_group.name}".'
                    )
                }
            )
        raise ValidationError(
            {
                error_field: f'No enabled secret matching "{name}" is assigned to secret group "{secret_group.name}".'
            }
        )

    scope_candidates = _workflow_scope_candidates(workflow)
    for scope_filter in scope_candidates:
        queryset = Secret.objects.filter(enabled=True, name=name, **scope_filter).order_by("name")
        if provider:
            queryset = queryset.filter(provider=provider)
        secret = queryset.first()
        if secret is not None:
            return secret

    if provider:
        raise ValidationError(
            {error_field: f'No enabled secret named "{name}" with provider "{provider}" is available.'}
        )
    raise ValidationError({error_field: f'No enabled secret named "{name}" is available in this workflow scope.'})
