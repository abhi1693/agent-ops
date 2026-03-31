from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.nodes import (
    WORKFLOW_BUILTIN_NODE_TEMPLATES,
    validate_workflow_builtin_node,
)
from automation.app_nodes import (
    WORKFLOW_APP_NODE_DEFINITIONS,
    get_workflow_app_node_metadata,
    validate_workflow_app_node,
)
from automation.tools import validate_workflow_tool_config
from automation.triggers import validate_workflow_trigger_config


WORKFLOW_NODE_KINDS = (
    {"value": "trigger", "label": "Trigger"},
    {"value": "agent", "label": "Agent"},
    {"value": "tool", "label": "Tool"},
    {"value": "condition", "label": "Condition"},
    {"value": "response", "label": "Response"},
)

SUPPORTED_WORKFLOW_NODE_KINDS = frozenset(kind["value"] for kind in WORKFLOW_NODE_KINDS)
SUPPORTED_CONDITION_OPERATORS = frozenset({"equals", "not_equals", "contains", "exists", "truthy"})
SUPPORTED_RESPONSE_STATUSES = frozenset({"succeeded", "failed"})
SUPPORTED_AGENT_API_TYPES = frozenset({"openai"})

_OPENAI_COMPATIBLE_AGENT_ROUTE = {
    "resource": "chat",
    "operation": "complete",
    "tool_name": "openai_compatible_chat",
}
_DEFAULT_AGENT_API_TYPE = "openai"
_AGENT_DEFAULTS_BY_API_TYPE = {
    "openai": {
        "api_key_name": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "output_key": "llm.response",
    }
}

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


def _copy_template_fields(*fields):
    return tuple(dict(field) for field in fields)


_WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_BUILTIN_NODE_TEMPLATES
}

_BUILTIN_NODE_APP_DESCRIPTION = (
    "Core workflow nodes, runtime primitives, and n8n-style built-in blocks available in the designer."
)

_WORKFLOW_INTERNAL_NODE_TEMPLATE_MAP = {
    "agent": {
        "kind": "agent",
        "type": "agent",
        "label": "Agent",
        "description": "Call an LLM with an OpenAI-style chat API and store the result in workflow context.",
        "icon": "mdi-robot-outline",
        "config": {
            "api_type": _DEFAULT_AGENT_API_TYPE,
            **_AGENT_DEFAULTS_BY_API_TYPE[_DEFAULT_AGENT_API_TYPE],
        },
        "fields": _copy_template_fields(
            {
                "key": "api_type",
                "label": "API type",
                "type": "select",
                "options": (
                    {"value": "openai", "label": "OpenAI"},
                ),
            },
            {
                "key": "template",
                "label": "Template",
                "type": "textarea",
                "rows": 6,
                "placeholder": "Summarize incident {{ trigger.payload.incident_id }} and propose next steps.",
                "help_text": "Rendered as the user prompt sent to the model.",
            },
            {
                "key": "output_key",
                "label": "Save result as",
                "type": "text",
                "placeholder": "draft",
            },
            {
                "key": "auth_secret_group_id",
                "label": "Auth secret group",
                "type": "select",
                "help_text": "Optional. If set, this node resolves authentication secrets from the selected secret group by assignment key or grouped secret name.",
            },
            {
                "key": "base_url",
                "label": "API base URL",
                "type": "text",
                "placeholder": "https://api.openai.com/v1",
                "help_text": "Override the default endpoint when you need a different OpenAI-compatible API base URL.",
            },
            {
                "key": "api_key_name",
                "label": "API key secret name",
                "type": "text",
                "placeholder": "OPENAI_API_KEY",
            },
            {
                "key": "api_key_provider",
                "label": "API key provider",
                "type": "text",
                "placeholder": "environment-variable",
                "help_text": "Optional. Leave blank to search all enabled providers in scope.",
            },
            {
                "key": "model",
                "label": "Model",
                "type": "text",
                "placeholder": "gpt-4.1-mini",
            },
            {
                "key": "system_prompt",
                "label": "System prompt",
                "type": "textarea",
                "rows": 4,
                "placeholder": "You are an incident response assistant.",
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "text",
                "placeholder": "0.2",
            },
            {
                "key": "max_tokens",
                "label": "Max tokens",
                "type": "text",
                "placeholder": "800",
            },
            {
                "key": "extra_body_json",
                "label": "Extra body JSON",
                "type": "textarea",
                "rows": 5,
                "placeholder": '{"response_format": {"type": "json_object"}}',
                "help_text": "Optional provider-specific fields merged into the request body after prompts and model.",
            },
        ),
        "app_id": "builtins",
        "app_label": "Built-ins",
        "app_description": _BUILTIN_NODE_APP_DESCRIPTION,
        "app_icon": "mdi-toy-brick-outline",
    },
    "response": {
        "kind": "response",
        "type": "response",
        "label": "Response",
        "description": "Finish the workflow and persist a terminal response payload.",
        "icon": "mdi-flag-checkered",
        "config": {"status": "succeeded"},
        "fields": _copy_template_fields(
            {
                "key": "template",
                "label": "Template",
                "type": "textarea",
                "rows": 4,
                "placeholder": "Completed {{ draft }}",
            },
            {
                "key": "value_path",
                "label": "Value path",
                "type": "text",
                "placeholder": "draft",
                "help_text": "Optional. When set, the response is read directly from context instead of rendering the template.",
            },
            {
                "key": "status",
                "label": "Status",
                "type": "select",
                "options": (
                    {"value": "succeeded", "label": "Succeeded"},
                    {"value": "failed", "label": "Failed"},
                ),
            },
        ),
        "app_id": "builtins",
        "app_label": "Built-ins",
        "app_description": _BUILTIN_NODE_APP_DESCRIPTION,
        "app_icon": "mdi-toy-brick-outline",
    },
}


