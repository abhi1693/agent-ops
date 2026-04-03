from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="openrouter")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="openrouter",
    node_type="openrouter.model.chat",
    details=(
        "Attach an OpenRouter model provider to an agent node with curated routing "
        "presets and an optional custom model override."
    ),
    display_name="OpenRouter",
    icon="mdi-router-wireless",
    base_url="https://openrouter.ai/api/v1",
    default_model="openai/gpt-5.2",
    model_options=(
        ("openrouter/auto", "OpenRouter Auto"),
        ("openai/gpt-5.2", "OpenAI GPT-5.2"),
        ("anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5"),
        ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("x-ai/grok-code-fast-1", "Grok Code Fast 1"),
    ),
    custom_model_placeholder="anthropic/claude-sonnet-4.5",
)
