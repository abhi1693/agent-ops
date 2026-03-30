from __future__ import annotations

import json
from datetime import timedelta, timezone as datetime_timezone
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError
from django.utils import timezone


WorkflowToolValidator = Callable[[dict[str, Any], str], None]
WorkflowToolExecutor = Callable[["WorkflowToolExecutionContext"], dict[str, Any]]


@dataclass(frozen=True)
class WorkflowToolDefinition:
    name: str
    label: str
    description: str
    icon: str = "mdi-tools"
    category: str = "Built-in"
    config: dict[str, Any] = field(default_factory=dict)
    fields: tuple[dict[str, Any], ...] = ()
    validator: WorkflowToolValidator | None = None
    executor: WorkflowToolExecutor | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "config": dict(self.config),
            "fields": [dict(field) for field in self.fields],
        }


@dataclass
class WorkflowToolExecutionContext:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    context: dict[str, Any]
    secret_paths: set[str]
    secret_values: list[str]
    render_template: Callable[[str, dict[str, Any]], str]
    set_path_value: Callable[[dict[str, Any], str, Any], None]
    resolve_scoped_secret: Callable[..., Any]


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _validate_optional_string(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" config.{key} must be a non-empty string.')


def _validate_required_string(config: dict[str, Any], key: str, *, node_id: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" must define config.{key}.')
    return value


def _validate_optional_json_template(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if isinstance(value, (dict, list)):
        return
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(
            f'Node "{node_id}" config.{key} must be a non-empty JSON string or object.'
        )


def _validate_required_json_template(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value in (None, ""):
        _raise_definition_error(f'Node "{node_id}" must define config.{key}.')
    _validate_optional_json_template(config, key, node_id=node_id)


def _tool_result(tool_name: str, **extra: Any) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "operation": tool_name,
        **extra,
    }


def normalize_workflow_tool_config(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(config or {})
    tool_name = normalized.get("tool_name")
    legacy_operation = normalized.get("operation")

    if tool_name in ("", None) and isinstance(legacy_operation, str) and legacy_operation.strip():
        normalized["tool_name"] = legacy_operation.strip()
    elif tool_name in ("", None):
        normalized["tool_name"] = "passthrough"

    return normalized


def normalize_workflow_definition_tools(definition: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {"nodes": [], "edges": []}

    normalized_definition = dict(definition)
    normalized_nodes = []
    for node in definition.get("nodes", []):
        if not isinstance(node, dict):
            normalized_nodes.append(node)
            continue

        normalized_node = dict(node)
        if normalized_node.get("kind") == "tool":
            normalized_node["config"] = normalize_workflow_tool_config(normalized_node.get("config"))
        normalized_nodes.append(normalized_node)

    normalized_definition["nodes"] = normalized_nodes
    return normalized_definition


def _validate_passthrough_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_optional_string(config, "tool_name", node_id=node_id)


def _execute_passthrough_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    return _tool_result("passthrough")


def _validate_set_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)


def _execute_set_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    value = runtime.config.get("value")
    runtime.set_path_value(runtime.context, output_key, value)
    return _tool_result("set", output_key=output_key, value=value)


def _validate_template_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    _validate_required_string(config, "template", node_id=node_id)


def _execute_template_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    template = runtime.config.get("template") or runtime.node.get("label") or runtime.node["id"]
    rendered = runtime.render_template(str(template), runtime.context)
    runtime.set_path_value(runtime.context, output_key, rendered)
    return _tool_result("template", output_key=output_key, value=rendered)


def _validate_secret_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    _validate_required_string(config, "name", node_id=node_id)
    provider = config.get("provider")
    if provider is not None and (not isinstance(provider, str) or not provider.strip()):
        _raise_definition_error(f'Node "{node_id}" config.provider must be a non-empty string.')


def _execute_secret_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = runtime.config.get("output_key") or runtime.node["id"]
    secret = runtime.resolve_scoped_secret(
        runtime.workflow,
        name=runtime.config["name"],
        provider=runtime.config.get("provider"),
    )
    value = secret.get_value(obj=runtime.workflow)
    runtime.set_path_value(runtime.context, output_key, value)
    runtime.secret_paths.add(output_key)
    if isinstance(value, str):
        runtime.secret_values.append(value)
    return _tool_result(
        "secret",
        output_key=output_key,
        secret={
            "name": secret.name,
            "provider": secret.provider,
        },
    )


def _coerce_positive_int(
    value: Any,
    *,
    field_name: str,
    node_id: str,
    default: int,
    maximum: int | None = None,
) -> int:
    if value in (None, ""):
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            _raise_definition_error(f'Node "{node_id}" config.{field_name} must be an integer.')
            raise AssertionError("unreachable") from exc

    if parsed < 1:
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must be greater than zero.')
    if maximum is not None and parsed > maximum:
        _raise_definition_error(
            f'Node "{node_id}" config.{field_name} must be less than or equal to {maximum}.'
        )
    return parsed


def _coerce_optional_float(
    value: Any,
    *,
    field_name: str,
    node_id: str,
) -> float | None:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must be a number.')
        raise AssertionError("unreachable") from exc


def _coerce_csv_strings(value: Any, *, field_name: str, node_id: str, default: list[str]) -> list[str]:
    if value in (None, ""):
        return list(default)

    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        if items:
            return items
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must contain at least one value.')

    if isinstance(value, list):
        items = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                _raise_definition_error(
                    f'Node "{node_id}" config.{field_name} must contain non-empty strings.'
                )
            items.append(item.strip())
        return items

    _raise_definition_error(
        f'Node "{node_id}" config.{field_name} must be a comma-separated string or a list of strings.'
    )


def _render_runtime_string(
    runtime: WorkflowToolExecutionContext,
    key: str,
    *,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    value = runtime.config.get(key, default)
    if value in (None, ""):
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.{key}.'})
        return None

    rendered = runtime.render_template(str(value), runtime.context).strip()
    if not rendered:
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" config.{key} rendered empty.'})
        return None
    return rendered


def _render_runtime_json(
    runtime: WorkflowToolExecutionContext,
    key: str,
    *,
    required: bool = False,
) -> Any:
    value = runtime.config.get(key)
    if value in (None, ""):
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.{key}.'})
        return None

    if isinstance(value, (dict, list)):
        raw_template = json.dumps(value)
    else:
        raw_template = str(value)

    rendered = runtime.render_template(raw_template, runtime.context).strip()
    if not rendered:
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" config.{key} rendered empty.'})
        return None

    try:
        return json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.{key} must render valid JSON.'}
        ) from exc


def _resolve_runtime_secret(
    runtime: WorkflowToolExecutionContext,
    *,
    name_key: str,
    provider_key: str,
) -> tuple[str, dict[str, str | None]]:
    secret_name = _render_runtime_string(runtime, name_key, required=True)
    secret_provider = _render_runtime_string(runtime, provider_key)
    secret = runtime.resolve_scoped_secret(
        runtime.workflow,
        name=secret_name,
        provider=secret_provider,
    )
    value = secret.get_value(obj=runtime.workflow)
    if not isinstance(value, str) or not value:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" secret "{secret.name}" must resolve to a non-empty string.'}
        )
    runtime.secret_values.append(value)
    return value, {"name": secret.name, "provider": secret.provider}


def _make_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(item) for item in value]
    return str(value)


def _isoformat_utc(value) -> str:
    return value.astimezone(datetime_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_openai_compatible_text(response_data: dict[str, Any]) -> str | None:
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue

        text_value = item.get("text")
        if isinstance(text_value, str):
            parts.append(text_value)
            continue

        if isinstance(text_value, dict):
            nested_value = text_value.get("value")
            if isinstance(nested_value, str):
                parts.append(nested_value)
                continue

    joined = "".join(parts).strip()
    return joined or None


def _http_json_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> tuple[Any, int]:
    final_url = url
    if query:
        encoded_query = urlencode(query, doseq=True)
        separator = "&" if "?" in final_url else "?"
        final_url = f"{final_url}{separator}{encoded_query}"

    request_headers = dict(headers or {})
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(final_url, data=data, headers=request_headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            raw_body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        snippet = f" {error_body[:400]}" if error_body else ""
        raise ValidationError(
            {"definition": f"HTTP {method.upper()} {final_url} failed with {exc.code}.{snippet}"}
        ) from exc
    except URLError as exc:
        raise ValidationError(
            {"definition": f"HTTP {method.upper()} {final_url} failed: {exc.reason}"}
        ) from exc

    if not raw_body:
        return None, status_code

    decoded_body = raw_body.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        return json.loads(decoded_body), status_code

    try:
        return json.loads(decoded_body), status_code
    except json.JSONDecodeError:
        return decoded_body, status_code


def _validate_external_output_key(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)


def _validate_pagerduty_list_incidents_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "api_key_name", node_id=node_id)
    _validate_optional_string(config, "api_key_provider", node_id=node_id)
    _coerce_csv_strings(config.get("statuses"), field_name="statuses", node_id=node_id, default=["triggered", "acknowledged"])
    _coerce_positive_int(config.get("limit"), field_name="limit", node_id=node_id, default=20, maximum=100)
    _validate_optional_string(config, "incident_key", node_id=node_id)
    _validate_optional_string(config, "base_url", node_id=node_id)


def _execute_pagerduty_list_incidents_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    api_key, secret_meta = _resolve_runtime_secret(
        runtime,
        name_key="api_key_name",
        provider_key="api_key_provider",
    )
    statuses = _coerce_csv_strings(
        runtime.config.get("statuses"),
        field_name="statuses",
        node_id=runtime.node["id"],
        default=["triggered", "acknowledged"],
    )
    limit = _coerce_positive_int(
        runtime.config.get("limit"),
        field_name="limit",
        node_id=runtime.node["id"],
        default=20,
        maximum=100,
    )
    incident_key = _render_runtime_string(runtime, "incident_key")
    base_url = (_render_runtime_string(runtime, "base_url") or "https://api.pagerduty.com").rstrip("/")
    query = {"statuses[]": statuses, "limit": limit}
    if incident_key:
        query["incident_key"] = incident_key

    response_data, _ = _http_json_request(
        method="GET",
        url=f"{base_url}/incidents",
        headers={
            "Authorization": f"Token token={api_key}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        },
        query=query,
    )
    incidents = response_data.get("incidents", []) if isinstance(response_data, dict) else []
    payload = {
        "incidents": _make_json_safe(incidents),
        "count": len(incidents),
    }
    runtime.set_path_value(runtime.context, output_key, payload)
    return _tool_result(
        "pagerduty_list_incidents",
        output_key=output_key,
        count=len(incidents),
        secret=secret_meta,
    )


def _validate_datadog_search_logs_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "api_key_name", node_id=node_id)
    _validate_optional_string(config, "api_key_provider", node_id=node_id)
    _validate_required_string(config, "app_key_name", node_id=node_id)
    _validate_optional_string(config, "app_key_provider", node_id=node_id)
    _validate_required_string(config, "query", node_id=node_id)
    _coerce_positive_int(config.get("window_minutes"), field_name="window_minutes", node_id=node_id, default=60, maximum=1440)
    _coerce_positive_int(config.get("limit"), field_name="limit", node_id=node_id, default=20, maximum=100)
    _validate_optional_string(config, "base_url", node_id=node_id)


def _execute_datadog_search_logs_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    api_key, api_secret_meta = _resolve_runtime_secret(
        runtime,
        name_key="api_key_name",
        provider_key="api_key_provider",
    )
    app_key, app_secret_meta = _resolve_runtime_secret(
        runtime,
        name_key="app_key_name",
        provider_key="app_key_provider",
    )
    query_text = _render_runtime_string(runtime, "query", required=True)
    window_minutes = _coerce_positive_int(
        runtime.config.get("window_minutes"),
        field_name="window_minutes",
        node_id=runtime.node["id"],
        default=60,
        maximum=1440,
    )
    limit = _coerce_positive_int(
        runtime.config.get("limit"),
        field_name="limit",
        node_id=runtime.node["id"],
        default=20,
        maximum=100,
    )
    base_url = (_render_runtime_string(runtime, "base_url") or "https://api.datadoghq.com").rstrip("/")
    time_to = timezone.now()
    time_from = time_to - timedelta(minutes=window_minutes)
    response_data, _ = _http_json_request(
        method="POST",
        url=f"{base_url}/api/v2/logs/events/search",
        headers={
            "Accept": "application/json",
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
        },
        json_body={
            "filter": {
                "query": query_text,
                "from": _isoformat_utc(time_from),
                "to": _isoformat_utc(time_to),
            },
            "page": {
                "limit": limit,
            },
            "sort": "timestamp",
        },
    )
    logs = response_data.get("data", []) if isinstance(response_data, dict) else []
    payload = {
        "logs": _make_json_safe(logs),
        "count": len(logs),
        "query": query_text,
    }
    runtime.set_path_value(runtime.context, output_key, payload)
    return _tool_result(
        "datadog_search_logs",
        output_key=output_key,
        count=len(logs),
        secrets=[api_secret_meta, app_secret_meta],
    )


def _validate_grafana_query_prometheus_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "api_key_name", node_id=node_id)
    _validate_optional_string(config, "api_key_provider", node_id=node_id)
    _validate_required_string(config, "base_url", node_id=node_id)
    _validate_required_string(config, "datasource_uid", node_id=node_id)
    _validate_required_string(config, "query", node_id=node_id)
    _validate_optional_string(config, "time", node_id=node_id)


def _execute_grafana_query_prometheus_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    api_key, secret_meta = _resolve_runtime_secret(
        runtime,
        name_key="api_key_name",
        provider_key="api_key_provider",
    )
    base_url = (_render_runtime_string(runtime, "base_url", required=True) or "").rstrip("/")
    datasource_uid = _render_runtime_string(runtime, "datasource_uid", required=True)
    query_text = _render_runtime_string(runtime, "query", required=True)
    query_time = _render_runtime_string(runtime, "time") or str(int(timezone.now().timestamp()))
    response_data, _ = _http_json_request(
        method="GET",
        url=f"{base_url}/api/datasources/proxy/uid/{datasource_uid}/api/v1/query",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        query={
            "query": query_text,
            "time": query_time,
        },
    )
    payload = _make_json_safe(response_data)
    runtime.set_path_value(runtime.context, output_key, payload)
    result_count = 0
    if isinstance(response_data, dict):
        result_count = len(response_data.get("data", {}).get("result", []) or [])
    return _tool_result(
        "grafana_query_prometheus",
        output_key=output_key,
        result_count=result_count,
        secret=secret_meta,
    )


def _validate_slack_send_message_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "bot_token_name", node_id=node_id)
    _validate_optional_string(config, "bot_token_provider", node_id=node_id)
    _validate_required_string(config, "channel", node_id=node_id)
    _validate_required_string(config, "text", node_id=node_id)
    _validate_optional_string(config, "thread_ts", node_id=node_id)
    _validate_optional_string(config, "base_url", node_id=node_id)


def _execute_slack_send_message_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    bot_token, secret_meta = _resolve_runtime_secret(
        runtime,
        name_key="bot_token_name",
        provider_key="bot_token_provider",
    )
    channel = _render_runtime_string(runtime, "channel", required=True)
    text = _render_runtime_string(runtime, "text", required=True)
    thread_ts = _render_runtime_string(runtime, "thread_ts")
    base_url = (_render_runtime_string(runtime, "base_url") or "https://slack.com/api").rstrip("/")
    body = {
        "channel": channel,
        "text": text,
    }
    if thread_ts:
        body["thread_ts"] = thread_ts

    response_data, _ = _http_json_request(
        method="POST",
        url=f"{base_url}/chat.postMessage",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {bot_token}",
        },
        json_body=body,
    )
    if not isinstance(response_data, dict):
        raise ValidationError({"definition": 'Slack returned an unexpected non-JSON response.'})
    if not response_data.get("ok"):
        slack_error = response_data.get("error") or "unknown_error"
        raise ValidationError({"definition": f"Slack chat.postMessage failed: {slack_error}."})

    payload = {
        "ok": True,
        "channel": response_data.get("channel"),
        "ts": response_data.get("ts"),
        "message": _make_json_safe(response_data.get("message")),
    }
    runtime.set_path_value(runtime.context, output_key, payload)
    return _tool_result(
        "slack_send_message",
        output_key=output_key,
        channel=response_data.get("channel"),
        ts=response_data.get("ts"),
        secret=secret_meta,
    )