def _copy_node_template(template: dict) -> dict:
    return {
        **dict(template),
        "config": dict(template.get("config") or {}),
        "fields": _copy_template_fields(*(template.get("fields") or ())),
    }


_WORKFLOW_APP_NODE_TEMPLATE_MAP = {
    definition.template_definition.type: _copy_node_template(
        definition.template_definition.serialize()
    )
    for definition in WORKFLOW_APP_NODE_DEFINITIONS
}


def _attach_route_metadata(template: dict) -> dict:
    hydrated_template = _copy_node_template(template)
    route_metadata = get_workflow_app_node_metadata(
        node_type=hydrated_template.get("type"),
    )
    return {
        **hydrated_template,
        **route_metadata,
    }


_BUILTIN_NODE_APP_DEFINITION = {
    "id": "builtins",
    "label": "Built-ins",
    "description": _BUILTIN_NODE_APP_DESCRIPTION,
    "icon": "mdi-toy-brick-outline",
    "templates": (
        _WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP["n8n-nodes-base.manualTrigger"],
        _WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP["n8n-nodes-base.scheduleTrigger"],
        _WORKFLOW_INTERNAL_NODE_TEMPLATE_MAP["agent"],
        _WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP["n8n-nodes-base.set"],
        _WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP["n8n-nodes-base.if"],
        _WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP["n8n-nodes-base.switch"],
        _WORKFLOW_INTERNAL_NODE_TEMPLATE_MAP["response"],
        _WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP["n8n-nodes-base.stopAndError"],
    ),
}


