from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

from django.core.exceptions import ValidationError

from automation.nodes.apps.integrations.mcp_server.node import (
    build_mcp_server_tool_descriptor,
    call_mcp_server_tool,
)
from automation.nodes.apps.openai.client import (
    build_openai_chat_payload,
    execute_openai_chat_completion,
    extract_openai_first_message,
    extract_openai_tool_calls,
)
from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeDefinition,
    node_text_field,
    node_textarea_field,
    WorkflowNodeImplementation,
    raise_definition_error,
)
from automation.tools.base import (
    _make_json_safe,
    _render_runtime_string,
    _validate_optional_string,
)
from automation.workflow_agents import (
    AGENT_LANGUAGE_MODEL_INPUT_PORT,
    AGENT_TOOL_INPUT_PORT,
    build_workflow_agent_tool_config,
    normalize_workflow_agent_config,
)


_MAX_TOOL_CALL_ROUNDS = 8
_TOOL_NAME_SANITIZER = re.compile(r"[^a-zA-Z0-9_-]+")
_AGENT_TOOL_FIXED_FIELD_KEYS = frozenset(
    {
        "output_key",
        "base_url",
        "server_url",
        "binary_path",
        "protocol_version",
        "timeout_seconds",
        "auth_header_name",
        "auth_header_template",
        "headers_json",
        "auth_scheme",
        "secret_name",
        "secret_group_id",
    }
)
_AGENT_TOOL_FIXED_FIELD_SUFFIXES = (
    "_secret_name",
    "_secret_provider",
)
_AGENT_SECRET_TOOL_TYPE = "utilities.action.secret"
_AGENT_MCP_TOOL_TYPE = "mcp.action.tool"
_CONNECTED_AGENT_RESULT_API_TYPE = "openai_compatible"


