from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError

from automation.nodes.adapters import tool_definition_as_node_implementation
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _coerce_positive_int,
    _make_json_safe,
    _render_runtime_external_url,
    _render_runtime_json,
    _render_runtime_string,
    _resolve_runtime_secret,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_json_template,
    _validate_optional_secret_group_id,
    _validate_optional_string,
    _validate_required_external_url,
    _validate_required_string,
    tool_text_field,
    tool_textarea_field,
)


_DEFAULT_PROTOCOL_VERSION = "2025-11-25"
_DEFAULT_TIMEOUT_SECONDS = 30
_REQUEST_ACCEPT_HEADER = "application/json, text/event-stream"
_MANAGED_HEADER_NAMES = frozenset(
    {
        "accept",
        "content-type",
        "mcp-protocol-version",
        "mcp-session-id",
    }
)
_SECRET_HEADER_NAMES = frozenset(
    {
        "api-key",
        "authorization",
        "cookie",
        "proxy-authorization",
        "set-cookie",
        "x-access-token",
        "x-api-key",
        "x-auth-token",
    }
)
_CLIENT_INFO = {
    "name": "agent-ops-workflow",
    "title": "Agent Ops Workflow Runtime",
    "version": "1.0.0",
}


def _validate_mcp_server_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_external_url(config, "server_url", node_id=node_id)
    _validate_required_string(config, "remote_tool_name", node_id=node_id)
    _validate_optional_json_template(config, "arguments_json", node_id=node_id)
    _validate_optional_json_template(config, "headers_json", node_id=node_id)
    if config.get("secret_name") not in (None, ""):
        _validate_optional_string(config, "secret_name", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)

    auth_header_template = config.get("auth_header_template")
    if auth_header_template is not None and not isinstance(auth_header_template, str):
        raise ValidationError(
            {"definition": f'Node "{node_id}" config.auth_header_template must be a string.'}
        )

    for key in ("auth_header_name", "protocol_version"):
        value = config.get(key)
        if value is not None and not isinstance(value, str):
            raise ValidationError({"definition": f'Node "{node_id}" config.{key} must be a string.'})

    auth_header_name = config.get("auth_header_name")
    if isinstance(auth_header_name, str) and auth_header_name.strip():
        normalized_header_name = auth_header_name.strip().lower()
        if normalized_header_name in _MANAGED_HEADER_NAMES:
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" config.auth_header_name cannot be "{auth_header_name}". '
                        "That header is managed by the MCP runtime."
                    )
                }
            )

    headers_json = config.get("headers_json")
    if isinstance(headers_json, dict):
        _validate_manual_header_names(headers_json.keys(), node_id=node_id)
    elif isinstance(headers_json, str) and "{{" not in headers_json and "{%" not in headers_json:
        try:
            parsed_headers = json.loads(headers_json)
        except json.JSONDecodeError:
            parsed_headers = None
        if isinstance(parsed_headers, dict):
            _validate_manual_header_names(parsed_headers.keys(), node_id=node_id)

    _coerce_positive_int(
        config.get("timeout_seconds"),
        field_name="timeout_seconds",
        node_id=node_id,
        default=_DEFAULT_TIMEOUT_SECONDS,
        maximum=300,
    )


def _headers_get(headers: dict[str, str], name: str) -> str | None:
    expected_name = name.lower()
    for header_name, header_value in headers.items():
        if header_name.lower() == expected_name:
            return header_value
    return None


def _normalize_header_name(header_name: str) -> str:
    return header_name.strip().lower()


def _validate_manual_header_names(header_names, *, node_id: str) -> None:
    for raw_header_name in header_names:
        header_name = str(raw_header_name).strip()
        normalized_header_name = _normalize_header_name(header_name)
        if normalized_header_name in _MANAGED_HEADER_NAMES:
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" config.headers_json cannot define "{header_name}". '
                        "That header is managed by the MCP runtime."
                    )
                }
            )
        if normalized_header_name in _SECRET_HEADER_NAMES:
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" config.headers_json cannot define secret-bearing header "{header_name}". '
                        "Secrets must come from stored Secret objects."
                    )
                }
            )


def _extract_http_error_detail(raw_body: str) -> str:
    body = raw_body.strip()
    if not body:
        return ""

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f" {body[:400]}"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "Unknown JSON-RPC error")
            data = error.get("data")
            if data not in (None, ""):
                return f" {message}: {_make_json_safe(data)}"
            return f" {message}"

    return f" {str(_make_json_safe(payload))[:400]}"


