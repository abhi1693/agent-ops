from automation.catalog.capabilities import CAPABILITY_TRIGGER_WEBHOOK
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
)


GITHUB_CONNECTION = ConnectionTypeDefinition(
    id="github.oauth2",
    integration_id="github",
    label="GitHub",
    auth_kind="oauth2",
    description="Reusable GitHub account connection for repository and webhook operations.",
)


APP = IntegrationApp(
    id="github",
    label="GitHub",
    description="GitHub repository, issue, and workflow automation.",
    icon="mdi-github",
    category_tags=("source_control", "developer_tools"),
    connection_types=(GITHUB_CONNECTION,),
    triggers=(
        CatalogNodeDefinition(
            id="github.trigger.webhook",
            integration_id="github",
            mode="trigger",
            kind="trigger",
            label="Repository Webhook",
            description="Starts a workflow from GitHub webhook deliveries.",
            icon="mdi-source-repository",
            resource="repository",
            operation="webhook",
            group="Triggers",
            capabilities=frozenset({CAPABILITY_TRIGGER_WEBHOOK}),
            connection_type=GITHUB_CONNECTION.id,
            parameter_schema=(
                ParameterDefinition(
                    key="owner",
                    label="Owner",
                    value_type="string",
                    required=True,
                    description="GitHub user or organization that owns the repository.",
                    placeholder="n8n-io",
                ),
                ParameterDefinition(
                    key="repository",
                    label="Repository",
                    value_type="string",
                    required=True,
                    description="Repository name that will emit webhook events.",
                    placeholder="n8n",
                ),
                ParameterDefinition(
                    key="events",
                    label="Events",
                    value_type="string[]",
                    required=True,
                    description="Webhook events that should trigger the workflow.",
                    placeholder="push,pull_request,issues",
                ),
            ),
            tags=("webhook", "repository"),
        ),
    ),
    sort_order=20,
)
