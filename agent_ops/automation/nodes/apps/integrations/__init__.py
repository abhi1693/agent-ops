"""Integration app nodes."""

from automation.nodes.apps.base import workflow_app

from .mcp_server.node import NODE_DEFINITION as MCP_SERVER_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="integrations",
    label="Integrations",
    description="Connect to remote servers and external runtime capabilities.",
    icon="mdi-connection",
    nodes=(MCP_SERVER_NODE_DEFINITION,),
    sort_order=120,
)

__all__ = ["APP_DEFINITION"]
