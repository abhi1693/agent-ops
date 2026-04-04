from __future__ import annotations

from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import (
    _render_runtime_json,
    _render_runtime_string,
    _validate_optional_string,
    _validate_required_json_template,
    _validate_required_string,
)


def _validate_core_set_config(*, config, node_id, **_) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    if "value_json" in config:
        _validate_required_json_template(config, "value_json", node_id=node_id)
    elif "value" in config:
        _validate_optional_string(config, "value", node_id=node_id)


def _execute_set(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    value = runtime.config.get("value")
    if "value_json" in runtime.config:
        value = _render_runtime_json(runtime, "value_json", default_mode="expression")
    elif isinstance(value, str):
        value = _render_runtime_string(runtime, "value", default_mode="expression")
    runtime.set_path_value(runtime.context, output_key, value)
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "tool_name": "set",
            "operation": "set",
            "output_key": output_key,
            "value": value,
        },
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.set",
    integration_id="core",
    mode="core",
    kind="data",
    label="Set",
    description="Creates or updates workflow variables and structured values.",
    icon="mdi-form-textbox",
    runtime_validator=_validate_core_set_config,
    runtime_executor=_execute_set,
    parameter_schema=(
        ParameterDefinition(
            key="output_key",
            label="Save Result As",
            value_type="string",
            required=True,
            description="Context path to write.",
            placeholder="context.value",
        ),
        ParameterDefinition(
            key="value",
            label="Value",
            value_type="string",
            required=False,
            description="Literal or templated value to store.",
            placeholder="{{ trigger.payload.message }}",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
