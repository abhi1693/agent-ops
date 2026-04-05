from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from automation.catalog.registry import WorkflowCatalogRegistry


CatalogNodeRuntimeValidator = Callable[..., None]
CatalogNodeRuntimeExecutor = Callable[..., Any]
CatalogWebhookRequestPreparer = Callable[..., tuple[str, dict[str, Any], dict[str, Any]]]


@dataclass(frozen=True)
class OutputPortDefinition:
    key: str
    label: str
    description: str = ""

    def serialize(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
        }


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
    field_type: str | None = None
    required: bool = False
    description: str = ""
    default: Any | None = None
    placeholder: str = ""
    help_text: str = ""
    hint: str = ""
    options: tuple[ParameterOptionDefinition, ...] = ()
    display_options: dict[str, dict[str, tuple[Any, ...] | list[Any]]] = field(default_factory=dict)
    ui_group: str | None = None
    binding: str | None = None
    rows: int | None = None
    is_node_setting: bool = False
    no_data_expression: bool = False
    requires_data_path: str | None = None
    options_by_field: dict[str, dict[str, tuple[ParameterOptionDefinition, ...]]] = field(default_factory=dict)

    def serialize(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value_type": self.value_type,
            "field_type": self.field_type,
            "required": self.required,
            "description": self.description,
            "default": self.default,
            "placeholder": self.placeholder,
            "help_text": self.help_text,
            "hint": self.hint,
            "options": [option.serialize() for option in self.options],
            "display_options": {
                condition_kind: {
                    condition_key: list(condition_values)
                    for condition_key, condition_values in condition_map.items()
                }
                for condition_kind, condition_map in self.display_options.items()
            },
            "ui_group": self.ui_group,
            "binding": self.binding,
            "rows": self.rows,
            "is_node_setting": self.is_node_setting,
            "no_data_expression": self.no_data_expression,
            "requires_data_path": self.requires_data_path,
            "options_by_field": {
                config_key: {
                    config_value: [option.serialize() for option in options]
                    for config_value, options in option_map.items()
                }
                for config_key, option_map in self.options_by_field.items()
            },
        }


@dataclass(frozen=True)
class ConnectionSlotDefinition:
    key: str
    label: str
    allowed_connection_types: tuple[str, ...]
    required: bool = False
    description: str = ""
    multiple: bool = False

    def serialize(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "allowed_connection_types": list(self.allowed_connection_types),
            "required": self.required,
            "description": self.description,
            "multiple": self.multiple,
        }


@dataclass(frozen=True)
class ConnectionHttpHeaderDefinition:
    field_key: str
    header_name: str
    prefix: str = ""
    prefix_field_key: str | None = None
    prefix_separator: str = ""
    required: bool = False

    def serialize(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "header_name": self.header_name,
            "prefix": self.prefix,
            "prefix_field_key": self.prefix_field_key,
            "prefix_separator": self.prefix_separator,
            "required": self.required,
        }


@dataclass(frozen=True)
class ConnectionHttpQueryDefinition:
    field_key: str
    query_param: str
    required: bool = False

    def serialize(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "query_param": self.query_param,
            "required": self.required,
        }


@dataclass(frozen=True)
class ConnectionHttpAuthDefinition:
    basic_username_field: str | None = None
    basic_password_field: str | None = None
    headers: tuple[ConnectionHttpHeaderDefinition, ...] = ()
    query: tuple[ConnectionHttpQueryDefinition, ...] = ()
    enabled_when_field: str | None = None
    enabled_when_values: tuple[str, ...] = ()

    def serialize(self) -> dict[str, Any]:
        return {
            "basic_username_field": self.basic_username_field,
            "basic_password_field": self.basic_password_field,
            "headers": [header.serialize() for header in self.headers],
            "query": [query.serialize() for query in self.query],
            "enabled_when_field": self.enabled_when_field,
            "enabled_when_values": list(self.enabled_when_values),
        }


