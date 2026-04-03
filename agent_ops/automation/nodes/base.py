from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from django.core.exceptions import ValidationError


WorkflowNodeFieldType = Literal["text", "textarea", "select", "node_target"]
WorkflowNodeFieldUiGroup = Literal["input", "result", "advanced"]
WorkflowNodeFieldBinding = Literal["literal", "template", "path"]
SUPPORTED_WORKFLOW_NODE_FIELD_TYPES = frozenset(("text", "textarea", "select", "node_target"))
SUPPORTED_WORKFLOW_NODE_FIELD_UI_GROUPS = frozenset(("input", "result", "advanced"))
SUPPORTED_WORKFLOW_NODE_FIELD_BINDINGS = frozenset(("literal", "template", "path"))
WorkflowNodeValidator = Callable[[dict[str, Any], str, list[str], set[str]], None]
WorkflowNodeExecutor = Callable[["WorkflowNodeExecutionContext"], "WorkflowNodeExecutionResult"]
WorkflowNodeWebhookHandler = Callable[
    ["WorkflowNodeWebhookContext"],
    tuple[dict[str, Any], dict[str, Any]],
]

_DEFAULT_WORKFLOW_NODE_APP_DESCRIPTION = (
    "n8n-style built-in nodes packaged as first-class workflow node types."
)


def _require_manifest_string(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    joined_keys = ", ".join(keys)
    raise ValueError(f"Manifest must define a non-empty string for one of: {joined_keys}.")


def _optional_manifest_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise ValueError(f'Manifest key "{key}" must be a non-empty string when provided.')
    return None


def _normalize_manifest_string_list(value: Any, *, key: str) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise ValueError(f'Manifest key "{key}" must be a list of strings.')

    normalized_values: list[str] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f'Manifest key "{key}[{index}]" must be a non-empty string.')
        normalized_values.append(entry.strip())
    return tuple(normalized_values)


