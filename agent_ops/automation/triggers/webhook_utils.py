from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ValidationError

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
