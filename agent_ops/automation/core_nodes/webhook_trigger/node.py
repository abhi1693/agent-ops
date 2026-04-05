from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.catalog.capabilities import CAPABILITY_TRIGGER_WEBHOOK
from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition, ParameterOptionDefinition
from automation.core_nodes._triggers import build_trigger_result
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.triggers.base import WorkflowTriggerRequestContext
from automation.triggers.webhook_utils import (
    get_request_meta,
    parse_json_body,
    validate_shared_secret_header,
)

_DEFAULT_SECRET_HEADER = "X-AgentOps-Webhook-Secret"
_AUTHENTICATION_NONE = "none"
_AUTHENTICATION_SECRET_HEADER = "secret_header"
_RESPONSE_MODE_IMMEDIATELY = "immediately"
_SUPPORTED_AUTHENTICATION_TYPES = (
    _AUTHENTICATION_NONE,
    _AUTHENTICATION_SECRET_HEADER,
)
_SUPPORTED_HTTP_METHODS = ("DELETE", "GET", "PATCH", "POST", "PUT")
_SUPPORTED_RESPONSE_MODES = (_RESPONSE_MODE_IMMEDIATELY,)


def normalize_webhook_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "/".join(segment for segment in value.strip().strip("/").split("/") if segment)


def get_configured_webhook_path(config: dict) -> str:
    return normalize_webhook_path(config.get("path"))


def _execute_webhook_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return build_trigger_result(runtime)


def _get_authentication_mode(config: dict) -> str:
    authentication = config.get("authentication")
    if isinstance(authentication, str) and authentication.strip():
        return authentication.strip().lower()
    return _AUTHENTICATION_NONE


def _get_response_mode(config: dict) -> str:
    response_mode = config.get("response_mode")
    if isinstance(response_mode, str) and response_mode.strip():
        return response_mode.strip().lower()
    return _RESPONSE_MODE_IMMEDIATELY

def _validate_webhook_trigger(**kwargs) -> None:
    config = kwargs["config"]
    node_id = kwargs["node_id"]

    raw_path = config.get("path")
    if raw_path not in (None, "") and (not isinstance(raw_path, str) or not raw_path.strip()):
        raise ValidationError({"definition": f'Node "{node_id}" config.path must be a non-empty string.'})
    normalized_path = get_configured_webhook_path(config)
    if "?" in normalized_path or "#" in normalized_path:
        raise ValidationError({"definition": f'Node "{node_id}" config.path cannot contain query strings or fragments.'})
    if any(character.isspace() for character in normalized_path):
        raise ValidationError({"definition": f'Node "{node_id}" config.path cannot contain whitespace.'})

    method = str(config.get("http_method") or "POST").strip().upper()
    if method not in _SUPPORTED_HTTP_METHODS:
        supported_methods = ", ".join(_SUPPORTED_HTTP_METHODS)
        raise ValidationError(
            {
                "definition": f'Node "{node_id}" config.http_method must be one of: {supported_methods}.'
            }
        )

    authentication = _get_authentication_mode(config)
    if authentication not in _SUPPORTED_AUTHENTICATION_TYPES:
        supported_types = ", ".join(_SUPPORTED_AUTHENTICATION_TYPES)
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" config.authentication must be one of: {supported_types}.'
                )
            }
        )

    response_mode = _get_response_mode(config)
    if response_mode not in _SUPPORTED_RESPONSE_MODES:
        supported_modes = ", ".join(_SUPPORTED_RESPONSE_MODES)
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" config.response_mode must be one of: {supported_modes}.'
                )
            }
        )

    secret_name = config.get("secret_name")
    if authentication == _AUTHENTICATION_SECRET_HEADER and (
        not isinstance(secret_name, str) or not secret_name.strip()
    ):
        raise ValidationError({"definition": f'Node "{node_id}" must define config.secret_name.'})
    if secret_name not in (None, "") and (not isinstance(secret_name, str) or not secret_name.strip()):
        raise ValidationError({"definition": f'Node "{node_id}" config.secret_name must be a non-empty string.'})

    secret_header = config.get("secret_header")
    if secret_header not in (None, "") and (not isinstance(secret_header, str) or not secret_header.strip()):
        raise ValidationError({"definition": f'Node "{node_id}" config.secret_header must be a non-empty string.'})

    secret_group_id = config.get("secret_group_id")
    if secret_group_id in (None, ""):
        return
    if isinstance(secret_group_id, int):
        return
    if isinstance(secret_group_id, str) and secret_group_id.strip().isdigit():
        return
    raise ValidationError({"definition": f'Node "{node_id}" config.secret_group_id must be a numeric secret group ID.'})


