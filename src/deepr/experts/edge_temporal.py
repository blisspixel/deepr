"""Shared temporal qualifier helpers for typed belief-graph edges."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

EDGE_TEMPORAL_FIELDS = ("valid_from", "valid_until", "observed_at", "temporal_scope")
EDGE_TEMPORAL_INSTANT_FIELDS = ("valid_from", "valid_until", "observed_at")


def normalize_temporal_context(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    nested = raw.get("temporal", {})
    raw_nested = nested if isinstance(nested, dict) else {}
    return {
        field: str(raw.get(field, raw_nested.get(field, ""))).strip()
        for field in EDGE_TEMPORAL_FIELDS
        if str(raw.get(field, raw_nested.get(field, ""))).strip()
    }


def parse_iso_temporal(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def temporal_failure_reasons(value: Any, *, field_error: str, order_error: str) -> list[str]:
    temporal = normalize_temporal_context(value)
    failures: list[str] = []
    parsed: dict[str, datetime] = {}
    for field in EDGE_TEMPORAL_INSTANT_FIELDS:
        field_value = temporal.get(field, "")
        if not field_value:
            continue
        parsed_value = parse_iso_temporal(field_value)
        if parsed_value is None:
            failures.append(field_error.format(field=field))
            continue
        parsed[field] = parsed_value
    if parsed.get("valid_from") and parsed.get("valid_until") and parsed["valid_from"] > parsed["valid_until"]:
        failures.append(order_error)
    return failures


__all__ = [
    "EDGE_TEMPORAL_FIELDS",
    "normalize_temporal_context",
    "parse_iso_temporal",
    "temporal_failure_reasons",
]
