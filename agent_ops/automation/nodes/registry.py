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
    WorkflowNodeWebhookContext,
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


def _load_node_implementation(module_import_path: str) -> WorkflowNodeImplementation:
    imported_module = importlib.import_module(module_import_path)
    implementation = getattr(imported_module, "NODE_IMPLEMENTATION", None)
    if not isinstance(implementation, WorkflowNodeImplementation):
        raise RuntimeError(
            f'Node module "{module_import_path}" must export NODE_IMPLEMENTATION.'
        )
    return implementation


def _load_builtin_node_definitions() -> tuple[WorkflowNodeDefinition, ...]:
    nodes_config = _WORKFLOW_BUILTIN_PACKAGE.get("agentOps", {})
    node_modules = nodes_config.get("nodes", ())
    definitions: list[WorkflowNodeDefinition] = []

    for module_path in node_modules:
        module_import_path = f"automation.nodes.{module_path}"
        implementation = _load_node_implementation(module_import_path)
        imported_module = importlib.import_module(module_import_path)

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


def _resolve_app_node_module_path(node_path: str, kind: str) -> str:
    candidates = [f"automation.nodes.apps.{node_path}.node"]

    parent_path, separator, leaf_name = node_path.rpartition(".")
    if separator:
        candidates.append(f"automation.nodes.apps.{parent_path}.{kind}.{leaf_name}")

    for candidate in candidates:
        if importlib.util.find_spec(candidate) is not None:
            return candidate

    raise RuntimeError(
        f'App node "{node_path}" kind "{kind}" is missing a matching Python module.'
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
        if kind not in {"trigger", "tool"}:
            raise RuntimeError(
                f'Node manifest "{node_path}" kind "{kind}" is not supported in the app node catalog.'
            )
        implementation = _load_node_implementation(
            _resolve_app_node_module_path(node_path, kind),
        )
        definition = WorkflowNodeDefinition.from_manifest(manifest, implementation=implementation)
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
    if node_definition.webhook_handler is None:
        raise ValidationError({"trigger": f'Node type "{node_definition.type}" does not support webhook delivery.'})

    normalized_config = normalize_workflow_node_config(
        node_type=node_definition.type,
        config=node.get("config") or {},
    )
    if node_definition.validator is not None:
        node_definition.validator(
            normalized_config,
            node["id"],
            [],
            {node["id"]},
        )

    trigger_mode = node_definition.type
    if node_definition.type.startswith("trigger."):
        trigger_mode = node_definition.type.removeprefix("trigger.")

    return (
        trigger_mode,
        *node_definition.webhook_handler(
            WorkflowNodeWebhookContext(
                workflow=workflow,
                node=node,
                config=normalized_config,
                request=request,
                body=request.body,
            )
        ),
    )


def normalize_workflow_node_config(
    *,
    node_type: str | None,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(config or {})
    auth_secret_group_id = normalized.get("auth_secret_group_id")
    if auth_secret_group_id in ("", None):
        normalized.pop("auth_secret_group_id", None)
    elif not isinstance(auth_secret_group_id, str):
        normalized["auth_secret_group_id"] = str(auth_secret_group_id)

    node_definition = get_workflow_node_definition(node_type)
    if node_definition is None:
        return normalized

    prefix = f"{node_definition.kind}."
    if node_definition.kind == "trigger" and node_definition.type.startswith(prefix):
        normalized["type"] = node_definition.type.removeprefix(prefix).strip()
    elif node_definition.kind == "tool" and node_definition.type.startswith(prefix):
        normalized["tool_name"] = node_definition.type.removeprefix(prefix).strip()

    return normalized
