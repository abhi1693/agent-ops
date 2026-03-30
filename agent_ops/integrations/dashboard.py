from django.urls import reverse

from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from users.restrictions import (
    has_model_action_permission,
    resolve_restriction_scope,
    restrict_queryset,
)


def _stat_item(label, count, route_name, *, disabled=False):
    return {
        "label": label,
        "count": count,
        "url": reverse(route_name),
        "disabled": disabled,
    }


def get_dashboard_contribution(request):
    actor_scope = resolve_restriction_scope(request=request)
    if actor_scope is None:
        return {}

    secret_allowed = has_model_action_permission(Secret, actor_scope=actor_scope, action="view")
    secret_group_allowed = has_model_action_permission(SecretGroup, actor_scope=actor_scope, action="view")
    secret_group_assignment_allowed = has_model_action_permission(
        SecretGroupAssignment,
        actor_scope=actor_scope,
        action="view",
    )
    if not secret_allowed and not secret_group_allowed and not secret_group_assignment_allowed:
        return {}

    items = []
    if secret_allowed:
        secrets = restrict_queryset(
            Secret.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "name",
            ),
            actor_scope=actor_scope,
            action="view",
        )
        items.append(_stat_item("Secrets", secrets.count(), "secret_list"))

    if secret_group_allowed:
        secret_groups = restrict_queryset(
            SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "name",
            ),
            actor_scope=actor_scope,
            action="view",
        )
        items.append(_stat_item("Secret Groups", secret_groups.count(), "secretgroup_list"))

    if secret_group_assignment_allowed:
        secret_group_assignments = restrict_queryset(
            SecretGroupAssignment.objects.select_related(
                "secret_group",
                "secret",
                "organization",
                "workspace",
                "environment",
            ).order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "secret_group__name",
                "order",
                "key",
            ),
            actor_scope=actor_scope,
            action="view",
        )
        items.append(
            _stat_item(
                "Secret Group Assignments",
                secret_group_assignments.count(),
                "secretgroupassignment_list",
            )
        )

    return {
        "stats": [
            {
                "title": "Integrations",
                "icon": "connection",
                "items": items,
            }
        ],
        "panels": [],
    }
