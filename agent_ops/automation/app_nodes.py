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
class WorkflowAppNodeRoute:
    app_id: str
    node_type: str
    kind: str
    resource: str
    operation: str
    trigger_type: str | None = None
    tool_name: str | None = None

    @classmethod
    def from_manifest(
        cls,
        payload: dict[str, Any],
        *,
        app_id: str,
        node_type: str,
        kind: str,
    ) -> "WorkflowAppNodeRoute":
        resource = payload.get("resource")
        operation = payload.get("operation")
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError(f'App node "{node_type}" route.resource must be a non-empty string.')
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError(f'App node "{node_type}" route.operation must be a non-empty string.')

        trigger_type = payload.get("triggerType")
        tool_name = payload.get("toolName")
        if trigger_type is not None and (not isinstance(trigger_type, str) or not trigger_type.strip()):
            raise ValueError(f'App node "{node_type}" route.triggerType must be a non-empty string when provided.')
        if tool_name is not None and (not isinstance(tool_name, str) or not tool_name.strip()):
            raise ValueError(f'App node "{node_type}" route.toolName must be a non-empty string when provided.')

        return cls(
            app_id=app_id,
            node_type=node_type,
            kind=kind,
            resource=resource.strip(),
            operation=operation.strip(),
            trigger_type=trigger_type.strip() if isinstance(trigger_type, str) else None,
            tool_name=tool_name.strip() if isinstance(tool_name, str) else None,
        )


@dataclass(frozen=True)
class WorkflowAppNodeDefinition:
    template_definition: WorkflowNodeDefinition
    route: WorkflowAppNodeRoute


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
        template_definition = WorkflowNodeDefinition.from_manifest(manifest)
        route_payload = manifest.get("agentOps", {}).get("route")
        if not isinstance(route_payload, dict):
            raise RuntimeError(f'App node "{template_definition.type}" must define an agentOps.route object.')

        route = WorkflowAppNodeRoute.from_manifest(
            route_payload,
            app_id=template_definition.app_id,
            node_type=template_definition.type,
            kind=template_definition.kind,
        )
        definitions.append(
            WorkflowAppNodeDefinition(
                template_definition=template_definition,
                route=route,
            )
        )

    return tuple(definitions)


WORKFLOW_APP_NODE_PACKAGE = _load_json(_APP_NODE_PACKAGE_MANIFEST_PATH)
WORKFLOW_APP_NODE_DEFINITIONS = _load_app_node_definitions()
WORKFLOW_APP_NODE_DEFINITION_MAP = {
    definition.template_definition.type: definition
    for definition in WORKFLOW_APP_NODE_DEFINITIONS
}
WORKFLOW_APP_NODE_ROUTES = tuple(
    definition.route
    for definition in WORKFLOW_APP_NODE_DEFINITIONS
)
WORKFLOW_APP_NODE_ROUTE_MAP = {
    route.node_type: route
    for route in WORKFLOW_APP_NODE_ROUTES
}


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def get_workflow_app_node_definition(
    *,
    node_type: str | None,
) -> WorkflowAppNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_APP_NODE_DEFINITION_MAP.get(node_type.strip())


def _get_node_route(node_type: str | None) -> WorkflowAppNodeRoute | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    return WORKFLOW_APP_NODE_ROUTE_MAP.get(node_type.strip())


def _resolve_required_route(*, node: dict[str, Any]) -> WorkflowAppNodeRoute:
    node_type = node.get("type")
    route = _get_node_route(node_type)
    if route is not None:
        return route

    _raise_definition_error(f'Node "{node["id"]}" type "{node_type}" is not a supported app node.')


def get_workflow_app_node_metadata(
    *,
    node_type: str | None,
) -> dict[str, str]:
    route = _get_node_route(node_type)
    if route is None:
        return {}
    return {
        "resource": route.resource,
        "operation": route.operation,
    }


def _reject_legacy_selector_fields(
    *,
    config: dict[str, Any],
    node_id: str,
    keys: tuple[str, ...],
) -> None:
    legacy_fields = [
        f"config.{key}"
        for key in keys
        if key in config
    ]
    if legacy_fields:
        _raise_definition_error(
            f'Node "{node_id}" must not define legacy selector fields: {", ".join(legacy_fields)}.'
        )


def _validate_single_outgoing_target(*, node_id: str, outgoing_targets: list[str]) -> None:
    if len(outgoing_targets) > 1:
        _raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')


def _validate_routed_trigger_config(
    *,
    route: WorkflowAppNodeRoute,
    config: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    _reject_legacy_selector_fields(
        config=config,
        node_id=node_id,
        keys=("resource", "operation", "type"),
    )
    return validate_workflow_trigger_config(
        {
            **config,
            "type": route.trigger_type,
        },
        node_id=node_id,
    )


def _validate_routed_tool_config(
    *,
    route: WorkflowAppNodeRoute,
    config: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    if route.tool_name is None:
        _raise_definition_error(f'Node "{node_id}" has no routed tool implementation.')
    _reject_legacy_selector_fields(
        config=config,
        node_id=node_id,
        keys=("resource", "operation", "tool_name"),
    )
    return validate_workflow_tool_config(
        {
            **config,
            "tool_name": route.tool_name,
        },
        node_id=node_id,
    )


def validate_workflow_app_node(*, node: dict[str, Any], outgoing_targets: list[str]) -> WorkflowAppNodeRoute | None:
    if _get_node_route(node.get("type")) is None:
        return None

    _validate_single_outgoing_target(node_id=node["id"], outgoing_targets=outgoing_targets)
    route = _resolve_required_route(node=node)

    config = node.get("config") or {}
    if route.trigger_type is not None:
        _validate_routed_trigger_config(route=route, config=config, node_id=node["id"])
        return route

    if route.tool_name is not None:
        _validate_routed_tool_config(route=route, config=config, node_id=node["id"])
        return route

    _raise_definition_error(f'Node "{node["id"]}" route "{route.node_type}" is not executable.')


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
    if _get_node_route(node.get("type")) is None:
        return None

    route = _resolve_required_route(node=node)
    config = node.get("config") or {}

    if route.trigger_type is not None:
        normalized = _validate_routed_trigger_config(route=route, config=config, node_id=node["id"])
        return {
            "payload": context["trigger"]["payload"],
            "trigger_type": normalized["type"],
            "trigger_meta": context["trigger"].get("meta", {}),
            "resource": route.resource,
            "operation": route.operation,
        }

    normalized = _validate_routed_tool_config(route=route, config=config, node_id=node["id"])
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
        **output,
        "resource": route.resource,
        "operation": route.operation,
    }


def prepare_workflow_app_webhook_request(*, workflow, node: dict[str, Any], request) -> tuple[str, dict[str, Any], dict[str, Any]]:
    route = _resolve_required_route(node=node)
    if route.trigger_type is None:
        raise ValidationError(
            {"trigger": f'Node type "{node.get("type") or node.get("kind")}" does not support webhook delivery.'}
        )

    normalized = _validate_routed_trigger_config(
        route=route,
        config=node.get("config") or {},
        node_id=node["id"],
    )
    trigger_definition = get_workflow_trigger_definition(route.trigger_type)
    if trigger_definition is None or trigger_definition.webhook_handler is None:
        raise ValidationError({"trigger": f'Trigger type "{route.trigger_type}" does not support webhook delivery.'})

    return (
        route.trigger_type,
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
