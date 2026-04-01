from __future__ import annotations

import hmac
import json
from typing import Any

from django.core.exceptions import ValidationError

from automation.auth import resolve_workflow_secret_ref

from .base import WorkflowTriggerRequestContext


def get_request_meta(request) -> dict[str, Any]:
    return {
        "source_ip": request.META.get("REMOTE_ADDR"),
        "content_type": request.META.get("CONTENT_TYPE"),
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }


def parse_json_body(context: WorkflowTriggerRequestContext) -> dict[str, Any]:
    if not context.body:
        return {}
    try:
        parsed = json.loads(context.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError({"trigger": "Webhook request body must be valid JSON."}) from exc
    if not isinstance(parsed, dict):
        raise ValidationError({"trigger": "Webhook request body must decode to a JSON object."})
    return parsed


def validate_shared_secret_header(context: WorkflowTriggerRequestContext) -> dict[str, str]:
    header_name = context.config.get("secret_header", "X-AgentOps-Webhook-Secret")
    header_value = context.request.headers.get(header_name)
    if not header_value:
        raise ValidationError({"trigger": f'Missing required webhook secret header "{header_name}".'})

    secret_name = context.config.get("secret_name")
    secret = resolve_workflow_secret_ref(
        context.workflow,
        secret_name=secret_name,
        secret_group_id=context.config.get("secret_group_id"),
        error_field="trigger",
    )
    expected_value = secret.get_value(obj=context.workflow)
    if not isinstance(expected_value, str) or not expected_value:
        raise ValidationError({"trigger": f'Secret "{secret.name}" must resolve to a non-empty string.'})
    if not hmac.compare_digest(header_value, expected_value):
        raise ValidationError({"trigger": "Webhook secret validation failed."})
    return {"name": secret.name, "provider": secret.provider, "header_name": header_name}
