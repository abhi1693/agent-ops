from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from automation.catalog.connections import WorkflowRuntimeConnection, resolve_workflow_connection
from automation.catalog.services import get_catalog_node
from automation.nodes.apps.openai.client import resolve_openai_chat_model_config
from automation.nodes.base import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.nodes.core.agent.node import _execute_connected_agent
from automation.tools.base import (
    _http_json_request,
    _make_json_safe,
    _render_runtime_external_url,
    _render_runtime_json,
    _render_runtime_string,
    _tool_result,
)


def _resolve_connection_with_base_url(
    runtime: WorkflowNodeExecutionContext,
    *,
    connection_type: str,
) -> tuple[WorkflowRuntimeConnection, str]:
    resolved = resolve_workflow_connection(
        runtime,
        connection_id=runtime.config.get("connection_id"),
        expected_connection_type=connection_type,
    )
    raw_base_url = (
        resolved.connection.auth_config.get("base_url")
        or resolved.connection.metadata.get("base_url")
    )
    if raw_base_url in (None, ""):
        raise ValidationError(
            {"definition": f'Connection "{resolved.connection.name}" must define auth_config.base_url or metadata.base_url.'}
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


def _execute_manual_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
        },
    )


def _execute_schedule_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    cron = _render_runtime_string(runtime, "cron", required=True, default_mode="static")
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "payload": runtime.context["trigger"]["payload"],
            "trigger_type": runtime.context["trigger"]["type"],
            "trigger_meta": runtime.context["trigger"].get("meta", {}),
            "schedule": {
                "mode": "cron",
                "cron": cron,
            },
        },
    )


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


