from __future__ import annotations

from automation.nodes.adapters import tool_definition_as_node_implementation
from automation.nodes.apps.openai.client import (
    build_openai_chat_payload,
    execute_openai_chat_completion,
    validate_openai_chat_model_config,
)
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _render_runtime_string,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_string,
    _validate_required_string,
    tool_text_field,
    tool_textarea_field,
)


def _validate_openai_compatible_chat_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    validate_openai_chat_model_config(config, node_id)
    _validate_required_string(config, "user_prompt", node_id=node_id)
    _validate_optional_string(config, "system_prompt", node_id=node_id)


def _execute_openai_compatible_chat_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    system_prompt = _render_runtime_string(runtime, "system_prompt")
    user_prompt = _render_runtime_string(runtime, "user_prompt", required=True)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    response_data, request_config = execute_openai_chat_completion(
        runtime,
        node=runtime.node,
        config=runtime.config,
        messages=messages,
    )
    payload = build_openai_chat_payload(response_data, fallback_model=request_config.model)
    runtime.set_path_value(runtime.context, output_key, payload)
    return _tool_result(
        "openai_compatible_chat",
        output_key=output_key,
        model=payload["model"],
        secret=request_config.secret_meta,
    )


TOOL_DEFINITION = WorkflowToolDefinition(
    name="openai_compatible_chat",
    label="LLM chat (OpenAI-compatible)",
    description="Call an OpenAI-compatible `/chat/completions` endpoint with a model, prompts, and API key.",
    icon="mdi-robot-happy-outline",
    category="AI",
    config={"output_key": "llm.response"},
    fields=(
        tool_text_field("output_key", "Save result as", placeholder="llm.response"),
        tool_text_field("base_url", "API base URL", placeholder="https://api.openai.com/v1"),
        tool_text_field("api_key_name", "API key secret name", placeholder="OPENAI_API_KEY"),
        tool_text_field(
            "api_key_provider",
            "API key provider",
            placeholder="environment-variable",
            help_text="Optional. Leave blank to search all enabled providers in scope.",
        ),
        tool_text_field("model", "Model", placeholder="gpt-4.1-mini"),
        tool_textarea_field(
            "system_prompt",
            "System prompt",
            rows=4,
            placeholder="You are an incident response assistant.",
        ),
        tool_textarea_field(
            "user_prompt",
            "User prompt",
            rows=6,
            placeholder="Summarize incident {{ trigger.payload.incident_id }} and propose next steps.",
        ),
        tool_text_field("temperature", "Temperature", placeholder="0.2"),
        tool_text_field("max_tokens", "Max tokens", placeholder="800"),
        tool_textarea_field(
            "extra_body_json",
            "Extra body JSON",
            rows=5,
            placeholder='{"response_format": {"type": "json_object"}}',
            help_text="Optional provider-specific fields merged into the request body after prompts and model.",
        ),
    ),
    validator=_validate_openai_compatible_chat_tool,
    executor=_execute_openai_compatible_chat_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
