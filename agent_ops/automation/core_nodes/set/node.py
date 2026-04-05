from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ValidationError

from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ParameterCollectionOptionDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import (
    _build_runtime_binding_context,
    _render_runtime_json,
    _render_runtime_string,
    _validate_required_json_template,
    _validate_required_string,
)


def _validate_core_set_config(*, config, node_id, **_) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)
    mode = str(config.get("mode") or "manual").strip().lower()
    if mode == "raw":
        _validate_required_json_template(config, "json_output", node_id=node_id)
        return
    if _extract_manual_mapping_entries(config):
        return
    raise ValidationError({"definition": f'Node "{node_id}" must define json output or manual mapping.'})


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


def _resolve_mapping_entry_value(entry: dict[str, Any]) -> Any:
    entry_type = str(entry.get("type") or "").strip()
    if entry_type == "numberValue" and "numberValue" in entry:
        return entry.get("numberValue")
    if entry_type == "booleanValue" and "booleanValue" in entry:
        return entry.get("booleanValue")
    if entry_type == "arrayValue" and "arrayValue" in entry:
        return entry.get("arrayValue")
    if entry_type == "objectValue" and "objectValue" in entry:
        return entry.get("objectValue")
    if entry_type == "stringValue" and "stringValue" in entry:
        return entry.get("stringValue")
    return None


def _build_manual_mapping_output(runtime: WorkflowNodeExecutionContext) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for entry in _extract_manual_mapping_entries(runtime.config):
        name = str(entry.get("name") or entry.get("key") or "").strip()
        if not name:
            continue
        payload[name] = _render_mapping_value(runtime, _resolve_mapping_entry_value(entry))
    return payload


def _execute_set(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    mode = str(runtime.config.get("mode") or "manual").strip().lower()
    if mode == "raw":
        value = _render_runtime_json(runtime, "json_output", default_mode="expression")
    else:
        value = _build_manual_mapping_output(runtime)
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
        ParameterDefinition(
            key="fields",
            label="Fields to Set",
            value_type="object",
            field_type="fixed_collection",
            required=False,
            description="Add one or more fields to write into workflow context.",
            ui_group="input",
            display_options={
                "show": {
                    "mode": ("manual",),
                },
            },
            collection_options=(
                ParameterCollectionOptionDefinition(
                    key="values",
                    label="Field",
                    multiple=True,
                    fields=(
                        ParameterDefinition(
                            key="name",
                            label="Name",
                            value_type="string",
                            required=True,
                            description="Field name to write. Supports dot notation.",
                            placeholder="ticket.id",
                        ),
                        ParameterDefinition(
                            key="type",
                            label="Type",
                            value_type="string",
                            required=False,
                            default="stringValue",
                            no_data_expression=True,
                            options=(
                                ParameterOptionDefinition(value="stringValue", label="String"),
                                ParameterOptionDefinition(value="numberValue", label="Number"),
                                ParameterOptionDefinition(value="booleanValue", label="Boolean"),
                                ParameterOptionDefinition(value="arrayValue", label="Array"),
                                ParameterOptionDefinition(value="objectValue", label="Object"),
                            ),
                        ),
                        ParameterDefinition(
                            key="stringValue",
                            label="Value",
                            value_type="string",
                            required=False,
                            placeholder="{{ trigger.payload.message }}",
                            display_options={
                                "show": {
                                    "type": ("stringValue",),
                                },
                            },
                        ),
                        ParameterDefinition(
                            key="numberValue",
                            label="Value",
                            value_type="number",
                            required=False,
                            placeholder="42",
                            display_options={
                                "show": {
                                    "type": ("numberValue",),
                                },
                            },
                        ),
                        ParameterDefinition(
                            key="booleanValue",
                            label="Value",
                            value_type="boolean",
                            required=False,
                            default=True,
                            options=(
                                ParameterOptionDefinition(value="true", label="True"),
                                ParameterOptionDefinition(value="false", label="False"),
                            ),
                            display_options={
                                "show": {
                                    "type": ("booleanValue",),
                                },
                            },
                        ),
                        ParameterDefinition(
                            key="arrayValue",
                            label="Value",
                            value_type="json",
                            required=False,
                            rows=4,
                            placeholder='["item-one", "item-two"]',
                            display_options={
                                "show": {
                                    "type": ("arrayValue",),
                                },
                            },
                        ),
                        ParameterDefinition(
                            key="objectValue",
                            label="Value",
                            value_type="json",
                            required=False,
                            rows=4,
                            placeholder='{"ticketId":"{{ trigger.payload.ticket_id }}"}',
                            display_options={
                                "show": {
                                    "type": ("objectValue",),
                                },
                            },
                        ),
                    ),
                ),
            ),
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
