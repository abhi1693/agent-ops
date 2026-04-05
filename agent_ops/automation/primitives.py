from __future__ import annotations

from automation.catalog.loader import initialize_workflow_catalog
from automation.catalog.payloads import build_workflow_catalog_payload
from automation.catalog.sections import WORKFLOW_NODE_CATALOG_SECTION_ORDER, WORKFLOW_NODE_CATALOG_SECTIONS
from automation.catalog.services import get_catalog_node
from automation.catalog.validation import raise_definition_error, validate_catalog_runtime_node
from automation.tools.base import SUPPORTED_WORKFLOW_FIELD_VALUE_MODES, WORKFLOW_INPUT_MODES_CONFIG_KEY
from automation.workflow_agents import AGENT_TOOL_INPUT_PORT, normalize_workflow_agent_config
from automation.workflow_connections import get_edge_source_port, split_workflow_edges, validate_agent_auxiliary_edges


WORKFLOW_DEFINITION_VERSION = 2


def _build_template_registry() -> tuple[dict, ...]:
    catalog_node_types = set(initialize_workflow_catalog()["node_types"])
    return tuple(
        template
        for template in build_workflow_catalog_payload()["definitions"]
        if template.get("type") in catalog_node_types
    )


_WORKFLOW_REGISTRY_NODE_TEMPLATES = _build_template_registry()
_WORKFLOW_NODE_TEMPLATE_REGISTRY = {
    template["type"]: template
    for template in _WORKFLOW_REGISTRY_NODE_TEMPLATES
}


def _copy_node_template(template: dict) -> dict:
    return {
        **dict(template),
        "config": dict(template.get("config") or {}),
        "fields": tuple(dict(field) for field in (template.get("fields") or ())),
    }


def _build_workflow_group_definitions():
    section_groups = {
        section_id: {
            **section_definition,
            "templates": [],
        }
        for section_id, section_definition in WORKFLOW_NODE_CATALOG_SECTIONS.items()
    }

    for template in _WORKFLOW_REGISTRY_NODE_TEMPLATES:
        section_id = template.get("catalog_section") or "apps"
        section_groups[section_id]["templates"].append(_copy_node_template(template))

    return tuple(
        {
            **section_groups[section_id],
            "templates": tuple(section_groups[section_id]["templates"]),
        }
        for section_id in WORKFLOW_NODE_CATALOG_SECTION_ORDER
        if section_groups[section_id]["templates"]
    )


_WORKFLOW_GROUP_DEFINITIONS = _build_workflow_group_definitions()

WORKFLOW_NODE_APPS = tuple(
    {
        "id": app_definition["id"],
        "label": app_definition["label"],
        "description": app_definition["description"],
        "icon": app_definition["icon"],
        "node_types": [template["type"] for template in app_definition["templates"]],
    }
    for app_definition in _WORKFLOW_GROUP_DEFINITIONS
)

WORKFLOW_NODE_TEMPLATES = tuple(
    template
    for app_definition in _WORKFLOW_GROUP_DEFINITIONS
    for template in app_definition["templates"]
)

WORKFLOW_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_NODE_TEMPLATES
}


def _kind_for_catalog_node(node_definition) -> str | None:
    mode = getattr(node_definition, "mode", None)
    kind = getattr(node_definition, "kind", None)

    if mode == "trigger" or kind == "trigger":
        return "trigger"
    if kind == "agent":
        return "agent"
    if kind in {"output", "response"}:
        return "response"
    if kind in {"control", "condition"}:
        return "condition"
    if kind:
        return "tool"
    return None


def resolve_workflow_node_template_type(*, node_type: str | None = None) -> str | None:
    if isinstance(node_type, str) and node_type.strip():
        normalized_type = node_type.strip()
        if normalized_type in WORKFLOW_NODE_TEMPLATE_MAP:
            return normalized_type
    return None


def get_workflow_node_template(*, node_type: str | None = None):
    resolved_type = resolve_workflow_node_template_type(node_type=node_type)
    if resolved_type is None:
        return None
    return WORKFLOW_NODE_TEMPLATE_MAP.get(resolved_type)


