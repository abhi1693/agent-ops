from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterable

from django.core.exceptions import ValidationError

from automation.nodes.adapters import (
    tool_definition_as_node_definition,
    tool_definition_as_node_implementation,
)
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
    _coerce_positive_int,
    _make_json_safe,
    _render_runtime_string,
    _resolve_runtime_secret,
    _tool_result,
    _validate_external_output_key,
    _validate_optional_secret_group_id,
    _validate_optional_string,
    _validate_required_string,
    tool_field_option,
    tool_select_field,
    tool_text_field,
    tool_textarea_field,
)


_READ_ONLY_POLICY = "read_only"
_ALLOW_MUTATING_POLICY = "allow_mutating"
_SUPPORTED_COMMAND_POLICIES = {_READ_ONLY_POLICY, _ALLOW_MUTATING_POLICY}

_ACTION_GET = "get"
_ACTION_DESCRIBE = "describe"
_ACTION_LOGS = "logs"
_ACTION_TOP = "top"
_ACTION_ROLLOUT_STATUS = "rollout_status"
_ACTION_CUSTOM = "custom"
_SUPPORTED_ACTIONS = {
    _ACTION_GET,
    _ACTION_DESCRIBE,
    _ACTION_LOGS,
    _ACTION_TOP,
    _ACTION_ROLLOUT_STATUS,
    _ACTION_CUSTOM,
}
_SUPPORTED_TOP_TARGETS = {"pod", "node"}
_SUPPORTED_ROLLOUT_KINDS = {"deployment", "daemonset", "statefulset"}

_READ_ONLY_TOP_LEVEL_COMMANDS = {
    "api-resources",
    "api-versions",
    "auth",
    "cluster-info",
    "describe",
    "diff",
    "events",
    "explain",
    "get",
    "logs",
    "top",
    "version",
    "wait",
}
_ROLLOUT_READ_ONLY_SUBCOMMANDS = {"history", "status"}
_CONFIG_READ_ONLY_SUBCOMMANDS = {"current-context", "get-contexts", "view"}
_LEADING_FLAGS_WITH_VALUES = {
    "-n",
    "--namespace",
    "--context",
    "--cluster",
    "--user",
    "--server",
    "--request-timeout",
    "--as",
    "--as-group",
    "--kubeconfig",
    "--token",
    "--selector",
    "--field-selector",
    "--output",
    "-o",
    "-c",
    "--container",
    "--tail",
    "--since",
}
_SINGULAR_RESOURCE_TYPE_MAP = {
    "pods": "pod",
    "deployments": "deployment",
    "daemonsets": "daemonset",
    "statefulsets": "statefulset",
    "replicasets": "replicaset",
    "jobs": "job",
    "cronjobs": "cronjob",
    "services": "service",
}


def _validate_kubectl_tool(config: dict, node_id: str) -> None:
    _validate_external_output_key(config, node_id)

    action = config.get("action", _ACTION_GET)
    if action not in _SUPPORTED_ACTIONS:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" config.action must be one of: '
                    f'{", ".join(sorted(_SUPPORTED_ACTIONS))}.'
                )
            }
        )

    if action == _ACTION_CUSTOM:
        _validate_required_string(config, "command", node_id=node_id)
    if action in {_ACTION_GET, _ACTION_DESCRIBE, _ACTION_LOGS}:
        _validate_required_string(config, "resource_type", node_id=node_id)
    if action in {_ACTION_DESCRIBE, _ACTION_LOGS, _ACTION_ROLLOUT_STATUS}:
        _validate_required_string(config, "resource_name", node_id=node_id)
    if action == _ACTION_TOP:
        top_target = config.get("top_target", "pod")
        if top_target not in _SUPPORTED_TOP_TARGETS:
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" config.top_target must be one of: '
                        f'{", ".join(sorted(_SUPPORTED_TOP_TARGETS))}.'
                    )
                }
            )
    if action == _ACTION_ROLLOUT_STATUS:
        rollout_kind = config.get("rollout_kind", "deployment")
        if rollout_kind not in _SUPPORTED_ROLLOUT_KINDS:
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" config.rollout_kind must be one of: '
                        f'{", ".join(sorted(_SUPPORTED_ROLLOUT_KINDS))}.'
                    )
                }
            )

    _validate_optional_string(config, "resource_type", node_id=node_id)
    _validate_optional_string(config, "resource_name", node_id=node_id)
    _validate_optional_string(config, "label_selector", node_id=node_id)
    _validate_optional_string(config, "container_name", node_id=node_id)
    _validate_optional_string(config, "tail_lines", node_id=node_id)
    _validate_optional_string(config, "since", node_id=node_id)
    _validate_optional_string(config, "binary_path", node_id=node_id)
    _validate_optional_string(config, "context_name", node_id=node_id)
    _validate_optional_string(config, "namespace", node_id=node_id)

    if config.get("secret_name") not in (None, ""):
        _validate_optional_string(config, "secret_name", node_id=node_id)
    _validate_optional_secret_group_id(config, "secret_group_id", node_id=node_id)

    output_format = config.get("output_format", "auto")
    if output_format not in {"text", "json", "auto"}:
        raise ValidationError(
            {"definition": f'Node "{node_id}" config.output_format must be one of: auto, text, json.'}
        )

    command_policy = config.get("command_policy", _READ_ONLY_POLICY)
    if command_policy not in _SUPPORTED_COMMAND_POLICIES:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" config.command_policy must be one of: '
                    f'{", ".join(sorted(_SUPPORTED_COMMAND_POLICIES))}.'
                )
            }
        )

    kubeconfig_secret_mode = config.get("kubeconfig_secret_mode", "content")
    if kubeconfig_secret_mode not in {"content", "path"}:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" config.kubeconfig_secret_mode must be one of: content, path.'
                )
            }
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


