from __future__ import annotations

from automation.catalog.loader import get_workflow_catalog

WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE = (
    "The workflow designer only supports v2 catalog nodes. Legacy workflow definitions are no longer supported."
)


def list_catalog_apps():
    registry = get_workflow_catalog()
    return tuple(
        sorted(
            registry["integration_apps"].values(),
            key=lambda app: (app.sort_order, app.id),
        )
    )


def get_catalog_app(app_id: str):
    return get_workflow_catalog()["integration_apps"].get(app_id)


def get_catalog_node(node_id: str):
    registry_node = get_workflow_catalog()["node_types"].get(node_id)
    if registry_node is not None:
        return registry_node

    from automation.nodes import get_workflow_node_definition

    return get_workflow_node_definition(node_id)


def get_catalog_connection_type(connection_type_id: str):
    return get_workflow_catalog()["connection_types"].get(connection_type_id)


def workflow_definition_supports_catalog_designer(definition) -> bool:
    if not isinstance(definition, dict):
        return True

    nodes = definition.get("nodes")
    edges = definition.get("edges")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []

    if not nodes and not edges:
        return True

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        if not isinstance(node_type, str) or not node_type.strip():
            continue
        if get_catalog_node(node_type) is None:
            return False
    return True


__all__ = (
    "get_catalog_app",
    "get_catalog_connection_type",
    "get_catalog_node",
    "list_catalog_apps",
    "WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE",
    "workflow_definition_supports_catalog_designer",
)
