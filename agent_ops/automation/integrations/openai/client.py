from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError

from automation.catalog.connections import (
    get_connection_slot_value,
    resolve_connection_request_auth,
    resolve_workflow_connection_fields,
)
from automation.runtime_types import WorkflowNodeExecutionContext
from automation.tools.base import (
    _coerce_optional_float,
    _coerce_positive_int,
    _extract_openai_compatible_text,
    _http_json_request,
    _make_json_safe,
    _render_runtime_external_url,
    _render_runtime_json,
    _render_runtime_string,
    _resolve_runtime_secret,
    _validate_optional_json_template,
    _validate_optional_secret_group_id,
    _validate_optional_string,
    _validate_required_external_url,
    _validate_required_string,
)


@dataclass(frozen=True)
class OpenAICompatibleRequestConfig:
    auth_headers: dict[str, str]
    base_url: str
    model: str
    temperature: float | None
    max_tokens: int | None
    extra_body: dict[str, Any] | None
    secret_meta: dict[str, str | None]


@dataclass
class _RuntimeConfigView:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    context: dict[str, Any]
    secret_values: list[str]
    render_template: Any
    resolve_scoped_secret: Any


def validate_openai_chat_model_config(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "model", node_id=node_id)
    if config.get("connection_id") in (None, ""):
        _validate_required_external_url(config, "base_url", node_id=node_id)
        _validate_required_string(config, "secret_name", node_id=node_id)
    if config.get("custom_model") not in (None, ""):
        _validate_optional_string(config, "custom_model", node_id=node_id)
    _validate_optional_json_template(config, "extra_body_json", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)
    _coerce_optional_float(config.get("temperature"), field_name="temperature", node_id=node_id)
    if config.get("max_tokens") not in (None, ""):
        _coerce_positive_int(config.get("max_tokens"), field_name="max_tokens", node_id=node_id, default=1)


def _build_runtime_view(
    runtime: WorkflowNodeExecutionContext | Any,
    *,
    node: dict[str, Any],
    config: dict[str, Any],
) -> _RuntimeConfigView:
    return _RuntimeConfigView(
        workflow=runtime.workflow,
        node=node,
        config=config,
        context=runtime.context,
        secret_values=runtime.secret_values,
        render_template=runtime.render_template,
        resolve_scoped_secret=runtime.resolve_scoped_secret,
    )


