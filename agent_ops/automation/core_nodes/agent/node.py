from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

from django.core.exceptions import ValidationError

from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition
from automation.catalog.services import get_catalog_node
from automation.integrations.openai.client import (
    build_openai_chat_payload,
    execute_openai_chat_completion,
    extract_openai_first_message,
    extract_openai_tool_calls,
)
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import (
    _make_json_safe,
    _render_runtime_string,
    _validate_optional_string,
    _validate_required_string,
)
from automation.workflow_agents import (
    AGENT_LANGUAGE_MODEL_INPUT_PORT,
    AGENT_TOOL_INPUT_PORT,
    build_workflow_agent_tool_config,
    normalize_workflow_agent_config,
)


_MAX_TOOL_CALL_ROUNDS = 8
_TOOL_NAME_SANITIZER = re.compile(r"[^a-zA-Z0-9_-]+")
_AGENT_TOOL_FIXED_FIELD_KEYS = frozenset({"output_key"})
_CONNECTED_AGENT_RESULT_API_TYPE = "openai_compatible"
_CATALOG_AGENT_TOOL_KINDS = frozenset({"action", "data"})


def _build_runtime_view(runtime: WorkflowNodeExecutionContext, *, node: dict[str, Any], config: dict[str, Any]):
    return SimpleNamespace(
        workflow=runtime.workflow,
        node=node,
        config=config,
        context=runtime.context,
        secret_values=runtime.secret_values,
        render_template=runtime.render_template,
    )


def _sanitize_tool_name(raw_name: str, used_names: set[str]) -> str:
    normalized_name = _TOOL_NAME_SANITIZER.sub("_", raw_name).strip("_-") or "tool"
    normalized_name = normalized_name[:48]
    candidate = normalized_name
    suffix = 2
    while candidate in used_names:
        candidate = f"{normalized_name[:40]}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _parse_tool_call_arguments(tool_call: dict[str, Any], *, node_id: str) -> dict[str, Any]:
    function_payload = tool_call.get("function")
    if not isinstance(function_payload, dict):
        raise ValidationError(
            {"definition": f'Node "{node_id}" received an invalid tool call payload from the model.'}
        )

    raw_arguments = function_payload.get("arguments")
    if raw_arguments in (None, ""):
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        raise ValidationError(
            {"definition": f'Node "{node_id}" received non-string tool call arguments from the model.'}
        )

    try:
        parsed_arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            {"definition": f'Node "{node_id}" received invalid JSON tool call arguments from the model.'}
        ) from exc

    if not isinstance(parsed_arguments, dict):
        raise ValidationError(
            {"definition": f'Node "{node_id}" tool call arguments must decode to a JSON object.'}
        )
    return parsed_arguments


def _serialize_tool_response_content(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("text"), str) and payload["text"].strip():
        return payload["text"].strip()
    if payload.get("structured_content") is not None:
        return json.dumps(payload["structured_content"], sort_keys=True)
    if payload.get("content") is not None:
        return json.dumps(payload["content"], sort_keys=True)
    return "{}"


def _get_catalog_tool_node_definition(node_type: Any) -> CatalogNodeDefinition | None:
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    definition = get_catalog_node(node_type.strip())
    if definition is None or definition.runtime_executor is None:
        return None
    if definition.kind not in _CATALOG_AGENT_TOOL_KINDS:
        return None
    return definition


def _build_catalog_tool_base_config(tool_node: dict[str, Any], definition: CatalogNodeDefinition) -> dict[str, Any]:
    base_config = dict(definition.config_defaults)
    for parameter in definition.parameter_schema:
        if parameter.default is not None:
            base_config.setdefault(parameter.key, parameter.default)
    return {
        **base_config,
        **(tool_node.get("config") or {}),
    }


def _is_agent_fixed_tool_field(*, field_key: str) -> bool:
    return field_key in _AGENT_TOOL_FIXED_FIELD_KEYS


def _has_agent_visible_tool_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _parameter_json_schema(parameter: ParameterDefinition) -> dict[str, Any]:
    schema_type = "string"
    if parameter.value_type == "boolean":
        schema_type = "boolean"
    elif parameter.value_type == "integer":
        schema_type = "integer"
    elif parameter.value_type == "number":
        schema_type = "number"
    elif parameter.value_type in {"json", "object"}:
        schema_type = "object"

    schema: dict[str, Any] = {"type": schema_type}
    if parameter.options:
        schema["enum"] = [option.value for option in parameter.options]
    description_parts = [parameter.label]
    if parameter.description:
        description_parts.append(parameter.description)
    if parameter.help_text:
        description_parts.append(parameter.help_text)
    schema["description"] = " ".join(description_parts)
    return schema


def _build_agent_catalog_tool_parameters(tool_node: dict[str, Any], definition: CatalogNodeDefinition) -> dict[str, Any]:
    base_config = _build_catalog_tool_base_config(tool_node, definition)
    properties: dict[str, Any] = {}
    for parameter in definition.parameter_schema:
        if _is_agent_fixed_tool_field(field_key=parameter.key):
            continue
        if _has_agent_visible_tool_value(base_config.get(parameter.key)):
            continue
        properties[parameter.key] = _parameter_json_schema(parameter)

    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }


