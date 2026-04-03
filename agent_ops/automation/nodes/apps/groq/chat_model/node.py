from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_definition,
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="groq")
NODE_DEFINITION = build_openai_compatible_chat_model_definition(
    api_type="groq",
    node_type="tool.groq_chat_model",
    details=(
        "Attach a Groq model provider to an agent node with curated low-latency "
        "presets and an optional custom model override."
    ),
    display_name="Groq",
    icon="mdi-lightning-bolt",
    base_url="https://api.groq.com/openai/v1",
    default_model="llama-3.3-70b-versatile",
    model_options=(
        ("llama-3.1-8b-instant", "Llama 3.1 8B Instant"),
        ("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile"),
        ("openai/gpt-oss-120b", "GPT-OSS 120B"),
        ("meta-llama/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B"),
    ),
    custom_model_placeholder="llama-3.3-70b-versatile",
)
