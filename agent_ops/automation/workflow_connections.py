from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from automation.workflow_agents import (
    AGENT_AUXILIARY_MAX_CONNECTIONS_BY_PORT,
    AGENT_LANGUAGE_MODEL_INPUT_PORT,
    SUPPORTED_AGENT_AUXILIARY_PORTS,
    describe_agent_auxiliary_supported_sources,
    is_agent_auxiliary_source_compatible,
)


def _normalized_port(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def get_edge_target_port(edge: dict[str, Any]) -> str | None:
    return _normalized_port(edge.get("targetPort"))


def is_auxiliary_edge(edge: dict[str, Any]) -> bool:
    target_port = get_edge_target_port(edge)
    return target_port in SUPPORTED_AGENT_AUXILIARY_PORTS


def split_workflow_edges(edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary_edges: list[dict[str, Any]] = []
    auxiliary_edges: list[dict[str, Any]] = []

    for edge in edges:
        if is_auxiliary_edge(edge):
            auxiliary_edges.append(edge)
        else:
            primary_edges.append(edge)

    return primary_edges, auxiliary_edges


def build_auxiliary_connections_by_target(
    *,
    nodes_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    connections_by_target: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for edge in edges:
        target_port = get_edge_target_port(edge)
        if target_port is None:
            continue
        source_node = nodes_by_id.get(edge.get("source"))
        target_node = nodes_by_id.get(edge.get("target"))
        if source_node is None or target_node is None:
            continue

        target_connections = connections_by_target.setdefault(target_node["id"], {})
        target_connections.setdefault(target_port, []).append(source_node)

    return connections_by_target


def validate_agent_auxiliary_edges(
    *,
    nodes_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    connections_by_target = build_auxiliary_connections_by_target(
        nodes_by_id=nodes_by_id,
        edges=edges,
    )

    for edge in edges:
        target_port = get_edge_target_port(edge)
        if target_port is None:
            continue

        edge_id = edge.get("id") or "<unknown>"
        source_node = nodes_by_id[edge["source"]]
        target_node = nodes_by_id[edge["target"]]

        if target_port not in SUPPORTED_AGENT_AUXILIARY_PORTS:
            raise ValidationError(
                {"definition": f'Edge "{edge_id}" targetPort "{target_port}" is not supported.'}
            )

        if target_node.get("kind") != "agent" or target_node.get("type") != "agent":
            raise ValidationError(
                {
                    "definition": (
                        f'Edge "{edge_id}" targetPort "{target_port}" is only supported when targeting an agent node.'
                    )
                }
            )

        source_port = _normalized_port(edge.get("sourcePort"))
        if source_port is not None and source_port != target_port:
            raise ValidationError(
                {
                    "definition": (
                        f'Edge "{edge_id}" sourcePort "{source_port}" must match targetPort "{target_port}" '
                        "for agent auxiliary connections."
                    )
                }
            )

        source_type = source_node.get("type")
        if not is_agent_auxiliary_source_compatible(source_node=source_node, target_port=target_port):
            supported_types_label = describe_agent_auxiliary_supported_sources(target_port)
            raise ValidationError(
                {
                    "definition": (
                        f'Edge "{edge_id}" cannot connect node type "{source_type}" to agent port "{target_port}". '
                        f"Supported source node types: {supported_types_label}."
                    )
                }
            )

    for target_node_id, connections_by_port in connections_by_target.items():
        for target_port, max_connections in AGENT_AUXILIARY_MAX_CONNECTIONS_BY_PORT.items():
            if max_connections is None:
                continue
            connection_count = len(connections_by_port.get(target_port, []))
            if connection_count > max_connections:
                raise ValidationError(
                    {
                        "definition": (
                            f'Agent node "{target_node_id}" accepts at most {max_connections} connection(s) '
                            f'on port "{target_port}".'
                        )
                    }
                )

    for node_id, node in nodes_by_id.items():
        if node.get("kind") != "agent" or node.get("type") != "agent":
            continue
        if len(connections_by_target.get(node_id, {}).get(AGENT_LANGUAGE_MODEL_INPUT_PORT, [])) < 1:
            raise ValidationError(
                {
                    "definition": (
                        f'Agent node "{node_id}" must connect exactly one chat model on port "{AGENT_LANGUAGE_MODEL_INPUT_PORT}".'
                    )
                }
            )
