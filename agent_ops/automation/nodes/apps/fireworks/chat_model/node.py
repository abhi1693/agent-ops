from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="fireworks")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="fireworks",
    node_type="tool.fireworks_chat_model",
    details=(
        "Attach a Fireworks model provider to an agent node with curated serverless "
        "open-model presets and an optional custom model override."
    ),
    display_name="Fireworks",
    icon="mdi-rocket-launch",
    app_id="fireworks",
    app_label="Fireworks",
    app_description="High-throughput serverless inference for open models with OpenAI-compatible chat completions.",
    app_icon="mdi-rocket-launch",
    base_url="https://api.fireworks.ai/inference/v1",
    default_model="accounts/fireworks/models/llama-v3p1-8b-instruct",
    model_options=(
        ("accounts/fireworks/models/llama-v3p1-8b-instruct", "Llama 3.1 8B Instruct"),
        ("accounts/fireworks/models/llama-v3p1-70b-instruct", "Llama 3.1 70B Instruct"),
        ("accounts/fireworks/models/deepseek-v3", "DeepSeek V3"),
        ("accounts/fireworks/models/qwen2p5-72b-instruct", "Qwen 2.5 72B Instruct"),
    ),
    custom_model_placeholder="accounts/fireworks/models/llama-v3p1-8b-instruct",
)
