"""Mistral workflow app nodes."""

from automation.nodes.apps.base import workflow_app

from .chat_model.node import NODE_DEFINITION as CHAT_MODEL_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="mistral",
    label="Mistral",
    description="Flagship, coding, and efficient frontier models served through Mistral's chat API.",
    icon="mdi-weather-windy",
    nodes=(CHAT_MODEL_NODE_DEFINITION,),
    sort_order=80,
)

__all__ = ["APP_DEFINITION"]
