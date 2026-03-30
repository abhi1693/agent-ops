from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from .alertmanager_webhook import TRIGGER_DEFINITION as ALERTMANAGER_WEBHOOK_TRIGGER
from .base import (
    WorkflowTriggerRequestContext,
    normalize_workflow_trigger_config,
    _raise_definition_error,
)
from .github_webhook import TRIGGER_DEFINITION as GITHUB_WEBHOOK_TRIGGER
from .kibana_webhook import TRIGGER_DEFINITION as KIBANA_WEBHOOK_TRIGGER
from .manual import TRIGGER_DEFINITION as MANUAL_TRIGGER


WORKFLOW_TRIGGER_REGISTRY = {
    trigger_definition.name: trigger_definition
    for trigger_definition in (
        MANUAL_TRIGGER,
        ALERTMANAGER_WEBHOOK_TRIGGER,
        KIBANA_WEBHOOK_TRIGGER,
        GITHUB_WEBHOOK_TRIGGER,
    )
}

WORKFLOW_TRIGGER_DEFINITIONS = tuple(
    trigger_definition.serialize() for trigger_definition in WORKFLOW_TRIGGER_REGISTRY.values()
)


def get_workflow_trigger_definition(name: str):
    return WORKFLOW_TRIGGER_REGISTRY.get(name)


def validate_workflow_trigger_config(config: dict[str, Any], *, node_id: str) -> dict[str, Any]:
    normalized = normalize_workflow_trigger_config(config)
    trigger_type = normalized.get("type")
    if not isinstance(trigger_type, str) or not trigger_type.strip():
        _raise_definition_error(f'Node "{node_id}" must define config.type.')

    trigger_definition = get_workflow_trigger_definition(trigger_type)
    if trigger_definition is None:
        available_names = ", ".join(sorted(WORKFLOW_TRIGGER_REGISTRY))
        _raise_definition_error(
            f'Node "{node_id}" config.type must be one of: {available_names}.'
        )

    if trigger_definition.validator is not None:
        trigger_definition.validator(normalized, node_id)

    return normalized


def prepare_webhook_trigger_request(*, workflow, node: dict[str, Any], request) -> tuple[str, dict[str, Any], dict[str, Any]]:
    normalized = validate_workflow_trigger_config(node.get("config") or {}, node_id=node["id"])
    trigger_type = normalized["type"]
    trigger_definition = get_workflow_trigger_definition(trigger_type)
    if trigger_definition is None or trigger_definition.webhook_handler is None:
        raise ValidationError({"trigger": f'Trigger type "{trigger_type}" does not support webhook delivery.'})

    return (
        trigger_type,
        *trigger_definition.webhook_handler(
            WorkflowTriggerRequestContext(
                workflow=workflow,
                node=node,
                config=normalized,
                request=request,
                body=request.body,
            )
        ),
    )