def _prepare_webhook_request(*, workflow, node: dict, request) -> tuple[str, dict, dict]:
    config = node.get("config") or {}
    expected_method = str(config.get("http_method") or "POST").strip().upper()
    configured_path = get_configured_webhook_path(config)
    request_webhook_path = normalize_webhook_path(
        getattr(getattr(request, "resolver_match", None), "kwargs", {}).get("webhook_path")
    )
    authentication = _get_authentication_mode(config)
    response_mode = _get_response_mode(config)
    if response_mode not in _SUPPORTED_RESPONSE_MODES:
        response_mode = _RESPONSE_MODE_IMMEDIATELY
    request_method = request.method.upper()
    if request_webhook_path != configured_path:
        expected_path_label = f'/{configured_path}' if configured_path else "/"
        request_path_label = f'/{request_webhook_path}' if request_webhook_path else "/"
        raise ValidationError(
            {
                "trigger": (
                    f'Webhook path "{request_path_label}" does not match configured path "{expected_path_label}".'
                )
            }
        )
    if request_method != expected_method:
        raise ValidationError(
            {
                "trigger": f'Webhook method "{request_method}" does not match configured method "{expected_method}".'
            }
        )

    context = WorkflowTriggerRequestContext(
        workflow=workflow,
        node=node,
        config=config,
        request=request,
        body=request.body,
    )
    payload = parse_json_body(context)
    metadata = {
        **get_request_meta(request),
        "source": "webhook",
        "method": request_method,
        "path": request.path,
        "webhook_path": request_webhook_path,
        "query_params": {key: request.GET.getlist(key) for key in request.GET},
        "authentication": authentication,
        "response_mode": response_mode,
    }

    if authentication == _AUTHENTICATION_SECRET_HEADER:
        metadata["secret"] = validate_shared_secret_header(context)

    return node["type"], payload, metadata


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.webhook_trigger",
    integration_id="core",
    mode="core",
    kind="trigger",
    label="Webhook",
    description="Starts a workflow when an HTTP request is sent to the workflow webhook endpoint.",
    icon="mdi-webhook",
    default_name="Webhook",
    node_group=("trigger",),
    capabilities=frozenset({CAPABILITY_TRIGGER_WEBHOOK}),
    runtime_validator=_validate_webhook_trigger,
    runtime_executor=_execute_webhook_trigger,
    webhook_request_preparer=_prepare_webhook_request,
    parameter_schema=(
        ParameterDefinition(
            key="http_method",
            label="HTTP Method",
            value_type="string",
            required=True,
            default="POST",
            description="HTTP method that must be used for webhook deliveries.",
            field_type="select",
            options=tuple(
                ParameterOptionDefinition(value=method, label=method)
                for method in _SUPPORTED_HTTP_METHODS
            ),
            no_data_expression=True,
            ui_group="input",
        ),
        ParameterDefinition(
            key="path",
            label="Path",
            value_type="string",
            required=False,
            default="",
            description="Optional webhook path suffix appended to the workflow webhook base URL.",
            placeholder="orders/new",
            no_data_expression=True,
            ui_group="input",
        ),
        ParameterDefinition(
            key="authentication",
            label="Authentication",
            value_type="string",
            required=True,
            default=_AUTHENTICATION_NONE,
            description="Choose how inbound webhook requests are authenticated.",
            field_type="select",
            options=(
                ParameterOptionDefinition(
                    value=_AUTHENTICATION_NONE,
                    label="None",
                ),
                ParameterOptionDefinition(
                    value=_AUTHENTICATION_SECRET_HEADER,
                    label="Secret header",
                    description="Validate a request header against a workflow secret reference.",
                ),
            ),
            no_data_expression=True,
            ui_group="input",
        ),
        ParameterDefinition(
            key="response_mode",
            label="Respond",
            value_type="string",
            required=True,
            default=_RESPONSE_MODE_IMMEDIATELY,
            description="Return a queued run response as soon as the webhook request is accepted.",
            field_type="select",
            options=(
                ParameterOptionDefinition(
                    value=_RESPONSE_MODE_IMMEDIATELY,
                    label="Immediately",
                    description="Return HTTP 202 Accepted after the workflow run is queued.",
                ),
            ),
            no_data_expression=True,
            ui_group="input",
        ),
        ParameterDefinition(
            key="secret_name",
            label="Secret",
            value_type="string",
            required=False,
            description="Workflow secret name used to validate the incoming shared-secret header.",
            placeholder="WEBHOOK_SHARED_SECRET",
            no_data_expression=True,
            display_options={"show": {"authentication": (_AUTHENTICATION_SECRET_HEADER,)}},
            ui_group="advanced",
        ),
        ParameterDefinition(
            key="secret_group_id",
            label="Secret Group Override",
            value_type="integer",
            required=False,
            description="Optional secret group ID to use instead of the workflow's default secret group.",
            placeholder="12",
            no_data_expression=True,
            display_options={"show": {"authentication": (_AUTHENTICATION_SECRET_HEADER,)}},
            ui_group="advanced",
        ),
        ParameterDefinition(
            key="secret_header",
            label="Header Name",
            value_type="string",
            required=False,
            default=_DEFAULT_SECRET_HEADER,
            description="Header name that carries the shared secret when secret-header authentication is enabled.",
            placeholder=_DEFAULT_SECRET_HEADER,
            no_data_expression=True,
            display_options={"show": {"authentication": (_AUTHENTICATION_SECRET_HEADER,)}},
            ui_group="advanced",
        ),
    ),
    tags=("webhook", "http"),
)


__all__ = (
    "NODE_DEFINITION",
    "get_configured_webhook_path",
    "normalize_webhook_path",
)
