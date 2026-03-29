from django.urls import reverse

from tenancy.models import Environment, Organization, Workspace


def _stat_item(label, count, route_name):
    return {
        "label": label,
        "count": count,
        "url": reverse(route_name),
    }


def get_dashboard_contribution(request):
    user = request.user
    if not (user.is_staff or user.is_superuser):
        return {}

    organizations = Organization.objects.order_by("name")
    workspaces = Workspace.objects.select_related("organization").order_by(
        "organization__name", "name"
    )
    environments = Environment.objects.select_related(
        "organization", "workspace"
    ).order_by("organization__name", "workspace__name", "name")

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