def _iter_command_tokens_without_leading_flags(command_parts: Iterable[str]) -> list[str]:
    trimmed: list[str] = []
    consume_next_value = False

    for token in command_parts:
        if consume_next_value:
            consume_next_value = False
            continue

        if not trimmed and token.startswith("-"):
            if token in _LEADING_FLAGS_WITH_VALUES:
                consume_next_value = True
            elif any(token.startswith(f"{flag}=") for flag in _LEADING_FLAGS_WITH_VALUES if flag.startswith("--")):
                continue
            continue

        trimmed.append(token)

    return trimmed


def _is_read_only_kubectl_command(command_parts: list[str]) -> bool:
    trimmed_parts = _iter_command_tokens_without_leading_flags(command_parts)
    if not trimmed_parts:
        return False

    top_level_command = trimmed_parts[0]
    if top_level_command in _READ_ONLY_TOP_LEVEL_COMMANDS:
        return True

    if top_level_command == "rollout":
        return len(trimmed_parts) > 1 and trimmed_parts[1] in _ROLLOUT_READ_ONLY_SUBCOMMANDS

    if top_level_command == "config":
        return len(trimmed_parts) > 1 and trimmed_parts[1] in _CONFIG_READ_ONLY_SUBCOMMANDS

    return False


def _get_top_level_command(command_parts: list[str]) -> str | None:
    trimmed_parts = _iter_command_tokens_without_leading_flags(command_parts)
    if not trimmed_parts:
        return None
    return trimmed_parts[0]


def _ensure_kubectl_output_format(command_parts: list[str], *, output_format: str) -> list[str]:
    if output_format not in {"json", "auto"}:
        return command_parts

    for index, command_part in enumerate(command_parts):
        if command_part == "-o":
            return command_parts
        if command_part.startswith("-o") and len(command_part) > 2:
            return command_parts
        if command_part == "--output":
            return command_parts
        if command_part.startswith("--output="):
            return command_parts
        if command_part == "--" and index < len(command_parts):
            break

    if output_format == "auto" and _get_top_level_command(command_parts) != "get":
        return command_parts

    return [*command_parts, "-ojson"]


def _normalize_resource_reference(resource_type: str, resource_name: str) -> str:
    normalized_type = _SINGULAR_RESOURCE_TYPE_MAP.get(resource_type.strip().lower(), resource_type.strip().lower())
    return f"{normalized_type}/{resource_name.strip()}"


