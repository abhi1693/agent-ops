from django.urls import reverse

from automation.models import Workflow
from users.restrictions import has_model_action_permission, resolve_restriction_scope, restrict_queryset


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

    workflow_allowed = has_model_action_permission(Workflow, actor_scope=actor_scope, action="view")
    if not workflow_allowed:
        return {}

    items = []
    if workflow_allowed:
        workflows = restrict_queryset(
            Workflow.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "name",
            ),
            actor_scope=actor_scope,
            action="view",
        )
        items.append(_stat_item("Workflows", workflows.count(), "workflow_list"))

    return {
        "stats": [
            {
                "title": "Workflow Automation",
                "icon": "graph-outline",
                "items": items,
            }
        ],
        "panels": [],
    }
