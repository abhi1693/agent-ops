from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from .dashboard import get_dashboard_contribution, register_dashboard_provider
        from .navigation import get_navigation_menus, register_navigation_provider
        from . import signals  # noqa: F401

        register_dashboard_provider(get_dashboard_contribution)
        register_navigation_provider(get_navigation_menus)