def _validate_prometheus_query_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "base_url", node_id=node_id)
    _validate_required_string(config, "query", node_id=node_id)
    _validate_optional_string(config, "time", node_id=node_id)
    _validate_optional_string(config, "bearer_token_name", node_id=node_id)
    _validate_optional_string(config, "bearer_token_provider", node_id=node_id)


def _execute_prometheus_query_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    base_url = (_render_runtime_string(runtime, "base_url", required=True) or "").rstrip("/")
    query_text = _render_runtime_string(runtime, "query", required=True)
    query_time = _render_runtime_string(runtime, "time")

    headers = {"Accept": "application/json"}
    secret_meta = None
    if runtime.config.get("bearer_token_name"):
        bearer_token, secret_meta = _resolve_runtime_secret(
            runtime,
            name_key="bearer_token_name",
            provider_key="bearer_token_provider",
        )
        headers["Authorization"] = f"Bearer {bearer_token}"

    query: dict[str, Any] = {"query": query_text}
    if query_time:
        query["time"] = query_time

    response_data, _ = _http_json_request(
        method="GET",
        url=f"{base_url}/api/v1/query",
        headers=headers,
        query=query,
    )
    payload = _make_json_safe(response_data)
    runtime.set_path_value(runtime.context, output_key, payload)
    result_count = 0
    if isinstance(response_data, dict):
        result_count = len(response_data.get("data", {}).get("result", []) or [])

    result = {
        "output_key": output_key,
        "result_count": result_count,
    }
    if secret_meta is not None:
        result["secret"] = secret_meta
    return _tool_result("prometheus_query", **result)


