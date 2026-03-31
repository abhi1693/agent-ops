from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.app_nodes import get_workflow_app_node_metadata, validate_workflow_app_node
from automation.tools import (
    WORKFLOW_TOOL_DEFINITIONS,
    normalize_workflow_tool_config,
)
from automation.triggers import (
    WORKFLOW_TRIGGER_DEFINITIONS,
    normalize_workflow_trigger_config,
)


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

WORKFLOW_RUNTIME_EXAMPLES = (
    {
        "label": "Trigger",
        "description": "Workflow entry point. The submitted payload is available as trigger.payload.",
        "example": '{\n  "resource": "webhook",\n  "operation": "receive"\n}',
    },
    {
        "label": "Agent",
        "description": "Render a deterministic message and store it in context.",
        "example": '{\n  "template": "Review ticket {{ trigger.payload.ticket_id }}",\n  "output_key": "draft"\n}',
    },
    {
        "label": "Tool",
        "description": "Run a named tool from the workflow tool catalog.",
        "example": '{\n  "tool_name": "template",\n  "template": "Org: {{ workflow.scope_label }}",\n  "output_key": "summary"\n}',
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


_WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD = {
    "key": "auth_secret_group_id",
    "label": "Auth secret group",
    "type": "select",
    "options": (),
    "help_text": (
        "Optional. If set, this node resolves authentication secrets from the selected secret "
        "group by assignment key or grouped secret name."
    ),
}


def _copy_template_fields(*fields):
    return tuple(dict(field) for field in fields)


def _get_tool_definition(name: str) -> dict | None:
    for tool_definition in WORKFLOW_TOOL_DEFINITIONS:
        if tool_definition["name"] == name:
            return tool_definition
    return None


def _get_trigger_definition(name: str) -> dict | None:
    for trigger_definition in WORKFLOW_TRIGGER_DEFINITIONS:
        if trigger_definition["name"] == name:
            return trigger_definition
    return None


def _select_options(*pairs: tuple[str, str]) -> tuple[dict[str, str], ...]:
    return tuple({"value": value, "label": label} for value, label in pairs)


def _copy_definition_fields(definition: dict | None, *, exclude_keys: tuple[str, ...] = ()) -> tuple[dict, ...]:
    if definition is None:
        return ()
    return tuple(
        dict(field)
        for field in definition.get("fields", ())
        if field.get("key") not in exclude_keys
    )


def _decorate_field(
    field: dict,
    *,
    visible_when: dict[str, tuple[str, ...]] | None = None,
    options_by_field: dict[str, dict[str, tuple[dict[str, str], ...]]] | None = None,
    **overrides,
) -> dict:
    decorated_field = {
        **dict(field),
        **overrides,
    }
    if visible_when:
        decorated_field["visible_when"] = {
            key: list(values)
            for key, values in visible_when.items()
        }
    if options_by_field:
        decorated_field["options_by_field"] = {
            field_key: {
                value: [dict(option) for option in options]
                for value, options in options_map.items()
            }
            for field_key, options_map in options_by_field.items()
        }
    return decorated_field


def _build_agent_node_templates():
    return (
        {
            "kind": "agent",
            "type": "agent",
            "label": "Agent",
            "description": "Render a deterministic agent message into workflow context.",
            "icon": "mdi-robot-outline",
            "config": {},
            "fields": (
                {
                    "key": "template",
                    "label": "Instruction template",
                    "type": "textarea",
                    "rows": 5,
                    "placeholder": "Review {{ trigger.payload.ticket_id }} and summarize next steps.",
                },
                {
                    "key": "output_key",
                    "label": "Save result as",
                    "type": "text",
                    "placeholder": "agent.summary",
                },
            ),
        },
    )


_WORKFLOW_FLOW_NODE_TEMPLATES = (
    *_build_agent_node_templates(),
    {
        "kind": "condition",
        "type": "condition",
        "label": "Condition",
        "description": "Branch to one of two connected targets.",
        "icon": "mdi-source-branch",
        "config": {
            "operator": "equals",
        },
        "fields": (
            {
                "key": "path",
                "label": "Context path",
                "type": "text",
                "placeholder": "trigger.payload.priority",
            },
            {
                "key": "operator",
                "label": "Operator",
                "type": "select",
                "options": (
                    {"value": "equals", "label": "Equals"},
                    {"value": "not_equals", "label": "Does not equal"},
                    {"value": "contains", "label": "Contains"},
                    {"value": "exists", "label": "Exists"},
                    {"value": "truthy", "label": "Is truthy"},
                ),
            },
            {
                "key": "right_value",
                "label": "Compare against",
                "type": "text",
                "placeholder": "high",
                "help_text": "Not used for exists or truthy operators.",
            },
            {
                "key": "true_target",
                "label": "If true, go to",
                "type": "node_target",
            },
            {
                "key": "false_target",
                "label": "If false, go to",
                "type": "node_target",
            },
        ),
    },
    {
        "kind": "response",
        "type": "response",
        "label": "Response",
        "description": "Finish the run with a response payload and status.",
        "icon": "mdi-flag-checkered",
        "config": {
            "status": "succeeded",
        },
        "fields": (
            {
                "key": "template",
                "label": "Response template",
                "type": "textarea",
                "rows": 4,
                "placeholder": "Completed {{ agent.summary }}",
                "help_text": "Used unless value_path is provided.",
            },
            {
                "key": "value_path",
                "label": "Value path",
                "type": "text",
                "placeholder": "agent.summary",
                "help_text": "Return an existing context value instead of rendering a template.",
            },
            {
                "key": "status",
                "label": "Run status",
                "type": "select",
                "options": (
                    {"value": "succeeded", "label": "Succeeded"},
                    {"value": "failed", "label": "Failed"},
                ),
            },
        ),
    },
)

def _build_trigger_node_templates():
    templates = []

    for trigger_definition in WORKFLOW_TRIGGER_DEFINITIONS:
        fields = [_WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD, *_copy_template_fields(*trigger_definition.get("fields", ()))]
        config = {
            **(trigger_definition.get("config") or {}),
            "type": trigger_definition["name"],
            "auth_secret_group_id": "",
        }
        templates.append(
            {
                "kind": "trigger",
                "type": f'trigger.{trigger_definition["name"]}',
                "label": trigger_definition["label"],
                "description": trigger_definition["description"],
                "icon": trigger_definition.get("icon", "mdi-play-circle-outline"),
                "config": config,
                "fields": tuple(fields),
            }
        )

    return tuple(templates)


def _build_tool_node_templates():
    templates = []

    for tool_definition in WORKFLOW_TOOL_DEFINITIONS:
        if tool_definition["name"] == "openai_compatible_chat":
            continue
        fields = [_WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD, *_copy_template_fields(*tool_definition.get("fields", ()))]
        config = {
            **(tool_definition.get("config") or {}),
            "tool_name": tool_definition["name"],
            "auth_secret_group_id": "",
        }
        templates.append(
            {
                "kind": "tool",
                "type": f'tool.{tool_definition["name"]}',
                "label": tool_definition["label"],
                "description": tool_definition["description"],
                "icon": tool_definition.get("icon", "mdi-tools"),
                "config": config,
                "fields": tuple(fields),
            }
        )

    return tuple(templates)


_TRIGGER_NODE_TEMPLATES = _build_trigger_node_templates()
_TOOL_NODE_TEMPLATES = _build_tool_node_templates()

_WORKFLOW_FLOW_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in _WORKFLOW_FLOW_NODE_TEMPLATES
}
_TRIGGER_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in _TRIGGER_NODE_TEMPLATES
}
_TOOL_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in _TOOL_NODE_TEMPLATES
}


