from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class WorkflowNodeExecutionResult:
    next_node_id: str | None
    next_port: str | None = None
    output: dict[str, Any] | None = None
    response: Any = None
    run_status: str | None = None
    terminal: bool = False


@dataclass
class WorkflowNodeExecutionContext:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    next_node_id: str | None
    connected_nodes_by_port: dict[str, list[dict[str, Any]]]
    context: dict[str, Any]
    secret_paths: set[str]
    secret_values: list[str]
    render_template: Callable[[str, dict[str, Any]], str]
    get_path_value: Callable[[Any, str | None], Any]
    set_path_value: Callable[[dict[str, Any], str, Any], None]
    resolve_scoped_secret: Callable[..., Any]
    evaluate_condition: Callable[[str, Any, Any], bool]


__all__ = ("WorkflowNodeExecutionContext", "WorkflowNodeExecutionResult")
