from automation.catalog.capabilities import CAPABILITY_AGENT_TOOL
from automation.catalog.execution import resolve_connection_with_base_url
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionSlotDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import (
    _http_json_request,
    _make_json_safe,
    _render_runtime_json,
    _render_runtime_string,
    _tool_result,
)
from django.core.exceptions import ValidationError


def _execute_elasticsearch_search(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    output_key = _render_runtime_string(runtime, "output_key", default="elasticsearch.search", default_mode="static")
    resolved, base_url = resolve_connection_with_base_url(runtime, connection_type="elasticsearch.api")
    index_name = _render_runtime_string(runtime, "index", default_mode="expression")
    query_body = _render_runtime_json(runtime, "query_json", required=True, default_mode="expression")
    if not isinstance(query_body, dict):
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.query_json must render a JSON object.'}
        )

    size_value = runtime.config.get("size")
    if size_value not in (None, "") and "size" not in query_body:
        try:
            query_body["size"] = int(size_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"definition": f'Node "{runtime.node["id"]}" config.size must be an integer.'}
            ) from exc

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth_scheme = _render_runtime_string(runtime, "auth_scheme", default="ApiKey", default_mode="static") or "ApiKey"
    if auth_scheme not in {"ApiKey", "Bearer"}:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.auth_scheme must be one of: ApiKey, Bearer.'}
        )
    auth_token = resolved.values.get("auth_token")
    if isinstance(auth_token, str) and auth_token:
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
    if output_key:
        runtime.set_path_value(runtime.context, output_key, payload)

    result = _tool_result(
        "elasticsearch_search",
        output_key=output_key,
        hit_count=len(hits),
        connection_id=runtime.config.get("connection_id"),
    )
    secret_meta = resolved.secret_metas.get("auth_token")
    if secret_meta is not None:
        result["secret"] = secret_meta
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output=result,
    )


ELASTICSEARCH_CONNECTION = ConnectionTypeDefinition(
    id="elasticsearch.api",
    integration_id="elasticsearch",
    label="Elasticsearch API",
    auth_kind="http_secret",
    description="Reusable HTTP connection for Elasticsearch clusters and compatible search endpoints.",
    field_schema=(
        ParameterDefinition(
            key="base_url",
            label="API Base URL",
            value_type="url",
            required=True,
            description="Base URL for the Elasticsearch cluster or compatible API.",
            placeholder="https://elastic.example.com",
        ),
        ParameterDefinition(
            key="auth_token",
            label="Auth Token Secret",
            value_type="secret_ref",
            required=False,
            description="Optional secret reference used in the Authorization header.",
            placeholder="ELASTICSEARCH_API_KEY",
        ),
    ),
)


APP = IntegrationApp(
    id="elasticsearch",
    label="Elasticsearch",
    description="Search and retrieve structured log and document data from Elasticsearch.",
    icon="mdi-database-search-outline",
    category_tags=("observability", "search"),
    connection_types=(ELASTICSEARCH_CONNECTION,),
    actions=(
        CatalogNodeDefinition(
            id="elasticsearch.action.search",
            integration_id="elasticsearch",
            mode="action",
            kind="action",
            label="Search Documents",
            description="Runs a structured Elasticsearch query against one or more indexes.",
            icon="mdi-database-search-outline",
            resource="document",
            operation="search",
            group="Search",
            capabilities=frozenset({CAPABILITY_AGENT_TOOL}),
            connection_type=ELASTICSEARCH_CONNECTION.id,
            runtime_executor=_execute_elasticsearch_search,
            connection_slots=(
                ConnectionSlotDefinition(
                    key="connection_id",
                    label="Connection",
                    allowed_connection_types=(ELASTICSEARCH_CONNECTION.id,),
                    required=True,
                    description="Reusable Elasticsearch connection used for authenticated search requests.",
                ),
            ),
            parameter_schema=(
                ParameterDefinition(
                    key="index",
                    label="Index",
                    value_type="string",
                    required=True,
                    description="Index or index pattern to search.",
                    placeholder="logs-*",
                ),
                ParameterDefinition(
                    key="query_json",
                    label="Query JSON",
                    value_type="json",
                    required=True,
                    description="Elasticsearch Query DSL body.",
                    placeholder='{"query":{"match_all":{}}}',
                ),
                ParameterDefinition(
                    key="size",
                    label="Result Size",
                    value_type="integer",
                    required=False,
                    description="Maximum number of hits to return.",
                    default=25,
                ),
                ParameterDefinition(
                    key="auth_scheme",
                    label="Auth Scheme",
                    value_type="string",
                    required=False,
                    description="Authorization scheme used with the connection secret.",
                    default="ApiKey",
                    options=(
                        ParameterOptionDefinition(value="ApiKey", label="ApiKey"),
                        ParameterOptionDefinition(value="Bearer", label="Bearer"),
                    ),
                ),
                ParameterDefinition(
                    key="output_key",
                    label="Save Result As",
                    value_type="string",
                    required=False,
                    description="Context path where the search payload should be stored.",
                    default="elasticsearch.search",
                    placeholder="elasticsearch.search",
                ),
            ),
            tags=("search", "logs"),
        ),
    ),
    sort_order=40,
)
