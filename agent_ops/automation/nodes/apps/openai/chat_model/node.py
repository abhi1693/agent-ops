from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
)
from automation.nodes.apps.openai.client import validate_openai_chat_model_config


def _validate_openai_chat_model_node(
    config: dict,
    node_id: str,
    outgoing_targets: list[str],
    node_ids: set[str],
) -> None:
    del outgoing_targets, node_ids
    validate_openai_chat_model_config(config, node_id)


def _execute_openai_chat_model_node(runtime) -> WorkflowNodeExecutionResult:
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            "model": runtime.config.get("model"),
            "base_url": runtime.config.get("base_url"),
            "api_type": "openai",
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_openai_chat_model_node,
    executor=_execute_openai_chat_model_node,
)
