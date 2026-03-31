from __future__ import annotations

import hashlib
import hmac

from django.core.exceptions import ValidationError

from automation.auth import resolve_workflow_secret
from automation.nodes.adapters import trigger_definition_as_node_implementation

from automation.triggers.base import (
    WorkflowTriggerDefinition,
    WorkflowTriggerRequestContext,
    _coerce_csv_strings,
    _validate_optional_string,
    _validate_required_string,
    trigger_text_field,
)
from automation.triggers.webhook_utils import get_request_meta, parse_json_body


def _validate_github_webhook_trigger(config: dict[str, object], node_id: str) -> None:
    _validate_required_string(config, "signature_secret_name", node_id=node_id)
    _validate_optional_string(config, "signature_secret_provider", node_id=node_id)
    _validate_optional_string(config, "auth_secret_group_id", node_id=node_id)
    _coerce_csv_strings(config.get("events"), field_name="events", node_id=node_id, default=[])


def _handle_github_webhook(context: WorkflowTriggerRequestContext) -> tuple[dict[str, object], dict[str, object]]:
    secret = resolve_workflow_secret(
        context.workflow,
        name=context.config["signature_secret_name"],
        provider=context.config.get("signature_secret_provider"),
        secret_group_id=context.config.get("auth_secret_group_id"),
        error_field="trigger",
    )
    secret_value = secret.get_value(obj=context.workflow)
    if not isinstance(secret_value, str) or not secret_value:
        raise ValidationError({"trigger": f'Secret "{secret.name}" must resolve to a non-empty string.'})

    signature = context.request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise ValidationError({"trigger": 'Missing required GitHub signature header "X-Hub-Signature-256".'})
    expected_signature = "sha256=" + hmac.new(
        secret_value.encode("utf-8"),
        context.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValidationError({"trigger": "GitHub webhook signature validation failed."})

    payload = parse_json_body(context)
    event_name = context.request.headers.get("X-GitHub-Event")
    if not event_name:
        raise ValidationError({"trigger": 'Missing required GitHub event header "X-GitHub-Event".'})

    allowed_events = _coerce_csv_strings(
        context.config.get("events"),
        field_name="events",
        node_id=context.node["id"],
        default=[],
    )
    if allowed_events and event_name not in allowed_events:
        raise ValidationError({"trigger": f'GitHub event "{event_name}" is not allowed by this trigger.'})

    metadata = {
        **get_request_meta(context.request),
        "source": "github_webhook",
        "event": event_name,
        "delivery": context.request.headers.get("X-GitHub-Delivery"),
        "hook_id": context.request.headers.get("X-GitHub-Hook-ID"),
        "secret": {
            "name": secret.name,
            "provider": secret.provider,
        },
    }
    return payload, metadata


TRIGGER_DEFINITION = WorkflowTriggerDefinition(
    name="github_webhook",
    label="GitHub webhook",
    description="Receive GitHub webhook deliveries with signature verification.",
    icon="mdi-github",
    category="Webhook",
    fields=(
        trigger_text_field(
            "signature_secret_name",
            "Signature secret name",
            placeholder="GITHUB_WEBHOOK_SECRET",
        ),
        trigger_text_field(
            "signature_secret_provider",
            "Signature secret provider",
            placeholder="environment-variable",
            help_text="Optional. Leave blank to search all enabled providers in scope.",
        ),
        trigger_text_field(
            "events",
            "Allowed events",
            placeholder="push,pull_request",
            help_text="Optional comma-separated allow-list. Leave blank to accept all GitHub events.",
        ),
    ),
    validator=_validate_github_webhook_trigger,
    webhook_handler=_handle_github_webhook,
)

NODE_IMPLEMENTATION = trigger_definition_as_node_implementation(TRIGGER_DEFINITION)
