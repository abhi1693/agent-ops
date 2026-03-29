from collections.abc import Callable

from django.urls import reverse

from core.changelog import get_objectchange_target_url, restrict_objectchange_queryset
from core.models import ObjectChange
from users.restrictions import resolve_restriction_scope


DashboardProvider = Callable[[object], dict]

_dashboard_providers: list[DashboardProvider] = []


def register_dashboard_provider(provider: DashboardProvider) -> None:
    if provider not in _dashboard_providers:
        _dashboard_providers.append(provider)


def _panel(template_name, column_classes, **kwargs):
    panel = {
        "template_name": template_name,
        "column_classes": column_classes,
    }
    panel.update(kwargs)
    return panel


def _get_recent_changes_queryset(request):
    actor_scope = resolve_restriction_scope(request=request)
    if actor_scope is None:
        return ObjectChange.objects.none(), actor_scope

    queryset = ObjectChange.objects.select_related(
        "user",
        "changed_object_type",
        "related_object_type",
    ).order_by("-time")
    if actor_scope.is_staff:
        return queryset, actor_scope

    return restrict_objectchange_queryset(queryset, actor_scope=actor_scope), actor_scope


def get_dashboard_contribution(request):
    recent_changes, actor_scope = _get_recent_changes_queryset(request)
    if actor_scope is None:
        return {}
    if not (actor_scope.is_staff or actor_scope.is_scoped or recent_changes.exists()):
        return {}

    changes = [
        {
            "action": change.get_action_display(),
            "badge_class": change.badge_class,
            "object_repr": change.object_repr,
            "time": change.time,
            "url": get_objectchange_target_url(change),
            "user_name": change.user_name or "System",
        }
        for change in recent_changes[:8]
    ]

    empty_message = "No recent changes recorded yet."
    if actor_scope.is_scoped and not actor_scope.is_staff:
        empty_message = "No recent changes recorded for your active scope."

    return {
        "stats": [],
        "panels": [
            _panel(
                "core/dashboard/changelog_panel.html",
                "col col-sm-12 col-lg-6 col-xl-4 my-2",
                title="Recent Changes",
                icon="history",
                changes=changes,
                change_count=len(changes),
                empty_message=empty_message,
                url=reverse("objectchange_list"),
            )
        ],
    }


def build_dashboard_context(request) -> dict:
    stats = []
    panels = []

    for provider in _dashboard_providers:
        contribution = provider(request)
        if not contribution:
            continue
        stats.extend(contribution.get("stats", []))
        panels.extend(contribution.get("panels", []))

    return {
        "stats": stats,
        "dashboard_panels": panels,
    }
