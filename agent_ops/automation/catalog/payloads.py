from __future__ import annotations

from typing import Any

from automation.catalog.capabilities import CAPABILITY_AGENT_MODEL
from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition, ParameterOptionDefinition
from automation.catalog.sections import WORKFLOW_NODE_CATALOG_SECTION_ORDER, WORKFLOW_NODE_CATALOG_SECTIONS
from automation.catalog.services import get_workflow_catalog

WORKFLOW_CATALOG_GROUPS: tuple[dict[str, str], ...] = (
    {
        "id": "ai",
        "label": "AI",
        "description": "Build autonomous agents, summarize or search documents, etc.",
        "icon": "mdi-robot-outline",
    },
    {
        "id": "data",
        "label": "Data transformation",
        "description": "Manipulate, filter or convert data",
        "icon": "mdi-pencil-outline",
    },
    {
        "id": "flow",
        "label": "Flow",
        "description": "Branch, merge or control the flow.",
        "icon": "mdi-source-branch",
    },
    {
        "id": "core",
        "label": "Core",
        "description": "Run built-in workflow steps.",
        "icon": "mdi-toolbox-outline",
    },
)

WORKFLOW_TRIGGER_SELECTION: dict[str, Any] = {
    "description": "Triggers start your workflow. Each workflow can only have one trigger.",
    "label": "Add trigger",
}

WORKFLOW_NODE_SELECTION_PRESENTATION: dict[str, Any] = {
    "app_actions": {
        "action_meta": "Action nodes",
        "empty": "No matching apps",
        "search_placeholder": "Search nodes...",
        "title": "Action in an app",
    },
    "app_details": {
        "default_title": "Node details",
        "empty": "No nodes available for this app",
        "sections": {
            "actions": "Actions",
            "triggers": "Triggers",
        },
    },
    "category_details": {
        "empty_template": "No matching {group} nodes",
        "fallback_empty": "No matching nodes",
        "search_placeholder": "Search nodes...",
    },
    "common": {
        "add_description": "Choose the next step to add to this workflow.",
        "connect_description": "Choose the next step to connect from here.",
        "default_empty": "No matching nodes",
        "default_search_placeholder": "Search nodes, apps, or actions",
        "default_title": "Add node",
    },
    "insert": {
        "model_provider": {
            "description": (
                "Choose a provider-backed model node. Each one includes curated presets "
                "and an optional custom override."
            ),
            "empty": "No matching model providers",
            "search_placeholder": "Search model providers",
            "title": "Attach model provider",
        },
        "tool": {
            "description": "Choose any tool or integration node to attach to this agent.",
            "empty": "No matching tools",
            "search_placeholder": "Search tools",
            "title": "Attach tool",
        },
    },
    "next_step_root": {
        "empty": "No matching node categories",
        "items": {
            "app_action": {
                "description": "Do something in an app or service like Elasticsearch or Prometheus.",
                "label": "Action in an app",
            },
        },
        "search_placeholder": "Search nodes...",
        "title": "What happens next?",
    },
    "trigger_apps": {
        "empty": "No matching apps",
        "search_placeholder": "Search nodes...",
        "title": "On app event",
        "trigger_meta": "Trigger nodes",
    },
    "trigger_root": {
        "additional": WORKFLOW_TRIGGER_SELECTION,
        "empty": "No matching triggers",
        "initial": {
            "description": "A trigger is a step that starts your workflow",
            "title": "What triggers this workflow?",
        },
        "items": {
            "app_event": {
                "description": "Start the workflow from an event in one of your apps.",
            },
            "manual": {
                "label": "Trigger manually",
            },
            "schedule": {
                "label": "On a schedule",
            },
        },
        "search_placeholder": "Search nodes...",
    },
}