def _build_openai_agent_node_template():
    openai_definition = _get_tool_definition("openai_compatible_chat")
    openai_fields = _copy_definition_fields(openai_definition)
    return {
        "kind": "agent",
        "type": "agent.openai",
        "label": "OpenAI-compatible",
        "description": "LLM agent node with OpenAI-style resource and operation routing.",
        "icon": "mdi-robot-happy-outline",
        "config": {
            "resource": "chat",
            "operation": "complete",
            "output_key": "llm.response",
        },
        "fields": (
            _WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD,
            {
                "key": "resource",
                "label": "Resource",
                "type": "select",
                "options": _select_options(("chat", "Chat")),
            },
            {
                "key": "operation",
                "label": "Operation",
                "type": "select",
                "options": _select_options(("complete", "Complete")),
            },
            *openai_fields,
        ),
    }


def _build_github_trigger_node_template():
    github_definition = _get_trigger_definition("github_webhook")
    github_fields = _copy_definition_fields(github_definition)
    return {
        "kind": "trigger",
        "type": "trigger.github",
        "label": "GitHub",
        "description": "GitHub trigger node with selector-driven resource and operation routing.",
        "icon": "mdi-github",
        "config": {
            "resource": "webhook",
            "operation": "receive",
        },
        "fields": (
            _WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD,
            {
                "key": "resource",
                "label": "Resource",
                "type": "select",
                "options": _select_options(("webhook", "Webhook")),
            },
            {
                "key": "operation",
                "label": "Operation",
                "type": "select",
                "options": _select_options(("receive", "Receive")),
            },
            *github_fields,
        ),
    }


