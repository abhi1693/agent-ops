from automation.catalog.capabilities import CAPABILITY_AGENT_TOOL
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
)


PROMETHEUS_CONNECTION = ConnectionTypeDefinition(
    id="prometheus.api",
    integration_id="prometheus",
    label="Prometheus API",
    auth_kind="http_secret",
    description="Reusable HTTP connection for Prometheus-compatible query endpoints.",
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