def _validate_elasticsearch_search_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "base_url", node_id=node_id)
    _validate_optional_string(config, "index", node_id=node_id)
    _validate_required_json_template(config, "query_json", node_id=node_id)
    _validate_optional_string(config, "auth_token_name", node_id=node_id)
    _validate_optional_string(config, "auth_token_provider", node_id=node_id)
    auth_scheme = config.get("auth_scheme", "ApiKey")
    if auth_scheme not in {"ApiKey", "Bearer"}:
        _raise_definition_error(
            f'Node "{node_id}" config.auth_scheme must be one of: ApiKey, Bearer.'
        )


def _execute_elasticsearch_search_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    base_url = (_render_runtime_string(runtime, "base_url", required=True) or "").rstrip("/")
    index_name = _render_runtime_string(runtime, "index")
    query_body = _render_runtime_json(runtime, "query_json", required=True)
    if not isinstance(query_body, dict):
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.query_json must render a JSON object.'}
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    secret_meta = None
    if runtime.config.get("auth_token_name"):
        auth_token, secret_meta = _resolve_runtime_secret(
            runtime,
            name_key="auth_token_name",
            provider_key="auth_token_provider",
        )
        auth_scheme = runtime.config.get("auth_scheme", "ApiKey")
        headers["Authorization"] = f"{auth_scheme} {auth_token}"

    search_path = "/_search"
    if index_name:
        search_path = f"/{index_name}/_search"

    response_data, _ = _http_json_request(
        method="POST",
        url=f"{base_url}{search_path}",
        headers=headers,
        json_body=query_body,
    )

    hits: list[Any] = []
    total_hits: Any = 0
    if isinstance(response_data, dict):
        hits = response_data.get("hits", {}).get("hits", []) or []
        total_hits = response_data.get("hits", {}).get("total", 0)

    payload = {
        "hits": _make_json_safe(hits),
        "total": _make_json_safe(total_hits),
        "aggregations": _make_json_safe(response_data.get("aggregations")) if isinstance(response_data, dict) else None,
        "took": response_data.get("took") if isinstance(response_data, dict) else None,
        "raw": _make_json_safe(response_data),
    }
    runtime.set_path_value(runtime.context, output_key, payload)

    result = {
        "output_key": output_key,
        "hit_count": len(hits),
    }
    if secret_meta is not None:
        result["secret"] = secret_meta
    return _tool_result("elasticsearch_search", **result)


