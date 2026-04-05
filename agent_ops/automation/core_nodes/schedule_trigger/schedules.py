from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone


@dataclass(frozen=True)
class ScheduleTriggerConfig:
    configured_schedule_at: datetime | None
    interval_minutes: int | None


def normalize_schedule_datetime(value: datetime | None, *, fallback: datetime | None = None) -> datetime | None:
    if value is None:
        return fallback
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def parse_schedule_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return normalize_schedule_datetime(value)
    if not isinstance(value, str):
        raise ValueError("Schedule At must be a valid date and time.")

    raw_value = value.strip()
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError("Schedule At must be a valid date and time.") from exc

    return normalize_schedule_datetime(parsed)


def serialize_schedule_datetime(value: datetime | None) -> str | None:
    normalized = normalize_schedule_datetime(value)
    if normalized is None:
        return None
    return normalized.isoformat()


def parse_schedule_trigger_config(config: dict[str, Any] | None) -> ScheduleTriggerConfig:
    schedule_config = config or {}
    configured_schedule_at = parse_schedule_datetime(schedule_config.get("schedule_at"))

    raw_interval = schedule_config.get("interval_minutes")
    if raw_interval in (None, ""):
        interval_minutes = None
    else:
        try:
            interval_minutes = int(raw_interval)
        except (TypeError, ValueError) as exc:
            raise ValueError("Interval Minutes must be an integer.") from exc
        if interval_minutes < 1:
            raise ValueError("Interval Minutes must be greater than or equal to 1.")

    if configured_schedule_at is None and interval_minutes is None:
        raise ValueError('must define "Schedule At" or "Interval Minutes".')

    return ScheduleTriggerConfig(
        configured_schedule_at=configured_schedule_at,
        interval_minutes=interval_minutes,
    )


def resolve_initial_schedule_time(*, schedule: ScheduleTriggerConfig, now: datetime | None = None) -> datetime:
    reference_time = normalize_schedule_datetime(now, fallback=timezone.now())
    if schedule.configured_schedule_at is not None:
        return schedule.configured_schedule_at
    return reference_time


def serialize_schedule_trigger_config(schedule: ScheduleTriggerConfig) -> dict[str, Any]:
    return {
        "schedule_at": serialize_schedule_datetime(schedule.configured_schedule_at),
        "interval_minutes": schedule.interval_minutes,
    }


def validate_schedule_config(config: dict[str, Any] | None) -> None:
    parse_schedule_trigger_config(config)