def _send_mcp_http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: int,
    json_body: dict | None = None,
) -> tuple[str, int, dict[str, str], str]:
    request_headers = dict(headers)
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(url, data=data, headers=request_headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            raw_body = response.read().decode("utf-8", errors="replace")
            response_headers = {key: value for key, value in response.headers.items()}
            content_type = response.headers.get("Content-Type", "")
            return raw_body, status_code, response_headers, content_type
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        detail = _extract_http_error_detail(error_body)
        raise ValidationError(
            {"definition": f"MCP HTTP {method.upper()} {url} failed with {exc.code}.{detail}"}
        ) from exc
    except URLError as exc:
        raise ValidationError(
            {"definition": f"MCP HTTP {method.upper()} {url} failed: {exc.reason}"}
        ) from exc


def _parse_sse_jsonrpc_messages(raw_body: str) -> list[dict]:
    messages: list[dict] = []
    current_data_lines: list[str] = []

    for line in raw_body.splitlines():
        if not line:
            if current_data_lines:
                payload = "\n".join(current_data_lines).strip()
                current_data_lines = []
                if not payload:
                    continue
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    messages.append(parsed)
            continue

        if line.startswith(":"):
            continue

        field_name, separator, field_value = line.partition(":")
        if not separator:
            continue
        if field_value.startswith(" "):
            field_value = field_value[1:]
        if field_name == "data":
            current_data_lines.append(field_value)

    if current_data_lines:
        payload = "\n".join(current_data_lines).strip()
        if payload:
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                messages.append(parsed)

    return messages


def _extract_jsonrpc_response_message(
    *,
    raw_body: str,
    content_type: str,
    request_id: int,
) -> dict:
    parsed_messages: list[dict] = []
    if "text/event-stream" in content_type.lower():
        parsed_messages = _parse_sse_jsonrpc_messages(raw_body)
    else:
        try:
            parsed_payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValidationError({"definition": "MCP server returned invalid JSON."}) from exc
        if isinstance(parsed_payload, list):
            parsed_messages = [message for message in parsed_payload if isinstance(message, dict)]
        elif isinstance(parsed_payload, dict):
            parsed_messages = [parsed_payload]

    for message in parsed_messages:
        if message.get("id") == request_id:
            return message

    raise ValidationError(
        {"definition": f"MCP server response did not include a JSON-RPC response for request id {request_id}."}
    )


def _extract_jsonrpc_result(message: dict, *, request_id: int) -> dict:
    error = message.get("error")
    if isinstance(error, dict):
        message_text = str(error.get("message") or "Unknown JSON-RPC error")
        error_data = error.get("data")
        if error_data not in (None, ""):
            message_text = f"{message_text}: {_make_json_safe(error_data)}"
        raise ValidationError({"definition": f"MCP request {request_id} failed: {message_text}"})

    result = message.get("result")
    if not isinstance(result, dict):
        raise ValidationError(
            {"definition": f"MCP request {request_id} returned an unexpected non-object result."}
        )
    return result


def _post_jsonrpc_request(
    *,
    url: str,
    headers: dict[str, str],
    timeout: int,
    request_id: int,
    method: str,
    params: dict | None = None,
) -> tuple[dict, dict[str, str]]:
    raw_body, _, response_headers, content_type = _send_mcp_http_request(
        method="POST",
        url=url,
        headers=headers,
        timeout=timeout,
        json_body={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        },
    )
    message = _extract_jsonrpc_response_message(
        raw_body=raw_body,
        content_type=content_type,
        request_id=request_id,
    )
    return _extract_jsonrpc_result(message, request_id=request_id), response_headers


def _post_notification(
    *,
    url: str,
    headers: dict[str, str],
    timeout: int,
    method: str,
    params: dict | None = None,
) -> None:
    _send_mcp_http_request(
        method="POST",
        url=url,
        headers=headers,
        timeout=timeout,
        json_body={
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        },
    )


def _delete_session(
    *,
    url: str,
    headers: dict[str, str],
    timeout: int,
) -> None:
    try:
        _send_mcp_http_request(
            method="DELETE",
            url=url,
            headers=headers,
            timeout=timeout,
        )
    except ValidationError:
        return


def _render_headers_json(runtime: WorkflowToolExecutionContext) -> dict[str, str]:
    rendered_headers = _render_runtime_json(runtime, "headers_json")
    if rendered_headers is None:
        return {}
    if not isinstance(rendered_headers, dict):
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.headers_json must render a JSON object.'}
        )

    _validate_manual_header_names(rendered_headers.keys(), node_id=runtime.node["id"])

    headers: dict[str, str] = {}
    for raw_key, raw_value in rendered_headers.items():
        header_name = str(raw_key).strip()
        if not header_name:
            raise ValidationError(
                {"definition": f'Node "{runtime.node["id"]}" config.headers_json cannot contain an empty header name.'}
            )
        if raw_value is None:
            continue
        if isinstance(raw_value, (dict, list)):
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{runtime.node["id"]}" config.headers_json values must be strings or scalars.'
                    )
                }
            )
        headers[header_name] = str(raw_value)
    return headers


