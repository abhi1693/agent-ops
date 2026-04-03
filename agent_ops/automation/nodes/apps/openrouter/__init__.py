"""OpenRouter workflow app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="openrouter",
    label="OpenRouter",
    description="One provider node that can route across multiple frontier model ecosystems.",
    icon="mdi-router-wireless",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=90,
)

__all__ = ["APP_DEFINITION"]
