from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="openai")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="openai",
    node_type="tool.openai_chat_model",
    details=(
        "Attach an OpenAI model provider to an agent node with curated GPT presets "
        "and an optional custom model override."
    ),
    display_name="OpenAI",
    icon="mdi-brain",
    app_id="openai",
    app_label="OpenAI",
    app_description="General-purpose GPT models for production agents and enterprise workflows.",
    app_icon="mdi-brain",
    base_url="https://api.openai.com/v1",
    default_model="gpt-4.1-mini",
    model_options=(
        ("gpt-4.1-mini", "GPT-4.1 Mini"),
        ("gpt-4.1", "GPT-4.1"),
        ("gpt-4o-mini", "GPT-4o Mini"),
        ("gpt-4o", "GPT-4o"),
    ),
    custom_model_placeholder="gpt-5.2",
)
