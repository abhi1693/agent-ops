from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="deepseek")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="deepseek",
    node_type="tool.deepseek_chat_model",
    details=(
        "Attach a DeepSeek model provider to an agent node with curated chat and "
        "reasoning presets plus an optional custom model override."
    ),
    display_name="DeepSeek",
    icon="mdi-radar",
    app_id="deepseek",
    app_label="DeepSeek",
    app_description="Fast open-weight chat and reasoning models exposed through an OpenAI-compatible API.",
    app_icon="mdi-radar",
    base_url="https://api.deepseek.com/v1",
    default_model="deepseek-chat",
    model_options=(
        ("deepseek-chat", "DeepSeek Chat"),
        ("deepseek-reasoner", "DeepSeek Reasoner"),
    ),
    custom_model_placeholder="deepseek-chat",
)