def _render_auth_header_value(runtime: WorkflowToolExecutionContext, *, token: str) -> str:
    raw_template = runtime.config.get("auth_header_template")
    if raw_template is None:
        return f"Bearer {token}"

    rendered_template = runtime.render_template(str(raw_template), runtime.context).strip()
    if not rendered_template:
        return token
    if "{token}" not in rendered_template:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{runtime.node["id"]}" config.auth_header_template must include "{{token}}" '
                    "or render empty to send the raw token."
                )
            }
        )
    return rendered_template.replace("{token}", token).strip()


def _extract_text_content(content_blocks: list | None) -> str | None:
    if not isinstance(content_blocks, list):
        return None

    parts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text_value = block.get("text")
        if isinstance(text_value, str) and text_value.strip():
            parts.append(text_value.strip())

    if not parts:
        return None
    return "\n\n".join(parts)


def _build_runtime_view(runtime, *, node: dict, config: dict):
    return SimpleNamespace(
        workflow=runtime.workflow,
        node=node,
        config=config,
        context=runtime.context,
        secret_values=runtime.secret_values,
        render_template=runtime.render_template,
        resolve_scoped_secret=runtime.resolve_scoped_secret,
    )


def _resolve_mcp_runtime_config(
    runtime,
    *,
    node: dict,
    config: dict,
    arguments: dict | None = None,
) -> tuple[dict, dict | None, dict | None]:
    runtime_view = _build_runtime_view(runtime, node=node, config=config)
    server_url = _render_runtime_external_url(runtime_view, "server_url", required=True)
    remote_tool_name = _render_runtime_string(runtime_view, "remote_tool_name", required=True)
    protocol_version = _render_runtime_string(runtime_view, "protocol_version") or _DEFAULT_PROTOCOL_VERSION
    timeout_seconds = _coerce_positive_int(
        runtime_view.config.get("timeout_seconds"),
        field_name="timeout_seconds",
        node_id=node["id"],
        default=_DEFAULT_TIMEOUT_SECONDS,
        maximum=300,
    )

    resolved_arguments = arguments
    if resolved_arguments is None:
        resolved_arguments = _render_runtime_json(runtime_view, "arguments_json")
        if resolved_arguments is None:
            resolved_arguments = {}
        if not isinstance(resolved_arguments, dict):
            raise ValidationError(
                {"definition": f'Node "{node["id"]}" config.arguments_json must render a JSON object.'}
            )
    elif not isinstance(resolved_arguments, dict):
        raise ValidationError(
            {"definition": f'Node "{node["id"]}" tool call arguments must be a JSON object.'}
        )

    base_headers = _render_headers_json(runtime_view)
    base_headers["Accept"] = _REQUEST_ACCEPT_HEADER

    secret_meta = None
    secret_name = _render_runtime_string(runtime_view, "secret_name")
    auth_token = None
    if secret_name:
        auth_token, secret_meta = _resolve_runtime_secret(
            runtime_view,
            secret_name=secret_name,
            secret_group_id=runtime_view.config.get("secret_group_id"),
            required=False,
        )
    if auth_token:
        auth_header_name = _render_runtime_string(runtime_view, "auth_header_name") or "Authorization"
        base_headers[auth_header_name] = _render_auth_header_value(runtime_view, token=auth_token)

    return {
        "server_url": server_url,
        "remote_tool_name": remote_tool_name,
        "protocol_version": protocol_version,
        "timeout_seconds": timeout_seconds,
        "arguments": resolved_arguments,
        "base_headers": base_headers,
    }, secret_meta, runtime_view