def _validate_openai_compatible_chat_tool(config: dict[str, Any], node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "base_url", node_id=node_id)
    _validate_required_string(config, "api_key_name", node_id=node_id)
    _validate_optional_string(config, "api_key_provider", node_id=node_id)
    _validate_required_string(config, "model", node_id=node_id)
    _validate_required_string(config, "user_prompt", node_id=node_id)
    _validate_optional_string(config, "system_prompt", node_id=node_id)
    _validate_optional_json_template(config, "extra_body_json", node_id=node_id)
    _coerce_optional_float(config.get("temperature"), field_name="temperature", node_id=node_id)
    if config.get("max_tokens") not in (None, ""):
        _coerce_positive_int(
            config.get("max_tokens"),
            field_name="max_tokens",
            node_id=node_id,
            default=1,
        )


def _execute_openai_compatible_chat_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    base_url = (_render_runtime_string(runtime, "base_url", required=True) or "").rstrip("/")
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

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
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

    text = _extract_openai_compatible_text(response_data)
    payload = {
        "text": text,
        "model": response_data.get("model", model),
        "usage": _make_json_safe(response_data.get("usage")),
        "finish_reason": _make_json_safe(
            response_data.get("choices", [{}])[0].get("finish_reason")
            if isinstance(response_data.get("choices"), list) and response_data.get("choices")
            else None
        ),
        "raw": _make_json_safe(response_data),
    }
    runtime.set_path_value(runtime.context, output_key, payload)
    return _tool_result(
        "openai_compatible_chat",
        output_key=output_key,
        model=payload["model"],
        secret=secret_meta,
    )