def resolve_openai_chat_model_config(
    runtime: WorkflowNodeExecutionContext | Any,
    *,
    node: dict[str, Any],
    config: dict[str, Any],
) -> OpenAICompatibleRequestConfig:
    runtime_view = _build_runtime_view(runtime, node=node, config=config)
    connection_id = get_connection_slot_value(runtime_view.config, slot_key="connection_id")
    if connection_id:
        resolved_connection = resolve_workflow_connection_fields(
            runtime_view,
            connection_id=connection_id,
            expected_connection_type="openai.api",
        )
        base_url = str(resolved_connection.values.get("base_url") or "https://api.openai.com/v1").strip().rstrip("/")
        auth_headers = resolve_connection_request_auth(runtime_view, resolved_connection=resolved_connection).headers
        auth_mode = resolved_connection.values.get("auth_mode") or "api_key"
        secret_meta = resolved_connection.secret_metas.get("api_key")
        if auth_mode == "oauth2_authorization_code":
            connection_state = getattr(resolved_connection.connection, "state", None)
            if connection_state is not None and connection_state.state_values.get("account_id") not in (None, ""):
                secret_meta = {
                    "name": "oauth_account",
                    "provider": "oauth2",
                    "secret_group": resolved_connection.connection.secret_group.name
                    if resolved_connection.connection.secret_group_id
                    else None,
                }
        if not isinstance(auth_headers.get("Authorization"), str) or not auth_headers["Authorization"]:
            raise ValidationError(
                {
                    "definition": (
                        f'Connection "{resolved_connection.connection.name}" must provide an Authorization header '
                        "for OpenAI requests."
                    )
                }
            )
    else:
        base_url = (
            _render_runtime_external_url(runtime_view, "base_url", required=True, default_mode="static") or ""
        ).rstrip("/")
        secret_name = _render_runtime_string(runtime_view, "secret_name", default_mode="static")
        if not secret_name:
            raise ValidationError({"definition": f'Node "{node["id"]}" must define config.secret_name.'})
        api_key, secret_meta = _resolve_runtime_secret(
            runtime_view,
            secret_name=secret_name,
            secret_group_id=runtime_view.config.get("secret_group_id"),
        )
        auth_headers = {"Authorization": f"Bearer {api_key}"}
    custom_model = _render_runtime_string(runtime_view, "custom_model", default_mode="static")
    model = custom_model or _render_runtime_string(runtime_view, "model", required=True, default_mode="static")
    temperature = _coerce_optional_float(
        runtime_view.config.get("temperature"),
        field_name="temperature",
        node_id=node["id"],
    )

    max_tokens = None
    if runtime_view.config.get("max_tokens") not in (None, ""):
        max_tokens = _coerce_positive_int(
            runtime_view.config.get("max_tokens"),
            field_name="max_tokens",
            node_id=node["id"],
            default=1,
        )

    extra_body = _render_runtime_json(runtime_view, "extra_body_json", default_mode="static")
    if extra_body is not None and not isinstance(extra_body, dict):
        raise ValidationError(
            {"definition": f'Node "{node["id"]}" config.extra_body_json must render a JSON object.'}
        )

    return OpenAICompatibleRequestConfig(
        auth_headers=auth_headers,
        base_url=base_url,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=extra_body,
        secret_meta=secret_meta,
    )


def execute_openai_chat_completion(
    runtime: WorkflowNodeExecutionContext | Any,
    *,
    node: dict[str, Any],
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], OpenAICompatibleRequestConfig]:
    resolved_config = resolve_openai_chat_model_config(
        runtime,
        node=node,
        config=config,
    )

    body: dict[str, Any] = {
        "model": resolved_config.model,
        "messages": messages,
    }
    if resolved_config.temperature is not None:
        body["temperature"] = resolved_config.temperature
    if resolved_config.max_tokens is not None:
        body["max_tokens"] = resolved_config.max_tokens
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if resolved_config.extra_body is not None:
        body.update(resolved_config.extra_body)

    response_data, _ = _http_json_request(
        method="POST",
        url=f"{resolved_config.base_url}/chat/completions",
        headers={
            "Accept": "application/json",
            **resolved_config.auth_headers,
        },
        json_body=body,
    )
    if not isinstance(response_data, dict):
        raise ValidationError(
            {"definition": "OpenAI-compatible API returned an unexpected non-JSON response."}
        )

    return response_data, resolved_config


def extract_openai_first_message(response_data: dict[str, Any]) -> dict[str, Any]:
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return {}

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return {}
    return message


def extract_openai_tool_calls(response_data: dict[str, Any]) -> list[dict[str, Any]]:
    message = extract_openai_first_message(response_data)
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [tool_call for tool_call in tool_calls if isinstance(tool_call, dict)]


def build_openai_chat_payload(response_data: dict[str, Any], *, fallback_model: str) -> dict[str, Any]:
    finish_reason = None
    choices = response_data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = choices[0].get("finish_reason")

    return {
        "text": _extract_openai_compatible_text(response_data),
        "model": response_data.get("model", fallback_model),
        "usage": _make_json_safe(response_data.get("usage")),
        "finish_reason": _make_json_safe(finish_reason),
        "raw": _make_json_safe(response_data),
    }


__all__ = (
    "OpenAICompatibleRequestConfig",
    "build_openai_chat_payload",
    "execute_openai_chat_completion",
    "extract_openai_first_message",
    "extract_openai_tool_calls",
    "resolve_openai_chat_model_config",
    "validate_openai_chat_model_config",
)