def _build_observability_trigger_node_template():
    alertmanager_definition = _get_trigger_definition("alertmanager_webhook")
    alertmanager_fields = _copy_definition_fields(alertmanager_definition)
    return {
        "kind": "trigger",
        "type": "trigger.observability",
        "label": "Observability trigger",
        "description": "Observability webhook trigger for alert streams such as Alertmanager and Kibana.",
        "icon": "mdi-bell-ring-outline",
        "config": {
            "resource": "alertmanager",
            "operation": "webhook",
        },
        "fields": (
            _WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD,
            {
                "key": "resource",
                "label": "Resource",
                "type": "select",
                "options": _select_options(
                    ("alertmanager", "Alertmanager"),
                    ("kibana", "Kibana"),
                ),
            },
            {
                "key": "operation",
                "label": "Operation",
                "type": "select",
                "options": _select_options(("webhook", "Webhook")),
            },
            *alertmanager_fields,
        ),
    }


def _build_observability_tool_node_template():
    prometheus_definition = _get_tool_definition("prometheus_query")
    elasticsearch_definition = _get_tool_definition("elasticsearch_search")
    prometheus_fields = {
        field["key"]: field
        for field in _copy_definition_fields(
            prometheus_definition,
            exclude_keys=("output_key", "base_url"),
        )
    }
    elasticsearch_fields = {
        field["key"]: field
        for field in _copy_definition_fields(
            elasticsearch_definition,
            exclude_keys=("output_key", "base_url"),
        )
    }

    return {
        "kind": "tool",
        "type": "tool.observability",
        "label": "Observability",
        "description": "Observability action node for Prometheus and Elasticsearch operations.",
        "icon": "mdi-chart-areaspline",
        "config": {
            "resource": "prometheus",
            "operation": "query",
            "output_key": "observability.result",
        },
        "fields": (
            _WORKFLOW_SHARED_AUTH_SECRET_GROUP_FIELD,
            {
                "key": "resource",
                "label": "Resource",
                "type": "select",
                "options": _select_options(
                    ("prometheus", "Prometheus"),
                    ("elasticsearch", "Elasticsearch"),
                ),
            },
            {
                "key": "operation",
                "label": "Operation",
                "type": "select",
                "options": _select_options(
                    ("query", "Query"),
                    ("search", "Search"),
                ),
                "options_by_field": {
                    "resource": {
                        "prometheus": list(_select_options(("query", "Query"))),
                        "elasticsearch": list(_select_options(("search", "Search"))),
                    }
                },
            },
            {
                "key": "output_key",
                "label": "Save result as",
                "type": "text",
                "placeholder": "observability.result",
            },
            {
                "key": "base_url",
                "label": "Service base URL",
                "type": "text",
                "placeholder": "https://prometheus.example.com",
            },
            _decorate_field(
                prometheus_fields["bearer_token_name"],
                visible_when={"resource": ("prometheus",)},
            ),
            _decorate_field(
                prometheus_fields["bearer_token_provider"],
                visible_when={"resource": ("prometheus",)},
            ),
            _decorate_field(
                prometheus_fields["query"],
                visible_when={"resource": ("prometheus",)},
            ),
            _decorate_field(
                prometheus_fields["time"],
                visible_when={"resource": ("prometheus",)},
            ),
            _decorate_field(
                elasticsearch_fields["index"],
                visible_when={"resource": ("elasticsearch",)},
            ),
            _decorate_field(
                elasticsearch_fields["auth_token_name"],
                visible_when={"resource": ("elasticsearch",)},
            ),
            _decorate_field(
                elasticsearch_fields["auth_token_provider"],
                visible_when={"resource": ("elasticsearch",)},
            ),
            _decorate_field(
                elasticsearch_fields["auth_scheme"],
                visible_when={"resource": ("elasticsearch",)},
            ),
            _decorate_field(
                elasticsearch_fields["query_json"],
                visible_when={"resource": ("elasticsearch",)},
            ),
        ),
    }


