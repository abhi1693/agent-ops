from __future__ import annotations

import importlib

from automation.catalog.definitions import CatalogNodeDefinition
from automation.catalog.registry import WorkflowCatalogRegistry


_CORE_NODE_MODULES = (
    "automation.core_nodes.manual_trigger.node",
    "automation.core_nodes.schedule_trigger.node",
    "automation.core_nodes.agent.node",
    "automation.core_nodes.set.node",
    "automation.core_nodes.if.node",
    "automation.core_nodes.switch.node",
    "automation.core_nodes.response.node",
    "automation.core_nodes.stop_and_error.node",
)


def _load_core_node_definition(module_import_path: str) -> CatalogNodeDefinition:
    imported_module = importlib.import_module(module_import_path)
    definition = getattr(imported_module, "NODE_DEFINITION", None)
    if not isinstance(definition, CatalogNodeDefinition):
        raise RuntimeError(f'Core node module "{module_import_path}" must export NODE_DEFINITION.')
    return definition


CORE_NODE_DEFINITIONS = tuple(
    _load_core_node_definition(module_import_path)
    for module_import_path in _CORE_NODE_MODULES
)


def register_core_nodes(registry: WorkflowCatalogRegistry) -> None:
    for node_definition in CORE_NODE_DEFINITIONS:
        node_definition.register(registry)
        registry["core_nodes"][node_definition.id] = node_definition


__all__ = ("CORE_NODE_DEFINITIONS", "register_core_nodes")
