"""DeepSeek workflow app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="deepseek",
    label="DeepSeek",
    description="Fast open-weight chat and reasoning models exposed through an OpenAI-compatible API.",
    icon="mdi-radar",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=50,
)

__all__ = ["APP_DEFINITION"]
