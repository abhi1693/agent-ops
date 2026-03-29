from django.urls import reverse

from integrations.models import Secret
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
    if not secret_allowed:
        return {}

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

    return {
        "stats": [
            {
                "title": "Integrations",
                "icon": "connection",
                "items": [
                    _stat_item("Secrets", secrets.count(), "secret_list"),
                ],
            }
        ],
        "panels": [],
    }
