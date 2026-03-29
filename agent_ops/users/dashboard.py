from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from users.models import Group, ObjectPermission, User


def _stat_item(label, count, route_name, disabled=False):
    return {
        "label": label,
        "count": count,
        "url": reverse(route_name),
        "disabled": disabled,
    }


def _panel(template_name, column_classes, **kwargs):
    panel = {
        "template_name": template_name,
        "column_classes": column_classes,
    }
    panel.update(kwargs)
    return panel


def get_dashboard_contribution(request):
    user = request.user
    config = user.get_config()
    is_staff = user.is_staff or user.is_superuser
    now = timezone.now()

    user_tokens = user.tokens.all()
    active_tokens = user_tokens.filter(enabled=True).filter(Q(expires__isnull=True) | Q(expires__gt=now))
    writable_tokens = active_tokens.filter(write_enabled=True)
    direct_permissions = user.object_permissions.order_by("name")
    group_memberships = user.groups.order_by("name")

    stats = [
        {
            "title": "Your Account",
            "icon": "account-circle-outline",
            "items": [
                _stat_item("Preferences", len(config.all()), "preferences"),
                _stat_item("Group Memberships", group_memberships.count(), "profile"),
                _stat_item("Direct Permissions", direct_permissions.count(), "profile"),
            ],
        },
        {
            "title": "Automation",
            "icon": "key-chain-variant",
            "items": [
                _stat_item("All Tokens", user_tokens.count(), "token_list"),
                _stat_item("Active Tokens", active_tokens.count(), "token_list"),
                _stat_item("Writable Tokens", writable_tokens.count(), "token_list"),
            ],
        },
        {
            "title": "Administration",
            "icon": "shield-account-outline",
            "items": [
                _stat_item("Users", User.objects.count(), "user_list", disabled=not is_staff),
                _stat_item("Groups", Group.objects.count(), "group_list", disabled=not is_staff),
                _stat_item(
                    "Object Permissions",
                    ObjectPermission.objects.count(),
                    "objectpermission_list",
                    disabled=not is_staff,
                ),
            ],
        },
    ]

    panels = []

    if not is_staff:
        panels.append(
            _panel(
                "users/dashboard/access_relationships_panel.html",
                "col col-sm-12 col-lg-6 col-xl-8 my-2",
                groups=[
                    {
                        "url": reverse("profile"),
                        "title": group.name,
                        "subtitle": group.description,
                    }
                    for group in group_memberships[:5]
                ],
                permissions=[
                    {
                        "url": reverse("profile"),
                        "title": permission.name,
                        "subtitle": (
                            f"{'Enabled' if permission.enabled else 'Disabled'}"
                            f" · {', '.join(permission.actions)}"
                        ),
                    }
                    for permission in direct_permissions[:5]
                ],
            )
        )

    return {
        "stats": stats,
        "panels": panels,
    }