_OPENAI_AGENT_NODE_TEMPLATE = _build_openai_agent_node_template()
_GITHUB_TRIGGER_NODE_TEMPLATE = _build_github_trigger_node_template()
_OBSERVABILITY_TRIGGER_NODE_TEMPLATE = _build_observability_trigger_node_template()
_OBSERVABILITY_TOOL_NODE_TEMPLATE = _build_observability_tool_node_template()


def _attach_app_metadata(template: dict, *, app_id: str, app_label: str, app_description: str, app_icon: str) -> dict:
    route_metadata = get_workflow_app_node_metadata(
        node_type=template.get("type"),
        config=template.get("config"),
    )
    return {
        **template,
        "app_id": app_id,
        "app_label": app_label,
        "app_description": app_description,
        "app_icon": app_icon,
        **route_metadata,
    }


_WORKFLOW_NODE_APP_DEFINITIONS = (
    {
        "id": "core",
        "label": "Core",
        "description": "Workflow-native blocks for entry points, control flow, context transforms, and responses.",
        "icon": "mdi-source-branch",
        "templates": (
            _TRIGGER_NODE_TEMPLATE_MAP["trigger.manual"],
            _WORKFLOW_FLOW_NODE_TEMPLATE_MAP["agent"],
            _WORKFLOW_FLOW_NODE_TEMPLATE_MAP["condition"],
            _WORKFLOW_FLOW_NODE_TEMPLATE_MAP["response"],
            _TOOL_NODE_TEMPLATE_MAP["tool.passthrough"],
            _TOOL_NODE_TEMPLATE_MAP["tool.set"],
            _TOOL_NODE_TEMPLATE_MAP["tool.template"],
            _TOOL_NODE_TEMPLATE_MAP["tool.secret"],
        ),
    },
    {
        "id": "openai",
        "label": "OpenAI-compatible",
        "description": "LLM-powered agent nodes backed by chat completions.",
        "icon": "mdi-robot-happy-outline",
        "templates": (
            _OPENAI_AGENT_NODE_TEMPLATE,
        ),
    },
    {
        "id": "github",
        "label": "GitHub",
        "description": "Receive webhook events from GitHub workflows and repositories.",
        "icon": "mdi-github",
        "templates": (
            _GITHUB_TRIGGER_NODE_TEMPLATE,
        ),
    },
    {
        "id": "observability",
        "label": "Observability",
        "description": "Ingest alerts and query monitoring systems such as Prometheus and Elasticsearch.",
        "icon": "mdi-chart-areaspline",
        "templates": (
            _OBSERVABILITY_TRIGGER_NODE_TEMPLATE,
            _OBSERVABILITY_TOOL_NODE_TEMPLATE,
        ),
    },
    {
        "id": "infrastructure",
        "label": "Infrastructure",
        "description": "Operate infrastructure workflows against the local app host environment.",
        "icon": "mdi-kubernetes",
        "templates": (
            _TOOL_NODE_TEMPLATE_MAP["tool.kubectl"],
        ),
    },
    {
        "id": "integrations",
        "label": "Integrations",
        "description": "Connect to remote servers and external runtime capabilities.",
        "icon": "mdi-connection",
        "templates": (
            _TOOL_NODE_TEMPLATE_MAP["tool.mcp_server"],
        ),
    },
)

