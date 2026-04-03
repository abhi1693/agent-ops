from __future__ import annotations

import hmac
import hashlib

from django.core.exceptions import ValidationError

from automation.catalog.connections import resolve_workflow_connection
from automation.catalog.services import get_catalog_node
from automation.nodes.base import WorkflowNodeExecutionContext
from automation.tools.base import _coerce_csv_strings
from automation.triggers.webhook_utils import get_request_meta, parse_json_body


def _catalog_webhook_runtime(workflow, node: dict, request) -> WorkflowNodeExecutionContext:
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
    runtime = _catalog_webhook_runtime(workflow, node, request)
    resolved = resolve_workflow_connection(
        runtime,
        connection_id=node.get("config", {}).get("connection_id"),
        expected_connection_type="github.oauth2",
    )
    if not resolved.secret_value:
        raise ValidationError(
            {"trigger": f'Connection "{resolved.connection.name}" must include a webhook signing secret.'}
        )

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise ValidationError({"trigger": 'Missing required GitHub signature header "X-Hub-Signature-256".'})

    expected_signature = "sha256=" + hmac.new(
        resolved.secret_value.encode("utf-8"),
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
    if resolved.secret_meta is not None:
        metadata["secret"] = resolved.secret_meta

    return node["type"], payload, metadata


def prepare_catalog_webhook_request(*, workflow, node: dict, request):
    node_type = node.get("type")
    node_definition = get_catalog_node(node_type)
    if node_definition is None:
        raise ValidationError({"trigger": f'Unsupported trigger node type "{node_type}".'})
    if "trigger" != node_definition.kind:
        raise ValidationError({"trigger": f'Node type "{node_definition.id}" does not support webhook delivery.'})
    if node_definition.id == "github.trigger.webhook":
        return _prepare_github_webhook_request(workflow=workflow, node=node, request=request)
    raise ValidationError({"trigger": f'Node type "{node_definition.id}" does not support webhook delivery yet.'})
