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
_SUPPORTED_HTTP_METHODS = ("DELETE", "GET", "PATCH", "POST", "PUT")


def _execute_webhook_trigger(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    return build_trigger_result(runtime)


def _validate_webhook_trigger(**kwargs) -> None:
    config = kwargs["config"]
    node_id = kwargs["node_id"]

    method = str(config.get("http_method") or "POST").strip().upper()
    if method not in _SUPPORTED_HTTP_METHODS:
        supported_methods = ", ".join(_SUPPORTED_HTTP_METHODS)
        raise ValidationError(
            {
                "definition": f'Node "{node_id}" config.http_method must be one of: {supported_methods}.'
            }
        )

    secret_name = config.get("secret_name")
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
    request_method = request.method.upper()
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
        "query_params": {key: request.GET.getlist(key) for key in request.GET},
    }

    if config.get("secret_name"):
        metadata["secret"] = validate_shared_secret_header(context)
    elif config.get("secret_header") and config.get("secret_header") != _DEFAULT_SECRET_HEADER:
        metadata["secret_header"] = str(config.get("secret_header")).strip()

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
            key="secret_name",
            label="Secret Name",
            value_type="string",
            required=False,
            description="Optional workflow secret name used to validate a shared-secret header.",
            placeholder="WEBHOOK_SHARED_SECRET",
            no_data_expression=True,
            ui_group="advanced",
        ),
        ParameterDefinition(
            key="secret_group_id",
            label="Secret Group ID",
            value_type="integer",
            required=False,
            description="Optional secret group override when the workflow secret group should not be used.",
            placeholder="12",
            no_data_expression=True,
            ui_group="advanced",
        ),
        ParameterDefinition(
            key="secret_header",
            label="Secret Header",
            value_type="string",
            required=False,
            default=_DEFAULT_SECRET_HEADER,
            description="Header name that carries the shared secret when secret validation is enabled.",
            placeholder=_DEFAULT_SECRET_HEADER,
            no_data_expression=True,
            ui_group="advanced",
        ),
    ),
    tags=("webhook", "http"),
)


__all__ = ("NODE_DEFINITION",)
