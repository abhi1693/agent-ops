from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _coerce_optional_float,
    _coerce_positive_int,
    _extract_openai_compatible_text,
    _http_json_request,
    _make_json_safe,
    _render_runtime_external_url,
    _render_runtime_json,
    _render_runtime_string,
    _resolve_runtime_secret,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_json_template,
    _validate_optional_string,
    _validate_required_external_url,
    _validate_required_string,
    tool_text_field,
    tool_textarea_field,
)


def _validate_openai_compatible_chat_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_external_url(config, "base_url", node_id=node_id)
    _validate_required_string(config, "api_key_name", node_id=node_id)
    _validate_optional_string(config, "api_key_provider", node_id=node_id)
    _validate_required_string(config, "model", node_id=node_id)
    _validate_required_string(config, "user_prompt", node_id=node_id)
    _validate_optional_string(config, "system_prompt", node_id=node_id)
    _validate_optional_json_template(config, "extra_body_json", node_id=node_id)
    _coerce_optional_float(config.get("temperature"), field_name="temperature", node_id=node_id)
    if config.get("max_tokens") not in (None, ""):
        _coerce_positive_int(config.get("max_tokens"), field_name="max_tokens", node_id=node_id, default=1)


def _execute_openai_compatible_chat_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    base_url = (_render_runtime_external_url(runtime, "base_url", required=True) or "").rstrip("/")
    api_key, secret_meta = _resolve_runtime_secret(
        runtime,
        name_key="api_key_name",
        provider_key="api_key_provider",
    )
    model = _render_runtime_string(runtime, "model", required=True)
    system_prompt = _render_runtime_string(runtime, "system_prompt")
    user_prompt = _render_runtime_string(runtime, "user_prompt", required=True)
    temperature = _coerce_optional_float(
        runtime.config.get("temperature"),
        field_name="temperature",
        node_id=runtime.node["id"],
    )
    max_tokens = None
    if runtime.config.get("max_tokens") not in (None, ""):
        max_tokens = _coerce_positive_int(
            runtime.config.get("max_tokens"),
            field_name="max_tokens",
            node_id=runtime.node["id"],
            default=1,
        )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    body = {"model": model, "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    extra_body = _render_runtime_json(runtime, "extra_body_json")
    if extra_body is not None:
        if not isinstance(extra_body, dict):
            raise ValidationError(
                {"definition": f'Node "{runtime.node["id"]}" config.extra_body_json must render a JSON object.'}
            )
        body.update(extra_body)

    response_data, _ = _http_json_request(
        method="POST",
        url=f"{base_url}/chat/completions",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json_body=body,
    )
    if not isinstance(response_data, dict):
        raise ValidationError(
            {"definition": "OpenAI-compatible API returned an unexpected non-JSON response."}
        )

    finish_reason = None
    choices = response_data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = choices[0].get("finish_reason")

    payload = {
        "text": _extract_openai_compatible_text(response_data),
        "model": response_data.get("model", model),
        "usage": _make_json_safe(response_data.get("usage")),
        "finish_reason": _make_json_safe(finish_reason),
        "raw": _make_json_safe(response_data),
    }
    runtime.set_path_value(runtime.context, output_key, payload)
    return _tool_result(
        "openai_compatible_chat",
        output_key=output_key,
        model=payload["model"],
        secret=secret_meta,
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