WORKFLOW_DESIGNER_PRESENTATION: dict[str, Any] = {
    "chrome": {
        "browser": {
            "aria_label": "Node browser",
            "close_label": "Close node browser",
            "default_title": "Add node",
            "search_label": "Search nodes",
        },
        "canvas": {
            "controls_aria_label": "Canvas controls",
            "empty_state": {
                "action_aria_label": "Add the first workflow step",
                "action_caption": "Choose a trigger to start the workflow",
                "action_label": "Add first step",
            },
            "zoom": {
                "fit": "Fit",
                "zoom_in": "Zoom in",
                "zoom_out": "Zoom out",
            },
        },
        "execution_panel": {
            "aria_label": "Execution preview",
            "context_label": "Context",
            "description": "Test the selected node here, or use the toolbar to run the full workflow.",
            "empty": "Run the selected node to inspect output, trace, and context here.",
            "output_label": "Output",
            "title": "Run preview",
            "trace_label": "Trace",
        },
        "settings_panel": {
            "aria_label": "Node settings",
            "close_label": "Close node settings",
            "title": "Node settings",
        },
        "toolbar": {
            "add_node": "Add node",
            "back_label": "Workflow",
            "run_workflow": "Run workflow",
            "settings": "Settings",
        },
    },
    "node_selection": WORKFLOW_NODE_SELECTION_PRESENTATION,
    "execution": {
        "default_status": {
            "badge_class": "text-bg-secondary",
            "label": "Idle",
        },
        "inspector": {
            "overview": {
                "active_nodes": "Active nodes",
                "failed_nodes": "Failed nodes",
                "idle_value": "None",
                "last_completed_node": "Last completed",
                "mode": "Mode",
                "selected_node": "Selected node",
                "skipped_nodes": "Skipped nodes",
                "step_count": "Step count",
                "trigger_mode": "Trigger mode",
                "workflow_version": "Workflow version",
            },
            "steps": {
                "empty": "No completed steps yet.",
                "next_node_label": "Next node",
                "result_label": "Result",
                "title": "Step details",
            },
            "tabs": {
                "context": "Context",
                "input": "Input",
                "output": "Output",
                "overview": "Overview",
                "steps": "Steps",
                "trace": "Trace",
            },
        },
        "messages": {
            "execution_failed": "Execution failed.",
            "poll_timeout": "Workflow run polling timed out.",
            "status_fetch_failed": "Unable to fetch run status.",
        },
        "result_labels": {
            "node_run": "Node run",
            "workflow_run": "Workflow run",
        },
        "run_button": {
            "idle": "Run node",
            "running": "Running node",
        },
        "running_status": {
            "node": "Running node",
            "workflow": "Running workflow",
        },
        "statuses": {
            "failed": {
                "badge_class": "text-bg-danger",
                "label": "Failed",
            },
            "pending": {
                "badge_class": "text-bg-secondary",
                "label": "Queued",
            },
            "running": {
                "badge_class": "text-bg-primary",
                "label": "Running",
            },
            "succeeded": {
                "badge_class": "text-bg-success",
                "label": "Completed",
            },
        },
    },
    "settings": {
        "controls": {
            "expression_hint": (
                "Use template syntax like {{ trigger.payload.ticket_id }} or "
                "{{ llm.response.text }}."
            ),
            "required_badge": "Required",
            "mode_expression": "Expression",
            "mode_static": "Static",
            "mode_suffix": "mode",
            "select_placeholder": "Select",
        },
        "empty": "No editable settings for this node yet.",
        "groups": {
            "advanced": {
                "description": "Provider, routing, and runtime controls for this node.",
                "title": "Other settings",
            },
            "identity": {
                "description": "Rename the node so the graph reads clearly.",
                "fields": {
                    "node_name": "Node name",
                },
                "title": "Identity",
            },
            "input": {
                "description": (
                    "Choose Static or Expression for each input, then map trigger payload "
                    "and earlier node outputs."
                ),
                "title": "Pass data in",
            },
            "connection": {
                "description": "Choose which reusable connection this node should use.",
                "title": "Connection",
            },
            "overview": {
                "description": (
                    "Keep the graph readable and make the node’s role obvious at a glance."
                ),
                "fields": {
                    "node_id": "Node id",
                    "type": "Type",
                },
                "title": "Node overview",
            },
            "result": {
                "description": "Choose where this node should read or write workflow context values.",
                "title": "Save result",
            },
            "docs": {
                "description": "Review the node contract, app ownership, and compatibility details.",
                "fields": {
                    "app": "App",
                    "capabilities": "Capabilities",
                    "connection_type": "Connection type",
                    "kind": "Kind",
                    "operation": "Operation",
                    "resource": "Resource",
                    "type": "Type",
                },
                "title": "Docs",
            },
        },
    },
}