def _normalize_manifest_subcategories(value: Any) -> dict[str, tuple[str, ...]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError('Manifest key "subcategories" must be an object.')

    normalized: dict[str, tuple[str, ...]] = {}
    for group_name, entries in value.items():
        if not isinstance(group_name, str) or not group_name.strip():
            raise ValueError('Manifest subcategory group names must be non-empty strings.')
        normalized[group_name.strip()] = _normalize_manifest_string_list(
            entries,
            key=f"subcategories.{group_name}",
        )
    return normalized


def _normalize_manifest_field_value_map(value: Any, *, key: str) -> dict[str, tuple[str, ...]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f'Manifest key "{key}" must be an object.')

    normalized: dict[str, tuple[str, ...]] = {}
    for config_key, allowed_values in value.items():
        if not isinstance(config_key, str) or not config_key.strip():
            raise ValueError(f'Manifest key "{key}" must only use non-empty string keys.')
        normalized[config_key.strip()] = _normalize_manifest_string_list(
            allowed_values,
            key=f"{key}.{config_key}",
        )
    return normalized


def _normalize_manifest_field_options_by_field(
    value: Any,
    *,
    key: str,
) -> dict[str, dict[str, tuple["WorkflowNodeFieldOption", ...]]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f'Manifest key "{key}" must be an object.')

    normalized: dict[str, dict[str, tuple[WorkflowNodeFieldOption, ...]]] = {}
    for config_key, option_map in value.items():
        if not isinstance(config_key, str) or not config_key.strip():
            raise ValueError(f'Manifest key "{key}" must only use non-empty string keys.')
        if not isinstance(option_map, dict):
            raise ValueError(f'Manifest key "{key}.{config_key}" must be an object.')

        normalized_option_map: dict[str, tuple[WorkflowNodeFieldOption, ...]] = {}
        for config_value, options_payload in option_map.items():
            if not isinstance(config_value, str) or not config_value.strip():
                raise ValueError(
                    f'Manifest key "{key}.{config_key}" must only use non-empty string option values.'
                )
            if not isinstance(options_payload, list):
                raise ValueError(f'Manifest key "{key}.{config_key}.{config_value}" must be a list.')
            normalized_option_map[config_value.strip()] = tuple(
                WorkflowNodeFieldOption.from_manifest(option_payload)
                for option_payload in options_payload
            )

        normalized[config_key.strip()] = normalized_option_map
    return normalized


@dataclass(frozen=True)
class WorkflowNodeImplementation:
    validator: WorkflowNodeValidator | None = None
    executor: WorkflowNodeExecutor | None = None
    webhook_handler: WorkflowNodeWebhookHandler | None = None


@dataclass(frozen=True)
class WorkflowNodeFieldOption:
    value: str
    label: str

    @classmethod
    def from_manifest(cls, payload: dict[str, Any]) -> "WorkflowNodeFieldOption":
        if not isinstance(payload, dict):
            raise ValueError("Field options must be objects.")
        value = _require_manifest_string(payload, "value")
        label = _optional_manifest_string(payload, "label") or value
        return cls(value=value, label=label)

    def serialize(self) -> dict[str, str]:
        return {
            "value": self.value,
            "label": self.label,
        }


@dataclass(frozen=True)
class WorkflowNodeFieldDefinition:
    key: str
    label: str
    type: WorkflowNodeFieldType
    options: tuple[WorkflowNodeFieldOption, ...] = ()
    visible_when: dict[str, tuple[str, ...]] = field(default_factory=dict)
    options_by_field: dict[str, dict[str, tuple[WorkflowNodeFieldOption, ...]]] = field(default_factory=dict)
    ui_group: WorkflowNodeFieldUiGroup | None = None
    binding: WorkflowNodeFieldBinding | None = None
    placeholder: str | None = None
    help_text: str | None = None
    rows: int | None = None

    @classmethod
    def from_manifest(cls, payload: dict[str, Any]) -> "WorkflowNodeFieldDefinition":
        if not isinstance(payload, dict):
            raise ValueError("Field definitions must be objects.")

        field_type = _require_manifest_string(payload, "type")
        if field_type not in SUPPORTED_WORKFLOW_NODE_FIELD_TYPES:
            raise ValueError(
                f'Unsupported workflow node field type "{field_type}". '
                f"Expected one of: {', '.join(sorted(SUPPORTED_WORKFLOW_NODE_FIELD_TYPES))}."
            )

        options_payload = payload.get("options", ())
        if options_payload in (None, ()):
            options: tuple[WorkflowNodeFieldOption, ...] = ()
        else:
            if not isinstance(options_payload, list):
                raise ValueError('Manifest field key "options" must be a list when provided.')
            options = tuple(
                WorkflowNodeFieldOption.from_manifest(option_payload)
                for option_payload in options_payload
            )

        rows = payload.get("rows")
        if rows is not None:
            if not isinstance(rows, int) or rows <= 0:
                raise ValueError('Manifest field key "rows" must be a positive integer when provided.')

        visible_when = _normalize_manifest_field_value_map(
            payload.get("visible_when", payload.get("visibleWhen")),
            key="visible_when",
        )
        options_by_field = _normalize_manifest_field_options_by_field(
            payload.get("options_by_field", payload.get("optionsByField")),
            key="options_by_field",
        )
        if field_type != "select" and options_by_field:
            raise ValueError('Manifest field key "options_by_field" is only supported for select fields.')

        ui_group = _optional_manifest_string(payload, "uiGroup", "ui_group")
        if ui_group is not None and ui_group not in SUPPORTED_WORKFLOW_NODE_FIELD_UI_GROUPS:
            raise ValueError(
                f'Manifest field key "ui_group" must be one of: '
                f'{", ".join(sorted(SUPPORTED_WORKFLOW_NODE_FIELD_UI_GROUPS))}.'
            )

        binding = _optional_manifest_string(payload, "binding")
        if binding is not None and binding not in SUPPORTED_WORKFLOW_NODE_FIELD_BINDINGS:
            raise ValueError(
                f'Manifest field key "binding" must be one of: '
                f'{", ".join(sorted(SUPPORTED_WORKFLOW_NODE_FIELD_BINDINGS))}.'
            )

        return cls(
            key=_require_manifest_string(payload, "key"),
            label=_require_manifest_string(payload, "label"),
            type=field_type,
            options=options,
            visible_when=visible_when,
            options_by_field=options_by_field,
            ui_group=ui_group,
            binding=binding,
            placeholder=_optional_manifest_string(payload, "placeholder"),
            help_text=_optional_manifest_string(payload, "helpText", "help_text"),
            rows=rows,
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


def node_field_option(value: str, label: str | None = None) -> WorkflowNodeFieldOption:
    rendered_value = str(value)
    return WorkflowNodeFieldOption(value=rendered_value, label=label or rendered_value)


def node_text_field(
    key: str,
    label: str,
    *,
    ui_group: WorkflowNodeFieldUiGroup | None = None,
    binding: WorkflowNodeFieldBinding | None = None,
    placeholder: str | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
) -> WorkflowNodeFieldDefinition:
    return WorkflowNodeFieldDefinition(
        key=key,
        label=label,
        type="text",
        ui_group=ui_group,
        binding=binding,
        placeholder=placeholder,
        help_text=help_text,
        visible_when=visible_when or {},
    )


def node_textarea_field(
    key: str,
    label: str,
    *,
    rows: int,
    ui_group: WorkflowNodeFieldUiGroup | None = None,
    binding: WorkflowNodeFieldBinding | None = None,
    placeholder: str | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
) -> WorkflowNodeFieldDefinition:
    return WorkflowNodeFieldDefinition(
        key=key,
        label=label,
        type="textarea",
        rows=rows,
        ui_group=ui_group,
        binding=binding,
        placeholder=placeholder,
        help_text=help_text,
        visible_when=visible_when or {},
    )


def node_select_field(
    key: str,
    label: str,
    *,
    options: tuple[WorkflowNodeFieldOption, ...],
    ui_group: WorkflowNodeFieldUiGroup | None = None,
    binding: WorkflowNodeFieldBinding | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
    options_by_field: dict[str, dict[str, tuple[WorkflowNodeFieldOption, ...]]] | None = None,
) -> WorkflowNodeFieldDefinition:
    return WorkflowNodeFieldDefinition(
        key=key,
        label=label,
        type="select",
        options=options,
        ui_group=ui_group,
        binding=binding,
        help_text=help_text,
        visible_when=visible_when or {},
        options_by_field=options_by_field or {},
    )


def node_node_target_field(
    key: str,
    label: str,
    *,
    ui_group: WorkflowNodeFieldUiGroup | None = None,
    help_text: str | None = None,
    visible_when: dict[str, tuple[str, ...]] | None = None,
) -> WorkflowNodeFieldDefinition:
    return WorkflowNodeFieldDefinition(
        key=key,
        label=label,
        type="node_target",
        ui_group=ui_group,
        help_text=help_text,
        visible_when=visible_when or {},
    )


@dataclass(frozen=True)
class WorkflowNodeDefinition:
    type: str
    kind: str
    display_name: str
    description: str
    icon: str
    node_version: str | None = None
    categories: tuple[str, ...] = ()
    subcategories: dict[str, tuple[str, ...]] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    fields: tuple[WorkflowNodeFieldDefinition, ...] = ()
    app_id: str = "builtins"
    app_label: str = "Built-ins"
    app_description: str = _DEFAULT_WORKFLOW_NODE_APP_DESCRIPTION
    app_icon: str = "mdi-toy-brick-outline"
    validator: WorkflowNodeValidator | None = None
    executor: WorkflowNodeExecutor | None = None
    webhook_handler: WorkflowNodeWebhookHandler | None = None

    @property
    def documentation_url(self) -> str | None:
        primary_docs = self.resources.get("primaryDocumentation")
        if not isinstance(primary_docs, list) or not primary_docs:
            return None
        first_doc = primary_docs[0]
        if not isinstance(first_doc, dict):
            return None
        url = first_doc.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        return url.strip()

    @classmethod
    def from_manifest(
        cls,
        manifest: dict[str, Any],
        *,
        implementation: WorkflowNodeImplementation | None = None,
    ) -> "WorkflowNodeDefinition":
        if not isinstance(manifest, dict):
            raise ValueError("Node manifest must decode to an object.")

        agent_ops = manifest.get("agentOps")
        if not isinstance(agent_ops, dict):
            raise ValueError('Node manifest must define an "agentOps" object.')

        config = agent_ops.get("config", {})
        if not isinstance(config, dict):
            raise ValueError('Node manifest key "agentOps.config" must be an object.')

        fields_payload = agent_ops.get("fields", ())
        if fields_payload in (None, ()):
            fields: tuple[WorkflowNodeFieldDefinition, ...] = ()
        else:
            if not isinstance(fields_payload, list):
                raise ValueError('Node manifest key "agentOps.fields" must be a list when provided.')
            fields = tuple(
                WorkflowNodeFieldDefinition.from_manifest(field_payload)
                for field_payload in fields_payload
            )

        resources = manifest.get("resources", {})
        if not isinstance(resources, dict):
            raise ValueError('Node manifest key "resources" must be an object when provided.')

        implementation = implementation or WorkflowNodeImplementation()

        return cls(
            type=_require_manifest_string(manifest, "node"),
            kind=_require_manifest_string(agent_ops, "kind"),
            display_name=_require_manifest_string(agent_ops, "displayName", "display_name"),
            description=(
                _optional_manifest_string(manifest, "details")
                or _require_manifest_string(agent_ops, "description")
            ),
            icon=_require_manifest_string(agent_ops, "icon"),
            node_version=_optional_manifest_string(manifest, "nodeVersion", "node_version"),
            categories=_normalize_manifest_string_list(manifest.get("categories"), key="categories"),
            subcategories=_normalize_manifest_subcategories(manifest.get("subcategories")),
            resources=deepcopy(resources),
            config=deepcopy(config),
            fields=fields,
            app_id=_optional_manifest_string(agent_ops, "appId", "app_id") or "builtins",
            app_label=_optional_manifest_string(agent_ops, "appLabel", "app_label") or "Built-ins",
            app_description=(
                _optional_manifest_string(agent_ops, "appDescription", "app_description")
                or _DEFAULT_WORKFLOW_NODE_APP_DESCRIPTION
            ),
            app_icon=_optional_manifest_string(agent_ops, "appIcon", "app_icon") or "mdi-toy-brick-outline",
            validator=implementation.validator,
            executor=implementation.executor,
            webhook_handler=implementation.webhook_handler,
        )

    def serialize(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "type": self.type,
            "label": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "config": deepcopy(self.config),
            "fields": [field.serialize() for field in self.fields],
            "app_id": self.app_id,
            "app_label": self.app_label,
            "app_description": self.app_description,
            "app_icon": self.app_icon,
        }
        if self.node_version is not None:
            payload["node_version"] = self.node_version
        if self.categories:
            payload["categories"] = list(self.categories)
        if self.subcategories:
            payload["subcategories"] = {
                key: list(values)
                for key, values in self.subcategories.items()
            }
        if self.resources:
            payload["resources"] = deepcopy(self.resources)
        if self.documentation_url is not None:
            payload["documentation_url"] = self.documentation_url
        return payload


@dataclass
class WorkflowNodeExecutionResult:
    next_node_id: str | None
    output: dict[str, Any] | None = None
    response: Any = None
    run_status: str | None = None
    terminal: bool = False


@dataclass
class WorkflowNodeExecutionContext:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    next_node_id: str | None
    connected_nodes_by_port: dict[str, list[dict[str, Any]]]
    context: dict[str, Any]
    secret_paths: set[str]
    secret_values: list[str]
    render_template: Callable[[str, dict[str, Any]], str]
    get_path_value: Callable[[Any, str | None], Any]
    set_path_value: Callable[[dict[str, Any], str, Any], None]
    resolve_scoped_secret: Callable[..., Any]
    evaluate_condition: Callable[[str, Any, Any], bool]


@dataclass
class WorkflowNodeWebhookContext:
    workflow: Any
    node: dict[str, Any]
    config: dict[str, Any]
    request: Any
    body: bytes


def raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def validate_optional_string(config: dict[str, Any], key: str, *, node_id: str) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise_definition_error(f'Node "{node_id}" config.{key} must be a non-empty string.')


def validate_required_string(config: dict[str, Any], key: str, *, node_id: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise_definition_error(f'Node "{node_id}" must define config.{key}.')
    return value
