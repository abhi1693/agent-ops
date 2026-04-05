from automation.catalog.capabilities import CAPABILITY_AGENT_TOOL
from automation.catalog.execution import (
    get_runtime_connection_slot_value,
    resolve_connection_request_auth,
    resolve_connection_with_base_url,
)
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionHttpAuthDefinition,
    ConnectionHttpHeaderDefinition,
    ConnectionSlotDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import (
    _http_json_request,
    _make_json_safe,
    _render_runtime_string,
    _tool_result,
)
from django.core.exceptions import ValidationError


def _execute_prometheus_query(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    instant = runtime.config.get("instant", True)
    if str(instant).lower() == "false":
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" only supports instant Prometheus queries right now.'}
        )

    output_key = _render_runtime_string(runtime, "output_key", default="prometheus.query", default_mode="static")
    resolved, base_url = resolve_connection_with_base_url(runtime, connection_type="prometheus.api")
    query_text = _render_runtime_string(runtime, "query", required=True, default_mode="expression")
    query_time = _render_runtime_string(runtime, "time", default_mode="expression")

    headers = {
        "Accept": "application/json",
        **resolve_connection_request_auth(runtime, resolved_connection=resolved).headers,
    }

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
    if output_key:
        runtime.set_path_value(runtime.context, output_key, payload)

    result_count = 0
    if isinstance(response_data, dict):
        result_count = len(response_data.get("data", {}).get("result", []) or [])

    result = _tool_result(
        "prometheus_query",
        output_key=output_key,
        result_count=result_count,
        connection_id=get_runtime_connection_slot_value(runtime),
    )
    secret_meta = resolved.secret_metas.get("bearer_token")
    if secret_meta is not None:
        result["secret"] = secret_meta
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output=result,
    )


PROMETHEUS_CONNECTION = ConnectionTypeDefinition(
    id="prometheus.api",
    integration_id="prometheus",
    label="Prometheus API",
    auth_kind="http_secret",
    description="Reusable HTTP credential for Prometheus-compatible query endpoints.",
    http_auth=ConnectionHttpAuthDefinition(
        headers=(
            ConnectionHttpHeaderDefinition(
                field_key="bearer_token",
                header_name="Authorization",
                prefix="Bearer ",
                required=False,
            ),
        ),
    ),
    field_schema=(
        ParameterDefinition(
            key="base_url",
            label="API Base URL",
            value_type="url",
            required=True,
            description="Base URL for the Prometheus-compatible HTTP API.",
            placeholder="https://prometheus.example.com",
        ),
        ParameterDefinition(
            key="bearer_token",
            label="Bearer Token",
            value_type="secret_ref",
            required=False,
            description="Optional bearer token stored with this connection for authenticated requests.",
            placeholder="prometheus-token",
        ),
    ),
)


APP = IntegrationApp(
    id="prometheus",
    label="Prometheus",
    description="Prometheus metrics querying and alert-driven automation.",
    icon="mdi-chart-line",
    category_tags=("observability", "metrics"),
    connection_types=(PROMETHEUS_CONNECTION,),
    actions=(
        CatalogNodeDefinition(
            id="prometheus.action.query",
            integration_id="prometheus",
            mode="action",
            kind="action",
            label="Run Query",
            description="Executes a PromQL query against a Prometheus-compatible API.",
            icon="mdi-chart-timeline-variant",
            resource="metric",
            operation="query",
            group="Metrics",
            capabilities=frozenset({CAPABILITY_AGENT_TOOL}),
            connection_type=PROMETHEUS_CONNECTION.id,
            runtime_executor=_execute_prometheus_query,
            connection_slots=(
                ConnectionSlotDefinition(
                    key="connection_id",
                    label="Credential for Prometheus API",
                    allowed_connection_types=(PROMETHEUS_CONNECTION.id,),
                    required=True,
                    description="Reusable Prometheus credential used for authenticated query execution.",
                ),
            ),
            parameter_schema=(
                ParameterDefinition(
                    key="query",
                    label="Query",
                    value_type="string",
                    required=True,
                    description="PromQL expression to execute.",
                    placeholder='sum(rate(http_requests_total[5m])) by (service)',
                ),
                ParameterDefinition(
                    key="instant",
                    label="Instant Query",
                    value_type="boolean",
                    required=False,
                    description="Run as an instant query instead of a range query.",
                    default=True,
                ),
                ParameterDefinition(
                    key="time",
                    label="Query Time",
                    value_type="string",
                    required=False,
                    description="Optional RFC3339 or unix timestamp for the instant query.",
                    placeholder="1711798200",
                ),
                ParameterDefinition(
                    key="output_key",
                    label="Save Result As",
                    value_type="string",
                    required=False,
                    description="Context path where the response payload should be stored.",
                    default="prometheus.query",
                    placeholder="prometheus.query",
                ),
            ),
            tags=("promql", "metrics"),
        ),
    ),
    sort_order=30,
)
