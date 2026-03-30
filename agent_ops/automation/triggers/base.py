from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from django.core.exceptions import ValidationError


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
    auth_secret_group_id = normalized.get("auth_secret_group_id")
    if trigger_type in ("", None):
        normalized["type"] = "manual"
    if auth_secret_group_id in ("", None):
        normalized.pop("auth_secret_group_id", None)
    elif not isinstance(auth_secret_group_id, str):
        normalized["auth_secret_group_id"] = str(auth_secret_group_id)
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