def _build_runtime_view(runtime: WorkflowNodeExecutionContext, *, node: dict[str, Any], config: dict[str, Any]):
    return SimpleNamespace(
        workflow=runtime.workflow,
        node=node,
        config=config,
        context=runtime.context,
        secret_values=runtime.secret_values,
        render_template=runtime.render_template,
        resolve_scoped_secret=runtime.resolve_scoped_secret,
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


def _normalize_function_parameters(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

    normalized_schema = dict(schema)
    if normalized_schema.get("type") not in (None, "object"):
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
    normalized_schema.setdefault("type", "object")
    return _make_json_safe(normalized_schema)


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


def _get_tool_node_definition(node_type: Any):
    # Agent-attached tools still resolve through the internal Python-backed
    # node registry even though end-user workflow execution is catalog-native.
    from automation.nodes.registry import get_workflow_node_definition

    definition = get_workflow_node_definition(node_type)
    if definition is None or definition.kind != "tool":
        return None
    return definition


def _resolve_internal_tool_node_type(node_type: Any) -> Any:
    definition = _get_tool_node_definition(node_type)
    if definition is not None:
        return definition.type
    return node_type


def _build_agent_tool_base_config(tool_node: dict[str, Any]) -> dict[str, Any]:
    definition = _get_tool_node_definition(tool_node.get("type"))
    if definition is None:
        return dict(tool_node.get("config") or {})
    return {
        **(definition.config or {}),
        **(tool_node.get("config") or {}),
    }


def _is_agent_fixed_tool_field(*, tool_node: dict[str, Any], field_key: str) -> bool:
    canonical_tool_type = _resolve_internal_tool_node_type(tool_node.get("type"))
    if field_key in _AGENT_TOOL_FIXED_FIELD_KEYS:
        return True
    if any(field_key.endswith(suffix) for suffix in _AGENT_TOOL_FIXED_FIELD_SUFFIXES):
        return True
    if canonical_tool_type == _AGENT_SECRET_TOOL_TYPE and field_key in {"secret_name", "secret_group_id"}:
        return True
    return False


def _has_agent_visible_tool_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _build_agent_generic_tool_parameters(tool_node: dict[str, Any]) -> dict[str, Any]:
    definition = _get_tool_node_definition(tool_node.get("type"))
    if definition is None:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    base_config = _build_agent_tool_base_config(tool_node)
    properties: dict[str, Any] = {}
    for field in definition.fields:
        if _is_agent_fixed_tool_field(tool_node=tool_node, field_key=field.key):
            continue
        if _has_agent_visible_tool_value(base_config.get(field.key)):
            continue

        property_schema: dict[str, Any] = {"type": "string"}
        if field.type == "select" and field.options:
            property_schema["enum"] = [option.value for option in field.options]
        description_parts = [field.label]
        if field.help_text:
            description_parts.append(field.help_text)
        property_schema["description"] = " ".join(description_parts)
        properties[field.key] = property_schema

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

    if tool_node.get("type") == _AGENT_SECRET_TOOL_TYPE:
        redacted_output = {
            key: value
            for key, value in execution_output.items()
            if key != "output_key"
        }
        return {
            "tool": tool_identifier,
            "is_error": False,
            "structured_content": _make_json_safe(redacted_output),
        }

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


def _execute_generic_agent_tool(
    runtime: WorkflowNodeExecutionContext,
    *,
    tool_node: dict[str, Any],
    arguments: dict[str, Any],
    tool_name: str,
    tool_call_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from automation.nodes.registry import execute_workflow_node

    base_config = _build_agent_tool_base_config(tool_node)
    scratch_output_key = None
    definition = _get_tool_node_definition(tool_node.get("type"))
    if definition is not None and any(field.key == "output_key" for field in definition.fields):
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
    if definition is not None and definition.validator is not None:
        definition.validator(merged_config, tool_node["id"], [], {tool_node["id"]})

    execution = execute_workflow_node(
        workflow=runtime.workflow,
        node={
            **tool_node,
            "config": merged_config,
        },
        next_node_id=None,
        connected_nodes_by_port={},
        context=runtime.context,
        secret_paths=runtime.secret_paths,
        secret_values=runtime.secret_values,
        render_template=runtime.render_template,
        get_path_value=runtime.get_path_value,
        set_path_value=runtime.set_path_value,
        resolve_scoped_secret=runtime.resolve_scoped_secret,
        evaluate_condition=runtime.evaluate_condition,
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
        if _resolve_internal_tool_node_type(tool_node.get("type")) == _AGENT_MCP_TOOL_TYPE:
            descriptor = build_mcp_server_tool_descriptor(
                runtime,
                node=tool_node,
                config=tool_node.get("config") or {},
            )
            exposed_name = _sanitize_tool_name(
                str(descriptor.get("name") or tool_node.get("label") or tool_node["id"]),
                used_names=used_tool_names,
            )
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": exposed_name,
                        "description": descriptor.get("description") or tool_node.get("label") or tool_node["id"],
                        "parameters": _normalize_function_parameters(descriptor.get("input_schema")),
                    },
                }
            )
            tool_bindings[exposed_name] = {
                "kind": "mcp_server",
                "node": tool_node,
                "descriptor": descriptor,
            }
            continue

        definition = _get_tool_node_definition(tool_node.get("type"))
        if definition is None:
            continue

        exposed_name = _sanitize_tool_name(
            str(tool_node.get("label") or definition.display_name or tool_node["id"]),
            used_names=used_tool_names,
        )
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": exposed_name,
                    "description": definition.description or tool_node.get("label") or tool_node["id"],
                    "parameters": _build_agent_generic_tool_parameters(tool_node),
                },
            }
        )
        tool_bindings[exposed_name] = {
            "kind": "workflow_tool",
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

    if connected_model_node is not None:
        model_node = connected_model_node
        model_config = connected_model_node.get("config") or {}
    else:
        model_node = runtime.node
        model_config = normalized_agent_config

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    tool_runs: list[dict[str, Any]] = []
    final_payload: dict[str, Any] | None = None

    for _ in range(_MAX_TOOL_CALL_ROUNDS):
        response_data, request_config = execute_openai_chat_completion(
            runtime,
            node=model_node,
            config=model_config,
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
            if binding["kind"] == "mcp_server":
                tool_payload, tool_execution_output = call_mcp_server_tool(
                    runtime,
                    node=tool_node,
                    config=tool_node.get("config") or {},
                    arguments=tool_arguments,
                )
            else:
                tool_payload, tool_execution_output = _execute_generic_agent_tool(
                    runtime,
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
            "connected_model_node_id": connected_model_node["id"] if connected_model_node else None,
            "connected_tool_count": len(tool_bindings),
            "tool_run_count": len(tool_runs),
        },
    )


def _validate_agent(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    normalized_agent_config = normalize_workflow_agent_config(config)
    _validate_optional_string(normalized_agent_config, "template", node_id=node_id)
    _validate_optional_string(normalized_agent_config, "system_prompt", node_id=node_id)
    _validate_optional_string(normalized_agent_config, "output_key", node_id=node_id)
    if len(outgoing_targets) > 1:
        raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')


def _execute_agent(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return _execute_connected_agent(runtime)


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_agent,
    executor=_execute_agent,
)
NODE_DEFINITION = WorkflowNodeDefinition(
    type="core.agent",
    kind="agent",
    display_name="Agent",
    description="Coordinate a connected chat model and optional tools, then store the result in workflow context.",
    icon="mdi-robot-outline",
    app_description="Core workflow nodes and runtime primitives available in the designer.",
    app_icon="mdi-toy-brick-outline",
    catalog_section="flow",
    config={"output_key": "llm.response"},
    fields=(
        node_textarea_field(
            "template",
            "Template",
            rows=6,
            ui_group="input",
            binding="template",
            placeholder="Summarize incident {{ trigger.payload.incident_id }} and propose next steps.",
            help_text="Rendered as the user prompt sent to the model.",
        ),
        node_text_field(
            "output_key",
            "Save result as",
            ui_group="result",
            binding="path",
            placeholder="draft",
        ),
        node_textarea_field(
            "system_prompt",
            "System prompt",
            rows=4,
            ui_group="input",
            binding="template",
            placeholder="You are an incident response assistant.",
        ),
    ),
    validator=NODE_IMPLEMENTATION.validator,
    executor=NODE_IMPLEMENTATION.executor,
)
