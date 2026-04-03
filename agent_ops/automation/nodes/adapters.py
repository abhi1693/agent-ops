from __future__ import annotations

from django.core.exceptions import ValidationError

from automation.nodes.base import (
    _DEFAULT_WORKFLOW_NODE_APP_DESCRIPTION,
    WorkflowNodeDefinition,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeFieldDefinition,
    WorkflowNodeFieldOption,
    WorkflowNodeImplementation,
    WorkflowNodeWebhookContext,
)
from automation.tools.base import (
    WorkflowToolFieldDefinition,
    WorkflowToolFieldOption,
    WorkflowToolDefinition,
    WorkflowToolExecutionContext,
)
from automation.triggers.base import (
    WorkflowTriggerFieldDefinition,
    WorkflowTriggerFieldOption,
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


def _node_field_options_from_tool_options(
    options: tuple[WorkflowToolFieldOption, ...],
) -> tuple[WorkflowNodeFieldOption, ...]:
    return tuple(
        WorkflowNodeFieldOption(value=option.value, label=option.label)
        for option in options
    )


def _node_fields_from_tool_fields(
    fields: tuple[WorkflowToolFieldDefinition, ...],
) -> tuple[WorkflowNodeFieldDefinition, ...]:
    return tuple(
        WorkflowNodeFieldDefinition(
            key=field.key,
            label=field.label,
            type=field.type,
            options=_node_field_options_from_tool_options(field.options),
            ui_group=field.ui_group,
            binding=field.binding,
            placeholder=field.placeholder,
            help_text=field.help_text,
            rows=field.rows,
        )
        for field in fields
    )


def tool_definition_as_node_definition(
    tool_definition: WorkflowToolDefinition,
    *,
    node_type: str,
    details: str | None = None,
    app_id: str = "builtins",
    app_label: str = "Built-ins",
    app_description: str = _DEFAULT_WORKFLOW_NODE_APP_DESCRIPTION,
    app_icon: str = "mdi-toy-brick-outline",
) -> WorkflowNodeDefinition:
    implementation = tool_definition_as_node_implementation(tool_definition)
    return WorkflowNodeDefinition(
        type=node_type,
        kind="tool",
        display_name=tool_definition.label,
        description=details or tool_definition.description,
        icon=tool_definition.icon,
        config=dict(tool_definition.config),
        fields=_node_fields_from_tool_fields(tool_definition.fields),
        app_id=app_id,
        app_label=app_label,
        app_description=app_description,
        app_icon=app_icon,
        validator=implementation.validator,
        executor=implementation.executor,
        webhook_handler=implementation.webhook_handler,
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


def _node_field_options_from_trigger_options(
    options: tuple[WorkflowTriggerFieldOption, ...],
) -> tuple[WorkflowNodeFieldOption, ...]:
    return tuple(
        WorkflowNodeFieldOption(value=option.value, label=option.label)
        for option in options
    )


def _node_fields_from_trigger_fields(
    fields: tuple[WorkflowTriggerFieldDefinition, ...],
) -> tuple[WorkflowNodeFieldDefinition, ...]:
    return tuple(
        WorkflowNodeFieldDefinition(
            key=field.key,
            label=field.label,
            type=field.type,
            options=_node_field_options_from_trigger_options(field.options),
            placeholder=field.placeholder,
            help_text=field.help_text,
            rows=field.rows,
        )
        for field in fields
    )


def trigger_definition_as_node_definition(
    trigger_definition: WorkflowTriggerDefinition,
    *,
    node_type: str,
    details: str | None = None,
    app_id: str = "builtins",
    app_label: str = "Built-ins",
    app_description: str = _DEFAULT_WORKFLOW_NODE_APP_DESCRIPTION,
    app_icon: str = "mdi-toy-brick-outline",
) -> WorkflowNodeDefinition:
    implementation = trigger_definition_as_node_implementation(trigger_definition)
    return WorkflowNodeDefinition(
        type=node_type,
        kind="trigger",
        display_name=trigger_definition.label,
        description=details or trigger_definition.description,
        icon=trigger_definition.icon,
        config=dict(trigger_definition.config),
        fields=_node_fields_from_trigger_fields(trigger_definition.fields),
        app_id=app_id,
        app_label=app_label,
        app_description=app_description,
        app_icon=app_icon,
        validator=implementation.validator,
        executor=implementation.executor,
        webhook_handler=implementation.webhook_handler,
    )