def _stringify_option_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _serialize_field_option(option: ParameterOptionDefinition) -> dict[str, str]:
    return {
        "label": option.label,
        "value": _stringify_option_value(option.value),
    }


def _build_boolean_options() -> list[dict[str, str]]:
    return [
        {"label": "True", "value": "true"},
        {"label": "False", "value": "false"},
    ]


def _build_visible_when(parameter: ParameterDefinition) -> dict[str, list[str]] | None:
    if not parameter.show_if:
        return None

    normalized: dict[str, list[str]] = {}
    for condition in parameter.show_if:
        for key, value in condition.items():
            if isinstance(value, (list, tuple)):
                normalized[key] = [_stringify_option_value(item) for item in value]
            else:
                normalized[key] = [_stringify_option_value(value)]
    return normalized or None


def _field_type_for_parameter(parameter: ParameterDefinition) -> str:
    if isinstance(parameter.field_type, str) and parameter.field_type.strip():
        return parameter.field_type.strip()
    if parameter.value_type == "node_ref":
        return "node_target"
    if parameter.options or parameter.value_type == "boolean":
        return "select"
    if parameter.value_type in {"json", "text"}:
        return "textarea"
    return "text"


def _serialize_parameter(parameter: ParameterDefinition) -> dict[str, Any]:
    options = [_serialize_field_option(option) for option in parameter.options]
    if parameter.value_type == "boolean" and not options:
        options = _build_boolean_options()

    payload = {
        "key": parameter.key,
        "label": parameter.label,
        "description": parameter.description,
        "required": parameter.required,
        "type": _field_type_for_parameter(parameter),
        "help_text": parameter.help_text or parameter.description,
        "placeholder": parameter.placeholder,
        "value_type": parameter.value_type,
    }
    binding = parameter.binding
    if binding is None:
        if parameter.value_type == "node_ref":
            binding = "path"
        elif parameter.value_type in {"text", "json"}:
            binding = "template"
    if binding is not None:
        payload["binding"] = binding
    visible_when = _build_visible_when(parameter)
    if visible_when:
        payload["visible_when"] = visible_when
    if options:
        payload["options"] = options
    if parameter.ui_group is not None:
        payload["ui_group"] = parameter.ui_group
    if parameter.options_by_field:
        payload["options_by_field"] = {
            config_key: {
                config_value: [_serialize_field_option(option) for option in options]
                for config_value, options in option_map.items()
            }
            for config_key, option_map in parameter.options_by_field.items()
        }
    if parameter.rows is not None:
        payload["rows"] = parameter.rows
    elif parameter.value_type in {"json", "text"}:
        payload["rows"] = 4
    return payload


def _serialize_default_value(value: Any) -> Any:
    return value


def _default_config_for_node(node: CatalogNodeDefinition) -> dict[str, Any]:
    config: dict[str, Any] = dict(node.config_defaults)
    for connection_slot in node.connection_slots:
        config[connection_slot.key] = ""
    for parameter in node.parameter_schema:
        if parameter.default is not None:
            config[parameter.key] = _serialize_default_value(parameter.default)
    return config


def _catalog_section_for_node(node: CatalogNodeDefinition) -> str:
    if isinstance(node.catalog_section, str) and node.catalog_section.strip():
        return node.catalog_section.strip()
    if node.mode == "trigger" or node.kind == "trigger":
        return "triggers"
    if node.integration_id == "core" and node.id == "core.set":
        return "data"
    if node.integration_id == "core":
        return "flow"
    return "apps"


def _ui_kind_for_node(node: CatalogNodeDefinition) -> str:
    if node.mode == "trigger" or node.kind == "trigger":
        return "trigger"
    if node.kind == "agent":
        return "agent"
    if node.kind == "output":
        return "response"
    if node.kind == "control":
        return "condition"
    return "tool"


