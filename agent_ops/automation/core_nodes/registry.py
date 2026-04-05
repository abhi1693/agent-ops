from __future__ import annotations

import importlib
from pathlib import Path

from automation.catalog.definitions import CatalogNodeDefinition
from automation.catalog.registry import WorkflowCatalogRegistry


_CORE_NODE_PACKAGE_ROOT = "automation.core_nodes"
_CORE_NODE_DIRECTORY = Path(__file__).resolve().parent


def _discover_core_node_modules() -> tuple[str, ...]:
    module_paths: list[str] = []
    for node_file in sorted(_CORE_NODE_DIRECTORY.glob("*/node.py")):
        package_name = node_file.parent.name
        if package_name.startswith("_") or package_name == "__pycache__":
            continue
        module_paths.append(f"{_CORE_NODE_PACKAGE_ROOT}.{package_name}.node")
    return tuple(module_paths)


_CORE_NODE_MODULES = _discover_core_node_modules()


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