def _initialize_mcp_session(
    *,
    server_url: str,
    base_headers: dict[str, str],
    timeout_seconds: int,
    protocol_version: str,
) -> tuple[dict[str, str], str | None, str]:
    initialize_result, initialize_headers = _post_jsonrpc_request(
        url=server_url,
        headers=base_headers,
        timeout=timeout_seconds,
        request_id=1,
        method="initialize",
        params={
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        },
    )

    negotiated_protocol_version = initialize_result.get("protocolVersion")
    if not isinstance(negotiated_protocol_version, str) or not negotiated_protocol_version.strip():
        raise ValidationError({"definition": "MCP initialize response did not include a valid protocolVersion."})

    session_headers = dict(base_headers)
    session_headers["MCP-Protocol-Version"] = negotiated_protocol_version
    session_id = _headers_get(initialize_headers, "MCP-Session-Id")
    if session_id:
        session_headers["MCP-Session-Id"] = session_id

    _post_notification(
        url=server_url,
        headers=session_headers,
        timeout=timeout_seconds,
        method="notifications/initialized",
    )

    return session_headers, session_id, negotiated_protocol_version


def _default_tool_descriptor(*, remote_tool_name: str, server_url: str) -> dict:
    return {
        "name": remote_tool_name,
        "description": f'Call MCP tool "{remote_tool_name}" via {server_url}.',
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        },
    }


def build_mcp_server_tool_descriptor(
    runtime,
    *,
    node: dict,
    config: dict,
) -> dict:
    resolved_config, _, _ = _resolve_mcp_runtime_config(
        runtime,
        node=node,
        config=config,
    )
    descriptor = _default_tool_descriptor(
        remote_tool_name=resolved_config["remote_tool_name"],
        server_url=resolved_config["server_url"],
    )

    session_headers = None
    session_id = None
    try:
        session_headers, session_id, negotiated_protocol_version = _initialize_mcp_session(
            server_url=resolved_config["server_url"],
            base_headers=resolved_config["base_headers"],
            timeout_seconds=resolved_config["timeout_seconds"],
            protocol_version=resolved_config["protocol_version"],
        )
        tools_result, _ = _post_jsonrpc_request(
            url=resolved_config["server_url"],
            headers=session_headers,
            timeout=resolved_config["timeout_seconds"],
            request_id=2,
            method="tools/list",
        )
        tools = tools_result.get("tools")
        if not isinstance(tools, list):
            return {
                **descriptor,
                "protocol_version": negotiated_protocol_version,
            }

        matched_tool = next(
            (
                tool
                for tool in tools
                if isinstance(tool, dict)
                and tool.get("name") == resolved_config["remote_tool_name"]
            ),
            None,
        )
        if not isinstance(matched_tool, dict):
            return {
                **descriptor,
                "protocol_version": negotiated_protocol_version,
            }

        input_schema = matched_tool.get("inputSchema", matched_tool.get("input_schema"))
        if not isinstance(input_schema, dict):
            input_schema = descriptor["input_schema"]

        return {
            "name": matched_tool.get("name") or descriptor["name"],
            "description": matched_tool.get("description") or descriptor["description"],
            "input_schema": _make_json_safe(input_schema),
            "protocol_version": negotiated_protocol_version,
        }
    except ValidationError:
        return descriptor
    finally:
        if session_id and session_headers is not None:
            _delete_session(
                url=resolved_config["server_url"],
                headers=session_headers,
                timeout=resolved_config["timeout_seconds"],
            )


