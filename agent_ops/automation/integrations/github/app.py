import hashlib
import hmac

from django.core.exceptions import ValidationError

from automation.catalog.capabilities import CAPABILITY_TRIGGER_WEBHOOK
from automation.catalog.connections import resolve_workflow_connection_fields
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionSlotDefinition,
    ConnectionTypeDefinition,
    IntegrationApp,
    ParameterDefinition,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import _coerce_csv_strings
from automation.triggers.webhook_utils import get_request_meta, parse_json_body


def _execute_github_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
        },
    )


def _catalog_webhook_runtime(workflow, node: dict) -> WorkflowNodeExecutionContext:
    return WorkflowNodeExecutionContext(
        workflow=workflow,
        node=node,
        config=node.get("config") or {},
        next_node_id=None,
        connected_nodes_by_port={},
        context={},
        secret_paths=set(),
        secret_values=[],
        render_template=lambda template, context: template,
        get_path_value=lambda data, path: None,
        set_path_value=lambda data, path, value: None,
        resolve_scoped_secret=lambda *args, **kwargs: None,
        evaluate_condition=lambda operator, left, right: False,
    )


def _prepare_github_webhook_request(*, workflow, node: dict, request) -> tuple[str, dict, dict]:
    runtime = _catalog_webhook_runtime(workflow, node)
    resolved = resolve_workflow_connection_fields(
        runtime,
        connection_id=node.get("config", {}).get("connection_id"),
        expected_connection_type="github.oauth2",
    )
    webhook_secret = resolved.values.get("webhook_secret")
    if not isinstance(webhook_secret, str) or not webhook_secret:
        raise ValidationError(
            {"trigger": f'Connection "{resolved.connection.name}" must include field "webhook_secret".'}
        )

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise ValidationError({"trigger": 'Missing required GitHub signature header "X-Hub-Signature-256".'})

    expected_signature = "sha256=" + hmac.new(
        webhook_secret.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValidationError({"trigger": "GitHub webhook signature validation failed."})

    payload = parse_json_body(type("WebhookContext", (), {"body": request.body})())
    event_name = request.headers.get("X-GitHub-Event")
    if not event_name:
        raise ValidationError({"trigger": 'Missing required GitHub event header "X-GitHub-Event".'})

    allowed_events = _coerce_csv_strings(
        node.get("config", {}).get("events"),
        field_name="events",
        node_id=node["id"],
        default=[],
    )
    if allowed_events and event_name not in allowed_events:
        raise ValidationError({"trigger": f'GitHub event "{event_name}" is not allowed by this trigger.'})

    owner = (node.get("config", {}).get("owner") or "").strip()
    repository = (node.get("config", {}).get("repository") or "").strip()
    if owner or repository:
        full_name = ((payload.get("repository") or {}).get("full_name") or "").strip()
        expected_full_name = f"{owner}/{repository}".strip("/")
        if not full_name or full_name.lower() != expected_full_name.lower():
            raise ValidationError(
                {"trigger": f'GitHub webhook repository "{full_name or "unknown"}" does not match "{expected_full_name}".'}
            )

    metadata = {
        **get_request_meta(request),
        "source": "github_webhook",
        "event": event_name,
        "delivery": request.headers.get("X-GitHub-Delivery"),
        "hook_id": request.headers.get("X-GitHub-Hook-ID"),
        "connection": {
            "id": str(resolved.connection.pk),
            "name": resolved.connection.name,
            "type": resolved.connection.connection_type,
        },
    }
    secret_meta = resolved.secret_metas.get("webhook_secret")
    if secret_meta is not None:
        metadata["secret"] = secret_meta

    return node["type"], payload, metadata


GITHUB_CONNECTION = ConnectionTypeDefinition(
    id="github.oauth2",
    integration_id="github",
    label="GitHub",
    auth_kind="oauth2",
    description="Reusable GitHub account connection for repository and webhook operations.",
    field_schema=(
        ParameterDefinition(
            key="webhook_secret",
            label="Webhook Secret",
            value_type="secret_ref",
            required=False,
            description="Optional signing secret used to validate GitHub webhook deliveries.",
            placeholder="GITHUB_WEBHOOK_SECRET",
        ),
    ),
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
            runtime_executor=_execute_github_trigger,
            webhook_request_preparer=_prepare_github_webhook_request,
            connection_slots=(
                ConnectionSlotDefinition(
                    key="connection_id",
                    label="Connection",
                    allowed_connection_types=(GITHUB_CONNECTION.id,),
                    required=True,
                    description="Reusable GitHub connection containing the webhook signing secret.",
                ),
            ),
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
