"""OpenAI-compatible app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="openai",
    label="OpenAI",
    description="General-purpose GPT models for production agents and enterprise workflows.",
    icon="mdi-brain",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=40,
)

__all__ = ["APP_DEFINITION"]
