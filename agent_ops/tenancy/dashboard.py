from django.urls import reverse

from tenancy.models import Environment, Organization, Workspace
from users.restrictions import (
    has_model_action_permission,
    resolve_restriction_scope,
    restrict_queryset,
)


def _stat_item(label, count, route_name):
    return {
        "label": label,
        "count": count,
        "url": reverse(route_name),
    }


def get_dashboard_contribution(request):
    actor_scope = resolve_restriction_scope(request=request)
    if actor_scope is None:
        return {}

    if not any(
        has_model_action_permission(model, actor_scope=actor_scope, action="view")
        for model in (Organization, Workspace, Environment)
    ):
        return {}

    organizations = restrict_queryset(
        Organization.objects.order_by("name"),
        actor_scope=actor_scope,
        action="view",
    )
    workspaces = restrict_queryset(
        Workspace.objects.select_related("organization").order_by(
            "organization__name", "name"
        ),
        actor_scope=actor_scope,
        action="view",
    )
    environments = restrict_queryset(
        Environment.objects.select_related(
            "organization", "workspace"
        ).order_by("organization__name", "workspace__name", "name"),
        actor_scope=actor_scope,
        action="view",
    )

    stats = [
        {
            "title": "Tenancy",
            "icon": "domain",
            "items": [
                _stat_item("Organizations", organizations.count(), "organization_list"),
                _stat_item("Workspaces", workspaces.count(), "workspace_list"),
                _stat_item("Environments", environments.count(), "environment_list"),
            ],
        }
    ]

    return {
        "stats": stats,
        "panels": [],
    }
