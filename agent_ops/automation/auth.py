from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from automation.models.secrets import Secret, SecretGroup


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
    default_label = "Use workflow secret group" if workflow.secret_group_id else "No secret group"
    options = [{"value": "", "label": default_label}]
    for secret_group in get_workflow_secret_groups_queryset(workflow):
        label = secret_group.name
        if secret_group.scope_label:
            label = f"{secret_group.name} ({secret_group.scope_label})"
        options.append({"value": str(secret_group.pk), "label": label})
    return options


def list_workflow_secret_name_options_by_group(workflow) -> dict[str, list[dict[str, str]]]:
    secret_groups = list(get_workflow_secret_groups_queryset(workflow))
    options_by_group = {str(secret_group.pk): [] for secret_group in secret_groups}
    if options_by_group:
        for secret in (
            Secret.objects.filter(secret_group_id__in=[secret_group.pk for secret_group in secret_groups], enabled=True)
            .order_by("name")
        ):
            options_by_group[str(secret.secret_group_id)].append({"value": secret.name, "label": secret.name})

    default_group_key = str(workflow.secret_group_id) if workflow.secret_group_id else ""
    options_by_group[""] = list(options_by_group.get(default_group_key, []))
    return options_by_group


def resolve_workflow_secret_group(
    workflow,
    *,
    error_field: str,
    secret_group_id: str | int | None = None,
) -> SecretGroup | None:
    resolved_group_id = secret_group_id
    if resolved_group_id in ("", None):
        resolved_group_id = workflow.secret_group_id
    if resolved_group_id in ("", None):
        return None

    try:
        resolved_group_id = int(resolved_group_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError({error_field: "Secret group reference must be a numeric ID."}) from exc

    secret_group = get_workflow_secret_groups_queryset(workflow).filter(pk=resolved_group_id).first()
    if secret_group is None:
        raise ValidationError({error_field: "Selected secret group is not available in this workflow scope."})
    return secret_group


def resolve_workflow_secret_ref(
    workflow,
    *,
    secret_name: str,
    secret_group_id: str | int | None = None,
    error_field: str = "definition",
    required: bool = True,
) -> Secret | None:
    if not isinstance(secret_name, str) or not secret_name.strip():
        if required:
            raise ValidationError({error_field: "Secret name is required for this node."})
        return None

    rendered_secret_name = secret_name.strip()
    secret_group = resolve_workflow_secret_group(
        workflow,
        error_field=error_field,
        secret_group_id=secret_group_id,
    )
    if secret_group is None:
        if required:
            raise ValidationError({error_field: "Workflow must define a secret group for secret-backed nodes."})
        return None

    secret = secret_group.get_secret(name=rendered_secret_name)
    if secret is not None:
        if not secret.enabled:
            if required:
                raise ValidationError(
                    {
                        error_field: (
                            f'Secret group "{secret_group.name}" includes disabled secret "{rendered_secret_name}".'
                        )
                    }
                )
            return None
        return secret
    if required:
        raise ValidationError(
            {
                error_field: (
                    f'Secret group "{secret_group.name}" does not include secret "{rendered_secret_name}".'
                )
            }
        )
    return None
