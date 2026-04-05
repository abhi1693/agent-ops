from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError

from automation.tools.base import _build_runtime_binding_context, _get_runtime_bound_path_value


_HANDLEBAR_PATTERN = re.compile(r"({[{%].*[}%]})")


def _looks_like_template(value: Any) -> bool:
    return isinstance(value, str) and bool(_HANDLEBAR_PATTERN.search(value))


def normalize_condition_operator(raw_operator: Any) -> str:
    if isinstance(raw_operator, dict):
        raw_operator = raw_operator.get("operation") or raw_operator.get("value")
    normalized = str(raw_operator or "").strip().lower()
    aliases = {
        "notequals": "not_equals",
        "doesnotequal": "not_equals",
        "isempty": "is_empty",
        "notempty": "not_empty",
        "startswith": "starts_with",
        "endswith": "ends_with",
        "larger": "greater_than",
        "smaller": "less_than",
    }
    return aliases.get(normalized.replace(" ", "").replace("-", "").replace(".", ""), normalized)


def resolve_condition_operand(runtime: Any, condition: dict[str, Any], side: str) -> Any:
    path_keys = (f"{side}Path", f"{side}_path")
    value_keys = (f"{side}Value", f"{side}_value")

    for path_key in path_keys:
        raw_path = condition.get(path_key)
        if isinstance(raw_path, str) and raw_path.strip():
            return _get_runtime_bound_path_value(runtime, raw_path.strip())

    for value_key in value_keys:
        if value_key not in condition:
            continue
        raw_value = condition.get(value_key)
        if _looks_like_template(raw_value):
            return runtime.render_template(str(raw_value), _build_runtime_binding_context(runtime)).strip()
        return raw_value
    return None


def _coerce_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def evaluate_condition_values(
    *,
    operator: str,
    left_value: Any,
    right_value: Any,
    ignore_case: bool = False,
) -> bool:
    normalized_operator = normalize_condition_operator(operator)

    if ignore_case and isinstance(left_value, str):
        left_value = left_value.lower()
    if ignore_case and isinstance(right_value, str):
        right_value = right_value.lower()

    if normalized_operator == "equals":
        return left_value == right_value
    if normalized_operator == "not_equals":
        return left_value != right_value
    if normalized_operator == "contains":
        if left_value is None:
            return False
        try:
            return right_value in left_value
        except TypeError:
            return False
    if normalized_operator == "not_contains":
        if left_value is None:
            return True
        try:
            return right_value not in left_value
        except TypeError:
            return True
    if normalized_operator == "exists":
        return left_value is not None
    if normalized_operator == "truthy":
        return bool(left_value)
    if normalized_operator == "is_empty":
        return left_value in (None, "", [], {}, ())
    if normalized_operator == "not_empty":
        return left_value not in (None, "", [], {}, ())
    if normalized_operator == "starts_with":
        return isinstance(left_value, str) and isinstance(right_value, str) and left_value.startswith(right_value)
    if normalized_operator == "ends_with":
        return isinstance(left_value, str) and isinstance(right_value, str) and left_value.endswith(right_value)
    if normalized_operator in {"greater_than", "less_than"}:
        left_number = _coerce_number(left_value)
        right_number = _coerce_number(right_value)
        if left_number is None or right_number is None:
            return False
        return left_number > right_number if normalized_operator == "greater_than" else left_number < right_number
    if normalized_operator == "regex":
        return isinstance(left_value, str) and isinstance(right_value, str) and re.search(right_value, left_value) is not None

    raise ValidationError({"definition": f'Unsupported condition operator "{operator}".'})


def evaluate_condition_entry(runtime: Any, condition: dict[str, Any], *, ignore_case: bool = False) -> bool:
    operator = normalize_condition_operator(condition.get("operator"))
    left_value = resolve_condition_operand(runtime, condition, "left")
    right_value = resolve_condition_operand(runtime, condition, "right")
    return evaluate_condition_values(
        operator=operator,
        left_value=left_value,
        right_value=right_value,
        ignore_case=ignore_case,
    )


def evaluate_condition_block(runtime: Any, block: dict[str, Any]) -> bool:
    raw_conditions = block.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise ValidationError({"definition": "Condition block must define at least one condition."})
    combinator = str(block.get("combinator") or "and").strip().lower()
    ignore_case = bool((block.get("options") or {}).get("ignoreCase", True))
    results = [
        evaluate_condition_entry(runtime, condition, ignore_case=ignore_case)
        for condition in raw_conditions
        if isinstance(condition, dict)
    ]
    if not results:
        raise ValidationError({"definition": "Condition block did not contain valid conditions."})
    if combinator == "or":
        return any(results)
    return all(results)