def _normalize_input_modes(*, template: dict, config: dict) -> dict:
    raw_input_modes = config.get(WORKFLOW_INPUT_MODES_CONFIG_KEY)
    if not isinstance(raw_input_modes, dict):
        config.pop(WORKFLOW_INPUT_MODES_CONFIG_KEY, None)
        return config

    allowed_modes_by_field: dict[str, str] = {}
    for field in template.get("fields") or ():
        if field.get("type") not in {"text", "textarea"}:
            continue
        field_key = field.get("key")
        if not isinstance(field_key, str) or not field_key:
            continue
        binding = field.get("binding")
        allowed_modes_by_field[field_key] = "expression" if binding == "template" else "static"

    normalized_input_modes: dict[str, str] = {}
    for field_key, mode in raw_input_modes.items():
        if not isinstance(field_key, str) or not isinstance(mode, str):
            continue
        if mode not in SUPPORTED_WORKFLOW_FIELD_VALUE_MODES:
            continue
        default_mode = allowed_modes_by_field.get(field_key)
        if default_mode is None:
            continue
        field_value = config.get(field_key)
        inferred_mode = (
            "expression"
            if default_mode == "static"
            and isinstance(field_value, str)
            and ("{{" in field_value or "{%" in field_value)
            else default_mode
        )
        if mode == inferred_mode:
            continue
        normalized_input_modes[field_key] = mode

    if normalized_input_modes:
        config[WORKFLOW_INPUT_MODES_CONFIG_KEY] = normalized_input_modes
    else:
        config.pop(WORKFLOW_INPUT_MODES_CONFIG_KEY, None)
    return config


def _normalize_edge_shape(edge: dict) -> dict:
    normalized_edge = dict(edge)
    if "sourcePort" not in normalized_edge and isinstance(normalized_edge.get("source_port"), str):
        normalized_edge["sourcePort"] = normalized_edge["source_port"]
    if "targetPort" not in normalized_edge and isinstance(normalized_edge.get("target_port"), str):
        normalized_edge["targetPort"] = normalized_edge["target_port"]
    return normalized_edge


def _connection_slot_keys_for_template(template: dict | None) -> tuple[str, ...]:
    if not isinstance(template, dict):
        return ()
    connection_slots = template.get("connection_slots")
    if not isinstance(connection_slots, (list, tuple)):
        return ()

    slot_keys: list[str] = []
    for connection_slot in connection_slots:
        if not isinstance(connection_slot, dict):
            continue
        slot_key = connection_slot.get("key")
        if isinstance(slot_key, str) and slot_key.strip():
            slot_keys.append(slot_key.strip())
    return tuple(slot_keys)


def _normalize_node_connections(*, node: dict, template: dict | None, config: dict) -> dict[str, str | int | list[str | int]]:
    normalized_connections: dict[str, str | int | list[str | int]] = {}
    slot_keys = set(_connection_slot_keys_for_template(template))

    raw_connections = node.get("connections")
    if isinstance(raw_connections, dict):
        for slot_key, raw_value in raw_connections.items():
            if not isinstance(slot_key, str) or not slot_key.strip():
                continue
            if raw_value in (None, "", []):
                continue
            normalized_connections[slot_key] = raw_value
            config.pop(slot_key, None)

    connection_id = node.get("connection_id")
    if connection_id in (None, ""):
        legacy_connection_id = config.pop("connection_id", None)
        connection_id = legacy_connection_id if legacy_connection_id not in (None, "") else None
    else:
        config.pop("connection_id", None)
    if connection_id not in (None, ""):
        normalized_connections.setdefault("connection_id", connection_id)

    for slot_key in slot_keys:
        slot_value = config.pop(slot_key, None)
        if slot_value in (None, "", []):
            continue
        normalized_connections.setdefault(slot_key, slot_value)

    return normalized_connections


def _normalize_node_config(*, node: dict, template: dict | None) -> tuple[dict, dict[str, str | int | list[str | int]]]:
    raw_config = node.get("config")
    normalized_config = dict(raw_config) if isinstance(raw_config, dict) else {}

    raw_parameters = node.get("parameters")
    if isinstance(raw_parameters, dict):
        normalized_config.update(raw_parameters)
    connection_bindings = _normalize_node_connections(
        node=node,
        template=template,
        config=normalized_config,
    )

    normalized_kind = node.get("kind")
    if normalized_kind == "agent" or (template and template.get("kind") == "agent"):
        normalized_config = normalize_workflow_agent_config(normalized_config)

    return normalized_config, connection_bindings


def _persisted_position(position: object) -> dict[str, int | float]:
    if not isinstance(position, dict):
        return {"x": 0, "y": 0}
    return {
        "x": position.get("x", 0) if isinstance(position.get("x"), int | float) else 0,
        "y": position.get("y", 0) if isinstance(position.get("y"), int | float) else 0,
    }


def _trim_persisted_parameters(*, template: dict | None, parameters: dict) -> dict:
    defaults = template.get("config") if isinstance(template, dict) and isinstance(template.get("config"), dict) else {}
    connection_slot_keys = set(_connection_slot_keys_for_template(template))
    trimmed: dict = {}
    for key, value in parameters.items():
        if key == "connection_id" or key in connection_slot_keys:
            continue
        if key == "instructions":
            continue
        if key == WORKFLOW_INPUT_MODES_CONFIG_KEY and value in ({}, None):
            continue
        if key in defaults and defaults[key] == value:
            continue
        trimmed[key] = value
    return trimmed


