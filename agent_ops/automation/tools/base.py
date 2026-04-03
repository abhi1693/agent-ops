from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta, timezone as datetime_timezone
from typing import Any, Callable, Iterable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError
from django.utils import timezone


WorkflowToolValidator = Callable[[dict[str, Any], str], None]
WorkflowToolExecutor = Callable[["WorkflowToolExecutionContext"], dict[str, Any]]
WorkflowToolFieldType = Literal["text", "textarea", "select", "node_target"]
WorkflowToolFieldUiGroup = Literal["input", "result", "advanced"]
WorkflowToolFieldBinding = Literal["literal", "template", "path"]
WorkflowFieldValueMode = Literal["static", "expression"]
SUPPORTED_WORKFLOW_TOOL_FIELD_UI_GROUPS = frozenset({"input", "result", "advanced"})
SUPPORTED_WORKFLOW_TOOL_FIELD_BINDINGS = frozenset({"literal", "template", "path"})
SUPPORTED_WORKFLOW_FIELD_VALUE_MODES = frozenset({"static", "expression"})
WORKFLOW_INPUT_MODES_CONFIG_KEY = "__input_modes"


@dataclass(frozen=True)
class WorkflowToolFieldOption:
    value: str
    label: str

    def serialize(self) -> dict[str, str]:
        return {
            "value": self.value,
            "label": self.label,
        }


@dataclass(frozen=True)
class WorkflowToolFieldDefinition:
    key: str
    label: str
    type: WorkflowToolFieldType
    options: tuple[WorkflowToolFieldOption, ...] = ()
    visible_when: dict[str, tuple[str, ...]] = field(default_factory=dict)
    options_by_field: dict[str, dict[str, tuple[WorkflowToolFieldOption, ...]]] = field(default_factory=dict)
    ui_group: WorkflowToolFieldUiGroup | None = None
    binding: WorkflowToolFieldBinding | None = None
    placeholder: str | None = None
    help_text: str | None = None
    rows: int | None = None

    def __post_init__(self) -> None:
        if self.type != "select" and self.options:
            raise ValueError(f'Field "{self.key}" can only define options for select fields.')
        if self.type != "select" and self.options_by_field:
            raise ValueError(f'Field "{self.key}" can only define options_by_field for select fields.')
        if self.type != "textarea" and self.rows is not None:
            raise ValueError(f'Field "{self.key}" can only define rows for textarea fields.')
        if self.rows is not None and self.rows < 1:
            raise ValueError(f'Field "{self.key}" rows must be greater than zero.')
        if self.ui_group is not None and self.ui_group not in SUPPORTED_WORKFLOW_TOOL_FIELD_UI_GROUPS:
            raise ValueError(
                f'Field "{self.key}" ui_group must be one of: '
                f'{", ".join(sorted(SUPPORTED_WORKFLOW_TOOL_FIELD_UI_GROUPS))}.'
            )
        if self.binding is not None and self.binding not in SUPPORTED_WORKFLOW_TOOL_FIELD_BINDINGS:
            raise ValueError(
                f'Field "{self.key}" binding must be one of: '
                f'{", ".join(sorted(SUPPORTED_WORKFLOW_TOOL_FIELD_BINDINGS))}.'
            )

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "type": self.type,
        }
        if self.options:
            payload["options"] = [option.serialize() for option in self.options]
        if self.visible_when:
            payload["visible_when"] = {
                key: list(values)
                for key, values in self.visible_when.items()
            }
        if self.options_by_field:
            payload["options_by_field"] = {
                config_key: {
                    config_value: [option.serialize() for option in options]
                    for config_value, options in option_map.items()
                }
                for config_key, option_map in self.options_by_field.items()
            }
        if self.ui_group is not None:
            payload["ui_group"] = self.ui_group
        if self.binding is not None:
            payload["binding"] = self.binding
        if self.placeholder is not None:
            payload["placeholder"] = self.placeholder
        if self.help_text is not None:
            payload["help_text"] = self.help_text
        if self.rows is not None:
            payload["rows"] = self.rows
        return payload


