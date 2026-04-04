from __future__ import annotations

from typing import Any

from automation.catalog.services import get_catalog_node
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult


def get_catalog_runtime_node(node_type: Any):
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    node_definition = get_catalog_node(node_type.strip())
    if node_definition is None or node_definition.runtime_executor is None:
        return None
    return node_definition


def execute_catalog_runtime_node(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult | None:
    node_definition = get_catalog_runtime_node(runtime.node.get("type"))
    if node_definition is None:
        return None
    return node_definition.runtime_executor(runtime)


__all__ = ("execute_catalog_runtime_node", "get_catalog_runtime_node")
