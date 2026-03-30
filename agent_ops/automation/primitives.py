from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.tools import WORKFLOW_TOOL_DEFINITIONS, validate_workflow_tool_config
from automation.triggers import WORKFLOW_TRIGGER_DEFINITIONS, validate_workflow_trigger_config


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
        "example": '{\n  "type": "github_webhook"\n}',
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


WORKFLOW_NODE_TEMPLATES = (
    {
        "kind": "trigger",
        "label": "Trigger",
        "description": "Start the workflow from an incoming payload.",
        "icon": "mdi-play-circle-outline",
        "config": {
            "type": "manual",
            "auth_secret_group_id": "",
        },
        "fields": (
            {
                "key": "type",
                "label": "Trigger type",
                "type": "select",
                "options": tuple(
                    {"value": trigger_definition["name"], "label": trigger_definition["label"]}
                    for trigger_definition in WORKFLOW_TRIGGER_DEFINITIONS
                ),
                "help_text": "Choose how this workflow starts. The inspector below will switch to that trigger's settings.",
            },
            {
                "key": "auth_secret_group_id",
                "label": "Auth secret group",
                "type": "select",
                "options": (),
                "help_text": "Optional. If set, this node resolves authentication secrets from the selected secret group by assignment key or grouped secret name.",
            },
        ),
    },
    {
        "kind": "agent",
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
    {
        "kind": "tool",
        "label": "Tool",
        "description": "Run a tool from the workflow tool catalog against workflow context.",
        "icon": "mdi-tools",
        "config": {
            "tool_name": "passthrough",
            "auth_secret_group_id": "",
        },
        "fields": (
            {
                "key": "tool_name",
                "label": "Tool",
                "type": "select",
                "options": tuple(
                    {"value": tool_definition["name"], "label": tool_definition["label"]}
                    for tool_definition in WORKFLOW_TOOL_DEFINITIONS
                ),
                "help_text": "Choose a tool definition. The inspector below will switch to that tool's settings.",
            },
            {
                "key": "auth_secret_group_id",
                "label": "Auth secret group",
                "type": "select",
                "options": (),
                "help_text": "Optional. If set, this node resolves authentication secrets from the selected secret group by assignment key or grouped secret name.",
            },
        ),
    },
    {
        "kind": "condition",
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

    if kind == "trigger":
        validate_workflow_trigger_config(config, node_id=node_id)
        if len(outgoing_targets) > 1:
            _raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')
        return

    if kind == "agent":
        _validate_optional_string(config, "template", node_id=node_id)
        _validate_optional_string(config, "output_key", node_id=node_id)
        if len(outgoing_targets) > 1:
            _raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')
        return

    if kind == "tool":
        validate_workflow_tool_config(config, node_id=node_id)
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