def _build_agent_tool_output_key(*, agent_node_id: str, tool_name: str, tool_call_id: str | None) -> str:
    call_fragment = _TOOL_NAME_SANITIZER.sub("_", tool_call_id or "call").strip("_-") or "call"
    return f"agent_tools.{agent_node_id}.{tool_name}.{call_fragment}"


def _build_generic_agent_tool_payload(
    *,
    tool_node: dict[str, Any],
    execution_output: dict[str, Any],
    scratch_value: Any,
) -> dict[str, Any]:
    tool_identifier = str(execution_output.get("tool_name") or tool_node.get("label") or tool_node["id"])

    if isinstance(scratch_value, str) and scratch_value.strip():
        return {
            "tool": tool_identifier,
            "is_error": False,
            "text": scratch_value,
        }

    if scratch_value is not None:
        return {
            "tool": tool_identifier,
            "is_error": False,
            "structured_content": _make_json_safe(scratch_value),
        }

    return {
        "tool": tool_identifier,
        "is_error": False,
        "structured_content": _make_json_safe(execution_output),
    }


def _execute_catalog_agent_tool(
    runtime: WorkflowNodeExecutionContext,
    *,
    definition: CatalogNodeDefinition,
    tool_node: dict[str, Any],
    arguments: dict[str, Any],
    tool_name: str,
    tool_call_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_config = _build_catalog_tool_base_config(tool_node, definition)
    scratch_output_key = None
    if any(parameter.key == "output_key" for parameter in definition.parameter_schema):
        scratch_output_key = _build_agent_tool_output_key(
            agent_node_id=runtime.node["id"],
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        base_config["output_key"] = scratch_output_key

    merged_config = {
        **base_config,
        **arguments,
    }
    if definition.runtime_validator is not None:
        definition.runtime_validator(
            config=merged_config,
            node_id=tool_node["id"],
            node_ids={tool_node["id"]},
            outgoing_targets=[],
            outgoing_targets_by_source_port={},
            untyped_outgoing_targets=[],
        )

    execution = definition.runtime_executor(
        WorkflowNodeExecutionContext(
            workflow=runtime.workflow,
            node={
                **tool_node,
                "config": merged_config,
            },
            config=merged_config,
            next_node_id=None,
            connected_nodes_by_port={},
            context=runtime.context,
            secret_paths=runtime.secret_paths,
            secret_values=runtime.secret_values,
            render_template=runtime.render_template,
            get_path_value=runtime.get_path_value,
            set_path_value=runtime.set_path_value,
            evaluate_condition=runtime.evaluate_condition,
        )
    )
    execution_output = execution.output or {}
    scratch_value = (
        runtime.get_path_value(runtime.context, scratch_output_key)
        if scratch_output_key is not None
        else None
    )
    return (
        _build_generic_agent_tool_payload(
            tool_node=tool_node,
            execution_output=execution_output,
            scratch_value=scratch_value,
        ),
        execution_output,
    )


def _build_agent_tool_bindings(
    runtime: WorkflowNodeExecutionContext,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    connected_tool_nodes = runtime.connected_nodes_by_port.get(AGENT_TOOL_INPUT_PORT, [])
    openai_tools: list[dict[str, Any]] = []
    tool_bindings: dict[str, dict[str, Any]] = {}
    used_tool_names: set[str] = set()

    for tool_node in connected_tool_nodes:
        definition = _get_catalog_tool_node_definition(tool_node.get("type"))
        if definition is None:
            continue

        exposed_name = _sanitize_tool_name(
            str(tool_node.get("label") or definition.label or tool_node["id"]),
            used_names=used_tool_names,
        )
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": exposed_name,
                    "description": definition.description or tool_node.get("label") or tool_node["id"],
                    "parameters": _build_agent_catalog_tool_parameters(tool_node, definition),
                },
            }
        )
        tool_bindings[exposed_name] = {
            "definition": definition,
            "node": tool_node,
        }

    return openai_tools, tool_bindings


