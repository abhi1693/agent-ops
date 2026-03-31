from __future__ import annotations

import importlib
import json
from pathlib import Path

from automation.nodes.base import (
    WorkflowNodeDefinition,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
)


_PACKAGE_MANIFEST_PATH = Path(__file__).with_name("package.json")


def _load_package_manifest() -> dict:
    with _PACKAGE_MANIFEST_PATH.open("r", encoding="utf-8") as package_file:
        return json.load(package_file)


def _load_node_manifest(manifest_path: Path) -> dict:
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


WORKFLOW_BUILTIN_NODE_PACKAGE = _load_package_manifest()


def _load_builtin_node_definitions() -> tuple[WorkflowNodeDefinition, ...]:
    nodes_config = WORKFLOW_BUILTIN_NODE_PACKAGE.get("agentOps", {})
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


WORKFLOW_BUILTIN_NODE_DEFINITIONS = _load_builtin_node_definitions()

WORKFLOW_BUILTIN_NODE_REGISTRY = {
    node_definition.type: node_definition
    for node_definition in WORKFLOW_BUILTIN_NODE_DEFINITIONS
}

WORKFLOW_BUILTIN_NODE_TEMPLATES = tuple(
    node_definition.serialize()
    for node_definition in WORKFLOW_BUILTIN_NODE_DEFINITIONS
)

WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP = {
    template["type"]: template
    for template in WORKFLOW_BUILTIN_NODE_TEMPLATES
}

def get_workflow_builtin_node_definition(node_type: str | None) -> WorkflowNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_BUILTIN_NODE_REGISTRY.get(node_type.strip())


def resolve_workflow_builtin_node_type(
    *,
    kind: str | None,
    node_type: str | None = None,
    config: dict | None = None,
) -> str | None:
    del kind, config
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    normalized_type = node_type.strip()
    if normalized_type in WORKFLOW_BUILTIN_NODE_REGISTRY:
        return normalized_type
    return None


def get_workflow_builtin_node_template(*, kind: str | None, node_type: str | None = None, config: dict | None = None):
    resolved_type = resolve_workflow_builtin_node_type(
        kind=kind,
        node_type=node_type,
        config=config,
    )
    if resolved_type is None:
        return None
    return WORKFLOW_BUILTIN_NODE_TEMPLATE_MAP.get(resolved_type)


def validate_workflow_builtin_node(*, node: dict, outgoing_targets: list[str], node_ids: set[str]) -> WorkflowNodeDefinition | None:
    node_definition = get_workflow_builtin_node_definition(node.get("type"))
    if node_definition is None:
        return None
    if node_definition.validator is not None:
        node_definition.validator(node.get("config") or {}, node["id"], outgoing_targets, node_ids)
    return node_definition


def execute_workflow_builtin_node(
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
    evaluate_condition,
) -> WorkflowNodeExecutionResult | None:
    node_definition = get_workflow_builtin_node_definition(node.get("type"))
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
            evaluate_condition=evaluate_condition,
        )
    )