def canonicalize_workflow_definition(definition: dict | None) -> dict:
    if not isinstance(definition, dict):
        return {
            "definition_version": WORKFLOW_DEFINITION_VERSION,
            "nodes": [],
            "edges": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        }

    normalized_definition = dict(definition)
    canonical_nodes = []
    raw_nodes = definition.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raw_nodes = None
    for node in raw_nodes or []:
        if not isinstance(node, dict):
            continue

        node_type = resolve_workflow_node_template_type(node_type=node.get("type")) or node.get("type")
        if not isinstance(node_type, str) or not node_type.strip():
            continue
        node_type = node_type.strip()
        node_template = get_workflow_node_template(node_type=node_type)
        config, connection_bindings = _normalize_node_config(node=node, template=node_template)
        parameters = _trim_persisted_parameters(template=node_template, parameters=config)
        name = node.get("name")
        if not isinstance(name, str) or not name.strip():
            name = node.get("label")
        if not isinstance(name, str) or not name.strip():
            name = node_template.get("label") if isinstance(node_template, dict) else node_type

        persisted_node = {
            "id": node.get("id"),
            "type": node_type,
            "name": name.strip(),
            "position": _persisted_position(node.get("position")),
        }
        if connection_bindings:
            persisted_node["connections"] = dict(connection_bindings)
        if parameters:
            persisted_node["parameters"] = parameters
        raw_kind = node.get("kind")
        if isinstance(raw_kind, str) and raw_kind.strip():
            persisted_node["kind"] = raw_kind.strip()
        if isinstance(node.get("notes"), str) and node["notes"].strip():
            persisted_node["notes"] = node["notes"]
        if isinstance(node.get("disabled"), bool):
            persisted_node["disabled"] = node["disabled"]
        if isinstance(node.get("ui"), dict) and node["ui"]:
            persisted_node["ui"] = dict(node["ui"])
        canonical_nodes.append(persisted_node)

    canonical_edges = []
    raw_edges = definition.get("edges", [])
    if not isinstance(raw_edges, list):
        raw_edges = None
    for edge in raw_edges or []:
        if not isinstance(edge, dict):
            continue
        normalized_edge = _normalize_edge_shape(edge)
        persisted_edge = {
            "id": normalized_edge.get("id"),
            "source": normalized_edge.get("source"),
            "target": normalized_edge.get("target"),
        }
        if isinstance(normalized_edge.get("sourcePort"), str) and normalized_edge["sourcePort"].strip():
            persisted_edge["source_port"] = normalized_edge["sourcePort"].strip()
        if isinstance(normalized_edge.get("targetPort"), str) and normalized_edge["targetPort"].strip():
            persisted_edge["target_port"] = normalized_edge["targetPort"].strip()
        if isinstance(normalized_edge.get("label"), str) and normalized_edge["label"].strip():
            persisted_edge["label"] = normalized_edge["label"].strip()
        canonical_edges.append(persisted_edge)

    viewport = definition.get("viewport")
    if not isinstance(viewport, dict):
        viewport = {"x": 0, "y": 0, "zoom": 1}

    return {
        "definition_version": WORKFLOW_DEFINITION_VERSION,
        "nodes": canonical_nodes if raw_nodes is not None else definition.get("nodes"),
        "edges": canonical_edges if raw_edges is not None else definition.get("edges"),
        "viewport": viewport,
    }


