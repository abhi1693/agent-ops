from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.catalog.services import get_catalog_node


def prepare_catalog_webhook_request(*, workflow, node: dict, request):
    node_type = node.get("type")
    node_definition = get_catalog_node(node_type)
    if node_definition is None:
        raise ValidationError({"trigger": f'Unsupported trigger node type "{node_type}".'})
    if node_definition.kind != "trigger":
        raise ValidationError({"trigger": f'Node type "{node_definition.id}" does not support webhook delivery.'})
    if node_definition.webhook_request_preparer is None:
        raise ValidationError({"trigger": f'Node type "{node_definition.id}" does not support webhook delivery.'})
    return node_definition.webhook_request_preparer(workflow=workflow, node=node, request=request)


__all__ = ("prepare_catalog_webhook_request",)
