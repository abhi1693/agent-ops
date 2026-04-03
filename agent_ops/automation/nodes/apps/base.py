from __future__ import annotations

from dataclasses import dataclass, replace

from automation.nodes.base import WorkflowNodeDefinition


def bind_workflow_app_node(
    *,
    app_id: str,
    app_label: str,
    app_description: str,
    app_icon: str,
    node: WorkflowNodeDefinition,
) -> WorkflowNodeDefinition:
    return replace(
        node,
        app_id=app_id,
        app_label=app_label,
        app_description=app_description,
        app_icon=app_icon,
    )


@dataclass(frozen=True)
class WorkflowAppDefinition:
    id: str
    label: str
    description: str
    icon: str
    nodes: tuple[WorkflowNodeDefinition, ...]
    sort_order: int = 1000

    def __post_init__(self) -> None:
        for field_name in ("id", "label", "description", "icon"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Workflow app "{field_name}" must be a non-empty string.')

        bound_nodes = tuple(
            bind_workflow_app_node(
                app_id=self.id,
                app_label=self.label,
                app_description=self.description,
                app_icon=self.icon,
                node=node,
            )
            for node in self.nodes
        )
        node_types = [node.type for node in bound_nodes]
        duplicate_node_types = {
            node_type
            for node_type in node_types
            if node_types.count(node_type) > 1
        }
        if duplicate_node_types:
            duplicate_list = ", ".join(sorted(duplicate_node_types))
            raise ValueError(
                f'Workflow app "{self.id}" declares duplicate node types: {duplicate_list}.'
            )

        object.__setattr__(self, "nodes", bound_nodes)

    def serialize(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "node_types": [node.type for node in self.nodes],
            "sort_order": self.sort_order,
        }


def workflow_app(
    *,
    id: str,
    label: str,
    description: str,
    icon: str,
    nodes: tuple[WorkflowNodeDefinition, ...],
    sort_order: int = 1000,
) -> WorkflowAppDefinition:
    return WorkflowAppDefinition(
        id=id,
        label=label,
        description=description,
        icon=icon,
        nodes=nodes,
        sort_order=sort_order,
    )
