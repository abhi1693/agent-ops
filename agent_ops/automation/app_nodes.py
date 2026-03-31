from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from automation.nodes.base import WorkflowNodeDefinition


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


def get_workflow_app_node_definition(node_type: str | None) -> WorkflowNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_APP_NODE_DEFINITION_MAP.get(node_type.strip())


def normalize_workflow_app_node_config(
    *,
    node_type: str | None,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(config or {})
    definition = get_workflow_app_node_definition(node_type)
    if definition is None:
        return normalized

    if definition.kind == "trigger":
        normalized["type"] = _derive_trigger_type(definition)
        return normalized

    if definition.kind == "tool":
        normalized["tool_name"] = _derive_tool_name(definition)
        return normalized

    raise RuntimeError(f'App node "{definition.type}" is not executable.')
