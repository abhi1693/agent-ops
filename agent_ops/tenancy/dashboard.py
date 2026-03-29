from django.urls import reverse

from tenancy.models import Environment, Organization, Workspace
from users.scopes import (
    get_request_actor_scope,
    scope_environments_queryset,
    scope_organizations_queryset,
    scope_workspaces_queryset,
)


def _stat_item(label, count, route_name):
    return {
        "label": label,
        "count": count,
        "url": reverse(route_name),
    }


def get_dashboard_contribution(request):
    actor_scope = get_request_actor_scope(request)
    if actor_scope is None:
        return {}

    organizations = scope_organizations_queryset(
        Organization.objects.order_by("name"),
        actor_scope,
    )
    workspaces = scope_workspaces_queryset(
        Workspace.objects.select_related("organization").order_by(
            "organization__name", "name"
        ),
        actor_scope,
    )
    environments = scope_environments_queryset(
        Environment.objects.select_related(
            "organization", "workspace"
        ).order_by("organization__name", "workspace__name", "name"),
        actor_scope,
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
