from __future__ import annotations

import importlib
import pkgutil

from automation.catalog.definitions import IntegrationApp


def discover_integration_module_names() -> tuple[str, ...]:
    integrations_package = importlib.import_module("automation.integrations")
    return tuple(
        sorted(
            module_info.name
            for module_info in pkgutil.iter_modules(integrations_package.__path__)
            if module_info.ispkg and not module_info.name.startswith("_")
        )
    )


def load_integration_app(module_name: str) -> IntegrationApp:
    module = importlib.import_module(f"automation.integrations.{module_name}.app")
    app_definition = getattr(module, "APP", None)
    if not isinstance(app_definition, IntegrationApp):
        raise RuntimeError(
            f'Integration module "automation.integrations.{module_name}.app" must export APP.'
        )
    return app_definition


def load_integration_apps() -> tuple[IntegrationApp, ...]:
    return tuple(
        sorted(
            (load_integration_app(module_name) for module_name in discover_integration_module_names()),
            key=lambda app: (app.sort_order, app.id),
        )
    )


__all__ = ("discover_integration_module_names", "load_integration_app", "load_integration_apps")
