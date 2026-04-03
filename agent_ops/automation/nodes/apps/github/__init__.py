"""GitHub app nodes."""

from automation.nodes.apps.base import workflow_app

from .webhook.node import NODE_DEFINITION as WEBHOOK_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="github",
    label="GitHub",
    description="Receive webhook events from GitHub workflows and repositories.",
    icon="mdi-github",
    nodes=(WEBHOOK_NODE_DEFINITION,),
    sort_order=20,
)

__all__ = ["APP_DEFINITION"]