def _build_guided_kubectl_command_parts(runtime: WorkflowToolExecutionContext, *, action: str) -> list[str]:
    if action == _ACTION_GET:
        resource_type = _render_runtime_string(runtime, "resource_type", required=True, default_mode="static")
        resource_name = _render_runtime_string(runtime, "resource_name", default_mode="static")
        label_selector = _render_runtime_string(runtime, "label_selector", default_mode="static")
        command_parts = ["get", resource_type]
        if resource_name:
            command_parts.append(resource_name)
        if label_selector:
            command_parts.extend(["--selector", label_selector])
        return command_parts

    if action == _ACTION_DESCRIBE:
        resource_type = _render_runtime_string(runtime, "resource_type", required=True, default_mode="static")
        resource_name = _render_runtime_string(runtime, "resource_name", required=True, default_mode="static")
        return ["describe", resource_type, resource_name]

    if action == _ACTION_LOGS:
        resource_type = _render_runtime_string(runtime, "resource_type", required=True, default_mode="static")
        resource_name = _render_runtime_string(runtime, "resource_name", required=True, default_mode="static")
        container_name = _render_runtime_string(runtime, "container_name", default_mode="static")
        tail_lines = _render_runtime_string(runtime, "tail_lines", default_mode="static")
        since = _render_runtime_string(runtime, "since", default_mode="static")
        command_parts = ["logs", _normalize_resource_reference(resource_type, resource_name)]
        if container_name:
            command_parts.extend(["-c", container_name])
        if tail_lines:
            command_parts.extend(["--tail", tail_lines])
        if since:
            command_parts.extend(["--since", since])
        return command_parts

    if action == _ACTION_TOP:
        top_target = _render_runtime_string(runtime, "top_target", default="pod") or "pod"
        resource_name = _render_runtime_string(runtime, "resource_name", default_mode="static")
        label_selector = _render_runtime_string(runtime, "label_selector", default_mode="static")
        command_parts = ["top", top_target]
        if resource_name:
            command_parts.append(resource_name)
        if label_selector and top_target == "pod":
            command_parts.extend(["--selector", label_selector])
        return command_parts

    if action == _ACTION_ROLLOUT_STATUS:
        rollout_kind = _render_runtime_string(runtime, "rollout_kind", default="deployment") or "deployment"
        resource_name = _render_runtime_string(runtime, "resource_name", required=True, default_mode="static")
        return ["rollout", "status", f"{rollout_kind}/{resource_name}"]

    raise ValidationError({"definition": f'Unsupported kubectl action "{action}".'})


def _execute_kubectl_tool(runtime: WorkflowToolExecutionContext) -> dict:
    output_key = _render_runtime_string(runtime, "output_key", required=True, default_mode="static")
    action = _render_runtime_string(runtime, "action", default=_ACTION_GET) or _ACTION_GET
    binary_path = _render_runtime_string(runtime, "binary_path", default_mode="static") or "kubectl"
    context_name = _render_runtime_string(runtime, "context_name", default_mode="static")
    namespace = _render_runtime_string(runtime, "namespace", default_mode="static")
    output_format = _render_runtime_string(runtime, "output_format", default_mode="static") or "auto"
    configured_command_policy = (
        _render_runtime_string(runtime, "command_policy", default_mode="static") or _READ_ONLY_POLICY
    )
    kubeconfig_secret_mode = (
        _render_runtime_string(runtime, "kubeconfig_secret_mode", default_mode="static") or "content"
    )
    timeout_seconds = _coerce_positive_int(
        runtime.config.get("timeout_seconds"),
        field_name="timeout_seconds",
        node_id=runtime.node["id"],
        default=20,
        maximum=300,
    )

    kubectl_binary = _resolve_kubectl_binary(binary_path)
    if action == _ACTION_CUSTOM:
        command = _render_runtime_string(runtime, "command", required=True, default_mode="static")
        parsed_command_parts = _parse_kubectl_command(command)
        command_policy = configured_command_policy
        if command_policy == _READ_ONLY_POLICY and not _is_read_only_kubectl_command(parsed_command_parts):
            raise ValidationError(
                {
                    "definition": (
                        "kubectl command was blocked by the read-only safety policy. "
                        "Use a read-only subcommand such as get, describe, logs, top, or rollout status, "
                        'or set config.command_policy to "allow_mutating" for an explicit write-enabled node.'
                    )
                }
            )
    else:
        parsed_command_parts = _build_guided_kubectl_command_parts(runtime, action=action)
        command_policy = _READ_ONLY_POLICY

    command_parts = _ensure_kubectl_output_format(
        parsed_command_parts,
        output_format=output_format,
    )

    kubeconfig_meta = None
    kubeconfig_path: str | None = None
    secret_name = _render_runtime_string(runtime, "secret_name", default_mode="static")
    if secret_name:
        kubeconfig_value, kubeconfig_meta = _resolve_runtime_secret(
            runtime,
            secret_name=secret_name,
            secret_group_id=runtime.config.get("secret_group_id"),
        )
        if kubeconfig_secret_mode == "path":
            kubeconfig_path = kubeconfig_value
        else:
            kubeconfig_file = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".kubeconfig",
                delete=False,
            )
            try:
                kubeconfig_file.write(kubeconfig_value)
                kubeconfig_file.flush()
            finally:
                kubeconfig_file.close()
            kubeconfig_path = kubeconfig_file.name

    argv = [kubectl_binary]
    if kubeconfig_path:
        argv.extend(["--kubeconfig", kubeconfig_path])
    if context_name:
        argv.extend(["--context", context_name])
    if namespace:
        argv.extend(["--namespace", namespace])
    argv.extend(command_parts)

    try:
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
        elif output_format == "auto":
            try:
                parsed_output = _make_json_safe(json.loads(stdout))
            except ValueError:
                parsed_output = None

        payload = {
            "action": action,
            "command": argv,
            "stdout": stdout,
            "stderr": stderr,
            "output_format": output_format,
            "resolved_output_format": "json" if parsed_output is not None else "text",
        }
        if parsed_output is not None:
            payload["data"] = parsed_output

        runtime.set_path_value(runtime.context, output_key, payload)
        result = {
            "action": action,
            "output_key": output_key,
            "command": argv,
            "command_policy": command_policy,
            "output_format": output_format,
            "resolved_output_format": "json" if parsed_output is not None else "text",
        }
        if kubeconfig_meta is not None:
            result["secret"] = kubeconfig_meta
            result["kubeconfig_secret_mode"] = kubeconfig_secret_mode
        if parsed_output is not None and isinstance(parsed_output, dict):
            items = parsed_output.get("items")
            if isinstance(items, list):
                result["item_count"] = len(items)
        return _tool_result("kubectl", **result)
    finally:
        if secret_name and kubeconfig_secret_mode == "content" and kubeconfig_path:
            try:
                os.unlink(kubeconfig_path)
            except FileNotFoundError:
                pass


