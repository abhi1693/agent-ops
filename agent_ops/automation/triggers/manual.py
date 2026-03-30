from __future__ import annotations

from .base import WorkflowTriggerDefinition, _validate_optional_string


def _validate_manual_trigger(config: dict[str, object], node_id: str) -> None:
    _validate_optional_string(config, "type", node_id=node_id)


TRIGGER_DEFINITION = WorkflowTriggerDefinition(
    name="manual",
    label="Manual",
    description="Run the workflow from the UI or API with a manually supplied JSON payload.",
    icon="mdi-play-circle-outline",
    validator=_validate_manual_trigger,
)
