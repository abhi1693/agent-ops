from __future__ import annotations

from typing import Any

from automation.tools.base import WORKFLOW_INPUT_MODES_CONFIG_KEY


AGENT_LANGUAGE_MODEL_INPUT_PORT = "ai_languageModel"
AGENT_TOOL_INPUT_PORT = "ai_tool"
AGENT_LANGUAGE_MODEL_NODE_TYPES = frozenset(
    {
        "openai.model.chat",
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
    prompt_template = normalized.get("template")
    legacy_instructions = normalized.get("instructions")
    if (
        (not isinstance(prompt_template, str) or not prompt_template.strip())
        and isinstance(legacy_instructions, str)
        and legacy_instructions.strip()
    ):
        normalized["template"] = legacy_instructions.strip()

    raw_input_modes = normalized.get(WORKFLOW_INPUT_MODES_CONFIG_KEY)
    if isinstance(raw_input_modes, dict):
        next_input_modes = dict(raw_input_modes)
        if (
            "template" not in next_input_modes
            and isinstance(next_input_modes.get("instructions"), str)
        ):
            next_input_modes["template"] = next_input_modes["instructions"]
        normalized[WORKFLOW_INPUT_MODES_CONFIG_KEY] = next_input_modes

    if normalized.get("output_key") in ("", None):
        normalized["output_key"] = DEFAULT_AGENT_OUTPUT_KEY

    return normalized


def build_workflow_agent_tool_config(*, node: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_workflow_agent_config(config)
    prompt_template = normalized.get("template")
    if not isinstance(prompt_template, str) or not prompt_template.strip():
        prompt_template = normalized.get("instructions")
    if isinstance(prompt_template, str) and prompt_template.strip():
        rendered_prompt_template = prompt_template.strip()
    else:
        rendered_prompt_template = (node.get("label") or node["id"]).strip()
    input_modes = normalized.get(WORKFLOW_INPUT_MODES_CONFIG_KEY)
    next_input_modes = dict(input_modes) if isinstance(input_modes, dict) else None
    if next_input_modes:
        template_mode = next_input_modes.get("template")
        if not isinstance(template_mode, str):
            template_mode = next_input_modes.get("instructions")
        if isinstance(template_mode, str):
            next_input_modes["user_prompt"] = template_mode
    return {
        **normalized,
        "user_prompt": rendered_prompt_template,
        "tool_name": "openai_compatible_chat",
        **(
            {WORKFLOW_INPUT_MODES_CONFIG_KEY: next_input_modes}
            if next_input_modes
            else {}
        ),
    }
