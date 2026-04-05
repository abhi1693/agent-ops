from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ValidationError

from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition, ParameterOptionDefinition
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import (
    _build_runtime_binding_context,
    _render_runtime_json,
    _render_runtime_string,
    _validate_optional_string,
    _validate_required_json_template,
    _validate_required_string,
)


def _validate_core_set_config(*, config, node_id, **_) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    mode = str(config.get("mode") or "manual").strip().lower()
    if mode == "raw":
        _validate_required_json_template(config, "json_output", node_id=node_id)
    elif _extract_manual_mapping_entries(config):
        return
    elif "value" in config:
        _validate_optional_string(config, "value", node_id=node_id)
    else:
        raise ValidationError({"definition": f'Node "{node_id}" must define a value, json output, or manual mapping.'})


def _render_mapping_value(runtime: WorkflowNodeExecutionContext, value: Any) -> Any:
    if isinstance(value, (dict, list)):
        rendered = runtime.render_template(
            json.dumps(value),
            _build_runtime_binding_context(runtime),
        ).strip()
        return json.loads(rendered)
    if isinstance(value, str) and ("{{" in value or "{%" in value):
        return runtime.render_template(value, _build_runtime_binding_context(runtime)).strip()
    return value


def _extract_manual_mapping_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    fields_payload = config.get("fields")
    if isinstance(fields_payload, dict):
        raw_values = fields_payload.get("values")
        if isinstance(raw_values, list):
            return [item for item in raw_values if isinstance(item, dict)]
    return []


def _build_manual_mapping_output(runtime: WorkflowNodeExecutionContext) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for entry in _extract_manual_mapping_entries(runtime.config):
        name = str(entry.get("name") or entry.get("key") or "").strip()
        if not name:
            continue
        if "jsonValue" in entry:
            payload[name] = _render_mapping_value(runtime, entry.get("jsonValue"))
            continue
        if "value" in entry:
            payload[name] = _render_mapping_value(runtime, entry.get("value"))
            continue
        payload[name] = None
    return payload


def _execute_set(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    mode = str(runtime.config.get("mode") or "manual").strip().lower()
    manual_mapping_output = _build_manual_mapping_output(runtime)
    value = runtime.config.get("value")
    if mode == "raw":
        value = _render_runtime_json(runtime, "json_output", default_mode="expression")
    elif manual_mapping_output:
        value = manual_mapping_output
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
    default_name="Edit Fields",
    default_color="#3b82f6",
    subtitle='={{config.output_key}}',
    node_group=("input",),
    runtime_validator=_validate_core_set_config,
    runtime_executor=_execute_set,
    parameter_schema=(
        ParameterDefinition(
            key="mode",
            label="Mode",
            value_type="string",
            required=False,
            description="How this node should build the output value.",
            default="manual",
            no_data_expression=True,
            ui_group="input",
            options=(
                ParameterOptionDefinition(value="manual", label="Manual Mapping"),
                ParameterOptionDefinition(value="raw", label="JSON"),
            ),
        ),
        ParameterDefinition(
            key="output_key",
            label="Save Result As",
            value_type="string",
            required=True,
            description="Context path to write.",
            placeholder="context.value",
            no_data_expression=True,
            ui_group="result",
        ),
        ParameterDefinition(
            key="value",
            label="Value",
            value_type="string",
            required=False,
            description="Literal or templated value to store.",
            placeholder="{{ trigger.payload.message }}",
            ui_group="input",
            display_options={
                "show": {
                    "mode": ("manual",),
                },
            },
        ),
        ParameterDefinition(
            key="json_output",
            label="JSON Output",
            value_type="json",
            required=False,
            description="Structured JSON output.",
            placeholder='{"ticketId":"{{ trigger.payload.ticket_id }}"}',
            rows=5,
            ui_group="input",
            display_options={
                "show": {
                    "mode": ("raw",),
                },
            },
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
