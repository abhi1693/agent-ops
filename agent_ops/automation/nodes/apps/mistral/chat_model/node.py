from __future__ import annotations

from automation.nodes.apps.openai.chat_model.helpers import (
    build_openai_compatible_chat_model_implementation,
)


NODE_IMPLEMENTATION = build_openai_compatible_chat_model_implementation(api_type="mistral")
