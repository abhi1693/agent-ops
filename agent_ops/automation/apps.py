from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "automation"

    def ready(self) -> None:
        from core.dashboard import register_dashboard_provider
        from core.navigation import register_navigation_provider

        from .dashboard import get_dashboard_contribution
        from .navigation import get_navigation_menus

        register_dashboard_provider(get_dashboard_contribution)
        register_navigation_provider(get_navigation_menus)

