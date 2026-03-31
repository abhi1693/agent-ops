from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError

from automation.nodes.base import (
    WorkflowNodeDefinition,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
)
from automation.tools import (
    WorkflowToolExecutionContext,
    execute_workflow_tool,
    validate_workflow_tool_config,
)
from automation.triggers import (
    prepare_webhook_trigger_request,
    validate_workflow_trigger_config,
)


_PACKAGE_MANIFEST_PATH = Path(__file__).with_name("package.json")
_APP_PACKAGE_MANIFEST_PATH = _PACKAGE_MANIFEST_PATH.with_name("apps").joinpath("package.json")


def _load_package_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as package_file:
        return json.load(package_file)


def _load_node_manifest(manifest_path: Path) -> dict[str, Any]:
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


_WORKFLOW_BUILTIN_PACKAGE = _load_package_manifest(_PACKAGE_MANIFEST_PATH)
_WORKFLOW_APP_PACKAGE = _load_package_manifest(_APP_PACKAGE_MANIFEST_PATH)


def _validate_trigger_node(config: dict[str, Any], node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del outgoing_targets, node_ids
    validate_workflow_trigger_config(config, node_id=node_id)


def _execute_trigger_node(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    normalized_trigger_config = validate_workflow_trigger_config(runtime.config, node_id=runtime.node["id"])
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": normalized_trigger_config["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
        },
    )


def _validate_tool_node(config: dict[str, Any], node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del outgoing_targets, node_ids
    validate_workflow_tool_config(config, node_id=node_id)


def _execute_tool_node(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    normalized_tool_config = validate_workflow_tool_config(runtime.config, node_id=runtime.node["id"])
    output = execute_workflow_tool(
        WorkflowToolExecutionContext(
            workflow=runtime.workflow,
            node=runtime.node,
            config=normalized_tool_config,
            context=runtime.context,
            secret_paths=runtime.secret_paths,
            secret_values=runtime.secret_values,
            render_template=runtime.render_template,
            set_path_value=runtime.set_path_value,
            resolve_scoped_secret=runtime.resolve_scoped_secret,
        )
    )
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            key: value
            for key, value in output.items()
            if key != "operation"
        },
    )


def _get_default_runtime_implementation(kind: str | None) -> WorkflowNodeImplementation | None:
    if kind == "trigger":
        return WorkflowNodeImplementation(
            validator=_validate_trigger_node,
            executor=_execute_trigger_node,
        )
    if kind == "tool":
        return WorkflowNodeImplementation(
            validator=_validate_tool_node,
            executor=_execute_tool_node,
        )
    return None


def _load_builtin_node_definitions() -> tuple[WorkflowNodeDefinition, ...]:
    nodes_config = _WORKFLOW_BUILTIN_PACKAGE.get("agentOps", {})
    node_modules = nodes_config.get("nodes", ())
    definitions: list[WorkflowNodeDefinition] = []

    for module_path in node_modules:
        imported_module = importlib.import_module(f"automation.nodes.{module_path}")
        implementation = getattr(imported_module, "NODE_IMPLEMENTATION", None)
        if not isinstance(implementation, WorkflowNodeImplementation):
            raise RuntimeError(
                f'Builtin node module "{module_path}" must export NODE_IMPLEMENTATION.'
            )

        module_file = getattr(imported_module, "__file__", None)
        if not isinstance(module_file, str) or not module_file:
            raise RuntimeError(f'Builtin node module "{module_path}" is missing a file path.')

        node_manifest_path = Path(module_file).with_name("node.json")
        definitions.append(
            WorkflowNodeDefinition.from_manifest(
                _load_node_manifest(node_manifest_path),
                implementation=implementation,
            )
        )

    return tuple(definitions)


def _validate_runtime_mapped_node_type(definition: WorkflowNodeDefinition) -> None:
    prefix = f"{definition.kind}."
    if not definition.type.startswith(prefix):
        raise RuntimeError(
            f'Node "{definition.type}" must use a "{prefix}<name>" type.'
        )

    runtime_name = definition.type.removeprefix(prefix).strip()
    if not runtime_name:
        raise RuntimeError(
            f'Node "{definition.type}" must use a "{prefix}<name>" type.'
        )