def _execute_connected_agent(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    normalized_agent_config = normalize_workflow_agent_config(runtime.config)
    connected_model_nodes = runtime.connected_nodes_by_port.get(AGENT_LANGUAGE_MODEL_INPUT_PORT, [])
    connected_model_node = connected_model_nodes[0] if connected_model_nodes else None
    if connected_model_node is None:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{runtime.node["id"]}" must connect a chat model to the ai_languageModel port.'
                )
            }
        )
    openai_tools, tool_bindings = _build_agent_tool_bindings(runtime)

    agent_runtime_view = _build_runtime_view(
        runtime,
        node=runtime.node,
        config=build_workflow_agent_tool_config(
            node=runtime.node,
            config=normalized_agent_config,
        ),
    )
    output_key = _render_runtime_string(
        agent_runtime_view,
        "output_key",
        required=True,
        default_mode="static",
    )
    system_prompt = _render_runtime_string(
        agent_runtime_view,
        "system_prompt",
        default_mode="expression",
    )
    user_prompt = _render_runtime_string(
        agent_runtime_view,
        "user_prompt",
        required=True,
        default_mode="expression",
    )

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    tool_runs: list[dict[str, Any]] = []
    final_payload: dict[str, Any] | None = None

    for _ in range(_MAX_TOOL_CALL_ROUNDS):
        response_data, request_config = execute_openai_chat_completion(
            runtime,
            node=connected_model_node,
            config=connected_model_node.get("config") or {},
            messages=messages,
            tools=openai_tools or None,
        )

        assistant_message = extract_openai_first_message(response_data)
        tool_calls = extract_openai_tool_calls(response_data)
        assistant_entry: dict[str, Any] = {"role": "assistant"}
        if assistant_message.get("content") not in (None, ""):
            assistant_entry["content"] = assistant_message.get("content")
        if tool_calls:
            assistant_entry["tool_calls"] = tool_calls
        messages.append(assistant_entry)

        if not tool_calls:
            final_payload = build_openai_chat_payload(
                response_data,
                fallback_model=request_config.model,
            )
            break

        for tool_call in tool_calls:
            function_payload = tool_call.get("function")
            if not isinstance(function_payload, dict):
                raise ValidationError(
                    {"definition": f'Node "{runtime.node["id"]}" received a malformed tool call from the model.'}
                )

            tool_name = function_payload.get("name")
            if not isinstance(tool_name, str) or tool_name not in tool_bindings:
                raise ValidationError(
                    {
                        "definition": (
                            f'Node "{runtime.node["id"]}" received a tool call for unsupported tool "{tool_name}".'
                        )
                    }
                )

            binding = tool_bindings[tool_name]
            tool_node = binding["node"]
            tool_arguments = _parse_tool_call_arguments(tool_call, node_id=runtime.node["id"])
            tool_payload, tool_execution_output = _execute_catalog_agent_tool(
                runtime,
                definition=binding["definition"],
                tool_node=tool_node,
                arguments=tool_arguments,
                tool_name=tool_name,
                tool_call_id=tool_call.get("id"),
            )
            tool_runs.append(
                {
                    "tool_name": tool_name,
                    "node_id": tool_node["id"],
                    "remote_tool_name": tool_payload["tool"],
                    "arguments": _make_json_safe(tool_arguments),
                    "is_error": tool_payload["is_error"],
                    "text": tool_payload.get("text"),
                    "result": _make_json_safe(tool_execution_output),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id") or tool_name,
                    "content": _serialize_tool_response_content(tool_payload),
                }
            )
    else:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{runtime.node["id"]}" exceeded the supported agent tool-call round limit.'
                )
            }
        )

    if final_payload is None:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" did not receive a final assistant response.'}
        )

    final_payload["tool_runs"] = _make_json_safe(tool_runs)
    runtime.set_path_value(runtime.context, output_key, final_payload)
    runtime.context.setdefault("messages", []).append(
        {
            "node_id": runtime.node["id"],
            "model": final_payload["model"],
            "text": final_payload.get("text"),
            "tool_runs": _make_json_safe(tool_runs),
        }
    )

    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "api_type": _CONNECTED_AGENT_RESULT_API_TYPE,
            "model": final_payload["model"],
            "connected_model_node_id": connected_model_node["id"],
            "connected_tool_count": len(tool_bindings),
            "tool_run_count": len(tool_runs),
        },
    )


def _validate_core_agent_config(*, config, node_id, **_) -> None:
    if config.get("instructions") not in (None, ""):
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" no longer supports config.instructions. Use config.template.'
                )
            }
        )
    _validate_required_string(config, "template", node_id=node_id)
    _validate_optional_string(config, "system_prompt", node_id=node_id)
    _validate_optional_string(config, "output_key", node_id=node_id)


def _execute_agent(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return _execute_connected_agent(runtime)


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.agent",
    integration_id="core",
    mode="core",
    kind="agent",
    label="Agent",
    description="Runs an agent with model, tools, and prompt instructions.",
    icon="mdi-robot-outline",
    runtime_validator=_validate_core_agent_config,
    runtime_executor=_execute_agent,
    parameter_schema=(
        ParameterDefinition(
            key="template",
            label="Template",
            value_type="text",
            required=True,
            description="Rendered as the user prompt passed to the connected model.",
            placeholder="Summarize the latest incidents and propose next actions.",
        ),
        ParameterDefinition(
            key="system_prompt",
            label="System Prompt",
            value_type="text",
            required=False,
            description="Optional system instructions for the connected model.",
            placeholder="You are an incident response assistant.",
        ),
        ParameterDefinition(
            key="output_key",
            label="Save Result As",
            value_type="string",
            required=False,
            description="Context path where the final model response is stored.",
            placeholder="llm.response",
            default="llm.response",
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
