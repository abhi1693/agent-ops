from __future__ import annotations

import base64
import hmac
from typing import Any

import jwt
from django.core.exceptions import ValidationError

from automation.catalog.connections import resolve_workflow_connection_fields
from automation.catalog.capabilities import CAPABILITY_TRIGGER_WEBHOOK
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ConnectionSlotDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.catalog.execution import get_runtime_connection_slot_value
from automation.core_nodes._triggers import build_trigger_result
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.triggers.base import WorkflowTriggerRequestContext
from automation.triggers.webhook_utils import get_request_meta, parse_json_body

_AUTHENTICATION_NONE = "none"
_AUTHENTICATION_BASIC_AUTH = "basicAuth"
_AUTHENTICATION_HEADER_AUTH = "headerAuth"
_AUTHENTICATION_JWT_AUTH = "jwtAuth"
_AUTHENTICATION_HEADER_SECRET_LEGACY = "header_secret"
_RESPONSE_MODE_IMMEDIATELY = "immediately"
_SUPPORTED_AUTHENTICATION_TYPES = (
    _AUTHENTICATION_NONE,
    _AUTHENTICATION_BASIC_AUTH,
    _AUTHENTICATION_HEADER_AUTH,
    _AUTHENTICATION_JWT_AUTH,
)
_SUPPORTED_HTTP_METHODS = ("DELETE", "GET", "PATCH", "POST", "PUT")
_SUPPORTED_RESPONSE_MODES = (_RESPONSE_MODE_IMMEDIATELY,)
_WEBHOOK_BASIC_AUTH_CONNECTION_TYPES = ("webhook.basic_auth",)
_WEBHOOK_HEADER_AUTH_CONNECTION_TYPES = ("webhook.header_auth", "webhook.shared_secret")
_WEBHOOK_JWT_AUTH_CONNECTION_TYPES = ("webhook.jwt_auth",)
_WEBHOOK_CONNECTION_SLOT_KEYS = {
    _AUTHENTICATION_BASIC_AUTH: "basic_auth_connection_id",
    _AUTHENTICATION_HEADER_AUTH: "connection_id",
    _AUTHENTICATION_JWT_AUTH: "jwt_auth_connection_id",
}
_AUTHENTICATION_ALIASES = {
    "none": _AUTHENTICATION_NONE,
    "basicauth": _AUTHENTICATION_BASIC_AUTH,
    "basic_auth": _AUTHENTICATION_BASIC_AUTH,
    "headerauth": _AUTHENTICATION_HEADER_AUTH,
    "header_secret": _AUTHENTICATION_HEADER_AUTH,
    "jwtauth": _AUTHENTICATION_JWT_AUTH,
    "jwt_auth": _AUTHENTICATION_JWT_AUTH,
}


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
        return _AUTHENTICATION_ALIASES.get(authentication.strip().lower(), authentication.strip())
    return _AUTHENTICATION_NONE


def _get_response_mode(config: dict) -> str:
    response_mode = config.get("response_mode")
    if isinstance(response_mode, str) and response_mode.strip():
        return response_mode.strip().lower()
    return _RESPONSE_MODE_IMMEDIATELY


def _build_webhook_runtime(*, workflow, node: dict, config: dict) -> WorkflowNodeExecutionContext:
    return WorkflowNodeExecutionContext(
        workflow=workflow,
        node=node,
        config=config,
        next_node_id=None,
        connected_nodes_by_port={},
        context={},
        secret_paths=set(),
        secret_values=[],
        render_template=lambda template, template_context: template,
        get_path_value=lambda data, path: None,
        set_path_value=lambda data, path, value: None,
        evaluate_condition=lambda operator, left, right: False,
    )


def _get_connection_slot_key(authentication: str) -> str:
    return _WEBHOOK_CONNECTION_SLOT_KEYS.get(authentication, "connection_id")


def _resolve_webhook_connection(
    *,
    runtime: WorkflowNodeExecutionContext,
    authentication: str,
    allowed_connection_types: tuple[str, ...],
):
    resolved = resolve_workflow_connection_fields(
        runtime,
        connection_id=get_runtime_connection_slot_value(runtime, slot_key=_get_connection_slot_key(authentication)),
        expected_connection_type=None,
    )
    if resolved.connection.connection_type not in allowed_connection_types:
        allowed = ", ".join(allowed_connection_types)
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{resolved.connection.name}" must use one of these credential types: {allowed}.'
                )
            }
        )
    return resolved


