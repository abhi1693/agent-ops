from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from automation.catalog.registry import WorkflowCatalogRegistry

@dataclass(frozen=True)
class ParameterOptionDefinition:
    value: str
    label: str
    description: str = ""

    def serialize(self) -> dict[str, str]:
        return {
            "value": self.value,
            "label": self.label,
            "description": self.description,
        }


@dataclass(frozen=True)
class ParameterDefinition:
    key: str
    label: str
    value_type: str
    required: bool = False
    description: str = ""
    default: Any | None = None
    placeholder: str = ""
    help_text: str = ""
    options: tuple[ParameterOptionDefinition, ...] = ()
    show_if: tuple[dict[str, Any], ...] = ()

    def serialize(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value_type": self.value_type,
            "required": self.required,
            "description": self.description,
            "default": self.default,
            "placeholder": self.placeholder,
            "help_text": self.help_text,
            "options": [option.serialize() for option in self.options],
            "show_if": [dict(condition) for condition in self.show_if],
        }


@dataclass(frozen=True)
class ConnectionTypeDefinition:
    id: str
    integration_id: str
    label: str
    auth_kind: str = "none"
    description: str = ""
    parameter_schema: tuple[ParameterDefinition, ...] = ()

    def register(self, registry: WorkflowCatalogRegistry) -> None:
        if self.id in registry["connection_types"]:
            raise ValueError(f'Workflow connection type "{self.id}" has already been registered.')
        registry["connection_types"][self.id] = self

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "integration_id": self.integration_id,
            "label": self.label,
            "auth_kind": self.auth_kind,
            "description": self.description,
            "parameter_schema": [item.serialize() for item in self.parameter_schema],
        }


@dataclass(frozen=True)
class CatalogNodeDefinition:
    id: str
    integration_id: str
    mode: str
    kind: str
    label: str
    description: str
    icon: str
    resource: str | None = None
    operation: str | None = None
    group: str | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    connection_type: str | None = None
    parameter_schema: tuple[ParameterDefinition, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        valid_modes = {"core", "action", "trigger"}
        if self.mode not in valid_modes:
            raise ValueError(f'Workflow node "{self.id}" has invalid mode "{self.mode}".')

        expected_prefix = f"{self.integration_id}."
        if not self.id.startswith(expected_prefix):
            raise ValueError(
                f'Workflow node "{self.id}" must use the "{expected_prefix}" prefix for integration '
                f'"{self.integration_id}".'
            )

    def register(self, registry: WorkflowCatalogRegistry) -> None:
        if self.id in registry["node_types"]:
            raise ValueError(f'Workflow catalog node "{self.id}" has already been registered.')
        registry["node_types"][self.id] = self
        for capability in self.capabilities:
            registry["capability_index"][capability].add(self.id)

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "integration_id": self.integration_id,
            "mode": self.mode,
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "resource": self.resource,
            "operation": self.operation,
            "group": self.group,
            "capabilities": sorted(self.capabilities),
            "connection_type": self.connection_type,
            "parameter_schema": [item.serialize() for item in self.parameter_schema],
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class IntegrationApp:
    id: str
    label: str
    description: str
    icon: str
    category_tags: tuple[str, ...] = ()
    connection_types: tuple[ConnectionTypeDefinition, ...] = ()
    actions: tuple[CatalogNodeDefinition, ...] = ()
    triggers: tuple[CatalogNodeDefinition, ...] = ()
    sort_order: int = 1000

    @property
    def nodes(self) -> tuple[CatalogNodeDefinition, ...]:
        return (*self.triggers, *self.actions)

    def register(self, registry: WorkflowCatalogRegistry) -> None:
        if self.id in registry["integration_apps"]:
            raise ValueError(f'Workflow integration app "{self.id}" has already been registered.')

        for connection_type in self.connection_types:
            if connection_type.integration_id != self.id:
                raise ValueError(
                    f'Connection type "{connection_type.id}" must belong to integration "{self.id}".'
                )
        for node in self.nodes:
            if node.integration_id != self.id:
                raise ValueError(f'Node "{node.id}" must belong to integration "{self.id}".')

        registry["integration_apps"][self.id] = self
        for category_tag in self.category_tags:
            registry["category_index"][category_tag].add(self.id)
        for connection_type in self.connection_types:
            connection_type.register(registry)
        for node in self.nodes:
            node.register(registry)

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "category_tags": list(self.category_tags),
            "connection_types": [connection_type.serialize() for connection_type in self.connection_types],
            "actions": [action.serialize() for action in self.actions],
            "triggers": [trigger.serialize() for trigger in self.triggers],
            "sort_order": self.sort_order,
        }


__all__ = (
    "CatalogNodeDefinition",
    "ConnectionTypeDefinition",
    "IntegrationApp",
    "ParameterDefinition",
    "ParameterOptionDefinition",
)
