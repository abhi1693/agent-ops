from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    WorkflowNodeWebhookContext,
)
from automation.tools.base import (
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
)
from automation.triggers.base import (
    WorkflowTriggerDefinition,
    WorkflowTriggerRequestContext,
)


def validate_tool_definition_config(
    tool_definition: WorkflowToolDefinition,
    *,
    config: dict,
    node_id: str,
) -> None:
    if tool_definition.validator is not None:
        tool_definition.validator(config, node_id)


def execute_tool_definition(
    tool_definition: WorkflowToolDefinition,
    *,
    runtime: WorkflowNodeExecutionContext,
) -> dict:
    if tool_definition.executor is None:
        raise ValidationError({"definition": f'Tool "{tool_definition.name}" does not support execution.'})
    return tool_definition.executor(
        WorkflowToolExecutionContext(
            workflow=runtime.workflow,
            node=runtime.node,
            config=runtime.config,
            context=runtime.context,
            secret_paths=runtime.secret_paths,
            secret_values=runtime.secret_values,
            render_template=runtime.render_template,
            set_path_value=runtime.set_path_value,
            resolve_scoped_secret=runtime.resolve_scoped_secret,
        )
    )


def tool_definition_as_node_implementation(
    tool_definition: WorkflowToolDefinition,
) -> WorkflowNodeImplementation:
    def _validate(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
        del outgoing_targets, node_ids
        validate_tool_definition_config(
            tool_definition,
            config=config,
            node_id=node_id,
        )

    def _execute(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
        output = execute_tool_definition(
            tool_definition,
            runtime=runtime,
        )
        return WorkflowNodeExecutionResult(
            next_node_id=runtime.next_node_id,
            output={
                key: value
                for key, value in output.items()
                if key != "operation"
            },
        )

    return WorkflowNodeImplementation(
        validator=_validate,
        executor=_execute,
    )


def trigger_definition_as_node_implementation(
    trigger_definition: WorkflowTriggerDefinition,
) -> WorkflowNodeImplementation:
    def _validate(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
        del outgoing_targets, node_ids
        if trigger_definition.validator is not None:
            trigger_definition.validator(config, node_id)

    def _execute(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
        trigger_type = runtime.context["trigger"].get("type")
        if not isinstance(trigger_type, str) or not trigger_type.strip():
            trigger_type = runtime.config.get("type")
        if not isinstance(trigger_type, str) or not trigger_type.strip():
            trigger_type = runtime.node.get("type")
        if isinstance(trigger_type, str) and trigger_type.startswith("trigger."):
            trigger_type = trigger_type.removeprefix("trigger.")

        return WorkflowNodeExecutionResult(
            next_node_id=runtime.next_node_id,
            output={
                "payload": runtime.context["trigger"]["payload"],
                "trigger_type": trigger_type,
                "trigger_meta": runtime.context["trigger"].get("meta", {}),
            },
        )

    def _handle_webhook(context: WorkflowNodeWebhookContext) -> tuple[dict, dict]:
        if trigger_definition.webhook_handler is None:
            raise ValidationError(
                {"trigger": f'Trigger "{trigger_definition.name}" does not support webhook delivery.'}
            )
        return trigger_definition.webhook_handler(
            WorkflowTriggerRequestContext(
                workflow=context.workflow,
                node=context.node,
                config=context.config,
                request=context.request,
                body=context.body,
            )
        )

    return WorkflowNodeImplementation(
        validator=_validate,
        executor=_execute,
        webhook_handler=_handle_webhook if trigger_definition.webhook_handler is not None else None,
    )
