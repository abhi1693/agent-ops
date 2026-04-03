from __future__ import annotations

import collections


class WorkflowCatalogRegistry(dict):
    """
    Fixed-shape registry for workflow catalog stores.

    Top-level stores are immutable after initialization; store contents remain mutable.
    """

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError as exc:
            raise KeyError(f"Invalid workflow catalog store: {key}") from exc

    def __setitem__(self, key, value):
        raise TypeError("Cannot add stores to workflow catalog registry after initialization")

    def __delitem__(self, key):
        raise TypeError("Cannot delete stores from workflow catalog registry")


def create_workflow_catalog_registry() -> WorkflowCatalogRegistry:
    return WorkflowCatalogRegistry(
        {
            "core_nodes": {},
            "integration_apps": {},
            "node_types": {},
            "connection_types": {},
            "capability_index": collections.defaultdict(set),
            "category_index": collections.defaultdict(set),
        }
    )


__all__ = ("WorkflowCatalogRegistry", "create_workflow_catalog_registry")
