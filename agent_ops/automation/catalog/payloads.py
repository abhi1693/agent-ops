from __future__ import annotations

from typing import Any

from automation.catalog.capabilities import CAPABILITY_AGENT_MODEL
from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition, ParameterOptionDefinition
from automation.catalog.services import get_workflow_catalog


def _stringify_option_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _serialize_field_option(option: ParameterOptionDefinition) -> dict[str, str]:
    return {
        "label": option.label,
        "value": _stringify_option_value(option.value),
    }


def _build_boolean_options() -> list[dict[str, str]]:
    return [
        {"label": "True", "value": "true"},
        {"label": "False", "value": "false"},
    ]


def _build_visible_when(parameter: ParameterDefinition) -> dict[str, list[str]] | None:
    if not parameter.show_if:
        return None

    normalized: dict[str, list[str]] = {}
    for condition in parameter.show_if:
        for key, value in condition.items():
            if isinstance(value, (list, tuple)):
                normalized[key] = [_stringify_option_value(item) for item in value]
            else:
                normalized[key] = [_stringify_option_value(value)]
    return normalized or None


def _field_type_for_parameter(parameter: ParameterDefinition) -> str:
    if parameter.value_type == "node_ref":
        return "node_target"
    if parameter.options or parameter.value_type == "boolean":
        return "select"
    if parameter.value_type in {"json", "text"}:
        return "textarea"
    return "text"


def _serialize_parameter(parameter: ParameterDefinition) -> dict[str, Any]:
    options = [_serialize_field_option(option) for option in parameter.options]
    if parameter.value_type == "boolean" and not options:
        options = _build_boolean_options()

    payload = {
        "key": parameter.key,
        "label": parameter.label,
        "type": _field_type_for_parameter(parameter),
        "help_text": parameter.help_text or parameter.description,
        "placeholder": parameter.placeholder,
    }
    if parameter.value_type == "node_ref":
        payload["binding"] = "path"
    elif parameter.value_type in {"text", "json"}:
        payload["binding"] = "template"
    visible_when = _build_visible_when(parameter)
    if visible_when:
        payload["visible_when"] = visible_when
    if options:
        payload["options"] = options
    if parameter.value_type in {"json", "text"}:
        payload["rows"] = 4
    return payload


def _serialize_default_value(value: Any) -> Any:
    return value


def _default_config_for_node(node: CatalogNodeDefinition) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for parameter in node.parameter_schema:
        if parameter.default is not None:
            config[parameter.key] = _serialize_default_value(parameter.default)
    return config


def _catalog_section_for_node(node: CatalogNodeDefinition) -> str:
    if node.mode == "trigger" or node.kind == "trigger":
        return "triggers"
    if node.integration_id == "core" and node.id == "core.set":
        return "data"
    if node.integration_id == "core":
        return "flow"
    return "apps"


def _ui_kind_for_node(node: CatalogNodeDefinition) -> str:
    if node.mode == "trigger" or node.kind == "trigger":
        return "trigger"
    if node.kind == "agent":
        return "agent"
    if node.kind == "output":
        return "response"
    if node.kind == "control":
        return "condition"
    return "tool"


def _category_for_ui_kind(kind: str) -> str:
    if kind == "trigger":
        return "entry_point"
    if kind == "condition":
        return "control_flow"
    if kind == "response":
        return "outcome"
    return "processing"


def _app_metadata_for_node(node: CatalogNodeDefinition) -> dict[str, str]:
    if node.integration_id == "core":
        return {
            "app_description": "Core workflow control and orchestration nodes.",
            "app_icon": "mdi-toy-brick-outline",
            "app_id": "core",
            "app_label": "Core",
        }

    app = get_workflow_catalog()["integration_apps"][node.integration_id]
    return {
        "app_description": app.description,
        "app_icon": app.icon,
        "app_id": app.id,
        "app_label": app.label,
    }


def serialize_catalog_node_for_designer(node: CatalogNodeDefinition) -> dict[str, Any]:
    ui_kind = _ui_kind_for_node(node)
    payload = {
        **_app_metadata_for_node(node),
        "capabilities": sorted(node.capabilities),
        "catalog_section": _catalog_section_for_node(node),
        "category": _category_for_ui_kind(ui_kind),
        "config": _default_config_for_node(node),
        "connection_type": node.connection_type,
        "description": node.description,
        "fields": [_serialize_parameter(parameter) for parameter in node.parameter_schema],
        "icon": node.icon,
        "kind": ui_kind,
        "label": node.label,
        "tags": list(node.tags),
        "type": node.id,
        "typeVersion": 1,
    }
    if CAPABILITY_AGENT_MODEL in node.capabilities:
        payload["is_model"] = True
    return payload


def build_workflow_catalog_payload() -> dict[str, list[dict[str, Any]]]:
    registry = get_workflow_catalog()
    ordered_nodes: list[CatalogNodeDefinition] = [
        *registry["core_nodes"].values(),
        *(
            node
            for app in sorted(registry["integration_apps"].values(), key=lambda item: (item.sort_order, item.id))
            for node in app.nodes
        ),
    ]
    return {
        "definitions": [serialize_catalog_node_for_designer(node) for node in ordered_nodes],
    }
