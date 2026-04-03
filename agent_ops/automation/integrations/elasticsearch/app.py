from automation.catalog.capabilities import CAPABILITY_AGENT_TOOL
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
    ParameterOptionDefinition,
)


ELASTICSEARCH_CONNECTION = ConnectionTypeDefinition(
    id="elasticsearch.api",
    integration_id="elasticsearch",
    label="Elasticsearch API",
    auth_kind="http_secret",
    description="Reusable HTTP connection for Elasticsearch clusters and compatible search endpoints.",
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
