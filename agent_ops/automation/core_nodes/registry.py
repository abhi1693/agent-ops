from __future__ import annotations

from automation.catalog.capabilities import (
    CAPABILITY_TRIGGER_MANUAL,
    CAPABILITY_TRIGGER_SCHEDULE,
)
from automation.catalog.definitions import (
    CatalogNodeDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.catalog.registry import WorkflowCatalogRegistry


CORE_NODE_DEFINITIONS = (
    CatalogNodeDefinition(
        id="core.manual_trigger",
        integration_id="core",
        mode="core",
        kind="trigger",
        label="Manual Trigger",
        description="Starts a workflow when a user runs it explicitly.",
        icon="mdi-play-circle-outline",
        capabilities=frozenset({CAPABILITY_TRIGGER_MANUAL}),
    ),
    CatalogNodeDefinition(
        id="core.schedule_trigger",
        integration_id="core",
        mode="core",
        kind="trigger",
        label="Schedule Trigger",
        description="Starts a workflow on a recurring cron schedule.",
        icon="mdi-calendar-clock",
        capabilities=frozenset({CAPABILITY_TRIGGER_SCHEDULE}),
        parameter_schema=(
            ParameterDefinition(
                key="cron",
                label="Cron Expression",
                value_type="string",
                required=True,
                description="Cron expression used to schedule workflow runs.",
                placeholder="0 * * * *",
            ),
        ),
    ),
    CatalogNodeDefinition(
        id="core.agent",
        integration_id="core",
        mode="core",
        kind="agent",
        label="Agent",
        description="Runs an agent with model, tools, and prompt instructions.",
        icon="mdi-robot-outline",
        parameter_schema=(
            ParameterDefinition(
                key="template",
                label="Template",
                value_type="text",
                required=True,
                description="Rendered as the user prompt passed to the connected model.",
                placeholder="Summarize the latest incidents and propose next actions.",
            ),
            ParameterDefinition(
                key="system_prompt",
                label="System Prompt",
                value_type="text",
                required=False,
                description="Optional system instructions for the connected model.",
                placeholder="You are an incident response assistant.",
            ),
            ParameterDefinition(
                key="output_key",
                label="Save Result As",
                value_type="string",
                required=False,
                description="Context path where the final model response is stored.",
                placeholder="llm.response",
                default="llm.response",
            ),
        ),
    ),
    CatalogNodeDefinition(
        id="core.set",
        integration_id="core",
        mode="core",
        kind="data",
        label="Set",
        description="Creates or updates workflow variables and structured values.",
        icon="mdi-form-textbox",
        parameter_schema=(
            ParameterDefinition(
                key="output_key",
                label="Save Result As",
                value_type="string",
                required=True,
                description="Context path to write.",
                placeholder="context.value",
            ),
            ParameterDefinition(
                key="value",
                label="Value",
                value_type="string",
                required=False,
                description="Literal or templated value to store.",
                placeholder="{{ trigger.payload.message }}",
            ),
        ),
    ),
    CatalogNodeDefinition(
        id="core.if",
        integration_id="core",
        mode="core",
        kind="control",
        label="If",
        description="Routes execution based on a conditional expression.",
        icon="mdi-source-branch",
        parameter_schema=(
            ParameterDefinition(
                key="path",
                label="Context Path",
                value_type="string",
                required=True,
                description="Path resolved from the workflow context.",
                placeholder="context.value",
            ),
            ParameterDefinition(
                key="operator",
                label="Operator",
                value_type="string",
                required=True,
                description="Comparison operator.",
                default="equals",
                options=(
                    ParameterOptionDefinition(value="equals", label="Equals"),
                    ParameterOptionDefinition(value="not_equals", label="Does Not Equal"),
                    ParameterOptionDefinition(value="contains", label="Contains"),
                    ParameterOptionDefinition(value="exists", label="Exists"),
                    ParameterOptionDefinition(value="truthy", label="Is Truthy"),
                ),
            ),
            ParameterDefinition(
                key="right_value",
                label="Compare Against",
                value_type="string",
                required=False,
                description="Value compared against the selected path.",
                placeholder="hello",
                show_if=(
                    {"operator": ["equals", "not_equals", "contains"]},
                ),
            ),
            ParameterDefinition(
                key="true_target",
                label="If True, Go To",
                value_type="node_ref",
                required=True,
                description="Next node when the condition matches.",
            ),
            ParameterDefinition(
                key="false_target",
                label="If False, Go To",
                value_type="node_ref",
                required=True,
                description="Next node when the condition does not match.",
            ),
        ),
    ),
    CatalogNodeDefinition(
        id="core.switch",
        integration_id="core",
        mode="core",
        kind="control",
        label="Switch",
        description="Routes execution across multiple cases using a selected value.",
        icon="mdi-call-split",
        parameter_schema=(
            ParameterDefinition(
                key="path",
                label="Context Path",
                value_type="string",
                required=True,
                description="Path resolved from the workflow context.",
                placeholder="trigger.payload.status",
            ),
            ParameterDefinition(
                key="case_1_value",
                label="Case 1 Value",
                value_type="string",
                required=True,
                description="First value to match.",
                placeholder="queued",
            ),
            ParameterDefinition(
                key="case_1_target",
                label="Case 1 Target",
                value_type="node_ref",
                required=True,
                description="Next node when case 1 matches.",
            ),
            ParameterDefinition(
                key="case_2_value",
                label="Case 2 Value",
                value_type="string",
                required=True,
                description="Second value to match.",
                placeholder="running",
            ),
            ParameterDefinition(
                key="case_2_target",
                label="Case 2 Target",
                value_type="node_ref",
                required=True,
                description="Next node when case 2 matches.",
            ),
            ParameterDefinition(
                key="fallback_target",
                label="Fallback Target",
                value_type="node_ref",
                required=True,
                description="Next node when no case matches.",
            ),
        ),
    ),
    CatalogNodeDefinition(
        id="core.response",
        integration_id="core",
        mode="core",
        kind="output",
        label="Response",
        description="Returns a structured workflow response to the caller.",
        icon="mdi-reply-outline",
        parameter_schema=(
            ParameterDefinition(
                key="template",
                label="Template",
                value_type="text",
                required=False,
                description="Rendered response body.",
                placeholder="Completed {{ llm.response.text }}",
            ),
            ParameterDefinition(
                key="value_path",
                label="Value Path",
                value_type="string",
                required=False,
                description="Optional direct context lookup instead of rendering the template.",
                placeholder="llm.response",
            ),
            ParameterDefinition(
                key="status",
                label="Status",
                value_type="string",
                required=False,
                description="Terminal run status.",
                default="succeeded",
                options=(
                    ParameterOptionDefinition(value="succeeded", label="Succeeded"),
                    ParameterOptionDefinition(value="failed", label="Failed"),
                ),
            ),
        ),
    ),
    CatalogNodeDefinition(
        id="core.stop_and_error",
        integration_id="core",
        mode="core",
        kind="control",
        label="Stop And Error",
        description="Stops execution immediately and emits an explicit workflow failure.",
        icon="mdi-alert-circle-outline",
        parameter_schema=(
            ParameterDefinition(
                key="message",
                label="Error Message",
                value_type="string",
                required=True,
                description="Message surfaced in the workflow run error output.",
                placeholder="The selected deployment environment is not allowed.",
            ),
        ),
    ),
)


def register_core_nodes(registry: WorkflowCatalogRegistry) -> None:
    for node_definition in CORE_NODE_DEFINITIONS:
        node_definition.register(registry)
        registry["core_nodes"][node_definition.id] = node_definition


__all__ = ("CORE_NODE_DEFINITIONS", "register_core_nodes")
