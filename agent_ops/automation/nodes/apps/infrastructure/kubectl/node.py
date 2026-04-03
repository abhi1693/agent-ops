from __future__ import annotations

import json
import shlex
import shutil
import subprocess

from django.core.exceptions import ValidationError

from automation.nodes.adapters import tool_definition_as_node_implementation
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _coerce_positive_int,
    _make_json_safe,
    _render_runtime_string,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_string,
    _validate_required_string,
    tool_field_option,
    tool_select_field,
    tool_text_field,
    tool_textarea_field,
)


def _validate_kubectl_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)
    _validate_required_string(config, "command", node_id=node_id)
    _validate_optional_string(config, "binary_path", node_id=node_id)
    _validate_optional_string(config, "context_name", node_id=node_id)
    _validate_optional_string(config, "namespace", node_id=node_id)
    output_format = config.get("output_format", "text")
    if output_format not in {"text", "json"}:
        raise ValidationError(
            {"definition": f'Node "{node_id}" config.output_format must be one of: text, json.'}
        )
    _coerce_positive_int(
        config.get("timeout_seconds"),
        field_name="timeout_seconds",
        node_id=node_id,
        default=20,
        maximum=300,
    )


def _resolve_kubectl_binary(binary_path: str) -> str:
    if "/" in binary_path:
        return binary_path

    resolved_path = shutil.which(binary_path)
    if resolved_path:
        return resolved_path
    raise ValidationError({"definition": f'Local binary "{binary_path}" was not found on PATH.'})


def _parse_kubectl_command(command: str) -> list[str]:
    try:
        command_parts = shlex.split(command)
    except ValueError as exc:
        raise ValidationError({"definition": f"kubectl command could not be parsed: {exc}"}) from exc

    if command_parts and command_parts[0] == "kubectl":
        command_parts = command_parts[1:]

    if not command_parts:
        raise ValidationError({"definition": "kubectl command must include arguments after the binary name."})
    return command_parts


def _execute_kubectl_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    binary_path = _render_runtime_string(runtime, "binary_path", default_mode="static") or "kubectl"
    context_name = _render_runtime_string(runtime, "context_name", default_mode="static")
    namespace = _render_runtime_string(runtime, "namespace", default_mode="static")
    command = _render_runtime_string(runtime, "command", required=True, default_mode="expression")
    output_format = _render_runtime_string(runtime, "output_format", default_mode="static") or "text"
    timeout_seconds = _coerce_positive_int(
        runtime.config.get("timeout_seconds"),
        field_name="timeout_seconds",
        node_id=runtime.node["id"],
        default=20,
        maximum=300,
    )

    kubectl_binary = _resolve_kubectl_binary(binary_path)
    command_parts = _parse_kubectl_command(command)

    argv = [kubectl_binary]
    if context_name:
        argv.extend(["--context", context_name])
    if namespace:
        argv.extend(["--namespace", namespace])
    argv.extend(command_parts)

    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ValidationError({"definition": f'Local binary "{kubectl_binary}" is not executable or not accessible.'}) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValidationError(
            {"definition": f"kubectl command timed out after {timeout_seconds} seconds: {' '.join(argv)}"}
        ) from exc

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        stderr_snippet = stderr.strip()[:400]
        stdout_snippet = stdout.strip()[:400]
        detail = stderr_snippet or stdout_snippet or "kubectl command failed without output."
        raise ValidationError(
            {"definition": f"kubectl exited with code {completed.returncode}: {detail}"}
        )

    parsed_output = None
    if output_format == "json":
        try:
            parsed_output = _make_json_safe(json.loads(stdout))
        except ValueError as exc:
            raise ValidationError({"definition": "kubectl stdout was not valid JSON."}) from exc

    payload = {
        "command": argv,
        "stdout": stdout,
        "stderr": stderr,
        "output_format": output_format,
    }
    if parsed_output is not None:
        payload["data"] = parsed_output

    runtime.set_path_value(runtime.context, output_key, payload)
    result = {
        "output_key": output_key,
        "command": argv,
        "output_format": output_format,
    }
    if parsed_output is not None and isinstance(parsed_output, dict):
        items = parsed_output.get("items")
        if isinstance(items, list):
            result["item_count"] = len(items)
    return _tool_result("kubectl", **result)


TOOL_DEFINITION = WorkflowToolDefinition(
    name="kubectl",
    label="kubectl",
    description="Run the locally installed kubectl binary on the app host using its configured cluster access.",
    icon="mdi-kubernetes",
    category="Infrastructure",
    config={"output_key": "kubectl.result", "output_format": "text", "timeout_seconds": 20},
    fields=(
        tool_text_field(
            "output_key",
            "Save result as",
            ui_group="result",
            binding="path",
            placeholder="kubectl.result",
        ),
        tool_textarea_field(
            "command",
            "kubectl command",
            rows=4,
            ui_group="input",
            binding="template",
            placeholder="get pods -A -o json",
            help_text="Arguments passed after the kubectl binary. A leading `kubectl` is ignored if you include it.",
        ),
        tool_select_field(
            "output_format",
            "Output format",
            ui_group="advanced",
            options=(
                tool_field_option("text"),
                tool_field_option("json"),
            ),
            help_text="Choose `json` when the command prints JSON, for example with `-o json`.",
        ),
        tool_text_field(
            "context_name",
            "Kube context",
            ui_group="advanced",
            placeholder="prod-cluster",
            help_text="Optional. Adds `--context` before the command.",
        ),
        tool_text_field(
            "namespace",
            "Namespace",
            ui_group="advanced",
            placeholder="payments",
            help_text="Optional. Adds `--namespace` before the command.",
        ),
        tool_text_field(
            "binary_path",
            "kubectl binary",
            ui_group="advanced",
            placeholder="kubectl",
            help_text="Optional. Defaults to `kubectl` from PATH on the app host.",
        ),
        tool_text_field(
            "timeout_seconds",
            "Timeout seconds",
            ui_group="advanced",
            placeholder="20",
        ),
    ),
    validator=_validate_kubectl_tool,
    executor=_execute_kubectl_tool,
)

NODE_IMPLEMENTATION = tool_definition_as_node_implementation(TOOL_DEFINITION)
