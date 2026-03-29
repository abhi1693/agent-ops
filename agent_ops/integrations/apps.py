from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"

    def ready(self):
        from core.dashboard import register_dashboard_provider
        from core.navigation import register_navigation_provider

        from . import builtin_secrets  # noqa: F401
        from .dashboard import get_dashboard_contribution
        from .navigation import get_navigation_menus

        register_dashboard_provider(get_dashboard_contribution)
        register_navigation_provider(get_navigation_menus)
