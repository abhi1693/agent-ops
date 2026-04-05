from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from automation.catalog.connections import get_connection_slot_value
from automation.catalog.definitions import CatalogNodeDefinition, ParameterDefinition
from automation.tools.base import (
    _coerce_csv_strings,
    _coerce_optional_float,
    _coerce_positive_int,
    _validate_optional_string,
    _validate_required_json_template,
    _validate_required_string,
)


def raise_definition_error(message: str) -> None:
    raise ValidationError({"definition": message})


def validate_terminal(node_id: str, outgoing_targets: list[str]) -> None:
    if outgoing_targets:
        raise_definition_error(f'Node "{node_id}" is terminal and cannot have outgoing edges.')


def validate_target_exists_and_connected(
    *,
    node_id: str,
    target_name: str,
    target_id: str,
    node_ids: set[str],
    outgoing_targets: list[str],
) -> None:
    if target_id not in node_ids:
        raise_definition_error(f'Node "{node_id}" {target_name} "{target_id}" does not exist.')
    if target_id not in outgoing_targets:
        raise_definition_error(
            f'Node "{node_id}" {target_name} "{target_id}" must also be represented by a graph edge.'
        )


def validate_connection_slots(
    *,
    node_definition: CatalogNodeDefinition,
    config: dict[str, Any],
    node_id: str,
) -> None:
    for connection_slot in node_definition.connection_slots:
        slot_value = get_connection_slot_value(
            config,
            slot_key=connection_slot.key,
            multiple=connection_slot.multiple,
        )
        if connection_slot.multiple:
            if connection_slot.required and not slot_value:
                raise_definition_error(f'Node "{node_id}" must define config.{connection_slot.key}.')
            if not isinstance(slot_value, list):
                raise_definition_error(
                    f'Node "{node_id}" config.{connection_slot.key} must be a list of connection IDs.'
                )
            for item in slot_value:
                if item in (None, ""):
                    raise_definition_error(
                        f'Node "{node_id}" config.{connection_slot.key} cannot contain empty connection IDs.'
                    )
            continue

        if connection_slot.required:
            _validate_required_string(config, connection_slot.key, node_id=node_id)
            continue
        if slot_value not in (None, ""):
            _validate_optional_string(config, connection_slot.key, node_id=node_id)


def validate_output_ports(
    *,
    node_definition: CatalogNodeDefinition,
    node_id: str,
    outgoing_targets_by_source_port: dict[str, list[str]],
    untyped_outgoing_targets: list[str],
) -> None:
    declared_output_ports = {port.key for port in node_definition.output_ports}
    if not declared_output_ports:
        if outgoing_targets_by_source_port:
            unexpected_ports_display = ", ".join(sorted(outgoing_targets_by_source_port))
            raise_definition_error(
                f'Node "{node_id}" does not support sourcePort-routed primary edges. '
                f"Unexpected ports: {unexpected_ports_display}."
            )
        return

    if untyped_outgoing_targets:
        raise_definition_error(
            f'Node "{node_id}" requires sourcePort on all primary outgoing edges.'
        )

    unexpected_ports = set(outgoing_targets_by_source_port) - declared_output_ports
    if unexpected_ports:
        unexpected_ports_display = ", ".join(sorted(unexpected_ports))
        raise_definition_error(
            f'Node "{node_id}" declares unsupported sourcePort values: {unexpected_ports_display}.'
        )


def _validate_boolean_value(*, value: Any, field_name: str, node_id: str) -> None:
    normalized = str(value).strip().lower()
    if normalized not in {"true", "false"}:
        raise_definition_error(f'Node "{node_id}" config.{field_name} must be true or false.')


def _validate_parameter_value(
    *,
    parameter: ParameterDefinition,
    config: dict[str, Any],
    node_id: str,
    node_ids: set[str],
    outgoing_targets: list[str],
) -> None:
    value = config.get(parameter.key)
    if parameter.required and value in (None, "", [], {}):
        raise_definition_error(f'Node "{node_id}" must define config.{parameter.key}.')
        return
    if value in (None, ""):
        return

    if parameter.value_type in {"string", "text"}:
        _validate_required_string(config, parameter.key, node_id=node_id)
    elif parameter.value_type == "node_ref":
        target_id = _validate_required_string(config, parameter.key, node_id=node_id)
        validate_target_exists_and_connected(
            node_id=node_id,
            target_name=parameter.key,
            target_id=target_id,
            node_ids=node_ids,
            outgoing_targets=outgoing_targets,
        )
    elif parameter.value_type == "json":
        _validate_required_json_template(config, parameter.key, node_id=node_id)
    elif parameter.value_type == "string[]":
        _coerce_csv_strings(value, field_name=parameter.key, node_id=node_id, default=[])
    elif parameter.value_type == "number":
        _coerce_optional_float(value, field_name=parameter.key, node_id=node_id)
    elif parameter.value_type == "integer":
        _coerce_positive_int(value, field_name=parameter.key, node_id=node_id, default=1)
    elif parameter.value_type == "boolean":
        _validate_boolean_value(value=value, field_name=parameter.key, node_id=node_id)

    if parameter.options:
        normalized_value = str(value).strip()
        allowed_values = {option.value for option in parameter.options}
        if normalized_value not in allowed_values:
            allowed_values_display = ", ".join(sorted(allowed_values))
            raise_definition_error(
                f'Node "{node_id}" config.{parameter.key} must be one of: {allowed_values_display}.'
            )


def validate_parameter_schema(
    *,
    node_definition: CatalogNodeDefinition,
    config: dict[str, Any],
    node_id: str,
    node_ids: set[str],
    outgoing_targets: list[str],
) -> None:
    for parameter in node_definition.parameter_schema:
        _validate_parameter_value(
            parameter=parameter,
            config=config,
            node_id=node_id,
            node_ids=node_ids,
            outgoing_targets=outgoing_targets,
        )


def validate_catalog_runtime_node(
    *,
    node_definition: CatalogNodeDefinition,
    config: dict[str, Any],
    node_id: str,
    node_ids: set[str],
    outgoing_targets: list[str],
    outgoing_targets_by_source_port: dict[str, list[str]],
    untyped_outgoing_targets: list[str],
) -> None:
    validate_connection_slots(
        node_definition=node_definition,
        config=config,
        node_id=node_id,
    )
    validate_output_ports(
        node_definition=node_definition,
        node_id=node_id,
        outgoing_targets_by_source_port=outgoing_targets_by_source_port,
        untyped_outgoing_targets=untyped_outgoing_targets,
    )
    if node_definition.runtime_validator is not None:
        node_definition.runtime_validator(
            config=config,
            node_id=node_id,
            node_ids=node_ids,
            outgoing_targets=outgoing_targets,
            outgoing_targets_by_source_port=outgoing_targets_by_source_port,
            untyped_outgoing_targets=untyped_outgoing_targets,
        )
        return
    validate_parameter_schema(
        node_definition=node_definition,
        config=config,
        node_id=node_id,
        node_ids=node_ids,
        outgoing_targets=outgoing_targets,
    )


__all__ = (
    "raise_definition_error",
    "validate_catalog_runtime_node",
    "validate_connection_slots",
    "validate_output_ports",
    "validate_parameter_schema",
    "validate_target_exists_and_connected",
    "validate_terminal",
)
