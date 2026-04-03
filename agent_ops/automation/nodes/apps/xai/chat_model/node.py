from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="xai")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="xai",
    node_type="xai.model.chat",
    details=(
        "Attach an xAI model provider to an agent node with curated Grok presets "
        "and an optional custom model override."
    ),
    display_name="xAI",
    icon="mdi-alpha-x-circle-outline",
    base_url="https://api.x.ai/v1",
    default_model="grok-code-fast-1",
    model_options=(
        ("grok-code-fast-1", "Grok Code Fast 1"),
        ("grok-4", "Grok 4"),
        ("grok-3", "Grok 3"),
        ("grok-3-mini", "Grok 3 Mini"),
    ),
    custom_model_placeholder="grok-code-fast-1",
)
