from __future__ import annotations

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


_APP_NODE_PACKAGE_MANIFEST_PATH = Path(__file__).parent / "nodes" / "apps" / "package.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def _load_app_node_definitions() -> tuple[WorkflowNodeDefinition, ...]:
    package_manifest = _load_json(_APP_NODE_PACKAGE_MANIFEST_PATH)
    node_paths = package_manifest.get("agentOps", {}).get("nodes", ())
    definitions: list[WorkflowNodeDefinition] = []

    for node_path in node_paths:
        manifest_path = _APP_NODE_PACKAGE_MANIFEST_PATH.parent.joinpath(*node_path.split(".")).joinpath("node.json")
        manifest = _load_json(manifest_path)
        definition = WorkflowNodeDefinition.from_manifest(manifest)
        _derive_app_node_runtime_name(definition)
        definitions.append(definition)

    return tuple(definitions)


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _derive_app_node_runtime_name(definition: WorkflowNodeDefinition) -> str:
    if definition.kind not in {"trigger", "tool"}:
        raise RuntimeError(
            f'App node "{definition.type}" kind "{definition.kind}" is not supported.'
        )

    prefix = f"{definition.kind}."
    if not definition.type.startswith(prefix):
        raise RuntimeError(
            f'App node "{definition.type}" must use a "{prefix}<name>" type.'
        )

    runtime_name = definition.type.removeprefix(prefix).strip()
    if not runtime_name:
        raise RuntimeError(
            f'App node "{definition.type}" must use a "{prefix}<name>" type.'
        )
    return runtime_name


def _derive_trigger_type(definition: WorkflowNodeDefinition) -> str:
    if definition.kind != "trigger":
        raise RuntimeError(f'App node "{definition.type}" is not a trigger node.')
    return _derive_app_node_runtime_name(definition)


def _derive_tool_name(definition: WorkflowNodeDefinition) -> str:
    if definition.kind != "tool":
        raise RuntimeError(f'App node "{definition.type}" is not a tool node.')
    return _derive_app_node_runtime_name(definition)


WORKFLOW_APP_NODE_PACKAGE = _load_json(_APP_NODE_PACKAGE_MANIFEST_PATH)
WORKFLOW_APP_NODE_DEFINITIONS = _load_app_node_definitions()
WORKFLOW_APP_NODE_DEFINITION_MAP = {
    definition.type: definition
    for definition in WORKFLOW_APP_NODE_DEFINITIONS
}


def _get_node_definition(node_type: str | None) -> WorkflowNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_APP_NODE_DEFINITION_MAP.get(node_type.strip())


def _resolve_required_definition(*, node: dict[str, Any]) -> WorkflowNodeDefinition:
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
    definition: WorkflowNodeDefinition,
    config: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    return validate_workflow_trigger_config(
        {
            **config,
            "type": _derive_trigger_type(definition),
        },
        node_id=node_id,
    )


def _validate_routed_tool_config(
    *,
    definition: WorkflowNodeDefinition,
    config: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    return validate_workflow_tool_config(
        {
            **config,
            "tool_name": _derive_tool_name(definition),
        },
        node_id=node_id,
    )


def validate_workflow_app_node(*, node: dict[str, Any], outgoing_targets: list[str]) -> WorkflowNodeDefinition | None:
    definition = _get_node_definition(node.get("type"))
    if definition is None:
        return None

    _validate_single_outgoing_target(node_id=node["id"], outgoing_targets=outgoing_targets)
    config = node.get("config") or {}
    if definition.kind == "trigger":
        _validate_routed_trigger_config(definition=definition, config=config, node_id=node["id"])
        return definition

    if definition.kind == "tool":
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

    if definition.kind == "trigger":
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
    if definition.kind != "trigger":
        raise ValidationError(
            {"trigger": f'Node type "{node.get("type") or node.get("kind")}" does not support webhook delivery.'}
        )

    normalized = _validate_routed_trigger_config(
        definition=definition,
        config=node.get("config") or {},
        node_id=node["id"],
    )
    trigger_type = _derive_trigger_type(definition)
    trigger_definition = get_workflow_trigger_definition(trigger_type)
    if trigger_definition is None or trigger_definition.webhook_handler is None:
        raise ValidationError({"trigger": f'Trigger type "{trigger_type}" does not support webhook delivery.'})

    return (
        trigger_type,
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
