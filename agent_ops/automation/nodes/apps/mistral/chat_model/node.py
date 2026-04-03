from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="mistral")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="mistral",
    node_type="tool.mistral_chat_model",
    details=(
        "Attach a Mistral model provider to an agent node with curated flagship, "
        "coding, and efficient presets plus an optional custom override."
    ),
    display_name="Mistral",
    icon="mdi-weather-windy",
    app_id="mistral",
    app_label="Mistral",
    app_description="Flagship, coding, and efficient frontier models served through Mistral's chat API.",
    app_icon="mdi-weather-windy",
    base_url="https://api.mistral.ai/v1",
    default_model="mistral-large-latest",
    model_options=(
        ("mistral-large-latest", "Mistral Large"),
        ("devstral-latest", "Devstral"),
        ("codestral-latest", "Codestral"),
        ("ministral-8b-latest", "Ministral 8B"),
    ),
    custom_model_placeholder="mistral-large-latest",
)
