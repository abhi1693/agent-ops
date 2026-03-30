from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from django.core.exceptions import ValidationError

from integrations.models import Secret


WorkflowTriggerValidator = Callable[[dict[str, Any], str], None]
WorkflowTriggerWebhookHandler = Callable[["WorkflowTriggerRequestContext"], tuple[dict[str, Any], dict[str, Any]]]


@dataclass(frozen=True)
class WorkflowTriggerDefinition:
    name: str
    label: str
    description: str
    icon: str = "mdi-play-circle-outline"
    category: str = "Built-in"
    config: dict[str, Any] = field(default_factory=dict)
    fields: tuple[dict[str, Any], ...] = ()
    validator: WorkflowTriggerValidator | None = None
    webhook_handler: WorkflowTriggerWebhookHandler | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "config": dict(self.config),
            "fields": [dict(field) for field in self.fields],
        }


@dataclass
class WorkflowTriggerRequestContext:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    request: Any
    body: bytes


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _raise_trigger_error(message: str) -> None:
    raise ValidationError({"trigger": message})


def _validate_optional_string(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" config.{key} must be a non-empty string.')


def _validate_required_string(config: dict[str, Any], key: str, *, node_id: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" must define config.{key}.')
    return value


def _coerce_csv_strings(value: Any, *, field_name: str, node_id: str, default: list[str] | None = None) -> list[str]:
    if value in (None, ""):
        return list(default or [])

    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        if items:
            return items
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must contain at least one value.')

    if isinstance(value, list):
        items = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                _raise_definition_error(
                    f'Node "{node_id}" config.{field_name} must contain non-empty strings.'
                )
            items.append(item.strip())
        return items

    _raise_definition_error(
        f'Node "{node_id}" config.{field_name} must be a comma-separated string or list of strings.'
    )


def normalize_workflow_trigger_config(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(config or {})
    trigger_type = normalized.get("type")
    if trigger_type in ("", None):
        normalized["type"] = "manual"
    return normalized


def normalize_workflow_definition_triggers(definition: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {"nodes": [], "edges": []}

    normalized_definition = dict(definition)
    normalized_nodes = []
    for node in definition.get("nodes", []):
        if not isinstance(node, dict):
            normalized_nodes.append(node)
            continue

        normalized_node = dict(node)
        if normalized_node.get("kind") == "trigger":
            normalized_node["config"] = normalize_workflow_trigger_config(normalized_node.get("config"))
        normalized_nodes.append(normalized_node)

    normalized_definition["nodes"] = normalized_nodes
    return normalized_definition


def _resolve_workflow_secret(workflow, *, name: str, provider: str | None = None) -> Secret:
    scope_candidates = []
    if workflow.environment_id:
        scope_candidates.append({"environment": workflow.environment})
    if workflow.workspace_id:
        scope_candidates.append({"workspace": workflow.workspace, "environment__isnull": True})
    if workflow.organization_id:
        scope_candidates.append(
            {
                "organization": workflow.organization,
                "workspace__isnull": True,
                "environment__isnull": True,
            }
        )

    for scope_filter in scope_candidates:
        queryset = Secret.objects.filter(enabled=True, name=name, **scope_filter).order_by("name")
        if provider:
            queryset = queryset.filter(provider=provider)
        secret = queryset.first()
        if secret is not None:
            return secret

    if provider:
        raise ValidationError({"trigger": f'No enabled secret named "{name}" with provider "{provider}" is available.'})
    raise ValidationError({"trigger": f'No enabled secret named "{name}" is available in this workflow scope.'})


def _get_request_meta(request) -> dict[str, Any]:
    return {
        "source_ip": request.META.get("REMOTE_ADDR"),
        "content_type": request.META.get("CONTENT_TYPE"),
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }


def _parse_json_body(context: WorkflowTriggerRequestContext) -> dict[str, Any]:
    if not context.body:
        return {}
    try:
        parsed = json.loads(context.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError({"trigger": "Webhook request body must be valid JSON."}) from exc
    if not isinstance(parsed, dict):
        raise ValidationError({"trigger": "Webhook request body must decode to a JSON object."})
    return parsed


def _validate_shared_secret_header(context: WorkflowTriggerRequestContext) -> dict[str, str]:
    secret_name = context.config["webhook_secret_name"]
    secret_provider = context.config.get("webhook_secret_provider")
    header_name = context.config.get("secret_header", "X-AgentOps-Webhook-Secret")
    header_value = context.request.headers.get(header_name)
    if not header_value:
        raise ValidationError({"trigger": f'Missing required webhook secret header "{header_name}".'})

    secret = _resolve_workflow_secret(
        context.workflow,
        name=secret_name,
        provider=secret_provider,
    )
    expected_value = secret.get_value(obj=context.workflow)
    if not isinstance(expected_value, str) or not expected_value:
        raise ValidationError({"trigger": f'Secret "{secret.name}" must resolve to a non-empty string.'})
    if not hmac.compare_digest(header_value, expected_value):
        raise ValidationError({"trigger": "Webhook secret validation failed."})
    return {"name": secret.name, "provider": secret.provider, "header_name": header_name}


def _validate_manual_trigger(config: dict[str, Any], node_id: str) -> None:
    _validate_optional_string(config, "type", node_id=node_id)


def _validate_alertmanager_webhook_trigger(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "webhook_secret_name", node_id=node_id)
    _validate_optional_string(config, "webhook_secret_provider", node_id=node_id)
    _validate_optional_string(config, "secret_header", node_id=node_id)


def _validate_kibana_webhook_trigger(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "webhook_secret_name", node_id=node_id)
    _validate_optional_string(config, "webhook_secret_provider", node_id=node_id)
    _validate_optional_string(config, "secret_header", node_id=node_id)


def _validate_github_webhook_trigger(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "signature_secret_name", node_id=node_id)
    _validate_optional_string(config, "signature_secret_provider", node_id=node_id)
    _coerce_csv_strings(config.get("events"), field_name="events", node_id=node_id, default=[])


def _handle_alertmanager_webhook(context: WorkflowTriggerRequestContext) -> tuple[dict[str, Any], dict[str, Any]]:
    secret_meta = _validate_shared_secret_header(context)
    payload = _parse_json_body(context)
    metadata = {
        **_get_request_meta(context.request),
        "source": "alertmanager_webhook",
        "secret": secret_meta,
    }
    return payload, metadata


def _handle_kibana_webhook(context: WorkflowTriggerRequestContext) -> tuple[dict[str, Any], dict[str, Any]]:
    secret_meta = _validate_shared_secret_header(context)
    payload = _parse_json_body(context)
    metadata = {
        **_get_request_meta(context.request),
        "source": "kibana_webhook",
        "secret": secret_meta,
    }
    return payload, metadata


def _handle_github_webhook(context: WorkflowTriggerRequestContext) -> tuple[dict[str, Any], dict[str, Any]]:
    secret = _resolve_workflow_secret(
        context.workflow,
        name=context.config["signature_secret_name"],
        provider=context.config.get("signature_secret_provider"),
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

    payload = _parse_json_body(context)
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
        **_get_request_meta(context.request),
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


WORKFLOW_TRIGGER_REGISTRY: dict[str, WorkflowTriggerDefinition] = {
    "manual": WorkflowTriggerDefinition(
        name="manual",
        label="Manual",
        description="Run the workflow from the UI or API with a manually supplied JSON payload.",
        icon="mdi-play-circle-outline",
        validator=_validate_manual_trigger,
    ),
    "alertmanager_webhook": WorkflowTriggerDefinition(
        name="alertmanager_webhook",
        label="Alertmanager webhook",
        description="Receive alert batches from Prometheus Alertmanager via webhook.",
        icon="mdi-bell-ring-outline",
        category="Webhook",
        fields=(
            {
                "key": "webhook_secret_name",
                "label": "Webhook secret name",
                "type": "text",
                "placeholder": "ALERTMANAGER_WEBHOOK_SECRET",
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
        validator=_validate_alertmanager_webhook_trigger,
        webhook_handler=_handle_alertmanager_webhook,
    ),
    "kibana_webhook": WorkflowTriggerDefinition(
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
    ),
    "github_webhook": WorkflowTriggerDefinition(
        name="github_webhook",
        label="GitHub webhook",
        description="Receive GitHub webhook deliveries with signature verification.",
        icon="mdi-github",
        category="Webhook",
        fields=(
            {
                "key": "signature_secret_name",
                "label": "Signature secret name",
                "type": "text",
                "placeholder": "GITHUB_WEBHOOK_SECRET",
            },
            {
                "key": "signature_secret_provider",
                "label": "Signature secret provider",
                "type": "text",
                "placeholder": "environment-variable",
                "help_text": "Optional. Leave blank to search all enabled providers in scope.",
            },
            {
                "key": "events",
                "label": "Allowed events",
                "type": "text",
                "placeholder": "push,pull_request",
                "help_text": "Optional comma-separated allow-list. Leave blank to accept all GitHub events.",
            },
        ),
        validator=_validate_github_webhook_trigger,
        webhook_handler=_handle_github_webhook,
    ),
}

WORKFLOW_TRIGGER_DEFINITIONS = tuple(
    trigger_definition.serialize() for trigger_definition in WORKFLOW_TRIGGER_REGISTRY.values()
)


def get_workflow_trigger_definition(name: str) -> WorkflowTriggerDefinition | None:
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
