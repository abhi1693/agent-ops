"""Fireworks workflow app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="fireworks",
    label="Fireworks",
    description="High-throughput serverless inference for open models with OpenAI-compatible chat completions.",
    icon="mdi-rocket-launch",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=60,
)

__all__ = ["APP_DEFINITION"]