def _execute_if(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    left_value = runtime.get_path_value(runtime.context, runtime.config.get("path"))
    matched = runtime.evaluate_condition(
        runtime.config["operator"],
        left_value,
        runtime.config.get("right_value"),
    )
    selected_target = runtime.config["true_target"] if matched else runtime.config["false_target"]
    return WorkflowNodeExecutionResult(
        next_node_id=selected_target,
        output={
            "path": runtime.config.get("path"),
            "operator": runtime.config["operator"],
            "matched": matched,
            "next_node_id": selected_target,
        },
    )


def _execute_switch(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    left_value = runtime.get_path_value(runtime.context, runtime.config["path"])
    left_text = "" if left_value is None else str(left_value)

    matched_case = "fallback"
    next_node_id = runtime.config["fallback_target"]
    if left_text == str(runtime.config["case_1_value"]):
        matched_case = "case_1"
        next_node_id = runtime.config["case_1_target"]
    elif left_text == str(runtime.config["case_2_value"]):
        matched_case = "case_2"
        next_node_id = runtime.config["case_2_target"]

    return WorkflowNodeExecutionResult(
        next_node_id=next_node_id,
        output={
            "path": runtime.config["path"],
            "matched_case": matched_case,
            "next_node_id": next_node_id,
            "value": left_value,
        },
    )


def _execute_response(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    if "value_path" in runtime.config and runtime.config.get("value_path") not in (None, ""):
        payload = runtime.get_path_value(
            runtime.context,
            _render_runtime_string(runtime, "value_path", default_mode="static"),
        )
    else:
        payload = (
            _render_runtime_string(runtime, "template", default_mode="expression")
            or runtime.node.get("label")
            or runtime.node["id"]
        )
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


def _execute_stop_and_error(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    payload = {
        "message": _render_runtime_string(runtime, "message", default_mode="expression")
        or "An error occurred.",
    }
    return WorkflowNodeExecutionResult(
        next_node_id=None,
        output=payload,
        response=payload,
        run_status="failed",
        terminal=True,
    )


def _execute_agent(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return _execute_connected_agent(runtime)


def _execute_openai_chat_model(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    resolved_config = resolve_openai_chat_model_config(
        runtime,
        node=runtime.node,
        config=runtime.config,
    )
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "model": resolved_config.model,
            "base_url": resolved_config.base_url,
            "api_type": "openai_compatible",
            "connection_id": runtime.config.get("connection_id"),
        },
    )


def _execute_prometheus_query(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    instant = runtime.config.get("instant", True)
    if str(instant).lower() == "false":
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" only supports instant Prometheus queries right now.'}
        )

    output_key = _render_runtime_string(runtime, "output_key", default="prometheus.query", default_mode="static")
    resolved, base_url = _resolve_connection_with_base_url(runtime, connection_type="prometheus.api")
    query_text = _render_runtime_string(runtime, "query", required=True, default_mode="expression")
    query_time = _render_runtime_string(runtime, "time", default_mode="expression")

    headers = {"Accept": "application/json"}
    if resolved.secret_value:
        headers["Authorization"] = f"Bearer {resolved.secret_value}"

    query = {"query": query_text}
    if query_time:
        query["time"] = query_time

    response_data, _ = _http_json_request(
        method="GET",
        url=f"{base_url}/api/v1/query",
        headers=headers,
        query=query,
    )
    payload = _make_json_safe(response_data)
    if output_key:
        runtime.set_path_value(runtime.context, output_key, payload)

    result_count = 0
    if isinstance(response_data, dict):
        result_count = len(response_data.get("data", {}).get("result", []) or [])

    result = _tool_result(
        "prometheus_query",
        output_key=output_key,
        result_count=result_count,
        connection_id=runtime.config.get("connection_id"),
    )
    if resolved.secret_meta is not None:
        result["secret"] = resolved.secret_meta
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output=result,
    )


def _execute_elasticsearch_search(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    output_key = _render_runtime_string(runtime, "output_key", default="elasticsearch.search", default_mode="static")
    resolved, base_url = _resolve_connection_with_base_url(runtime, connection_type="elasticsearch.api")
    index_name = _render_runtime_string(runtime, "index", default_mode="expression")
    query_body = _render_runtime_json(runtime, "query_json", required=True, default_mode="expression")
    if not isinstance(query_body, dict):
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.query_json must render a JSON object.'}
        )

    size_value = runtime.config.get("size")
    if size_value not in (None, "") and "size" not in query_body:
        try:
            query_body["size"] = int(size_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"definition": f'Node "{runtime.node["id"]}" config.size must be an integer.'}
            ) from exc

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth_scheme = _render_runtime_string(runtime, "auth_scheme", default="ApiKey", default_mode="static") or "ApiKey"
    if auth_scheme not in {"ApiKey", "Bearer"}:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.auth_scheme must be one of: ApiKey, Bearer.'}
        )
    if resolved.secret_value:
        headers["Authorization"] = f"{auth_scheme} {resolved.secret_value}"

    search_path = "/_search"
    if index_name:
        search_path = f"/{index_name}/_search"

    response_data, _ = _http_json_request(
        method="POST",
        url=f"{base_url}{search_path}",
        headers=headers,
        json_body=query_body,
    )

    hits: list[Any] = []
    total_hits: Any = 0
    aggregations = None
    took = None
    if isinstance(response_data, dict):
        hits = response_data.get("hits", {}).get("hits", []) or []
        total_hits = response_data.get("hits", {}).get("total", 0)
        aggregations = response_data.get("aggregations")
        took = response_data.get("took")

    payload = {
        "hits": _make_json_safe(hits),
        "total": _make_json_safe(total_hits),
        "aggregations": _make_json_safe(aggregations),
        "took": took,
        "raw": _make_json_safe(response_data),
    }
    if output_key:
        runtime.set_path_value(runtime.context, output_key, payload)

    result = _tool_result(
        "elasticsearch_search",
        output_key=output_key,
        hit_count=len(hits),
        connection_id=runtime.config.get("connection_id"),
    )
    if resolved.secret_meta is not None:
        result["secret"] = resolved.secret_meta
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output=result,
    )


_EXECUTORS = {
    "core.manual_trigger": _execute_manual_trigger,
    "core.schedule_trigger": _execute_schedule_trigger,
    "github.trigger.webhook": _execute_manual_trigger,
    "core.set": _execute_set,
    "core.if": _execute_if,
    "core.switch": _execute_switch,
    "core.response": _execute_response,
    "core.stop_and_error": _execute_stop_and_error,
    "core.agent": _execute_agent,
    "openai.model.chat": _execute_openai_chat_model,
    "prometheus.action.query": _execute_prometheus_query,
    "elasticsearch.action.search": _execute_elasticsearch_search,
}


def get_catalog_runtime_node(node_type: Any):
    if not isinstance(node_type, str) or not node_type.strip():
        return None
    node_definition = get_catalog_node(node_type.strip())
    if node_definition is None:
        return None
    if node_definition.id not in _EXECUTORS:
        return None
    return node_definition


def execute_catalog_runtime_node(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult | None:
    node_definition = get_catalog_runtime_node(runtime.node.get("type"))
    if node_definition is None:
        return None
    executor = _EXECUTORS[node_definition.id]
    return executor(runtime)