def _build_workflow_app_group_definitions():
    app_groups: list[dict] = []
    groups_by_id: dict[str, dict] = {}

    for app_node_definition in WORKFLOW_APP_NODE_DEFINITIONS:
        template_definition = app_node_definition.template_definition
        template = _WORKFLOW_APP_NODE_TEMPLATE_MAP.get(template_definition.type)
        if template is None:
            raise KeyError(f'Missing workflow app node template for "{template_definition.type}".')

        app_group = groups_by_id.get(template_definition.app_id)
        if app_group is None:
            app_group = {
                "id": template_definition.app_id,
                "label": template_definition.app_label,
                "description": template_definition.app_description,
                "icon": template_definition.app_icon,
                "templates": [],
            }
            groups_by_id[template_definition.app_id] = app_group
            app_groups.append(app_group)

        app_group["templates"].append(_attach_route_metadata(template))

    return tuple(
        {
            **app_group,
            "templates": tuple(app_group["templates"]),
        }
        for app_group in app_groups
    )


_WORKFLOW_APP_GROUP_DEFINITIONS = _build_workflow_app_group_definitions()

WORKFLOW_NODE_APPS = tuple(
    {
        "id": app_definition["id"],
        "label": app_definition["label"],
        "description": app_definition["description"],
        "icon": app_definition["icon"],
        "node_types": [template["type"] for template in app_definition["templates"]],
    }
    for app_definition in (_BUILTIN_NODE_APP_DEFINITION, *_WORKFLOW_APP_GROUP_DEFINITIONS)
)

WORKFLOW_NODE_TEMPLATES = tuple(
    template
    for app_definition in (_BUILTIN_NODE_APP_DEFINITION, *_WORKFLOW_APP_GROUP_DEFINITIONS)
    for template in app_definition["templates"]
)

WORKFLOW_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_NODE_TEMPLATES
}

def normalize_workflow_agent_config(
    config: dict | None,
) -> dict:
    normalized = dict(config or {})
    auth_secret_group_id = normalized.get("auth_secret_group_id")

    if auth_secret_group_id in ("", None):
        normalized.pop("auth_secret_group_id", None)
    elif not isinstance(auth_secret_group_id, str):
        normalized["auth_secret_group_id"] = str(auth_secret_group_id)

    configured_api_type = normalized.get("api_type")
    if isinstance(configured_api_type, str) and configured_api_type.strip():
        normalized_api_type = configured_api_type.strip()
    else:
        normalized_api_type = _DEFAULT_AGENT_API_TYPE

    normalized["api_type"] = normalized_api_type
    for key, value in _AGENT_DEFAULTS_BY_API_TYPE.get(normalized_api_type, {}).items():
        if normalized.get(key) in ("", None):
            normalized[key] = value

    return normalized


