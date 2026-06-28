"""Value normalization helpers for source-pack compiler artifacts."""

from __future__ import annotations

from typing import Any


def int_or_zero(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def float_0_1(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def float_nonnegative(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, parsed)


def int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def normalized_key(value: Any, *, default: str = "") -> str:
    text = str(value if value is not None else default).strip().lower()
    return text.replace("-", "_").replace(" ", "_") or default


def enum_value(value: Any, allowed: set[str], *, default: str) -> str:
    normalized = normalized_key(value, default=default)
    return normalized if normalized in allowed else default


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def string_field(item: dict[str, Any], key: str) -> str:
    return str(item.get(key, "") or "").strip()


def string_list_field(item: dict[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]