def _parse_basic_auth_header(header_value: str) -> tuple[str, str] | None:
    if not isinstance(header_value, str) or not header_value.startswith("Basic "):
        return None
    encoded_value = header_value[6:].strip()
    if not encoded_value:
        return None
    try:
        decoded_value = base64.b64decode(encoded_value.encode("ascii"), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in decoded_value:
        return None
    username, password = decoded_value.split(":", 1)
    return username, password


def _resolve_header_auth_fields(resolved) -> tuple[str, str]:
    header_name = str(resolved.values.get("name") or resolved.values.get("header_name") or "").strip()
    expected_value = resolved.values.get("value")
    if not isinstance(expected_value, str) or not expected_value:
        expected_value = resolved.values.get("secret_value")

    if not header_name:
        field_key = "name" if resolved.connection.connection_type == "webhook.header_auth" else "header_name"
        raise ValidationError(
            {"trigger": f'Connection "{resolved.connection.name}" must include field "{field_key}".'}
        )
    if not isinstance(expected_value, str) or not expected_value:
        field_key = "value" if resolved.connection.connection_type == "webhook.header_auth" else "secret_value"
        raise ValidationError(
            {"trigger": f'Connection "{resolved.connection.name}" must include field "{field_key}".'}
        )

    return header_name, expected_value


def _validate_basic_auth_request(*, request, resolved) -> None:
    username = str(resolved.values.get("username") or "").strip()
    expected_password = resolved.values.get("password")

    if not username:
        raise ValidationError({"trigger": f'Connection "{resolved.connection.name}" must include field "username".'})
    if not isinstance(expected_password, str) or not expected_password:
        raise ValidationError({"trigger": f'Connection "{resolved.connection.name}" must include field "password".'})

    provided_auth = _parse_basic_auth_header(request.headers.get("Authorization", ""))
    if provided_auth is None:
        raise ValidationError({"trigger": 'Missing required Authorization header for "Basic Auth".'})

    provided_username, provided_password = provided_auth
    if not hmac.compare_digest(provided_username, username) or not hmac.compare_digest(
        provided_password, expected_password
    ):
        raise ValidationError({"trigger": "Webhook basic-auth validation failed."})


def _validate_header_auth_request(*, request, resolved) -> None:
    header_name, expected_value = _resolve_header_auth_fields(resolved)
    received_value = request.headers.get(header_name)
    if not isinstance(received_value, str) or not received_value:
        raise ValidationError({"trigger": f'Missing required webhook auth header "{header_name}".'})
    if not hmac.compare_digest(received_value, expected_value):
        raise ValidationError({"trigger": "Webhook header-auth validation failed."})


def _validate_jwt_auth_request(*, request, resolved) -> dict[str, Any]:
    key_type = str(resolved.values.get("key_type") or "passphrase").strip() or "passphrase"
    algorithm = str(resolved.values.get("algorithm") or "HS256").strip() or "HS256"
    auth_header = request.headers.get("Authorization", "")
    if not isinstance(auth_header, str) or not auth_header.startswith("Bearer "):
        raise ValidationError({"trigger": 'Missing Bearer token in Authorization header for "JWT Auth".'})
    token = auth_header[7:].strip()
    if not token:
        raise ValidationError({"trigger": 'Missing Bearer token in Authorization header for "JWT Auth".'})

    decode_kwargs: dict[str, Any] = {"algorithms": [algorithm]}
    if algorithm == "none":
        secret_or_public_key = None
        decode_kwargs["options"] = {"verify_signature": False}
    elif key_type == "passphrase":
        secret_or_public_key = resolved.values.get("secret")
        if not isinstance(secret_or_public_key, str) or not secret_or_public_key:
            raise ValidationError({"trigger": f'Connection "{resolved.connection.name}" must include field "secret".'})
    elif key_type == "pemKey":
        secret_or_public_key = resolved.values.get("public_key")
        if not isinstance(secret_or_public_key, str) or not secret_or_public_key:
            raise ValidationError(
                {"trigger": f'Connection "{resolved.connection.name}" must include field "public_key".'}
            )
    else:
        raise ValidationError({"trigger": f'Connection "{resolved.connection.name}" uses unsupported key type "{key_type}".'})

    try:
        payload = jwt.decode(token, secret_or_public_key, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise ValidationError({"trigger": f"Webhook JWT validation failed: {exc}."}) from exc

    if not isinstance(payload, dict):
        raise ValidationError({"trigger": "Webhook JWT validation failed: token payload must be an object."})
    return payload

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
    if authentication != _AUTHENTICATION_NONE and config.get(_get_connection_slot_key(authentication)) in (None, ""):
        raise ValidationError(
            {
                "definition": (
                    f'Node "{node_id}" must define config.{_get_connection_slot_key(authentication)} when webhook authentication is enabled.'
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
    resolved = None
    jwt_payload = None
    if authentication != _AUTHENTICATION_NONE:
        runtime = _build_webhook_runtime(workflow=workflow, node=node, config=config)
        if authentication == _AUTHENTICATION_BASIC_AUTH:
            resolved = _resolve_webhook_connection(
                runtime=runtime,
                authentication=authentication,
                allowed_connection_types=_WEBHOOK_BASIC_AUTH_CONNECTION_TYPES,
            )
            _validate_basic_auth_request(request=request, resolved=resolved)
        elif authentication == _AUTHENTICATION_HEADER_AUTH:
            resolved = _resolve_webhook_connection(
                runtime=runtime,
                authentication=authentication,
                allowed_connection_types=_WEBHOOK_HEADER_AUTH_CONNECTION_TYPES,
            )
            _validate_header_auth_request(request=request, resolved=resolved)
        elif authentication == _AUTHENTICATION_JWT_AUTH:
            resolved = _resolve_webhook_connection(
                runtime=runtime,
                authentication=authentication,
                allowed_connection_types=_WEBHOOK_JWT_AUTH_CONNECTION_TYPES,
            )
            jwt_payload = _validate_jwt_auth_request(request=request, resolved=resolved)

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
    if resolved is not None:
        metadata["connection"] = {
            "id": str(resolved.connection.pk),
            "name": resolved.connection.name,
            "type": resolved.connection.connection_type,
        }
    if authentication == _AUTHENTICATION_HEADER_AUTH:
        secret_meta = resolved.secret_metas.get("value") or resolved.secret_metas.get("secret_value")
        if secret_meta is not None:
            metadata["secret"] = secret_meta
    if authentication == _AUTHENTICATION_JWT_AUTH and jwt_payload is not None:
        metadata["jwt_payload"] = jwt_payload

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
    connection_slots=(
        ConnectionSlotDefinition(
            key="basic_auth_connection_id",
            label="Credential for Basic Auth",
            allowed_connection_types=_WEBHOOK_BASIC_AUTH_CONNECTION_TYPES,
            required=False,
            description="Reusable Basic Auth credential used when webhook authentication is enabled.",
            visible_when={"authentication": (_AUTHENTICATION_BASIC_AUTH,)},
        ),
        ConnectionSlotDefinition(
            key="connection_id",
            label="Credential for Header Auth",
            allowed_connection_types=_WEBHOOK_HEADER_AUTH_CONNECTION_TYPES,
            required=False,
            description="Reusable Header Auth credential used when webhook authentication is enabled.",
            visible_when={"authentication": (_AUTHENTICATION_HEADER_AUTH, _AUTHENTICATION_HEADER_SECRET_LEGACY)},
        ),
        ConnectionSlotDefinition(
            key="jwt_auth_connection_id",
            label="Credential for JWT Auth",
            allowed_connection_types=_WEBHOOK_JWT_AUTH_CONNECTION_TYPES,
            required=False,
            description="Reusable JWT Auth credential used when webhook authentication is enabled.",
            visible_when={"authentication": (_AUTHENTICATION_JWT_AUTH,)},
        ),
    ),
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
                    value=_AUTHENTICATION_BASIC_AUTH,
                    label="Basic Auth",
                ),
                ParameterOptionDefinition(
                    value=_AUTHENTICATION_HEADER_AUTH,
                    label="Header Auth",
                ),
                ParameterOptionDefinition(
                    value=_AUTHENTICATION_JWT_AUTH,
                    label="JWT Auth",
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
    ),
    tags=("webhook", "http"),
)


__all__ = (
    "NODE_DEFINITION",
    "get_configured_webhook_path",
    "normalize_webhook_path",
)
