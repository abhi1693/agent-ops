from __future__ import annotations

from .base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _http_json_request,
    _make_json_safe,
    _render_runtime_external_url,
    _render_runtime_string,
    _resolve_runtime_secret,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_string,
    _validate_required_external_url,
    _validate_required_string,
    tool_text_field,
    tool_textarea_field,
)


def _validate_prometheus_query_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_external_url(config, "base_url", node_id=node_id)
    _validate_required_string(config, "query", node_id=node_id)
    _validate_optional_string(config, "time", node_id=node_id)
    _validate_optional_string(config, "bearer_token_name", node_id=node_id)
    _validate_optional_string(config, "bearer_token_provider", node_id=node_id)


def _execute_prometheus_query_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True)
    base_url = (_render_runtime_external_url(runtime, "base_url", required=True) or "").rstrip("/")
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

    query = {"query": query_text}
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

    result = {"output_key": output_key, "result_count": result_count}
    if secret_meta is not None:
        result["secret"] = secret_meta
    return _tool_result("prometheus_query", **result)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="prometheus_query",
    label="Prometheus query",
    description="Run a Prometheus instant query against the native HTTP API.",
    icon="mdi-chart-areaspline",
    category="Observability",
    config={"output_key": "prometheus.query"},
    fields=(
        tool_text_field("output_key", "Save result as", placeholder="prometheus.query"),
        tool_text_field("base_url", "Prometheus base URL", placeholder="https://prometheus.example.com"),
        tool_text_field(
            "bearer_token_name",
            "Bearer token secret name",
            placeholder="PROMETHEUS_API_TOKEN",
            help_text="Optional. Leave blank if Prometheus is reachable without auth.",
        ),
        tool_text_field(
            "bearer_token_provider",
            "Bearer token provider",
            placeholder="environment-variable",
            help_text="Optional. Leave blank to search all enabled providers in scope.",
        ),
        tool_textarea_field(
            "query",
            "PromQL query",
            rows=4,
            placeholder="sum(rate(http_requests_total[5m]))",
        ),
        tool_text_field("time", "Query time", placeholder="Optional RFC3339 or unix timestamp"),
    ),
    validator=_validate_prometheus_query_tool,
    executor=_execute_prometheus_query_tool,
)
