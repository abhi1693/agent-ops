from __future__ import annotations

from django.core.exceptions import ValidationError

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
    _render_runtime_json,
    _render_runtime_string,
    _resolve_runtime_secret,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_secret_group_id,
    _validate_optional_string,
    _validate_required_external_url,
    _validate_required_json_template,
    tool_field_option,
    tool_select_field,
    tool_text_field,
    tool_textarea_field,
)


def _validate_elasticsearch_search_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_external_url(config, "base_url", node_id=node_id)
    _validate_optional_string(config, "index", node_id=node_id)
    _validate_required_json_template(config, "query_json", node_id=node_id)
    if config.get("secret_name") not in (None, ""):
        _validate_optional_string(config, "secret_name", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)
    auth_scheme = config.get("auth_scheme", "ApiKey")
    if auth_scheme not in {"ApiKey", "Bearer"}:
        raise ValidationError(
            {"definition": f'Node "{node_id}" config.auth_scheme must be one of: ApiKey, Bearer.'}
        )


def _execute_elasticsearch_search_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    base_url = (_render_runtime_external_url(runtime, "base_url", required=True, default_mode="static") or "").rstrip("/")
    index_name = _render_runtime_string(runtime, "index", default_mode="static")
    query_body = _render_runtime_json(runtime, "query_json", required=True, default_mode="expression")
    if not isinstance(query_body, dict):
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.query_json must render a JSON object.'}
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    secret_meta = None
    secret_name = _render_runtime_string(runtime, "secret_name", default_mode="static")
    auth_token = None
    if secret_name:
        auth_token, secret_meta = _resolve_runtime_secret(
            runtime,
            secret_name=secret_name,
            secret_group_id=runtime.config.get("secret_group_id"),
        )
    if auth_token:
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

    hits: list = []
    total_hits = 0
    aggregations = None
    took = None
    if isinstance(response_data, dict):
        hits = response_data.get("hits", {}).get("hits", []) or []
        total_hits = response_data.get("hits", {}).get("total", 0)
        aggregations = response_data.get("aggregations")
        took = response_data.get("took")

    payload = {
        "hits": _make_json_safe(hits),
        "total": _make_json_safe(total_hits),
        "aggregations": _make_json_safe(aggregations),
        "took": took,
        "raw": _make_json_safe(response_data),
    }
    runtime.set_path_value(runtime.context, output_key, payload)

    result = {"output_key": output_key, "hit_count": len(hits)}
    if secret_meta is not None:
        result["secret"] = secret_meta
    return _tool_result("elasticsearch_search", **result)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="elasticsearch_search",
    label="Elasticsearch search",
    description="Run an Elasticsearch `_search` request and store hits, totals, and aggregations.",
    icon="mdi-database-search-outline",
    category="Observability",
    config={"output_key": "elasticsearch.search", "auth_scheme": "ApiKey"},
    fields=(
        tool_text_field(
            "output_key",
            "Save result as",
            ui_group="result",
            binding="path",
            placeholder="elasticsearch.search",
        ),
        tool_text_field(
            "base_url",
            "Elasticsearch base URL",
            ui_group="advanced",
            placeholder="https://elasticsearch.example.com",
        ),
        tool_text_field(
            "index",
            "Index",
            ui_group="input",
            binding="template",
            placeholder="logs-*",
            help_text="Optional. Leave blank to search all indices reachable at this endpoint.",
        ),
        tool_select_field(
            "auth_scheme",
            "Auth scheme",
            ui_group="advanced",
            options=(
                tool_field_option("ApiKey"),
                tool_field_option("Bearer"),
            ),
        ),
        tool_text_field(
            "secret_name",
            "Secret name",
            ui_group="advanced",
            placeholder="ELASTICSEARCH_API_KEY",
            help_text="Optional. Resolve this secret and send it in the Authorization header.",
        ),
        tool_text_field(
            "secret_group_id",
            "Secret group",
            ui_group="advanced",
            placeholder="Use workflow secret group",
            help_text="Optional. Override the workflow secret group for this node with a scoped secret group ID.",
        ),
        tool_textarea_field(
            "query_json",
            "Query JSON",
            rows=8,
            ui_group="input",
            binding="template",
            placeholder='{"size": 10, "query": {"match": {"service": "api"}}}',
        ),
    ),
    validator=_validate_elasticsearch_search_tool,
    executor=_execute_elasticsearch_search_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
NODE_DEFINITION = tool_definition_as_node_definition(
    TOOL_DEFINITION,
    node_type="elasticsearch.action.search",
    details="Elasticsearch search node for observability workflows.",
)
