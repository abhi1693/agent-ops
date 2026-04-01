from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.nodes import (
    WORKFLOW_NODE_DEFINITIONS as WORKFLOW_MANIFEST_NODE_DEFINITIONS,
    WORKFLOW_NODE_TEMPLATES as WORKFLOW_MANIFEST_NODE_TEMPLATES,
    normalize_workflow_node_config,
    validate_workflow_node,
)
from automation.workflow_connections import (
    split_workflow_edges,
    validate_agent_auxiliary_edges,
)
from automation.workflow_agents import (
    AGENT_TOOL_INPUT_PORT,
    normalize_workflow_agent_config,
)


WORKFLOW_NODE_KINDS = (
    {"value": "trigger", "label": "Trigger"},
    {"value": "agent", "label": "Agent"},
    {"value": "tool", "label": "Tool"},
    {"value": "condition", "label": "Condition"},
    {"value": "response", "label": "Response"},
)

SUPPORTED_WORKFLOW_NODE_KINDS = frozenset(kind["value"] for kind in WORKFLOW_NODE_KINDS)

WORKFLOW_RUNTIME_EXAMPLES = (
    {
        "label": "Trigger",
        "description": "Workflow entry point. The submitted payload is available as trigger.payload.",
        "example": '{\n  "webhook_secret_name": "ALERTMANAGER_WEBHOOK_SECRET"\n}',
    },
    {
        "label": "Agent",
        "description": "Call an LLM with an OpenAI-style chat API and store the result in context.",
        "example": '{\n  "api_type": "openai",\n  "model": "gpt-4.1-mini",\n  "template": "Review ticket {{ trigger.payload.ticket_id }}",\n  "system_prompt": "You are a ticket triage assistant.",\n  "output_key": "llm.response"\n}',
    },
    {
        "label": "Tool",
        "description": "Run a named tool from the workflow tool catalog.",
        "example": '{\n  "template": "Org: {{ workflow.scope_label }}",\n  "output_key": "summary"\n}',
    },
    {
        "label": "Condition",
        "description": "Branch to one of two connected targets using a context value.",
        "example": '{\n  "path": "draft",\n  "operator": "contains",\n  "right_value": "priority",\n  "true_target": "response-priority",\n  "false_target": "response-default"\n}',
    },
    {
        "label": "Response",
        "description": "Finish the run and persist the output payload.",
        "example": '{\n  "template": "Completed for {{ draft }}",\n  "status": "succeeded"\n}',
    },
)


_WORKFLOW_MANIFEST_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_MANIFEST_NODE_TEMPLATES
}


def _copy_node_template(template: dict) -> dict:
    return {
        **dict(template),
        "config": dict(template.get("config") or {}),
        "fields": tuple(dict(field) for field in (template.get("fields") or ())),
    }


