from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from .base import (
    WorkflowToolExecutionContext,
    normalize_workflow_tool_config,
    _raise_definition_error,
)
from automation.nodes.apps.infrastructure.kubectl.node import TOOL_DEFINITION as KUBECTL_TOOL
from automation.nodes.apps.integrations.mcp_server.node import TOOL_DEFINITION as MCP_SERVER_TOOL
from automation.nodes.apps.observability.tool.node import (
    ELASTICSEARCH_SEARCH_TOOL_DEFINITION as ELASTICSEARCH_SEARCH_TOOL,
    PROMETHEUS_QUERY_TOOL_DEFINITION as PROMETHEUS_QUERY_TOOL,
)
from automation.nodes.apps.openai.chat.node import TOOL_DEFINITION as OPENAI_COMPATIBLE_CHAT_TOOL
from automation.nodes.apps.utilities.secret.node import TOOL_DEFINITION as SECRET_TOOL
from automation.nodes.apps.utilities.template.node import TOOL_DEFINITION as TEMPLATE_TOOL
from .set_value import TOOL_DEFINITION as SET_TOOL


WORKFLOW_TOOL_REGISTRY = {
    tool_definition.name: tool_definition
    for tool_definition in (
        SET_TOOL,
        TEMPLATE_TOOL,
        SECRET_TOOL,
        KUBECTL_TOOL,
        MCP_SERVER_TOOL,
        PROMETHEUS_QUERY_TOOL,
        ELASTICSEARCH_SEARCH_TOOL,
        OPENAI_COMPATIBLE_CHAT_TOOL,
    )
}

WORKFLOW_TOOL_DEFINITIONS = tuple(
    tool_definition.serialize() for tool_definition in WORKFLOW_TOOL_REGISTRY.values()
)


def get_workflow_tool_definition(name: str):
    return WORKFLOW_TOOL_REGISTRY.get(name)


def validate_workflow_tool_config(config: dict[str, Any], *, node_id: str) -> dict[str, Any]:
    normalized = normalize_workflow_tool_config(config)
    tool_name = normalized.get("tool_name")

    if not isinstance(tool_name, str) or not tool_name.strip():
        _raise_definition_error(f'Node "{node_id}" must define config.tool_name.')

    tool_definition = get_workflow_tool_definition(tool_name)
    if tool_definition is None:
        available_names = ", ".join(sorted(WORKFLOW_TOOL_REGISTRY))
        _raise_definition_error(
            f'Node "{node_id}" config.tool_name must be one of: {available_names}.'
        )

    if tool_definition.validator is not None:
        tool_definition.validator(normalized, node_id)

    return normalized


def execute_workflow_tool(runtime: WorkflowToolExecutionContext) -> dict[str, Any]:
    tool_name = runtime.config["tool_name"]
    tool_definition = get_workflow_tool_definition(tool_name)
    if tool_definition is None or tool_definition.executor is None:
        raise ValidationError({"definition": f'Unsupported tool "{tool_name}".'})
    return tool_definition.executor(runtime)
