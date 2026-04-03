from __future__ import annotations

from automation.catalog.discovery import load_integration_apps
from automation.catalog.registry import WorkflowCatalogRegistry, create_workflow_catalog_registry


_workflow_catalog: WorkflowCatalogRegistry | None = None


def build_workflow_catalog() -> WorkflowCatalogRegistry:
    from automation.core_nodes.registry import register_core_nodes

    registry = create_workflow_catalog_registry()
    register_core_nodes(registry)
    for integration_app in load_integration_apps():
        integration_app.register(registry)
    return registry


def initialize_workflow_catalog() -> WorkflowCatalogRegistry:
    global _workflow_catalog
    if _workflow_catalog is None:
        _workflow_catalog = build_workflow_catalog()
    return _workflow_catalog


def get_workflow_catalog() -> WorkflowCatalogRegistry:
    return initialize_workflow_catalog()


def reset_workflow_catalog() -> None:
    global _workflow_catalog
    _workflow_catalog = None


__all__ = (
    "build_workflow_catalog",
    "get_workflow_catalog",
    "initialize_workflow_catalog",
    "reset_workflow_catalog",
)