def build_workflow_agent_tool_config(*, node: dict, config: dict) -> dict:
    normalized = normalize_workflow_agent_config(config)
    prompt_template = normalized.get("template")
    if isinstance(prompt_template, str) and prompt_template.strip():
        rendered_prompt_template = prompt_template.strip()
    else:
        rendered_prompt_template = (node.get("label") or node["id"]).strip()
    return {
        **normalized,
        "user_prompt": rendered_prompt_template,
        **_OPENAI_COMPATIBLE_AGENT_ROUTE,
    }


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
            normalized_node["config"] = normalized_config

        normalized_nodes.append(normalized_node)

    normalized_definition["nodes"] = normalized_nodes
    return normalized_definition


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _validate_optional_string(config: dict, key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" config.{key} must be a non-empty string.')


def validate_workflow_runtime_definition(*, nodes: list[dict], edges: list[dict]) -> None:
    nodes_by_id = {node["id"]: node for node in nodes}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    for edge in edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])

    trigger_nodes = [node for node in nodes if node["kind"] == "trigger"]
    if len(trigger_nodes) != 1:
        _raise_definition_error("Workflow runtime requires exactly one trigger node.")

    _validate_runtime_cycle_free(adjacency=adjacency)

    for node in nodes:
        _validate_runtime_node(
            node=node,
            node_ids=set(nodes_by_id),
            outgoing_targets=adjacency.get(node["id"], []),
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


def _validate_runtime_node(*, node: dict, node_ids: set[str], outgoing_targets: list[str]) -> None:
    node_id = node["id"]
    kind = node["kind"]
    if kind not in SUPPORTED_WORKFLOW_NODE_KINDS:
        _raise_definition_error(
            f'Node "{node_id}" kind "{kind}" is not a supported built-in runtime primitive.'
        )

    config = node.get("config") or {}
    if not isinstance(config, dict):
        _raise_definition_error(f'Node "{node_id}" config must be a JSON object.')

    if validate_workflow_builtin_node(
        node=node,
        outgoing_targets=outgoing_targets,
        node_ids=node_ids,
    ) is not None:
        return

    if validate_workflow_app_node(node=node, outgoing_targets=outgoing_targets) is not None:
        return

    node_template = get_workflow_node_template(
        node_type=node.get("type"),
    )
    if node_template is None:
        node_type = node.get("type")
        if not isinstance(node_type, str) or not node_type.strip():
            _raise_definition_error(f'Node "{node_id}" must define a supported type.')
        _raise_definition_error(f'Node "{node_id}" type "{node_type}" is not supported.')

    if kind == "trigger":
        validate_workflow_trigger_config(config, node_id=node_id)
        return

    if kind == "tool":
        validate_workflow_tool_config(config, node_id=node_id)
        return

    if kind == "agent":
        normalized_agent_config = normalize_workflow_agent_config(config)
        agent_api_type = normalized_agent_config.get("api_type", _DEFAULT_AGENT_API_TYPE)
        if agent_api_type not in SUPPORTED_AGENT_API_TYPES:
            _raise_definition_error(
                (
                    f'Node "{node_id}" config.api_type must be one of: '
                    f'{", ".join(sorted(SUPPORTED_AGENT_API_TYPES))}.'
                )
            )
        validate_workflow_tool_config(
            build_workflow_agent_tool_config(
                node=node,
                config=normalized_agent_config,
            ),
            node_id=node_id,
        )
        if len(outgoing_targets) > 1:
            _raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')
        return

    if kind == "condition":
        _validate_optional_string(config, "path", node_id=node_id)
        operator = config.get("operator")
        if operator not in SUPPORTED_CONDITION_OPERATORS:
            _raise_definition_error(
                f'Node "{node_id}" config.operator must be one of: {", ".join(sorted(SUPPORTED_CONDITION_OPERATORS))}.'
            )
        if operator not in {"exists", "truthy"} and "right_value" not in config:
            _raise_definition_error(f'Node "{node_id}" must define config.right_value for operator "{operator}".')
        true_target = config.get("true_target")
        false_target = config.get("false_target")
        if not isinstance(true_target, str) or not true_target.strip():
            _raise_definition_error(f'Node "{node_id}" must define config.true_target.')
        if not isinstance(false_target, str) or not false_target.strip():
            _raise_definition_error(f'Node "{node_id}" must define config.false_target.')
        if true_target == false_target:
            _raise_definition_error(f'Node "{node_id}" true_target and false_target must be different.')
        for target_name, target_id in (("true_target", true_target), ("false_target", false_target)):
            if target_id not in node_ids:
                _raise_definition_error(f'Node "{node_id}" {target_name} "{target_id}" does not exist.')
            if target_id not in outgoing_targets:
                _raise_definition_error(
                    f'Node "{node_id}" {target_name} "{target_id}" must also be represented by a graph edge.'
                )
        return

    if kind == "response":
        _validate_optional_string(config, "template", node_id=node_id)
        _validate_optional_string(config, "value_path", node_id=node_id)
        status = config.get("status", "succeeded")
        if status not in SUPPORTED_RESPONSE_STATUSES:
            _raise_definition_error(
                f'Node "{node_id}" config.status must be one of: {", ".join(sorted(SUPPORTED_RESPONSE_STATUSES))}.'
            )
        if outgoing_targets:
            _raise_definition_error(f'Node "{node_id}" is terminal and cannot have outgoing edges.')