def tool_field_option(value: str, label: str | None = None) -> WorkflowToolFieldOption:
    rendered_value = str(value)
    return WorkflowToolFieldOption(value=rendered_value, label=label or rendered_value)


def tool_text_field(
    key: str,
    label: str,
    *,
    ui_group: WorkflowToolFieldUiGroup | None = None,
    binding: WorkflowToolFieldBinding | None = None,
    placeholder: str | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
) -> WorkflowToolFieldDefinition:
    return WorkflowToolFieldDefinition(
        key=key,
        label=label,
        type="text",
        ui_group=ui_group,
        binding=binding,
        placeholder=placeholder,
        help_text=help_text,
        visible_when=visible_when or {},
    )


def tool_textarea_field(
    key: str,
    label: str,
    *,
    rows: int,
    ui_group: WorkflowToolFieldUiGroup | None = None,
    binding: WorkflowToolFieldBinding | None = None,
    placeholder: str | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
) -> WorkflowToolFieldDefinition:
    return WorkflowToolFieldDefinition(
        key=key,
        label=label,
        type="textarea",
        ui_group=ui_group,
        binding=binding,
        rows=rows,
        placeholder=placeholder,
        help_text=help_text,
        visible_when=visible_when or {},
    )


def tool_select_field(
    key: str,
    label: str,
    *,
    options: Iterable[WorkflowToolFieldOption],
    ui_group: WorkflowToolFieldUiGroup | None = None,
    binding: WorkflowToolFieldBinding | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
    options_by_field: dict[str, dict[str, tuple[WorkflowToolFieldOption, ...]]] | None = None,
) -> WorkflowToolFieldDefinition:
    return WorkflowToolFieldDefinition(
        key=key,
        label=label,
        type="select",
        options=tuple(options),
        ui_group=ui_group,
        binding=binding,
        help_text=help_text,
        visible_when=visible_when or {},
        options_by_field=options_by_field or {},
    )


@dataclass(frozen=True)
class WorkflowToolDefinition:
    name: str
    label: str
    description: str
    icon: str = "mdi-tools"
    category: str = "Built-in"
    config: dict[str, Any] = field(default_factory=dict)
    fields: tuple[WorkflowToolFieldDefinition, ...] = ()
    validator: WorkflowToolValidator | None = None
    executor: WorkflowToolExecutor | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "config": dict(self.config),
            "fields": [field.serialize() for field in self.fields],
        }


@dataclass
class WorkflowToolExecutionContext:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    context: dict[str, Any]
    secret_paths: set[str]
    secret_values: list[str]
    render_template: Callable[[str, dict[str, Any]], str]
    set_path_value: Callable[[dict[str, Any], str, Any], None]
    resolve_scoped_secret: Callable[..., Any]


