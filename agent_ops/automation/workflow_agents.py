from __future__ import annotations

from typing import Any


AGENT_LANGUAGE_MODEL_INPUT_PORT = "ai_languageModel"
AGENT_TOOL_INPUT_PORT = "ai_tool"
AGENT_LANGUAGE_MODEL_NODE_TYPES = frozenset(
    {
        "tool.deepseek_chat_model",
        "tool.fireworks_chat_model",
        "tool.groq_chat_model",
        "tool.mistral_chat_model",
        "tool.openai_chat_model",
        "tool.openrouter_chat_model",
        "tool.xai_chat_model",
    }
)
SUPPORTED_AGENT_AUXILIARY_PORTS = frozenset(
    {
        AGENT_LANGUAGE_MODEL_INPUT_PORT,
        AGENT_TOOL_INPUT_PORT,
    }
)
AGENT_AUXILIARY_MAX_CONNECTIONS_BY_PORT = {
    AGENT_LANGUAGE_MODEL_INPUT_PORT: 1,
}
DEFAULT_AGENT_OUTPUT_KEY = "llm.response"


def is_agent_language_model_node_type(node_type: Any) -> bool:
    return isinstance(node_type, str) and node_type in AGENT_LANGUAGE_MODEL_NODE_TYPES


def is_agent_tool_source_node(source_node: dict[str, Any] | None) -> bool:
    if not isinstance(source_node, dict):
        return False
    if source_node.get("kind") != "tool":
        return False
    return not is_agent_language_model_node_type(source_node.get("type"))


def is_agent_auxiliary_source_compatible(*, source_node: dict[str, Any] | None, target_port: str) -> bool:
    if target_port == AGENT_LANGUAGE_MODEL_INPUT_PORT:
        if not isinstance(source_node, dict):
            return False
        return is_agent_language_model_node_type(source_node.get("type"))
    if target_port == AGENT_TOOL_INPUT_PORT:
        return is_agent_tool_source_node(source_node)
    return False


def describe_agent_auxiliary_supported_sources(target_port: str) -> str:
    if target_port == AGENT_LANGUAGE_MODEL_INPUT_PORT:
        return ", ".join(sorted(AGENT_LANGUAGE_MODEL_NODE_TYPES))
    if target_port == AGENT_TOOL_INPUT_PORT:
        return "any tool node except model provider nodes"
    return "none"


def normalize_workflow_agent_config(
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(config or {})
    if normalized.get("output_key") in ("", None):
        normalized["output_key"] = DEFAULT_AGENT_OUTPUT_KEY

    return normalized


def build_workflow_agent_tool_config(*, node: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_workflow_agent_config(config)
    prompt_template = normalized.get("template")
    if isinstance(prompt_template, str) and prompt_template.strip():
        rendered_prompt_template = prompt_template.strip()
    else:
        rendered_prompt_template = (node.get("label") or node["id"]).strip()
    return {
        **normalized,
        "user_prompt": rendered_prompt_template,
        "tool_name": "openai_compatible_chat",
    }
