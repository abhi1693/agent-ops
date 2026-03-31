from __future__ import annotations

from automation.triggers.base import (
    WorkflowTriggerDefinition,
    WorkflowTriggerRequestContext,
    _validate_optional_string,
    _validate_required_string,
    trigger_text_field,
)
from automation.triggers.webhook_utils import get_request_meta, parse_json_body, validate_shared_secret_header


def _validate_alertmanager_webhook_trigger(config: dict[str, object], node_id: str) -> None:
    _validate_required_string(config, "webhook_secret_name", node_id=node_id)
    _validate_optional_string(config, "webhook_secret_provider", node_id=node_id)
    _validate_optional_string(config, "secret_header", node_id=node_id)
    _validate_optional_string(config, "auth_secret_group_id", node_id=node_id)


def _handle_alertmanager_webhook(context: WorkflowTriggerRequestContext) -> tuple[dict[str, object], dict[str, object]]:
    secret_meta = validate_shared_secret_header(context)
    payload = parse_json_body(context)
    metadata = {
        **get_request_meta(context.request),
        "source": "alertmanager_webhook",
        "secret": secret_meta,
    }
    return payload, metadata


TRIGGER_DEFINITION = WorkflowTriggerDefinition(
    name="alertmanager_webhook",
    label="Alertmanager webhook",
    description="Receive alert batches from Prometheus Alertmanager via webhook.",
    icon="mdi-bell-ring-outline",
    category="Webhook",
    fields=(
        trigger_text_field(
            "webhook_secret_name",
            "Webhook secret name",
            placeholder="ALERTMANAGER_WEBHOOK_SECRET",
        ),
        trigger_text_field(
            "webhook_secret_provider",
            "Webhook secret provider",
            placeholder="environment-variable",
            help_text="Optional. Leave blank to search all enabled providers in scope.",
        ),
        trigger_text_field(
            "secret_header",
            "Secret header",
            placeholder="X-AgentOps-Webhook-Secret",
        ),
    ),
    validator=_validate_alertmanager_webhook_trigger,
    webhook_handler=_handle_alertmanager_webhook,
)
