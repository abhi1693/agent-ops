from __future__ import annotations

import importlib
import pkgutil

from automation.nodes.apps.base import WorkflowAppDefinition


def _discover_workflow_app_module_names() -> tuple[str, ...]:
    apps_package = importlib.import_module("automation.nodes.apps")
    return tuple(
        sorted(
            module_info.name
            for module_info in pkgutil.iter_modules(apps_package.__path__)
            if module_info.ispkg and not module_info.name.startswith("_")
        )
    )


def _load_workflow_app_definition(module_name: str) -> WorkflowAppDefinition:
    module = importlib.import_module(f"automation.nodes.apps.{module_name}")
    app_definition = getattr(module, "APP_DEFINITION", None)
    if not isinstance(app_definition, WorkflowAppDefinition):
        raise RuntimeError(
            f'Workflow app module "automation.nodes.apps.{module_name}" must export APP_DEFINITION.'
        )
    return app_definition


def load_workflow_app_definitions() -> tuple[WorkflowAppDefinition, ...]:
    app_definitions = tuple(
        sorted(
            (
                _load_workflow_app_definition(module_name)
                for module_name in _discover_workflow_app_module_names()
            ),
            key=lambda app_definition: (app_definition.sort_order, app_definition.id),
        )
    )

    app_ids = [app_definition.id for app_definition in app_definitions]
    duplicate_app_ids = {
        app_id
        for app_id in app_ids
        if app_ids.count(app_id) > 1
    }
    if duplicate_app_ids:
        duplicate_list = ", ".join(sorted(duplicate_app_ids))
        raise RuntimeError(f"Workflow apps declare duplicate ids: {duplicate_list}.")

    node_types = [
        node_definition.type
        for app_definition in app_definitions
        for node_definition in app_definition.nodes
    ]
    duplicate_node_types = {
        node_type
        for node_type in node_types
        if node_types.count(node_type) > 1
    }
    if duplicate_node_types:
        duplicate_list = ", ".join(sorted(duplicate_node_types))
        raise RuntimeError(f"Workflow apps declare duplicate node types: {duplicate_list}.")

    return app_definitions


WORKFLOW_APP_DEFINITIONS = load_workflow_app_definitions()
WORKFLOW_APP_DEFINITION_MAP = {
    app_definition.id: app_definition
    for app_definition in WORKFLOW_APP_DEFINITIONS
}
WORKFLOW_APP_NODE_DEFINITIONS = tuple(
    node_definition
    for app_definition in WORKFLOW_APP_DEFINITIONS
    for node_definition in app_definition.nodes
)
