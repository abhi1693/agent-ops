"""Infrastructure app nodes."""

from automation.nodes.apps.base import workflow_app

from .kubectl.node import NODE_DEFINITION as KUBECTL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="infrastructure",
    label="Infrastructure",
    description="Operate infrastructure workflows against the local app host environment.",
    icon="mdi-kubernetes",
    nodes=(KUBECTL_NODE_DEFINITION,),
    sort_order=110,
)

__all__ = ["APP_DEFINITION"]
