from __future__ import annotations


WORKFLOW_NODE_CATALOG_SECTION_ORDER = ("triggers", "flow", "data", "apps")
WORKFLOW_NODE_CATALOG_SECTIONS = {
    "triggers": {
        "id": "triggers",
        "label": "Triggers",
        "description": "Choose how the workflow starts.",
        "icon": "mdi-rocket-launch-outline",
    },
    "flow": {
        "id": "flow",
        "label": "Flow",
        "description": "Control execution and AI-driven workflow steps.",
        "icon": "mdi-vector-polyline",
    },
    "data": {
        "id": "data",
        "label": "Data",
        "description": "Set values, render templates, and resolve workflow data.",
        "icon": "mdi-database-outline",
    },
    "apps": {
        "id": "apps",
        "label": "Apps",
        "description": "Connect workflow steps to external systems and providers.",
        "icon": "mdi-apps",
    },
}


__all__ = (
    "WORKFLOW_NODE_CATALOG_SECTION_ORDER",
    "WORKFLOW_NODE_CATALOG_SECTIONS",
)