def normalize_workflow_definition_nodes(definition: dict | None) -> dict:
    if not isinstance(definition, dict):
        return {"nodes": [], "edges": []}

    normalized_definition = dict(definition)
    normalized_nodes = []
    raw_nodes = definition.get("nodes", [])
    if not isinstance(raw_nodes, list):
        normalized_definition["nodes"] = raw_nodes
        normalized_definition["edges"] = definition.get("edges", [])
        return normalized_definition

    for node in raw_nodes:
        if not isinstance(node, dict):
            normalized_nodes.append(node)
            continue

        normalized_node = dict(node)
        node_template = get_workflow_node_template(node_type=normalized_node.get("type"))
        existing_config, connection_bindings = _normalize_node_config(node=normalized_node, template=node_template)
        existing_config.update(connection_bindings)

        if not isinstance(normalized_node.get("label"), str) or not normalized_node["label"].strip():
            if isinstance(normalized_node.get("name"), str) and normalized_node["name"].strip():
                normalized_node["label"] = normalized_node["name"].strip()

        if not isinstance(normalized_node.get("kind"), str) or not normalized_node["kind"].strip():
            catalog_node = get_catalog_node(normalized_node.get("type"))
            derived_kind = _kind_for_catalog_node(catalog_node)
            if derived_kind is None and node_template is not None:
                derived_kind = node_template.get("kind")
            if isinstance(derived_kind, str) and derived_kind:
                normalized_node["kind"] = derived_kind

        if node_template is not None:
            normalized_node["type"] = node_template["type"]
            normalized_node["typeVersion"] = 1
            normalized_config = {
                **(node_template.get("config") or {}),
                **existing_config,
            }
            normalized_node["config"] = _normalize_input_modes(
                template=node_template,
                config=normalized_config,
            )

        normalized_nodes.append(normalized_node)

    normalized_definition["nodes"] = normalized_nodes
    raw_edges = definition.get("edges", [])
    if isinstance(raw_edges, list):
        normalized_definition["edges"] = [
            _normalize_edge_shape(edge)
            if isinstance(edge, dict)
            else edge
            for edge in raw_edges
        ]
    else:
        normalized_definition["edges"] = raw_edges
    return normalized_definition

def _validate_runtime_cycle_free(*, adjacency: dict[str, list[str]]) -> None:
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise_definition_error("Workflow runtime does not support cycles yet.")

        visiting.add(node_id)
        for target_id in adjacency.get(node_id, []):
            visit(target_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in adjacency:
        visit(node_id)


def _is_disabled_runtime_node(node: dict) -> bool:
    return node.get("disabled") is True

def _validate_catalog_runtime_node(
    *,
    node: dict,
    node_ids: set[str],
    outgoing_targets: list[str],
    outgoing_targets_by_source_port: dict[str, list[str]],
    untyped_outgoing_targets: list[str],
    attached_agent_tool_node_ids: set[str],
) -> None:
    node_id = node["id"]
    node_type = node.get("type")
    node_definition = get_catalog_node(node_type)
    if node_definition is None:
        raise_definition_error(f'Node "{node_id}" type "{node_type}" is not supported.')

    config = node.get("config") or {}
    if not isinstance(config, dict):
        raise_definition_error(f'Node "{node_id}" config must be a JSON object.')

    if node_id in attached_agent_tool_node_ids and node_definition.kind in {"action", "model"}:
        # Agent-attached catalog tools may omit optional prompt values; only schema/runtime validity matters.
        return

    validate_catalog_runtime_node(
        node_definition=node_definition,
        config=config,
        node_id=node_id,
        node_ids=node_ids,
        outgoing_targets=outgoing_targets,
        outgoing_targets_by_source_port=outgoing_targets_by_source_port,
        untyped_outgoing_targets=untyped_outgoing_targets,
    )


def validate_workflow_runtime_definition(*, nodes: list[dict], edges: list[dict]) -> None:
    nodes_by_id = {node["id"]: node for node in nodes}
    primary_edges, auxiliary_edges = split_workflow_edges(edges)
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    primary_targets_by_source_port: dict[str, dict[str, list[str]]] = {node_id: {} for node_id in nodes_by_id}
    untyped_primary_targets: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    for edge in primary_edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
        source_port = get_edge_source_port(edge)
        if source_port is None:
            untyped_primary_targets.setdefault(edge["source"], []).append(edge["target"])
            continue
        primary_targets_by_source_port.setdefault(edge["source"], {}).setdefault(source_port, []).append(edge["target"])

    trigger_nodes = [node for node in nodes if node["kind"] == "trigger"]
    if len(trigger_nodes) != 1:
        raise_definition_error("Workflow runtime requires exactly one trigger node.")
    if any(_is_disabled_runtime_node(node) for node in trigger_nodes):
        raise_definition_error("Workflow trigger nodes cannot be disabled.")

    _validate_runtime_cycle_free(adjacency=adjacency)
    validate_agent_auxiliary_edges(nodes_by_id=nodes_by_id, edges=auxiliary_edges)
    attached_agent_tool_node_ids = {
        edge["source"]
        for edge in auxiliary_edges
        if edge.get("targetPort") == AGENT_TOOL_INPUT_PORT
    }

    for node in nodes:
        _validate_catalog_runtime_node(
            node=node,
            node_ids=set(nodes_by_id),
            outgoing_targets=adjacency.get(node["id"], []),
            outgoing_targets_by_source_port=primary_targets_by_source_port.get(node["id"], {}),
            untyped_outgoing_targets=untyped_primary_targets.get(node["id"], []),
            attached_agent_tool_node_ids=attached_agent_tool_node_ids,
        )
