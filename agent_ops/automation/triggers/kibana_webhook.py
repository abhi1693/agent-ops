from __future__ import annotations

from .base import (
    WorkflowTriggerDefinition,
    WorkflowTriggerRequestContext,
    _validate_optional_string,
    _validate_required_string,
)
from .webhook_utils import get_request_meta, parse_json_body, validate_shared_secret_header


def _validate_kibana_webhook_trigger(config: dict[str, object], node_id: str) -> None:
    _validate_required_string(config, "webhook_secret_name", node_id=node_id)
    _validate_optional_string(config, "webhook_secret_provider", node_id=node_id)
    _validate_optional_string(config, "secret_header", node_id=node_id)
    _validate_optional_string(config, "auth_secret_group_id", node_id=node_id)


def _handle_kibana_webhook(context: WorkflowTriggerRequestContext) -> tuple[dict[str, object], dict[str, object]]:
    secret_meta = validate_shared_secret_header(context)
    payload = parse_json_body(context)
    metadata = {
        **get_request_meta(context.request),
        "source": "kibana_webhook",
        "secret": secret_meta,
    }
    return payload, metadata


TRIGGER_DEFINITION = WorkflowTriggerDefinition(
    name="kibana_webhook",
    label="Kibana webhook",
    description="Receive Kibana rule actions via webhook with a shared secret header.",
    icon="mdi-view-dashboard-outline",
    category="Webhook",
    fields=(
        {
            "key": "webhook_secret_name",
            "label": "Webhook secret name",
            "type": "text",
            "placeholder": "KIBANA_WEBHOOK_SECRET",
        },
        {
            "key": "webhook_secret_provider",
            "label": "Webhook secret provider",
            "type": "text",
            "placeholder": "environment-variable",
            "help_text": "Optional. Leave blank to search all enabled providers in scope.",
        },
        {
            "key": "secret_header",
            "label": "Secret header",
            "type": "text",
            "placeholder": "X-AgentOps-Webhook-Secret",
        },
    ),
    validator=_validate_kibana_webhook_trigger,
    webhook_handler=_handle_kibana_webhook,
)