def call_mcp_server_tool(
    runtime,
    *,
    node: dict,
    config: dict,
    arguments: dict | None = None,
) -> tuple[dict, dict | None]:
    resolved_config, secret_meta, _ = _resolve_mcp_runtime_config(
        runtime,
        node=node,
        config=config,
        arguments=arguments,
    )

    session_headers = None
    session_id = None
    negotiated_protocol_version = resolved_config["protocol_version"]
    try:
        session_headers, session_id, negotiated_protocol_version = _initialize_mcp_session(
            server_url=resolved_config["server_url"],
            base_headers=resolved_config["base_headers"],
            timeout_seconds=resolved_config["timeout_seconds"],
            protocol_version=resolved_config["protocol_version"],
        )

        call_result, _ = _post_jsonrpc_request(
            url=resolved_config["server_url"],
            headers=session_headers,
            timeout=resolved_config["timeout_seconds"],
            request_id=2,
            method="tools/call",
            params={
                "name": resolved_config["remote_tool_name"],
                "arguments": resolved_config["arguments"],
            },
        )
    finally:
        if session_id:
            _delete_session(
                url=resolved_config["server_url"],
                headers=session_headers,
                timeout=resolved_config["timeout_seconds"],
            )

    content_blocks = call_result.get("content")
    if content_blocks is None:
        content_blocks = []
    if not isinstance(content_blocks, list):
        raise ValidationError({"definition": "MCP tools/call response content must be an array."})

    structured_content = call_result.get("structuredContent")
    payload = {
        "server_url": resolved_config["server_url"],
        "tool": resolved_config["remote_tool_name"],
        "protocol_version": negotiated_protocol_version,
        "content": _make_json_safe(content_blocks),
        "structured_content": _make_json_safe(structured_content),
        "text": _extract_text_content(content_blocks),
        "is_error": bool(call_result.get("isError")),
        "raw": _make_json_safe(call_result),
    }

    return payload, secret_meta


def _execute_mcp_server_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    payload, secret_meta = call_mcp_server_tool(
        runtime,
        node=runtime.node,
        config=runtime.config,
    )
    runtime.set_path_value(runtime.context, output_key, payload)

    result = {
        "output_key": output_key,
        "remote_tool_name": payload["tool"],
        "protocol_version": payload["protocol_version"],
        "content_count": len(payload["content"]),
        "is_error": payload["is_error"],
    }
    if secret_meta is not None:
        result["secret"] = secret_meta
    return _tool_result("mcp_server", **result)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="mcp_server",
    label="MCP server",
    description="Call a remote MCP server tool over Streamable HTTP using initialize, initialized, and tools/call.",
    icon="mdi-connection",
    category="Integrations",
    config={
        "output_key": "mcp.result",
        "protocol_version": _DEFAULT_PROTOCOL_VERSION,
        "arguments_json": {},
        "timeout_seconds": _DEFAULT_TIMEOUT_SECONDS,
        "auth_header_name": "Authorization",
        "auth_header_template": "Bearer {token}",
    },
    fields=(
        tool_text_field("output_key", "Save result as", placeholder="mcp.result"),
        tool_text_field(
            "server_url",
            "MCP endpoint URL",
            placeholder="https://mcp.example.com/mcp",
        ),
        tool_text_field(
            "remote_tool_name",
            "Server tool name",
            placeholder="weather_current",
        ),
        tool_textarea_field(
            "arguments_json",
            "Tool arguments JSON",
            rows=8,
            placeholder='{"location": "San Francisco", "units": "imperial"}',
            help_text="Optional. Rendered JSON object passed as the MCP tool arguments.",
        ),
        tool_text_field(
            "auth_header_name",
            "Auth header name",
            placeholder="Authorization",
            help_text="Optional. Defaults to `Authorization` when a stored Secret object is configured for auth.",
        ),
        tool_text_field(
            "secret_name",
            "Secret name",
            placeholder="MCP_API_TOKEN",
            help_text="Optional. Resolve this secret and inject it into the auth header for each MCP request.",
        ),
        tool_text_field(
            "secret_group_id",
            "Secret group",
            placeholder="Use workflow secret group",
            help_text="Optional. Override the workflow secret group for this node with a scoped secret group ID.",
        ),
        tool_text_field(
            "auth_header_template",
            "Auth header template",
            placeholder="Bearer {token}",
            help_text="Optional. Use `{token}` where the resolved secret should be inserted. Leave blank to send the raw token.",
        ),
        tool_textarea_field(
            "headers_json",
            "Extra headers JSON",
            rows=5,
            placeholder='{"X-Tenant": "ops"}',
            help_text="Optional non-secret headers merged into every request. Auth and session headers are managed separately from stored Secret objects.",
        ),
        tool_text_field(
            "protocol_version",
            "Protocol version",
            placeholder=_DEFAULT_PROTOCOL_VERSION,
        ),
        tool_text_field(
            "timeout_seconds",
            "Timeout seconds",
            placeholder=str(_DEFAULT_TIMEOUT_SECONDS),
        ),
    ),
    validator=_validate_mcp_server_tool,
    executor=_execute_mcp_server_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
