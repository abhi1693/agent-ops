"""xAI workflow app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="xai",
    label="xAI",
    description="Grok reasoning and coding models exposed through xAI's OpenAI-compatible API.",
    icon="mdi-alpha-x-circle-outline",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=100,
)

__all__ = ["APP_DEFINITION"]
