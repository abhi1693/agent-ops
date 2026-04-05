from __future__ import annotations

from typing import Any

from automation.catalog.definitions import (
    CatalogNodeDefinition,
    OutputPortDefinition,
    ParameterCollectionOptionDefinition,
    ParameterDefinition,
    ParameterOptionDefinition,
)
from automation.catalog.validation import raise_definition_error, validate_parameter_schema
from automation.core_nodes._conditions import evaluate_condition_block
from automation.runtime_types import WorkflowNodeExecutionContext, WorkflowNodeExecutionResult
from automation.tools.base import _render_runtime_string


MAX_SWITCH_CASES = 5
FALLBACK_PORT = "fallback"
CASE_PORTS = tuple(f"case_{index}" for index in range(1, MAX_SWITCH_CASES + 1))


def _get_switch_mode(config: dict[str, Any]) -> str:
    raw_mode = str(config.get("mode") or "").strip().lower()
    if raw_mode in {"expression", "rules"}:
        return raw_mode
    return "rules"


def _get_switch_rule_values(config: dict[str, Any]) -> list[dict[str, Any]]:
    rules_payload = config.get("rules")
    if isinstance(rules_payload, dict):
        raw_values = rules_payload.get("values")
        if isinstance(raw_values, list):
            return [item for item in raw_values if isinstance(item, dict)]
    return []


def _build_switch_rule_condition_block(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "conditions": [
            {
                "leftPath": rule.get("leftPath"),
                "operator": rule.get("operator"),
                "rightValue": rule.get("rightValue"),
            }
        ],
        "combinator": "and",
    }


def _get_expression_output_count(config: dict[str, Any]) -> int:
    raw_count = config.get("numberOutputs") or 2
    try:
        parsed_count = int(raw_count)
    except (TypeError, ValueError):
        return 2
    return max(1, min(MAX_SWITCH_CASES, parsed_count))


def _get_active_switch_ports(config: dict[str, Any]) -> tuple[str, ...]:
    mode = _get_switch_mode(config)
    if mode == "expression":
        return tuple(CASE_PORTS[:_get_expression_output_count(config)])
    rule_values = _get_switch_rule_values(config)
    case_ports = tuple(CASE_PORTS[: len(rule_values)])
    if len(case_ports) < len(rule_values):
        raise_definition_error(f"Switch supports at most {MAX_SWITCH_CASES} rule outputs.")
    fallback_output = str(
        config.get("fallbackOutput")
        or "extra"
    ).strip()
    if fallback_output != "none":
        return (*case_ports, FALLBACK_PORT)
    return case_ports


def _validate_core_switch_config(
    *,
    config,
    node_id,
    node_ids,
    outgoing_targets,
    outgoing_targets_by_source_port,
    untyped_outgoing_targets,
    **_,
) -> None:
    validate_parameter_schema(
        node_definition=NODE_DEFINITION,
        config=config,
        node_id=node_id,
        node_ids=node_ids,
        outgoing_targets=outgoing_targets,
    )
    mode = _get_switch_mode(config)
    if mode == "expression" and config.get("output") in (None, ""):
        raise_definition_error(f'Node "{node_id}" must define config.output in expression mode.')
    if mode == "rules" and not _get_switch_rule_values(config):
        raise_definition_error(f'Node "{node_id}" switch must define at least one rule.')
    active_ports = _get_active_switch_ports(config)
    if not active_ports:
        raise_definition_error(f'Node "{node_id}" switch must define at least one output.')
    unexpected_ports = set(outgoing_targets_by_source_port) - set(active_ports)
    if unexpected_ports:
        unexpected_ports_display = ", ".join(sorted(unexpected_ports))
        raise_definition_error(f'Node "{node_id}" does not support configured port(s): {unexpected_ports_display}.')
    for port_key in active_ports:
        if len(outgoing_targets_by_source_port.get(port_key, [])) != 1:
            raise_definition_error(f'Node "{node_id}" must connect exactly one "{port_key}" edge.')
    target_ids = [outgoing_targets_by_source_port[port_key][0] for port_key in active_ports]
    if len(set(target_ids)) != len(target_ids):
        raise_definition_error(f'Node "{node_id}" switch targets must be different.')