WORKFLOW_TOOL_REGISTRY: dict[str, WorkflowToolDefinition] = {
    "passthrough": WorkflowToolDefinition(
        name="passthrough",
        label="Passthrough",
        description="No-op tool that keeps the workflow moving without changing context.",
        icon="mdi-arrow-right",
        validator=_validate_passthrough_tool,
        executor=_execute_passthrough_tool,
    ),
    "set": WorkflowToolDefinition(
        name="set",
        label="Set value",
        description="Write a static value into workflow context.",
        icon="mdi-form-textbox",
        config={"output_key": "tool.output"},
        fields=(
            {
                "key": "output_key",
                "label": "Save result as",
                "type": "text",
                "placeholder": "tool.output",
            },
            {
                "key": "value",
                "label": "Value",
                "type": "text",
                "placeholder": "static-value",
                "help_text": "Use advanced runtime JSON for structured values.",
            },
        ),
        validator=_validate_set_tool,
        executor=_execute_set_tool,
    ),
    "template": WorkflowToolDefinition(
        name="template",
        label="Render template",
        description="Render a template against workflow context and save the result.",
        icon="mdi-text-box-edit-outline",
        config={"output_key": "tool.output"},
        fields=(
            {
                "key": "output_key",
                "label": "Save result as",
                "type": "text",
                "placeholder": "tool.output",
            },
            {
                "key": "template",
                "label": "Template",
                "type": "textarea",
                "rows": 4,
                "placeholder": "Service: {{ workflow.scope_label }}",
            },
        ),
        validator=_validate_template_tool,
        executor=_execute_template_tool,
    ),
    "secret": WorkflowToolDefinition(
        name="secret",
        label="Resolve secret",
        description="Resolve a scoped secret and store the redacted value path in context.",
        icon="mdi-key-variant",
        config={"output_key": "credentials.value"},
        fields=(
            {
                "key": "output_key",
                "label": "Save result as",
                "type": "text",
                "placeholder": "credentials.openai",
            },
            {
                "key": "name",
                "label": "Secret name",
                "type": "text",
                "placeholder": "OPENAI_API_KEY",
            },
            {
                "key": "provider",
                "label": "Secret provider",
                "type": "text",
                "placeholder": "environment-variable",
                "help_text": "Optional. Leave blank to search all enabled providers in scope.",
            },
        ),
        validator=_validate_secret_tool,
        executor=_execute_secret_tool,
    ),
    "pagerduty_list_incidents": WorkflowToolDefinition(
        name="pagerduty_list_incidents",
        label="PagerDuty incidents",
        description="Fetch open PagerDuty incidents into workflow context.",
        icon="mdi-bell-alert-outline",
        category="Incident response",
        config={"output_key": "pagerduty.incidents", "statuses": "triggered,acknowledged", "limit": 20},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "pagerduty.incidents"},
            {"key": "api_key_name", "label": "API key secret name", "type": "text", "placeholder": "PAGERDUTY_API_KEY"},
            {"key": "api_key_provider", "label": "API key provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "incident_key", "label": "Incident key", "type": "text", "placeholder": "{{ trigger.payload.incident_key }}", "help_text": "Optional. Filter to a specific incident key."},
            {"key": "statuses", "label": "Statuses", "type": "text", "placeholder": "triggered,acknowledged"},
            {"key": "limit", "label": "Limit", "type": "text", "placeholder": "20"},
        ),
        validator=_validate_pagerduty_list_incidents_tool,
        executor=_execute_pagerduty_list_incidents_tool,
    ),
    "datadog_search_logs": WorkflowToolDefinition(
        name="datadog_search_logs",
        label="Datadog log search",
        description="Search Datadog logs for a query over a recent time window.",
        icon="mdi-text-search",
        category="Observability",
        config={"output_key": "datadog.logs", "window_minutes": 60, "limit": 20},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "datadog.logs"},
            {"key": "api_key_name", "label": "API key secret name", "type": "text", "placeholder": "DATADOG_API_KEY"},
            {"key": "api_key_provider", "label": "API key provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "app_key_name", "label": "App key secret name", "type": "text", "placeholder": "DATADOG_APP_KEY"},
            {"key": "app_key_provider", "label": "App key provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "query", "label": "Query", "type": "textarea", "rows": 4, "placeholder": "service:api status:error"},
            {"key": "window_minutes", "label": "Window minutes", "type": "text", "placeholder": "60"},
            {"key": "limit", "label": "Limit", "type": "text", "placeholder": "20"},
        ),
        validator=_validate_datadog_search_logs_tool,
        executor=_execute_datadog_search_logs_tool,
    ),
    "grafana_query_prometheus": WorkflowToolDefinition(
        name="grafana_query_prometheus",
        label="Grafana Prometheus query",
        description="Run a Prometheus instant query through a Grafana datasource proxy.",
        icon="mdi-chart-line",
        category="Observability",
        config={"output_key": "grafana.query"},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "grafana.query"},
            {"key": "api_key_name", "label": "API key secret name", "type": "text", "placeholder": "GRAFANA_API_KEY"},
            {"key": "api_key_provider", "label": "API key provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "base_url", "label": "Grafana base URL", "type": "text", "placeholder": "https://grafana.example.com"},
            {"key": "datasource_uid", "label": "Datasource UID", "type": "text", "placeholder": "prometheus-main"},
            {"key": "query", "label": "PromQL query", "type": "textarea", "rows": 4, "placeholder": "sum(rate(http_requests_total[5m]))"},
            {"key": "time", "label": "Query time", "type": "text", "placeholder": "Optional RFC3339 or unix timestamp"},
        ),
        validator=_validate_grafana_query_prometheus_tool,
        executor=_execute_grafana_query_prometheus_tool,
    ),
    "prometheus_query": WorkflowToolDefinition(
        name="prometheus_query",
        label="Prometheus query",
        description="Run a Prometheus instant query against the native HTTP API.",
        icon="mdi-chart-areaspline",
        category="Observability",
        config={"output_key": "prometheus.query"},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "prometheus.query"},
            {"key": "base_url", "label": "Prometheus base URL", "type": "text", "placeholder": "https://prometheus.example.com"},
            {"key": "bearer_token_name", "label": "Bearer token secret name", "type": "text", "placeholder": "PROMETHEUS_API_TOKEN", "help_text": "Optional. Leave blank if Prometheus is reachable without auth."},
            {"key": "bearer_token_provider", "label": "Bearer token provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "query", "label": "PromQL query", "type": "textarea", "rows": 4, "placeholder": "sum(rate(http_requests_total[5m]))"},
            {"key": "time", "label": "Query time", "type": "text", "placeholder": "Optional RFC3339 or unix timestamp"},
        ),
        validator=_validate_prometheus_query_tool,
        executor=_execute_prometheus_query_tool,
    ),
    "elasticsearch_search": WorkflowToolDefinition(
        name="elasticsearch_search",
        label="Elasticsearch search",
        description="Run an Elasticsearch `_search` request and store hits, totals, and aggregations.",
        icon="mdi-database-search-outline",
        category="Observability",
        config={"output_key": "elasticsearch.search", "auth_scheme": "ApiKey"},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "elasticsearch.search"},
            {"key": "base_url", "label": "Elasticsearch base URL", "type": "text", "placeholder": "https://elasticsearch.example.com"},
            {"key": "index", "label": "Index", "type": "text", "placeholder": "logs-*", "help_text": "Optional. Leave blank to search all indices reachable at this endpoint."},
            {"key": "auth_token_name", "label": "Auth token secret name", "type": "text", "placeholder": "ELASTICSEARCH_API_KEY", "help_text": "Optional. Provide a token when the cluster requires auth."},
            {"key": "auth_token_provider", "label": "Auth token provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "auth_scheme", "label": "Auth scheme", "type": "select", "options": ({"value": "ApiKey", "label": "ApiKey"}, {"value": "Bearer", "label": "Bearer"})},
            {"key": "query_json", "label": "Query JSON", "type": "textarea", "rows": 8, "placeholder": "{\"size\": 10, \"query\": {\"match\": {\"service\": \"api\"}}}"},
        ),
        validator=_validate_elasticsearch_search_tool,
        executor=_execute_elasticsearch_search_tool,
    ),
    "openai_compatible_chat": WorkflowToolDefinition(
        name="openai_compatible_chat",
        label="LLM chat (OpenAI-compatible)",
        description="Call an OpenAI-compatible `/chat/completions` endpoint with a model, prompts, and API key.",
        icon="mdi-robot-happy-outline",
        category="AI",
        config={"output_key": "llm.response"},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "llm.response"},
            {"key": "base_url", "label": "API base URL", "type": "text", "placeholder": "https://api.openai.com/v1"},
            {"key": "api_key_name", "label": "API key secret name", "type": "text", "placeholder": "OPENAI_API_KEY"},
            {"key": "api_key_provider", "label": "API key provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "model", "label": "Model", "type": "text", "placeholder": "gpt-4.1-mini"},
            {"key": "system_prompt", "label": "System prompt", "type": "textarea", "rows": 4, "placeholder": "You are an incident response assistant."},
            {"key": "user_prompt", "label": "User prompt", "type": "textarea", "rows": 6, "placeholder": "Summarize {{ trigger.payload.alerts|length }} alerts and propose next steps."},
            {"key": "temperature", "label": "Temperature", "type": "text", "placeholder": "0.2"},
            {"key": "max_tokens", "label": "Max tokens", "type": "text", "placeholder": "800"},
            {"key": "extra_body_json", "label": "Extra body JSON", "type": "textarea", "rows": 5, "placeholder": "{\"response_format\": {\"type\": \"json_object\"}}", "help_text": "Optional provider-specific fields merged into the request body after prompts and model."},
        ),
        validator=_validate_openai_compatible_chat_tool,
        executor=_execute_openai_compatible_chat_tool,
    ),
    "slack_send_message": WorkflowToolDefinition(
        name="slack_send_message",
        label="Slack send message",
        description="Post a message to Slack and store the delivery metadata.",
        icon="mdi-slack",
        category="Messaging",
        config={"output_key": "slack.delivery"},
        fields=(
            {"key": "output_key", "label": "Save result as", "type": "text", "placeholder": "slack.delivery"},
            {"key": "bot_token_name", "label": "Bot token secret name", "type": "text", "placeholder": "SLACK_BOT_TOKEN"},
            {"key": "bot_token_provider", "label": "Bot token provider", "type": "text", "placeholder": "environment-variable", "help_text": "Optional. Leave blank to search all enabled providers in scope."},
            {"key": "channel", "label": "Channel", "type": "text", "placeholder": "#ops-alerts"},
            {"key": "text", "label": "Message text", "type": "textarea", "rows": 4, "placeholder": "Workflow {{ workflow.name }} completed."},
            {"key": "thread_ts", "label": "Thread timestamp", "type": "text", "placeholder": "Optional thread_ts"},
        ),
        validator=_validate_slack_send_message_tool,
        executor=_execute_slack_send_message_tool,
    ),
}