def _raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def _validate_optional_string(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" config.{key} must be a non-empty string.')


def _validate_required_string(config: dict[str, Any], key: str, *, node_id: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(f'Node "{node_id}" must define config.{key}.')
    return value


def _validate_optional_secret_group_id(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value in (None, ""):
        return
    if isinstance(value, int):
        return
    if isinstance(value, str) and value.strip().isdigit():
        return
    _raise_definition_error(f'Node "{node_id}" config.{key} must be a numeric secret group ID.')


def _validate_external_url_value(url_value: str, *, field_name: str, node_id: str) -> str:
    parsed_url = urlsplit(url_value)
    if parsed_url.username is not None or parsed_url.password is not None:
        _raise_definition_error(
            (
                f'Node "{node_id}" config.{field_name} cannot include embedded credentials in the URL. '
                "Secrets must come from stored Secret objects."
            )
        )
    return url_value


def _validate_required_external_url(config: dict[str, Any], key: str, *, node_id: str) -> str:
    return _validate_external_url_value(
        _validate_required_string(config, key, node_id=node_id),
        field_name=key,
        node_id=node_id,
    )


def _validate_optional_json_template(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if isinstance(value, (dict, list)):
        return
    if not isinstance(value, str) or not value.strip():
        _raise_definition_error(
            f'Node "{node_id}" config.{key} must be a non-empty JSON string or object.'
        )


def _validate_required_json_template(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value in (None, ""):
        _raise_definition_error(f'Node "{node_id}" must define config.{key}.')
    _validate_optional_json_template(config, key, node_id=node_id)


def _tool_result(tool_name: str, **extra: Any) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "operation": tool_name,
        **extra,
    }


def normalize_workflow_tool_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return dict(config or {})


def normalize_workflow_definition_tools(definition: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {"nodes": [], "edges": []}

    normalized_definition = dict(definition)
    normalized_nodes = []
    for node in definition.get("nodes", []):
        if not isinstance(node, dict):
            normalized_nodes.append(node)
            continue

        normalized_node = dict(node)
        if normalized_node.get("kind") == "tool":
            normalized_node["config"] = normalize_workflow_tool_config(normalized_node.get("config"))
        normalized_nodes.append(normalized_node)

    normalized_definition["nodes"] = normalized_nodes
    return normalized_definition


def _coerce_positive_int(
    value: Any,
    *,
    field_name: str,
    node_id: str,
    default: int,
    maximum: int | None = None,
) -> int:
    if value in (None, ""):
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            _raise_definition_error(f'Node "{node_id}" config.{field_name} must be an integer.')
            raise AssertionError("unreachable") from exc

    if parsed < 1:
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must be greater than zero.')
    if maximum is not None and parsed > maximum:
        _raise_definition_error(
            f'Node "{node_id}" config.{field_name} must be less than or equal to {maximum}.'
        )
    return parsed


def _coerce_optional_float(
    value: Any,
    *,
    field_name: str,
    node_id: str,
) -> float | None:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must be a number.')
        raise AssertionError("unreachable") from exc


def _coerce_csv_strings(value: Any, *, field_name: str, node_id: str, default: list[str]) -> list[str]:
    if value in (None, ""):
        return list(default)

    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        if items:
            return items
        _raise_definition_error(f'Node "{node_id}" config.{field_name} must contain at least one value.')

    if isinstance(value, list):
        items = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                _raise_definition_error(
                    f'Node "{node_id}" config.{field_name} must contain non-empty strings.'
                )
            items.append(item.strip())
        return items

    _raise_definition_error(
        f'Node "{node_id}" config.{field_name} must be a comma-separated string or a list of strings.'
    )


def _looks_like_runtime_expression(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _get_runtime_input_mode(
    config: dict[str, Any],
    key: str,
    *,
    default: WorkflowFieldValueMode = "static",
) -> WorkflowFieldValueMode:
    raw_modes = config.get(WORKFLOW_INPUT_MODES_CONFIG_KEY)
    if isinstance(raw_modes, dict):
        mode = raw_modes.get(key)
        if isinstance(mode, str) and mode in SUPPORTED_WORKFLOW_FIELD_VALUE_MODES:
            return mode
    if default == "static" and _looks_like_runtime_expression(config.get(key)):
        return "expression"
    return default


def _render_runtime_string(
    runtime: WorkflowToolExecutionContext,
    key: str,
    *,
    required: bool = False,
    default: str | None = None,
    default_mode: WorkflowFieldValueMode = "static",
) -> str | None:
    value = runtime.config.get(key, default)
    if value in (None, ""):
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.{key}.'})
        return None

    mode = _get_runtime_input_mode(runtime.config, key, default=default_mode)
    rendered = (
        runtime.render_template(str(value), runtime.context).strip()
        if mode == "expression"
        else str(value).strip()
    )
    if not rendered:
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" config.{key} rendered empty.'})
        return None
    return rendered


def _render_runtime_external_url(
    runtime: WorkflowToolExecutionContext,
    key: str,
    *,
    required: bool = False,
    default: str | None = None,
    default_mode: WorkflowFieldValueMode = "static",
) -> str | None:
    rendered = _render_runtime_string(
        runtime,
        key,
        required=required,
        default=default,
        default_mode=default_mode,
    )
    if rendered is None:
        return None

    parsed_url = urlsplit(rendered)
    if parsed_url.username is not None or parsed_url.password is not None:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{runtime.node["id"]}" config.{key} cannot render a URL with embedded credentials. '
                    "Secrets must come from stored Secret objects."
                )
            }
        )
    return rendered


def _render_runtime_json(
    runtime: WorkflowToolExecutionContext,
    key: str,
    *,
    required: bool = False,
    default_mode: WorkflowFieldValueMode = "static",
) -> Any:
    value = runtime.config.get(key)
    if value in (None, ""):
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.{key}.'})
        return None

    mode = _get_runtime_input_mode(runtime.config, key, default=default_mode)
    if mode == "static":
        if isinstance(value, (dict, list)):
            return value
        rendered = str(value).strip()
    else:
        if isinstance(value, (dict, list)):
            raw_template = json.dumps(value)
        else:
            raw_template = str(value)
        rendered = runtime.render_template(raw_template, runtime.context).strip()

    if not rendered:
        if required:
            raise ValidationError({"definition": f'Node "{runtime.node["id"]}" config.{key} rendered empty.'})
        return None

    try:
        return json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" config.{key} must render valid JSON.'}
        ) from exc


def _resolve_runtime_secret(
    runtime: WorkflowToolExecutionContext,
    *,
    secret_name: str,
    secret_group_id: str | int | None = None,
    required: bool = True,
) -> tuple[str, dict[str, str | None]] | tuple[None, None]:
    secret = runtime.resolve_scoped_secret(
        runtime.workflow,
        secret_name=secret_name,
        secret_group_id=secret_group_id,
        required=required,
    )
    if secret is None:
        return None, None
    value = secret.get_value(obj=runtime.workflow)
    if not isinstance(value, str) or not value:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" secret "{secret.name}" must resolve to a non-empty string.'}
        )
    runtime.secret_values.append(value)
    return value, {
        "name": secret.name,
        "provider": secret.provider,
        "secret_group": secret.secret_group.name if secret.secret_group_id else None,
    }


def _make_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(item) for item in value]
    return str(value)


