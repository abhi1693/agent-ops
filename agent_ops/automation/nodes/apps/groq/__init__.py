"""Groq workflow app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="groq",
    label="Groq",
    description="Ultra-low-latency hosted models optimized for real-time and tool-heavy agent flows.",
    icon="mdi-lightning-bolt",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=70,
)

__all__ = ["APP_DEFINITION"]