def _load_app_node_definitions() -> tuple[WorkflowNodeDefinition, ...]:
    nodes_config = _WORKFLOW_APP_PACKAGE.get("agentOps", {})
    node_paths = nodes_config.get("nodes", ())
    definitions: list[WorkflowNodeDefinition] = []

    for node_path in node_paths:
        manifest_path = _APP_PACKAGE_MANIFEST_PATH.parent.joinpath(*node_path.split(".")).joinpath("node.json")
        manifest = _load_node_manifest(manifest_path)
        agent_ops = manifest.get("agentOps") if isinstance(manifest, dict) else None
        kind = agent_ops.get("kind") if isinstance(agent_ops, dict) else None
        implementation = _get_default_runtime_implementation(kind)
        definition = WorkflowNodeDefinition.from_manifest(manifest, implementation=implementation)
        if definition.kind not in {"trigger", "tool"}:
            raise RuntimeError(
                f'Node "{definition.type}" kind "{definition.kind}" is not supported in the app node catalog.'
            )
        _validate_runtime_mapped_node_type(definition)
        definitions.append(definition)

    return tuple(definitions)


_BUILTIN_NODE_DEFINITIONS = _load_builtin_node_definitions()
_APP_NODE_DEFINITIONS = _load_app_node_definitions()

WORKFLOW_NODE_DEFINITIONS = (
    *_BUILTIN_NODE_DEFINITIONS,
    *_APP_NODE_DEFINITIONS,
)

WORKFLOW_NODE_REGISTRY = {
    node_definition.type: node_definition
    for node_definition in WORKFLOW_NODE_DEFINITIONS
}

WORKFLOW_NODE_TEMPLATES = tuple(
    node_definition.serialize()
    for node_definition in WORKFLOW_NODE_DEFINITIONS
)

WORKFLOW_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_NODE_TEMPLATES
}


def get_workflow_node_definition(node_type: str | None) -> WorkflowNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_NODE_REGISTRY.get(node_type.strip())


def get_workflow_node_template(*, node_type: str | None = None):
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_NODE_TEMPLATE_MAP.get(node_type.strip())


def validate_workflow_node(*, node: dict, outgoing_targets: list[str], node_ids: set[str]) -> WorkflowNodeDefinition | None:
    node_definition = get_workflow_node_definition(node.get("type"))
    if node_definition is None:
        return None
    if node_definition.validator is not None:
        node_definition.validator(node.get("config") or {}, node["id"], outgoing_targets, node_ids)
    return node_definition


def execute_workflow_node(
    *,
    workflow,
    node: dict,
    next_node_id: str | None,
    context: dict,
    secret_paths: set[str],
    secret_values: list[str],
    render_template,
    get_path_value,
    set_path_value,
    resolve_scoped_secret,
    evaluate_condition,
) -> WorkflowNodeExecutionResult | None:
    node_definition = get_workflow_node_definition(node.get("type"))
    if node_definition is None or node_definition.executor is None:
        return None
    return node_definition.executor(
        WorkflowNodeExecutionContext(
            workflow=workflow,
            node=node,
            config=node.get("config") or {},
            next_node_id=next_node_id,
            context=context,
            secret_paths=secret_paths,
            secret_values=secret_values,
            render_template=render_template,
            get_path_value=get_path_value,
            set_path_value=set_path_value,
            resolve_scoped_secret=resolve_scoped_secret,
            evaluate_condition=evaluate_condition,
        )
    )


def prepare_workflow_node_webhook_request(*, workflow, node: dict, request) -> tuple[str, dict[str, Any], dict[str, Any]]:
    node_definition = get_workflow_node_definition(node.get("type"))
    if node_definition is None:
        node_type = node.get("type")
        raise ValidationError({"trigger": f'Unsupported trigger node type "{node_type}".'})
    if node_definition.kind != "trigger":
        raise ValidationError({"trigger": f'Node type "{node_definition.type}" does not support webhook delivery.'})
    return prepare_webhook_trigger_request(
        workflow=workflow,
        node=node,
        request=request,
    )


def normalize_workflow_node_config(
    *,
    node_type: str | None,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(config or {})
    node_definition = get_workflow_node_definition(node_type)
    if node_definition is None:
        return normalized

    prefix = f"{node_definition.kind}."
    if node_definition.kind == "trigger" and node_definition.type.startswith(prefix):
        normalized["type"] = node_definition.type.removeprefix(prefix).strip()
    elif node_definition.kind == "tool" and node_definition.type.startswith(prefix):
        normalized["tool_name"] = node_definition.type.removeprefix(prefix).strip()

    return normalized
