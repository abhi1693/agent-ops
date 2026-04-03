from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeDefinition,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    node_field_option,
    node_select_field,
    node_text_field,
    node_textarea_field,
    raise_definition_error,
    validate_optional_string,
)
from automation.tools.base import _render_runtime_string


SUPPORTED_RESPONSE_STATUSES = frozenset({"succeeded", "failed"})


def _validate_response(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    validate_optional_string(config, "template", node_id=node_id)
    validate_optional_string(config, "value_path", node_id=node_id)
    status = config.get("status", "succeeded")
    if status not in SUPPORTED_RESPONSE_STATUSES:
        raise_definition_error(
            f'Node "{node_id}" config.status must be one of: {", ".join(sorted(SUPPORTED_RESPONSE_STATUSES))}.'
        )
    if outgoing_targets:
        raise_definition_error(f'Node "{node_id}" is terminal and cannot have outgoing edges.')


def _execute_response(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    if "value_path" in runtime.config:
        payload = runtime.get_path_value(
            runtime.context,
            _render_runtime_string(runtime, "value_path", default_mode="static"),
        )
    else:
        template = (
            _render_runtime_string(runtime, "template", default_mode="expression")
            or runtime.node.get("label")
            or runtime.node["id"]
        )
        payload = template

    output = {
        "node_id": runtime.node["id"],
        "response": payload,
    }
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        output=output,
        response=output,
        run_status=runtime.config.get("status", "succeeded"),
        terminal=True,
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_response,
    executor=_execute_response,
)
NODE_DEFINITION = WorkflowNodeDefinition(
    type="response",
    kind="response",
    display_name="Response",
    description="Finish the workflow and persist a terminal response payload.",
    icon="mdi-flag-checkered",
    app_description="Core workflow nodes, runtime primitives, and n8n-style built-in blocks available in the designer.",
    app_icon="mdi-toy-brick-outline",
    config={"status": "succeeded"},
    fields=(
        node_textarea_field(
            "template",
            "Template",
            rows=4,
            ui_group="input",
            binding="template",
            placeholder="Completed {{ draft }}",
        ),
        node_text_field(
            "value_path",
            "Value path",
            ui_group="input",
            binding="path",
            placeholder="draft",
            help_text=(
                "Optional. When set, the response is read directly from context "
                "instead of rendering the template."
            ),
        ),
        node_select_field(
            "status",
            "Status",
            ui_group="result",
            options=(
                node_field_option("succeeded", "Succeeded"),
                node_field_option("failed", "Failed"),
            ),
        ),
    ),
    validator=NODE_IMPLEMENTATION.validator,
    executor=NODE_IMPLEMENTATION.executor,
)