TOOL_DEFINITION = WorkflowToolDefinition(
    name="kubectl",
    label="kubectl",
    description=(
        "Run Kubernetes investigation actions against the locally installed kubectl binary. "
        "Choose a guided action like get, logs, top, or rollout status, or drop to a custom command when needed."
    ),
    icon="mdi-kubernetes",
    category="Infrastructure",
    config={
        "output_key": "kubectl.result",
        "action": "get",
        "command_policy": "read_only",
        "output_format": "auto",
        "top_target": "pod",
        "rollout_kind": "deployment",
        "timeout_seconds": 20,
        "kubeconfig_secret_mode": "content",
    },
    fields=(
        tool_text_field(
            "output_key",
            "Save result as",
            ui_group="result",
            binding="path",
            placeholder="kubectl.result",
        ),
        tool_select_field(
            "action",
            "Action",
            ui_group="input",
            options=(
                tool_field_option(_ACTION_GET, "Get"),
                tool_field_option(_ACTION_DESCRIBE, "Describe"),
                tool_field_option(_ACTION_LOGS, "Logs"),
                tool_field_option(_ACTION_TOP, "Top"),
                tool_field_option(_ACTION_ROLLOUT_STATUS, "Rollout status"),
                tool_field_option(_ACTION_CUSTOM, "Custom command"),
            ),
            help_text="Choose a guided kubectl action. Use custom command only when the guided actions are not enough.",
        ),
        tool_text_field(
            "resource_type",
            "Resource type",
            ui_group="input",
            binding="template",
            placeholder="pods",
            help_text="Examples: pods, deployments, jobs, services.",
            visible_when={
                "action": (_ACTION_GET, _ACTION_DESCRIBE, _ACTION_LOGS),
            },
        ),
        tool_text_field(
            "resource_name",
            "Resource name",
            ui_group="input",
            binding="template",
            placeholder="api-0",
            help_text="Optional for get. Required for describe, logs, and rollout status.",
            visible_when={
                "action": (_ACTION_GET, _ACTION_DESCRIBE, _ACTION_LOGS, _ACTION_TOP, _ACTION_ROLLOUT_STATUS),
            },
        ),
        tool_text_field(
            "label_selector",
            "Label selector",
            ui_group="input",
            binding="template",
            placeholder="app=payments-api",
            help_text="Optional. Used for get, or for top when the target is pod.",
            visible_when={
                "action": (_ACTION_GET, _ACTION_TOP),
            },
        ),
        tool_text_field(
            "container_name",
            "Container",
            ui_group="input",
            binding="template",
            placeholder="app",
            visible_when={
                "action": (_ACTION_LOGS,),
            },
        ),
        tool_text_field(
            "tail_lines",
            "Tail lines",
            ui_group="input",
            binding="template",
            placeholder="200",
            help_text="Optional. Passed to `kubectl logs --tail`.",
            visible_when={
                "action": (_ACTION_LOGS,),
            },
        ),
        tool_text_field(
            "since",
            "Since",
            ui_group="input",
            binding="template",
            placeholder="15m",
            help_text="Optional. Passed to `kubectl logs --since`.",
            visible_when={
                "action": (_ACTION_LOGS,),
            },
        ),
        tool_select_field(
            "top_target",
            "Top target",
            ui_group="input",
            options=(
                tool_field_option("pod", "Pod"),
                tool_field_option("node", "Node"),
            ),
            visible_when={
                "action": (_ACTION_TOP,),
            },
        ),
        tool_select_field(
            "rollout_kind",
            "Rollout kind",
            ui_group="input",
            options=tuple(
                tool_field_option(kind, kind.title())
                for kind in sorted(_SUPPORTED_ROLLOUT_KINDS)
            ),
            visible_when={
                "action": (_ACTION_ROLLOUT_STATUS,),
            },
        ),
        tool_textarea_field(
            "command",
            "kubectl command",
            rows=4,
            ui_group="input",
            binding="template",
            placeholder="get pods -A -o json",
            help_text="Arguments passed after the kubectl binary. A leading `kubectl` is ignored if you include it.",
            visible_when={
                "action": (_ACTION_CUSTOM,),
            },
        ),
        tool_select_field(
            "command_policy",
            "Command safety",
            ui_group="advanced",
            options=(
                tool_field_option("read_only", "Read-only"),
                tool_field_option("allow_mutating", "Allow mutating"),
            ),
            help_text=(
                "Read-only blocks mutating kubectl operations such as apply, delete, patch, exec, and port-forward. "
                "Use allow mutating only for explicit remediation workflows."
            ),
            visible_when={
                "action": (_ACTION_CUSTOM,),
            },
        ),
        tool_select_field(
            "output_format",
            "Output format",
            ui_group="advanced",
            options=(
                tool_field_option("auto"),
                tool_field_option("text"),
                tool_field_option("json"),
            ),
            help_text=(
                "Auto adds `-o json` for `kubectl get` commands when no output flag is present, "
                "while leaving text-oriented commands such as logs, top, describe, or rollout status unchanged."
            ),
            visible_when={
                "action": (_ACTION_GET, _ACTION_CUSTOM),
            },
        ),
        tool_text_field(
            "context_name",
            "Kube context",
            ui_group="advanced",
            binding="template",
            placeholder="prod-cluster",
            help_text="Optional. Adds `--context` before the command.",
        ),
        tool_text_field(
            "namespace",
            "Namespace",
            ui_group="advanced",
            binding="template",
            placeholder="payments",
            help_text="Optional. Adds `--namespace` before the command.",
        ),
        tool_select_field(
            "kubeconfig_secret_mode",
            "Kubeconfig secret type",
            ui_group="advanced",
            options=(
                tool_field_option("content"),
                tool_field_option("path"),
            ),
            help_text="When a secret is configured, treat it either as raw kubeconfig content or as a filesystem path to an existing kubeconfig file.",
        ),
        tool_text_field(
            "secret_name",
            "Kubeconfig secret name",
            ui_group="advanced",
            placeholder="KUBECONFIG",
            help_text="Optional. Resolve this secret and pass it to kubectl as either kubeconfig content or a kubeconfig path.",
        ),
        tool_text_field(
            "secret_group_id",
            "Secret group",
            ui_group="advanced",
            placeholder="Use workflow secret group",
            help_text="Optional. Override the workflow secret group for this node.",
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
NODE_DEFINITION = tool_definition_as_node_definition(
    TOOL_DEFINITION,
    node_type="tool.kubectl",
    details="Operate infrastructure workflows against the local app host environment.",
)
