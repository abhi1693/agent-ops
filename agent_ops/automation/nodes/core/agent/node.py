from __future__ import annotations

from automation.nodes.base import (
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
    WorkflowNodeImplementation,
    raise_definition_error,
)
from automation.tools import (
    WorkflowToolExecutionContext,
    execute_workflow_tool,
    validate_workflow_tool_config,
)
from automation.workflow_agents import (
    DEFAULT_AGENT_API_TYPE,
    SUPPORTED_AGENT_API_TYPES,
    build_workflow_agent_tool_config,
    normalize_workflow_agent_config,
)


def _validate_agent(config: dict, node_id: str, outgoing_targets: list[str], node_ids: set[str]) -> None:
    del node_ids
    normalized_agent_config = normalize_workflow_agent_config(config)
    agent_api_type = normalized_agent_config.get("api_type", DEFAULT_AGENT_API_TYPE)
    if agent_api_type not in SUPPORTED_AGENT_API_TYPES:
        raise_definition_error(
            f'Node "{node_id}" config.api_type must be one of: {", ".join(sorted(SUPPORTED_AGENT_API_TYPES))}.'
        )
    validate_workflow_tool_config(
        build_workflow_agent_tool_config(
            node={"id": node_id},
            config=normalized_agent_config,
        ),
        node_id=node_id,
    )
    if len(outgoing_targets) > 1:
        raise_definition_error(f'Node "{node_id}" can only connect to a single next node.')


def _execute_agent(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    normalized_agent_config = normalize_workflow_agent_config(runtime.config)
    normalized_tool_config = validate_workflow_tool_config(
        build_workflow_agent_tool_config(
            node=runtime.node,
            config=normalized_agent_config,
        ),
        node_id=runtime.node["id"],
    )
    output = execute_workflow_tool(
        WorkflowToolExecutionContext(
            workflow=runtime.workflow,
            node=runtime.node,
            config=normalized_tool_config,
            context=runtime.context,
            secret_paths=runtime.secret_paths,
            secret_values=runtime.secret_values,
            render_template=runtime.render_template,
            set_path_value=runtime.set_path_value,
            resolve_scoped_secret=runtime.resolve_scoped_secret,
        )
    )
    return WorkflowNodeExecutionResult(
        next_node_id=runtime.next_node_id,
        output={
            **{
                key: value
                for key, value in output.items()
                if key != "operation"
            },
            "api_type": normalized_agent_config.get("api_type", DEFAULT_AGENT_API_TYPE),
        },
    )


NODE_IMPLEMENTATION = WorkflowNodeImplementation(
    validator=_validate_agent,
    executor=_execute_agent,
)