WORKFLOW_TOOL_DEFINITIONS = tuple(
    tool_definition.serialize() for tool_definition in WORKFLOW_TOOL_REGISTRY.values()
)


def get_workflow_tool_definition(name: str) -> WorkflowToolDefinition | None:
    return WORKFLOW_TOOL_REGISTRY.get(name)


def validate_workflow_tool_config(config: dict[str, Any], *, node_id: str) -> dict[str, Any]:
    normalized = normalize_workflow_tool_config(config)
    tool_name = normalized.get("tool_name")
    legacy_operation = normalized.get("operation")

    if (
        isinstance(legacy_operation, str)
        and legacy_operation.strip()
        and isinstance(tool_name, str)
        and tool_name.strip()
        and legacy_operation.strip() != tool_name.strip()
    ):
        _raise_definition_error(
            f'Node "{node_id}" config.operation must match config.tool_name when both are provided.'
        )

    if not isinstance(tool_name, str) or not tool_name.strip():
        _raise_definition_error(f'Node "{node_id}" must define config.tool_name.')

    tool_definition = get_workflow_tool_definition(tool_name)
    if tool_definition is None:
        available_names = ", ".join(sorted(WORKFLOW_TOOL_REGISTRY))
        _raise_definition_error(
            f'Node "{node_id}" config.tool_name must be one of: {available_names}.'
        )

    if tool_definition.validator is not None:
        tool_definition.validator(normalized, node_id)

    return normalized


def execute_workflow_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    tool_name = runtime.config["tool_name"]
    tool_definition = get_workflow_tool_definition(tool_name)
    if tool_definition is None or tool_definition.executor is None:
        raise ValidationError({"definition": f'Unsupported tool "{tool_name}".'})
    return tool_definition.executor(runtime)