def _execute_switch(runtime: WorkflowNodeExecutionContext) -> WorkflowNodeExecutionResult:
    mode = _get_switch_mode(runtime.config)
    matched_case = FALLBACK_PORT
    output: dict[str, Any]
    if mode == "expression":
        raw_output = runtime.config.get("output")
        if isinstance(raw_output, str):
            rendered_output = _render_runtime_string(runtime, "output", required=True, default_mode="expression")
        else:
            rendered_output = str(raw_output)
        try:
            output_index = int(str(rendered_output).strip())
        except (TypeError, ValueError) as exc:
            raise_definition_error(f'Node "{runtime.node["id"]}" switch output must resolve to an integer.')
            raise AssertionError("unreachable") from exc
        if output_index < 0 or output_index >= _get_expression_output_count(runtime.config):
            raise_definition_error(
                f'Node "{runtime.node["id"]}" switch output index {output_index} is out of range.'
            )
        matched_case = f"case_{output_index + 1}"
        output = {
            "mode": "expression",
            "matched_case": matched_case,
            "output_index": output_index,
        }
    else:
        matched_rule_index = None
        for index, rule in enumerate(_get_switch_rule_values(runtime.config), start=1):
            conditions = _build_switch_rule_condition_block(rule)
            if evaluate_condition_block(runtime, conditions):
                matched_rule_index = index
                matched_case = f"case_{index}"
                break
        output = {
            "mode": "rules",
            "matched_case": matched_case,
            "matched_rule_index": matched_rule_index,
            "rule_count": len(_get_switch_rule_values(runtime.config)),
        }

    return WorkflowNodeExecutionResult(
        next_node_id=None,
        next_port=matched_case,
        output={**output, "next_port": matched_case},
    )


NODE_DEFINITION = CatalogNodeDefinition(
    id="core.switch",
    integration_id="core",
    mode="core",
    kind="control",
    label="Switch",
    description="Routes execution across multiple cases using a selected value.",
    icon="mdi-call-split",
    default_name="Switch",
    default_color="#506000",
    subtitle='={{config.mode}}',
    node_group=("transform",),
    output_ports=(
        *(OutputPortDefinition(key=port_key, label=port_key.replace("_", " ").title(), description=f"Taken when {port_key} matches.") for port_key in CASE_PORTS),
        OutputPortDefinition(key=FALLBACK_PORT, label="Fallback", description="Taken when no case matches."),
    ),
    runtime_validator=_validate_core_switch_config,
    runtime_executor=_execute_switch,
    parameter_schema=(
        ParameterDefinition(
            key="mode",
            label="Mode",
            value_type="string",
            required=False,
            description="How data should be routed.",
            default="rules",
            no_data_expression=True,
            ui_group="input",
            options=(
                ParameterOptionDefinition(value="rules", label="Rules"),
                ParameterOptionDefinition(value="expression", label="Expression"),
            ),
        ),
        ParameterDefinition(
            key="rules",
            label="Routing Rules",
            value_type="object",
            field_type="fixed_collection",
            required=False,
            description="Each rule maps a condition to one numbered output.",
            ui_group="input",
            display_options={
                "show": {
                    "mode": ("rules",),
                },
            },
            collection_options=(
                ParameterCollectionOptionDefinition(
                    key="values",
                    label="Rule",
                    multiple=True,
                    fields=(
                        ParameterDefinition(
                            key="leftPath",
                            label="Left Path",
                            value_type="string",
                            required=True,
                            description="Workflow context path to evaluate.",
                            placeholder="incident.summary.severity",
                        ),
                        ParameterDefinition(
                            key="operator",
                            label="Operator",
                            value_type="string",
                            required=True,
                            default="equals",
                            no_data_expression=True,
                            options=(
                                ParameterOptionDefinition(value="equals", label="Equals"),
                                ParameterOptionDefinition(value="not_equals", label="Does not equal"),
                                ParameterOptionDefinition(value="contains", label="Contains"),
                                ParameterOptionDefinition(value="greater_than", label="Greater than"),
                                ParameterOptionDefinition(value="less_than", label="Less than"),
                            ),
                        ),
                        ParameterDefinition(
                            key="rightValue",
                            label="Right Value",
                            value_type="string",
                            required=False,
                            placeholder="critical",
                        ),
                    ),
                ),
            ),
        ),
        ParameterDefinition(
            key="numberOutputs",
            label="Number of Outputs",
            value_type="integer",
            required=False,
            description="How many case outputs to expose in expression mode.",
            default=2,
            ui_group="advanced",
            display_options={
                "show": {
                    "mode": ("expression",),
                },
            },
        ),
        ParameterDefinition(
            key="fallbackOutput",
            label="Fallback Output",
            value_type="string",
            required=False,
            description="Choose whether to expose a fallback branch when no rule matches.",
            default="extra",
            no_data_expression=True,
            ui_group="advanced",
            options=(
                ParameterOptionDefinition(value="extra", label="Fallback branch"),
                ParameterOptionDefinition(value="none", label="No fallback"),
            ),
            display_options={
                "show": {
                    "mode": ("rules",),
                },
            },
        ),
        ParameterDefinition(
            key="output",
            label="Output Index",
            value_type="string",
            required=False,
            description="Expression or literal index to route to. Uses zero-based indexing.",
            placeholder="{{ trigger.payload.index }}",
            ui_group="input",
            display_options={
                "show": {
                    "mode": ("expression",),
                },
            },
        ),
    ),
)


__all__ = ("NODE_DEFINITION",)
