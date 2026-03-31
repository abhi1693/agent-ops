from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError

from automation.nodes.base import WorkflowNodeDefinition
from automation.tools import (
    WorkflowToolExecutionContext,
    execute_workflow_tool,
    validate_workflow_tool_config,
)
from automation.triggers import (
    WorkflowTriggerRequestContext,
    get_workflow_trigger_definition,
    validate_workflow_trigger_config,
)


@dataclass(frozen=True)
class WorkflowAppNodeDefinition:
    template_definition: WorkflowNodeDefinition
    trigger_type: str | None = None
    tool_name: str | None = None

    @classmethod
    def from_manifest(
        cls,
        manifest: dict[str, Any],
    ) -> "WorkflowAppNodeDefinition":
        template_definition = WorkflowNodeDefinition.from_manifest(manifest)
        agent_ops = manifest.get("agentOps", {})
        trigger_type = agent_ops.get("triggerType")
        tool_name = agent_ops.get("toolName")
        node_type = template_definition.type
        kind = template_definition.kind
        if trigger_type is not None and (not isinstance(trigger_type, str) or not trigger_type.strip()):
            raise ValueError(f'App node "{node_type}" agentOps.triggerType must be a non-empty string when provided.')
        if tool_name is not None and (not isinstance(tool_name, str) or not tool_name.strip()):
            raise ValueError(f'App node "{node_type}" agentOps.toolName must be a non-empty string when provided.')
        if kind == "trigger" and trigger_type is None:
            raise ValueError(f'App node "{node_type}" trigger nodes must define agentOps.triggerType.')
        if kind == "tool" and tool_name is None:
            raise ValueError(f'App node "{node_type}" tool nodes must define agentOps.toolName.')

        return cls(
            template_definition=template_definition,
            trigger_type=trigger_type.strip() if isinstance(trigger_type, str) else None,
            tool_name=tool_name.strip() if isinstance(tool_name, str) else None,
        )


_APP_NODE_PACKAGE_MANIFEST_PATH = Path(__file__).parent / "nodes" / "apps" / "package.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def _load_app_node_definitions() -> tuple[WorkflowAppNodeDefinition, ...]:
    package_manifest = _load_json(_APP_NODE_PACKAGE_MANIFEST_PATH)
    node_paths = package_manifest.get("agentOps", {}).get("nodes", ())
    definitions: list[WorkflowAppNodeDefinition] = []

    for node_path in node_paths:
        manifest_path = _APP_NODE_PACKAGE_MANIFEST_PATH.parent.joinpath(*node_path.split(".")).joinpath("node.json")
        manifest = _load_json(manifest_path)
        definitions.append(WorkflowAppNodeDefinition.from_manifest(manifest))

    return tuple(definitions)


WORKFLOW_APP_NODE_PACKAGE = _load_json(_APP_NODE_PACKAGE_MANIFEST_PATH)
WORKFLOW_APP_NODE_DEFINITIONS = _load_app_node_definitions()
WORKFLOW_APP_NODE_DEFINITION_MAP = {
    definition.template_definition.type: definition
    for definition in WORKFLOW_APP_NODE_DEFINITIONS
}


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _get_node_definition(node_type: str | None) -> WorkflowAppNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_APP_NODE_DEFINITION_MAP.get(node_type.strip())


def _resolve_required_definition(*, node: dict[str, Any]) -> WorkflowAppNodeDefinition:
    node_type = node.get("type")
    definition = _get_node_definition(node_type)
    if definition is not None:
        return definition

    _raise_definition_error(f'Node "{node["id"]}" type "{node_type}" is not a supported app node.')


def _validate_single_outgoing_target(*, node_id: str, outgoing_targets: list[str]) -> None:
    if len(outgoing_targets) > 1:
        _raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')


def _validate_routed_trigger_config(
    *,
    definition: WorkflowAppNodeDefinition,
    config: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    return validate_workflow_trigger_config(
        {
            **config,
            "type": definition.trigger_type,
        },
        node_id=node_id,
    )


def _validate_routed_tool_config(
    *,
    definition: WorkflowAppNodeDefinition,
    config: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    if definition.tool_name is None:
        _raise_definition_error(f'Node "{node_id}" has no routed tool implementation.')
    return validate_workflow_tool_config(
        {
            **config,
            "tool_name": definition.tool_name,
        },
        node_id=node_id,
    )


def validate_workflow_app_node(*, node: dict[str, Any], outgoing_targets: list[str]) -> WorkflowAppNodeDefinition | None:
    definition = _get_node_definition(node.get("type"))
    if definition is None:
        return None

    _validate_single_outgoing_target(node_id=node["id"], outgoing_targets=outgoing_targets)
    config = node.get("config") or {}
    if definition.trigger_type is not None:
        _validate_routed_trigger_config(definition=definition, config=config, node_id=node["id"])
        return definition

    if definition.tool_name is not None:
        _validate_routed_tool_config(definition=definition, config=config, node_id=node["id"])
        return definition

    _raise_definition_error(f'Node "{node["id"]}" type "{node.get("type")}" is not executable.')


def execute_workflow_app_node(
    *,
    workflow,
    node: dict[str, Any],
    context: dict[str, Any],
    secret_paths: set[str],
    secret_values: list[str],
    render_template,
    set_path_value,
    resolve_scoped_secret,
) -> dict[str, Any] | None:
    definition = _get_node_definition(node.get("type"))
    if definition is None:
        return None

    config = node.get("config") or {}

    if definition.trigger_type is not None:
        normalized = _validate_routed_trigger_config(definition=definition, config=config, node_id=node["id"])
        return {
            "payload": context["trigger"]["payload"],
            "trigger_type": normalized["type"],
            "trigger_meta": context["trigger"].get("meta", {}),
        }

    normalized = _validate_routed_tool_config(definition=definition, config=config, node_id=node["id"])
    output = execute_workflow_tool(
        WorkflowToolExecutionContext(
            workflow=workflow,
            node=node,
            config=normalized,
            context=context,
            secret_paths=secret_paths,
            secret_values=secret_values,
            render_template=render_template,
            set_path_value=set_path_value,
            resolve_scoped_secret=resolve_scoped_secret,
        )
    )
    return {
        key: value
        for key, value in output.items()
        if key != "operation"
    }


def prepare_workflow_app_webhook_request(*, workflow, node: dict[str, Any], request) -> tuple[str, dict[str, Any], dict[str, Any]]:
    definition = _resolve_required_definition(node=node)
    if definition.trigger_type is None:
        raise ValidationError(
            {"trigger": f'Node type "{node.get("type") or node.get("kind")}" does not support webhook delivery.'}
        )

    normalized = _validate_routed_trigger_config(
        definition=definition,
        config=node.get("config") or {},
        node_id=node["id"],
    )
    trigger_definition = get_workflow_trigger_definition(definition.trigger_type)
    if trigger_definition is None or trigger_definition.webhook_handler is None:
        raise ValidationError({"trigger": f'Trigger type "{definition.trigger_type}" does not support webhook delivery.'})

    return (
        definition.trigger_type,
        *trigger_definition.webhook_handler(
            WorkflowTriggerRequestContext(
                workflow=workflow,
                node=node,
                config=normalized,
                request=request,
                body=request.body,
            )
        ),
    )
