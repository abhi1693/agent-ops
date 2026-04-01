from __future__ import annotations

from automation.nodes.adapters import trigger_definition_as_node_implementation
from automation.triggers.base import (
    WorkflowTriggerDefinition,
    WorkflowTriggerRequestContext,
    _validate_optional_secret_group_id,
    _validate_optional_string,
    _validate_required_string,
    trigger_text_field,
)
from automation.triggers.webhook_utils import get_request_meta, parse_json_body, validate_shared_secret_header


def _validate_kibana_webhook_trigger(config: dict[str, object], node_id: str) -> None:
    _validate_optional_string(config, "secret_header", node_id=node_id)
    _validate_required_string(config, "secret_name", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)


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
        trigger_text_field(
            "secret_name",
            "Secret name",
            placeholder="KIBANA_WEBHOOK_SECRET",
        ),
        trigger_text_field(
            "secret_group_id",
            "Secret group",
            placeholder="Use workflow secret group",
            help_text="Optional. Override the workflow secret group for this trigger with a scoped secret group ID.",
        ),
        trigger_text_field(
            "secret_header",
            "Secret header",
            placeholder="X-AgentOps-Webhook-Secret",
        ),
    ),
    validator=_validate_kibana_webhook_trigger,
    webhook_handler=_handle_kibana_webhook,
)

NODE_IMPLEMENTATION = trigger_definition_as_node_implementation(TRIGGER_DEFINITION)