def _category_for_ui_kind(kind: str) -> str:
    if kind == "trigger":
        return "entry_point"
    if kind == "condition":
        return "control_flow"
    if kind == "response":
        return "outcome"
    return "processing"


def _group_for_node(*, app_id: str | None, catalog_section: str, ui_kind: str) -> str:
    normalized_app_id = (app_id or "").strip()
    is_external_app = normalized_app_id not in {"", "builtins", "core"}

    if ui_kind == "trigger":
        return "app_trigger" if is_external_app else "trigger"
    if ui_kind == "agent":
        return "ai"
    if is_external_app:
        return "app_action"
    if catalog_section == "data":
        return "data"
    if ui_kind == "condition":
        return "flow"
    return "core"


def _app_metadata_for_node(node: CatalogNodeDefinition) -> dict[str, str]:
    if all(
        isinstance(value, str) and value.strip()
        for value in (node.app_id, node.app_label, node.app_description, node.app_icon)
    ):
        return {
            "app_description": node.app_description.strip(),
            "app_icon": node.app_icon.strip(),
            "app_id": node.app_id.strip(),
            "app_label": node.app_label.strip(),
        }

    if node.integration_id == "core":
        return {
            "app_description": "Core workflow control and orchestration nodes.",
            "app_icon": "mdi-toy-brick-outline",
            "app_id": "core",
            "app_label": "Core",
        }

    app = get_workflow_catalog()["integration_apps"][node.integration_id]
    return {
        "app_description": app.description,
        "app_icon": app.icon,
        "app_id": app.id,
        "app_label": app.label,
    }


def serialize_catalog_node_for_designer(node: CatalogNodeDefinition) -> dict[str, Any]:
    ui_kind = _ui_kind_for_node(node)
    catalog_section = _catalog_section_for_node(node)
    app_metadata = _app_metadata_for_node(node)
    payload = {
        **app_metadata,
        "group": _group_for_node(
            app_id=app_metadata["app_id"],
            catalog_section=catalog_section,
            ui_kind=ui_kind,
        ),
        "capabilities": sorted(node.capabilities),
        "catalog_section": catalog_section,
        "category": _category_for_ui_kind(ui_kind),
        "config": _default_config_for_node(node),
        "connection_slots": [slot.serialize() for slot in node.connection_slots],
        "connection_type": node.connection_type,
        "output_ports": [port.serialize() for port in node.output_ports],
        "description": node.description,
        "fields": [_serialize_parameter(parameter) for parameter in node.parameter_schema],
        "icon": node.icon,
        "kind": ui_kind,
        "label": node.label,
        "mode": node.mode,
        "operation": node.operation,
        "resource": node.resource,
        "tags": list(node.tags),
        "type": node.id,
        "typeVersion": 1,
    }
    if CAPABILITY_AGENT_MODEL in node.capabilities:
        payload["is_model"] = True
    return payload

def build_workflow_catalog_payload() -> dict[str, Any]:
    registry = get_workflow_catalog()
    integration_node_ids = {
        node.id
        for app in registry["integration_apps"].values()
        for node in app.nodes
    }
    ordered_nodes: list[CatalogNodeDefinition] = [
        *registry["core_nodes"].values(),
        *(
            node
            for app in sorted(registry["integration_apps"].values(), key=lambda item: (item.sort_order, item.id))
            for node in app.nodes
        ),
        *sorted(
            (
                node
                for node_id, node in registry["node_types"].items()
                if node_id not in registry["core_nodes"]
                and node_id not in integration_node_ids
            ),
            key=lambda node: (
                _catalog_section_for_node(node),
                (node.app_id or node.integration_id),
                node.id,
            ),
        ),
    ]
    return {
        "groups": [dict(item) for item in WORKFLOW_CATALOG_GROUPS],
        "definitions": [serialize_catalog_node_for_designer(node) for node in ordered_nodes],
        "presentation": WORKFLOW_DESIGNER_PRESENTATION,
        "sections": [WORKFLOW_NODE_CATALOG_SECTIONS[section_id] for section_id in WORKFLOW_NODE_CATALOG_SECTION_ORDER],
    }
