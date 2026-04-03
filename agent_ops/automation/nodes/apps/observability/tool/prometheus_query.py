from __future__ import annotations

from automation.nodes.adapters import (
    tool_definition_as_node_definition,
    tool_definition_as_node_implementation,
)
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _http_json_request,
    _make_json_safe,
    _render_runtime_external_url,
    _render_runtime_string,
    _resolve_runtime_secret,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_secret_group_id,
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
    if config.get("secret_name") not in (None, ""):
        _validate_optional_string(config, "secret_name", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)


def _execute_prometheus_query_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    base_url = (_render_runtime_external_url(runtime, "base_url", required=True, default_mode="static") or "").rstrip("/")
    query_text = _render_runtime_string(runtime, "query", required=True, default_mode="expression")
    query_time = _render_runtime_string(runtime, "time", default_mode="expression")

    headers = {"Accept": "application/json"}
    secret_meta = None
    secret_name = _render_runtime_string(runtime, "secret_name", default_mode="static")
    bearer_token = None
    if secret_name:
        bearer_token, secret_meta = _resolve_runtime_secret(
            runtime,
            secret_name=secret_name,
            secret_group_id=runtime.config.get("secret_group_id"),
        )
    if bearer_token:
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
        tool_text_field(
            "output_key",
            "Save result as",
            ui_group="result",
            binding="path",
            placeholder="prometheus.query",
        ),
        tool_text_field(
            "base_url",
            "Prometheus base URL",
            ui_group="advanced",
            placeholder="https://prometheus.example.com",
        ),
        tool_textarea_field(
            "query",
            "PromQL query",
            rows=4,
            ui_group="input",
            binding="template",
            placeholder="sum(rate(http_requests_total[5m]))",
        ),
        tool_text_field(
            "time",
            "Query time",
            ui_group="input",
            binding="template",
            placeholder="Optional RFC3339 or unix timestamp",
        ),
        tool_text_field(
            "secret_name",
            "Secret name",
            ui_group="advanced",
            placeholder="PROMETHEUS_API_TOKEN",
            help_text="Optional. Resolve this secret and send it as a bearer token.",
        ),
        tool_text_field(
            "secret_group_id",
            "Secret group",
            ui_group="advanced",
            placeholder="Use workflow secret group",
            help_text="Optional. Override the workflow secret group for this node with a scoped secret group ID.",
        ),
    ),
    validator=_validate_prometheus_query_tool,
    executor=_execute_prometheus_query_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
NODE_DEFINITION = tool_definition_as_node_definition(
    TOOL_DEFINITION,
    node_type="tool.prometheus_query",
    details="Prometheus query node for observability workflows.",
)