WORKFLOW_NODE_APPS = tuple(
    {
        "id": app_definition["id"],
        "label": app_definition["label"],
        "description": app_definition["description"],
        "icon": app_definition["icon"],
        "node_types": [template["type"] for template in app_definition["templates"]],
    }
    for app_definition in _WORKFLOW_NODE_APP_DEFINITIONS
)

WORKFLOW_NODE_TEMPLATES = tuple(
    _attach_app_metadata(
        template,
        app_id=app_definition["id"],
        app_label=app_definition["label"],
        app_description=app_definition["description"],
        app_icon=app_definition["icon"],
    )
    for app_definition in _WORKFLOW_NODE_APP_DEFINITIONS
    for template in app_definition["templates"]
)

WORKFLOW_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_NODE_TEMPLATES
}

_TRIGGER_TEMPLATE_TYPE_BY_TRIGGER_TYPE = {
    "manual": "trigger.manual",
}

_TOOL_TEMPLATE_TYPE_BY_TOOL_NAME = {
    "passthrough": "tool.passthrough",
    "set": "tool.set",
    "template": "tool.template",
    "secret": "tool.secret",
    "kubectl": "tool.kubectl",
    "mcp_server": "tool.mcp_server",
}


def resolve_workflow_node_template_type(
    *,
    kind: str | None,
    node_type: str | None = None,
    config: dict | None = None,
) -> str | None:
    if isinstance(node_type, str) and node_type.strip():
        normalized_type = node_type.strip()
        return normalized_type if normalized_type in WORKFLOW_NODE_TEMPLATE_MAP else None

    if kind == "trigger":
        trigger_type = normalize_workflow_trigger_config(config).get("type", "manual")
        candidate = _TRIGGER_TEMPLATE_TYPE_BY_TRIGGER_TYPE.get(trigger_type)
        return candidate if candidate in WORKFLOW_NODE_TEMPLATE_MAP else None

    if kind == "tool":
        tool_name = normalize_workflow_tool_config(config).get("tool_name", "passthrough")
        candidate = _TOOL_TEMPLATE_TYPE_BY_TOOL_NAME.get(tool_name)
        return candidate if candidate in WORKFLOW_NODE_TEMPLATE_MAP else None

    if isinstance(kind, str) and kind in WORKFLOW_NODE_TEMPLATE_MAP:
        return kind

    return None


def get_workflow_node_template(*, kind: str | None, node_type: str | None = None, config: dict | None = None):
    resolved_type = resolve_workflow_node_template_type(
        kind=kind,
        node_type=node_type,
        config=config,
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

        node_template = get_workflow_node_template(
            kind=normalized_node.get("kind"),
            node_type=normalized_node.get("type"),
            config=existing_config,
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

    if validate_workflow_app_node(node=node, outgoing_targets=outgoing_targets) is not None:
        return

    if kind == "agent":
        _validate_optional_string(config, "template", node_id=node_id)
        _validate_optional_string(config, "output_key", node_id=node_id)
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
