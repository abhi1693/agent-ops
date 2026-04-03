from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.catalog.payloads import build_workflow_catalog_payload
from automation.catalog.services import get_catalog_node
from automation.nodes.apps.openai.client import validate_openai_chat_model_config
from automation.nodes.base import WORKFLOW_NODE_CATALOG_SECTION_ORDER, WORKFLOW_NODE_CATALOG_SECTIONS
from automation.tools.base import (
    SUPPORTED_WORKFLOW_FIELD_VALUE_MODES,
    WORKFLOW_INPUT_MODES_CONFIG_KEY,
    _coerce_csv_strings,
    _coerce_optional_float,
    _coerce_positive_int,
    _validate_optional_json_template,
    _validate_optional_string,
    _validate_required_json_template,
    _validate_required_string,
)
from automation.workflow_agents import AGENT_TOOL_INPUT_PORT, normalize_workflow_agent_config
from automation.workflow_connections import split_workflow_edges, validate_agent_auxiliary_edges

def _build_template_registry() -> tuple[dict, ...]:
    return tuple(build_workflow_catalog_payload()["definitions"])


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


def normalize_workflow_definition_nodes(definition: dict | None) -> dict:
    if not isinstance(definition, dict):
        return {"nodes": [], "edges": []}

    normalized_definition = dict(definition)
    normalized_nodes = []

    for node in definition.get("nodes", []):
        if not isinstance(node, dict):
            normalized_nodes.append(node)
            continue

        normalized_node = dict(node)
        existing_config = normalized_node.get("config")
        if not isinstance(existing_config, dict):
            existing_config = {}
        else:
            existing_config = dict(existing_config)

        if normalized_node.get("kind") == "agent":
            existing_config = normalize_workflow_agent_config(existing_config)

        node_template = get_workflow_node_template(node_type=normalized_node.get("type"))
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
    return normalized_definition


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _validate_runtime_cycle_free(*, adjacency: dict[str, list[str]]) -> None:
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            _raise_definition_error("Workflow runtime does not support cycles yet.")

        visiting.add(node_id)
        for target_id in adjacency.get(node_id, []):
            visit(target_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in adjacency:
        visit(node_id)


def _validate_terminal(node_id: str, outgoing_targets: list[str]) -> None:
    if outgoing_targets:
        _raise_definition_error(f'Node "{node_id}" is terminal and cannot have outgoing edges.')


def _validate_target_exists_and_connected(
    *,
    node_id: str,
    target_name: str,
    target_id: str,
    node_ids: set[str],
    outgoing_targets: list[str],
) -> None:
    if target_id not in node_ids:
        _raise_definition_error(f'Node "{node_id}" {target_name} "{target_id}" does not exist.')
    if target_id not in outgoing_targets:
        _raise_definition_error(
            f'Node "{node_id}" {target_name} "{target_id}" must also be represented by a graph edge.'
        )


def _validate_catalog_runtime_node(
    *,
    node: dict,
    node_ids: set[str],
    outgoing_targets: list[str],
    attached_agent_tool_node_ids: set[str],
) -> None:
    node_id = node["id"]
    node_type = node.get("type")
    node_definition = get_catalog_node(node_type)
    if node_definition is None:
        _raise_definition_error(f'Node "{node_id}" type "{node_type}" is not supported.')

    config = node.get("config") or {}
    if not isinstance(config, dict):
        _raise_definition_error(f'Node "{node_id}" config must be a JSON object.')

    if node_type == "core.manual_trigger":
        return

    if node_type == "core.schedule_trigger":
        _validate_required_string(config, "cron", node_id=node_id)
        return

    if node_type == "core.agent":
        _validate_optional_string(config, "template", node_id=node_id)
        _validate_optional_string(config, "instructions", node_id=node_id)
        _validate_optional_string(config, "system_prompt", node_id=node_id)
        _validate_optional_string(config, "output_key", node_id=node_id)
        return

    if node_type == "core.set":
        _validate_required_string(config, "output_key", node_id=node_id)
        if "value_json" in config:
            _validate_required_json_template(config, "value_json", node_id=node_id)
        elif "value" in config:
            _validate_optional_string(config, "value", node_id=node_id)
        return

    if node_type == "core.if":
        _validate_required_string(config, "operator", node_id=node_id)
        operator = config["operator"]
        if operator not in {"equals", "not_equals", "contains", "exists", "truthy"}:
            _raise_definition_error(
                f'Node "{node_id}" config.operator must be one of: contains, equals, exists, not_equals, truthy.'
            )
        _validate_optional_string(config, "path", node_id=node_id)
        if operator not in {"exists", "truthy"} and "right_value" not in config:
            _raise_definition_error(f'Node "{node_id}" must define config.right_value for operator "{operator}".')
        true_target = _validate_required_string(config, "true_target", node_id=node_id)
        false_target = _validate_required_string(config, "false_target", node_id=node_id)
        if true_target == false_target:
            _raise_definition_error(f'Node "{node_id}" true_target and false_target must be different.')
        _validate_target_exists_and_connected(
            node_id=node_id,
            target_name="true_target",
            target_id=true_target,
            node_ids=node_ids,
            outgoing_targets=outgoing_targets,
        )
        _validate_target_exists_and_connected(
            node_id=node_id,
            target_name="false_target",
            target_id=false_target,
            node_ids=node_ids,
            outgoing_targets=outgoing_targets,
        )
        return

    if node_type == "core.switch":
        _validate_required_string(config, "path", node_id=node_id)
        _validate_required_string(config, "case_1_value", node_id=node_id)
        case_1_target = _validate_required_string(config, "case_1_target", node_id=node_id)
        _validate_required_string(config, "case_2_value", node_id=node_id)
        case_2_target = _validate_required_string(config, "case_2_target", node_id=node_id)
        fallback_target = _validate_required_string(config, "fallback_target", node_id=node_id)
        target_ids = [case_1_target, case_2_target, fallback_target]
        if len(set(target_ids)) != len(target_ids):
            _raise_definition_error(f'Node "{node_id}" switch targets must be different.')
        for target_name, target_id in (
            ("case_1_target", case_1_target),
            ("case_2_target", case_2_target),
            ("fallback_target", fallback_target),
        ):
            _validate_target_exists_and_connected(
                node_id=node_id,
                target_name=target_name,
                target_id=target_id,
                node_ids=node_ids,
                outgoing_targets=outgoing_targets,
            )
        return

    if node_type == "core.response":
        _validate_terminal(node_id, outgoing_targets)
        _validate_optional_string(config, "template", node_id=node_id)
        _validate_optional_string(config, "value_path", node_id=node_id)
        status = config.get("status", "succeeded")
        if status not in {"succeeded", "failed"}:
            _raise_definition_error(f'Node "{node_id}" config.status must be one of: failed, succeeded.')
        return

    if node_type == "core.stop_and_error":
        _validate_terminal(node_id, outgoing_targets)
        _validate_required_string(config, "message", node_id=node_id)
        return

    if node_type == "openai.model.chat":
        validate_openai_chat_model_config(config, node_id)
        return

    if node_type == "prometheus.action.query":
        _validate_required_string(config, "query", node_id=node_id)
        _validate_optional_string(config, "connection_id", node_id=node_id)
        _validate_optional_string(config, "time", node_id=node_id)
        _validate_optional_string(config, "output_key", node_id=node_id)
        instant = config.get("instant")
        if instant not in (None, ""):
            normalized = str(instant).strip().lower()
            if normalized not in {"true", "false"}:
                _raise_definition_error(f'Node "{node_id}" config.instant must be true or false.')
        return

    if node_type == "elasticsearch.action.search":
        _validate_required_string(config, "index", node_id=node_id)
        _validate_required_json_template(config, "query_json", node_id=node_id)
        _validate_optional_string(config, "connection_id", node_id=node_id)
        _validate_optional_string(config, "auth_scheme", node_id=node_id)
        _validate_optional_string(config, "output_key", node_id=node_id)
        if config.get("size") not in (None, ""):
            _coerce_positive_int(config.get("size"), field_name="size", node_id=node_id, default=1)
        return

    if node_type == "github.trigger.webhook":
        _validate_required_string(config, "owner", node_id=node_id)
        _validate_required_string(config, "repository", node_id=node_id)
        _validate_required_string(config, "connection_id", node_id=node_id)
        _coerce_csv_strings(config.get("events"), field_name="events", node_id=node_id, default=[])
        return

    if node_id in attached_agent_tool_node_ids and node_definition.kind in {"action", "model"}:
        # Agent-attached catalog tools may omit optional prompt values; only schema/runtime validity matters.
        return

    # Fall back to schema-level checks for any future catalog node that is added before a dedicated validator.
    for parameter in node_definition.parameter_schema:
        value = config.get(parameter.key)
        if parameter.required and value in (None, "", [], {}):
            _raise_definition_error(f'Node "{node_id}" must define config.{parameter.key}.')
        if parameter.value_type in {"string", "text", "node_ref"} and value not in (None, ""):
            _validate_required_string(config, parameter.key, node_id=node_id)
        elif parameter.value_type == "json" and value not in (None, ""):
            _validate_required_json_template(config, parameter.key, node_id=node_id)
        elif parameter.value_type == "string[]" and value not in (None, ""):
            _coerce_csv_strings(value, field_name=parameter.key, node_id=node_id, default=[])
        elif parameter.value_type == "number" and value not in (None, ""):
            _coerce_optional_float(value, field_name=parameter.key, node_id=node_id)
        elif parameter.value_type == "integer" and value not in (None, ""):
            _coerce_positive_int(value, field_name=parameter.key, node_id=node_id, default=1)


def validate_workflow_runtime_definition(*, nodes: list[dict], edges: list[dict]) -> None:
    nodes_by_id = {node["id"]: node for node in nodes}
    primary_edges, auxiliary_edges = split_workflow_edges(edges)
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    for edge in primary_edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])

    trigger_nodes = [node for node in nodes if node["kind"] == "trigger"]
    if len(trigger_nodes) != 1:
        _raise_definition_error("Workflow runtime requires exactly one trigger node.")

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
            attached_agent_tool_node_ids=attached_agent_tool_node_ids,
        )
