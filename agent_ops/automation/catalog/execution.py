from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.catalog.connections import (
    WorkflowResolvedConnection,
    build_resolved_connection_request_auth,
    get_connection_slot_value,
    resolve_connection_request_auth,
    resolve_workflow_connection_fields,
)
from automation.runtime_types import WorkflowNodeExecutionContext
from automation.tools.base import _render_runtime_external_url


def resolve_connection_with_base_url(
    runtime: WorkflowNodeExecutionContext,
    *,
    connection_type: str,
    base_url_field: str = "base_url",
    connection_slot_key: str = "connection_id",
) -> tuple[WorkflowResolvedConnection, str]:
    resolved = resolve_workflow_connection_fields(
        runtime,
        connection_id=get_connection_slot_value(runtime.config, slot_key=connection_slot_key),
        expected_connection_type=connection_type,
    )
    raw_base_url = resolved.values.get(base_url_field)
    if raw_base_url in (None, ""):
        raise ValidationError(
            {"definition": f'Connection "{resolved.connection.name}" must define field "{base_url_field}".'}
        )

    runtime_config = dict(runtime.config)
    runtime_config["base_url"] = raw_base_url
    validated_runtime = WorkflowNodeExecutionContext(
        workflow=runtime.workflow,
        node=runtime.node,
        config=runtime_config,
        next_node_id=runtime.next_node_id,
        connected_nodes_by_port=runtime.connected_nodes_by_port,
        context=runtime.context,
        secret_paths=runtime.secret_paths,
        secret_values=runtime.secret_values,
        render_template=runtime.render_template,
        get_path_value=runtime.get_path_value,
        set_path_value=runtime.set_path_value,
        resolve_scoped_secret=runtime.resolve_scoped_secret,
        evaluate_condition=runtime.evaluate_condition,
    )
    base_url = _render_runtime_external_url(
        validated_runtime,
        "base_url",
        required=True,
        default_mode="static",
    )
    return resolved, (base_url or "").rstrip("/")


__all__ = (
    "build_resolved_connection_request_auth",
    "get_connection_slot_value",
    "resolve_connection_request_auth",
    "resolve_connection_with_base_url",
)
