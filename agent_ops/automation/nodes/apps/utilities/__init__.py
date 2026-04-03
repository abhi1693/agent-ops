"""Utility app nodes."""

from automation.nodes.apps.base import workflow_app

from .secret.node import NODE_DEFINITION as SECRET_NODE_DEFINITION
from .template.node import NODE_DEFINITION as TEMPLATE_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="utilities",
    label="AgentOps utilities",
    description="AgentOps-specific helper nodes that are intentionally separate from the catalog-native core set.",
    icon="mdi-tools",
    nodes=(
        TEMPLATE_NODE_DEFINITION,
        SECRET_NODE_DEFINITION,
    ),
    sort_order=10,
)

__all__ = ["APP_DEFINITION"]