def _build_workflow_group_definitions():
    app_groups: list[dict] = []
    groups_by_id: dict[str, dict] = {}

    for node_definition in WORKFLOW_MANIFEST_NODE_DEFINITIONS:
        template = _WORKFLOW_MANIFEST_NODE_TEMPLATE_MAP.get(node_definition.type)
        if template is None:
            raise KeyError(f'Missing workflow node template for "{node_definition.type}".')

        app_group = groups_by_id.get(node_definition.app_id)
        if app_group is None:
            app_group = {
                "id": node_definition.app_id,
                "label": node_definition.app_label,
                "description": node_definition.app_description,
                "icon": node_definition.app_icon,
                "templates": [],
            }
            groups_by_id[node_definition.app_id] = app_group
            app_groups.append(app_group)

        app_group["templates"].append(_copy_node_template(template))

    return tuple(
        {
            **app_group,
            "templates": tuple(app_group["templates"]),
        }
        for app_group in app_groups
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

_AGENT_TOOL_FIXED_FIELD_KEYS = frozenset(
    {
        "output_key",
        "auth_secret_group_id",
        "base_url",
        "server_url",
        "binary_path",
        "protocol_version",
        "timeout_seconds",
        "auth_header_name",
        "auth_header_template",
        "headers_json",
        "api_key_name",
        "api_key_provider",
        "auth_token_name",
        "auth_token_provider",
        "bearer_token_name",
        "bearer_token_provider",
    }
)
_AGENT_TOOL_FIXED_FIELD_SUFFIXES = (
    "_key_name",
    "_key_provider",
    "_token_name",
    "_token_provider",
    "_secret_name",
    "_secret_provider",
)


def resolve_workflow_node_template_type(
    *,
    node_type: str | None = None,
) -> str | None:
    if isinstance(node_type, str) and node_type.strip():
        normalized_type = node_type.strip()
        if normalized_type in WORKFLOW_NODE_TEMPLATE_MAP:
            return normalized_type

    return None


def get_workflow_node_template(*, node_type: str | None = None):
    resolved_type = resolve_workflow_node_template_type(
        node_type=node_type,
    )
    if resolved_type is None:
        return None
    return WORKFLOW_NODE_TEMPLATE_MAP.get(resolved_type)


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

        node_template = get_workflow_node_template(
            node_type=normalized_node.get("type"),
        )

        if node_template is not None:
            normalized_node["type"] = node_template["type"]
            normalized_node["typeVersion"] = 1
            normalized_config = {
                **(node_template.get("config") or {}),
                **existing_config,
            }
            normalized_config = normalize_workflow_node_config(
                node_type=node_template["type"],
                config=normalized_config,
            )
            normalized_node["config"] = normalized_config

        normalized_nodes.append(normalized_node)

    normalized_definition["nodes"] = normalized_nodes
    return normalized_definition


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _is_agent_fixed_tool_field(*, node: dict, field_key: str) -> bool:
    if field_key in _AGENT_TOOL_FIXED_FIELD_KEYS:
        return True
    if any(field_key.endswith(suffix) for suffix in _AGENT_TOOL_FIXED_FIELD_SUFFIXES):
        return True
    if node.get("type") == "tool.secret" and field_key in {"name", "provider"}:
        return True
    return False


def _has_agent_validation_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _build_agent_tool_validation_placeholder(field: dict) -> str:
    options = field.get("options")
    if isinstance(options, list) and options:
        first_option = options[0]
        if isinstance(first_option, dict) and isinstance(first_option.get("value"), str):
            return first_option["value"]

    placeholder = field.get("placeholder")
    if isinstance(placeholder, str) and placeholder.strip():
        return placeholder.strip()

    if str(field.get("key") or "").endswith("_json"):
        return "{}"
    return "agent input"


def _build_agent_attached_tool_validation_node(node: dict) -> dict:
    node_template = get_workflow_node_template(node_type=node.get("type"))
    if node_template is None:
        return node

    base_config = {
        **(node_template.get("config") or {}),
        **(node.get("config") or {}),
    }
    for field in node_template.get("fields") or ():
        field_key = field.get("key")
        if not isinstance(field_key, str) or not field_key:
            continue
        if _is_agent_fixed_tool_field(node=node, field_key=field_key):
            continue
        if _has_agent_validation_value(base_config.get(field_key)):
            continue
        base_config[field_key] = _build_agent_tool_validation_placeholder(field)

    return {
        **node,
        "config": base_config,
    }


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
        _validate_runtime_node(
            node=node,
            node_ids=set(nodes_by_id),
            outgoing_targets=adjacency.get(node["id"], []),
            attached_agent_tool_node_ids=attached_agent_tool_node_ids,
        )


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


def _validate_runtime_node(
    *,
    node: dict,
    node_ids: set[str],
    outgoing_targets: list[str],
    attached_agent_tool_node_ids: set[str],
) -> None:
    node_id = node["id"]
    kind = node["kind"]
    if kind not in SUPPORTED_WORKFLOW_NODE_KINDS:
        _raise_definition_error(
            f'Node "{node_id}" kind "{kind}" is not a supported built-in runtime primitive.'
        )

    config = node.get("config") or {}
    if not isinstance(config, dict):
        _raise_definition_error(f'Node "{node_id}" config must be a JSON object.')

    validation_node = node
    if node_id in attached_agent_tool_node_ids and kind == "tool":
        validation_node = _build_agent_attached_tool_validation_node(node)

    node_definition = validate_workflow_node(
        node=validation_node,
        outgoing_targets=outgoing_targets,
        node_ids=node_ids,
    )
    if node_definition is not None:
        return

    node_type = node.get("type")
    if not isinstance(node_type, str) or not node_type.strip():
        _raise_definition_error(f'Node "{node_id}" must define a supported type.')
    _raise_definition_error(f'Node "{node_id}" type "{node_type}" is not supported.')