@dataclass(frozen=True)
class ConnectionOAuth2Definition:
    token_url_field: str
    client_id_field: str | None = None
    client_secret_field: str | None = None
    access_token_state_key: str = "access_token"
    refresh_token_state_key: str = "refresh_token"
    expires_at_state_key: str = "expires_at"
    account_id_state_key: str | None = None
    access_token_header_name: str = "Authorization"
    access_token_prefix: str = "Bearer "
    enabled_when_field: str | None = None
    enabled_when_values: tuple[str, ...] = ()

    def serialize(self) -> dict[str, Any]:
        return {
            "token_url_field": self.token_url_field,
            "client_id_field": self.client_id_field,
            "client_secret_field": self.client_secret_field,
            "access_token_state_key": self.access_token_state_key,
            "refresh_token_state_key": self.refresh_token_state_key,
            "expires_at_state_key": self.expires_at_state_key,
            "account_id_state_key": self.account_id_state_key,
            "access_token_header_name": self.access_token_header_name,
            "access_token_prefix": self.access_token_prefix,
            "enabled_when_field": self.enabled_when_field,
            "enabled_when_values": list(self.enabled_when_values),
        }


@dataclass(frozen=True)
class ConnectionTypeDefinition:
    id: str
    integration_id: str
    label: str
    auth_kind: str = "none"
    description: str = ""
    parameter_schema: tuple[ParameterDefinition, ...] = ()
    field_schema: tuple[ParameterDefinition, ...] = ()
    state_schema: tuple[ParameterDefinition, ...] = ()
    http_auth: ConnectionHttpAuthDefinition | None = None
    oauth2: ConnectionOAuth2Definition | None = None

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
            "field_schema": [item.serialize() for item in self.field_schema],
            "state_schema": [item.serialize() for item in self.state_schema],
            "http_auth": self.http_auth.serialize() if self.http_auth is not None else None,
            "oauth2": self.oauth2.serialize() if self.oauth2 is not None else None,
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
    type_version: int = 1
    default_name: str | None = None
    default_color: str | None = None
    subtitle: str | None = None
    node_group: tuple[str, ...] = ()
    app_id: str | None = None
    app_label: str | None = None
    app_description: str | None = None
    app_icon: str | None = None
    resource: str | None = None
    operation: str | None = None
    group: str | None = None
    catalog_section: str | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    output_ports: tuple[OutputPortDefinition, ...] = ()
    connection_type: str | None = None
    connection_slots: tuple[ConnectionSlotDefinition, ...] = ()
    config_defaults: dict[str, Any] = field(default_factory=dict)
    parameter_schema: tuple[ParameterDefinition, ...] = ()
    runtime_validator: CatalogNodeRuntimeValidator | None = None
    runtime_executor: CatalogNodeRuntimeExecutor | None = None
    webhook_request_preparer: CatalogWebhookRequestPreparer | None = None
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

        if len({slot.key for slot in self.connection_slots}) != len(self.connection_slots):
            raise ValueError(f'Workflow node "{self.id}" defines duplicate connection slot keys.')

        if len({port.key for port in self.output_ports}) != len(self.output_ports):
            raise ValueError(f'Workflow node "{self.id}" defines duplicate output port keys.')

        if self.connection_type is not None and self.connection_slots:
            primary_slot = self.connection_slots[0]
            if self.connection_type not in primary_slot.allowed_connection_types:
                raise ValueError(
                    f'Workflow node "{self.id}" connection_type "{self.connection_type}" must be allowed by '
                    f'primary connection slot "{primary_slot.key}".'
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
            "type_version": self.type_version,
            "default_name": self.default_name,
            "default_color": self.default_color,
            "subtitle": self.subtitle,
            "node_group": list(self.node_group),
            "app_id": self.app_id,
            "app_label": self.app_label,
            "app_description": self.app_description,
            "app_icon": self.app_icon,
            "resource": self.resource,
            "operation": self.operation,
            "group": self.group,
            "catalog_section": self.catalog_section,
            "capabilities": sorted(self.capabilities),
            "output_ports": [port.serialize() for port in self.output_ports],
            "connection_type": self.connection_type,
            "connection_slots": [slot.serialize() for slot in self.connection_slots],
            "config_defaults": dict(self.config_defaults),
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
    "ConnectionSlotDefinition",
    "ConnectionTypeDefinition",
    "IntegrationApp",
    "OutputPortDefinition",
    "ParameterDefinition",
    "ParameterOptionDefinition",
)