def _isoformat_utc(value) -> str:
    return value.astimezone(datetime_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _http_json_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> tuple[Any, int]:
    final_url = url
    if query:
        encoded_query = urlencode(query, doseq=True)
        separator = "&" if "?" in final_url else "?"
        final_url = f"{final_url}{separator}{encoded_query}"

    request_headers = dict(headers or {})
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(final_url, data=data, headers=request_headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            raw_body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        snippet = f" {error_body[:400]}" if error_body else ""
        raise ValidationError(
            {"definition": f"HTTP {method.upper()} {final_url} failed with {exc.code}.{snippet}"}
        ) from exc
    except URLError as exc:
        raise ValidationError(
            {"definition": f"HTTP {method.upper()} {final_url} failed: {exc.reason}"}
        ) from exc

    if not raw_body:
        return None, status_code

    decoded_body = raw_body.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        return json.loads(decoded_body), status_code

    try:
        return json.loads(decoded_body), status_code
    except json.JSONDecodeError:
        return decoded_body, status_code


def _validate_external_output_key(config: dict[str, Any], node_id: str) -> None:
    _validate_required_string(config, "output_key", node_id=node_id)


def _extract_openai_compatible_text(response_data: dict[str, Any]) -> str | None:
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue

        text_value = item.get("text")
        if isinstance(text_value, str):
            parts.append(text_value)
            continue

        if isinstance(text_value, dict):
            nested_value = text_value.get("value")
            if isinstance(nested_value, str):
                parts.append(nested_value)

    joined = "".join(parts).strip()
    return joined or None
