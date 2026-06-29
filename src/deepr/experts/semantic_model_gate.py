"""Shared gates for semantic model stages."""

from __future__ import annotations

import hashlib
import json
from typing import Any

ZERO_DOLLAR_CAPACITY_PREFIXES = ("local", "local-", "local_", "plan_quota:")
METERED_CAPACITY_LABELS = {"api_metered", "metered_api", "api", "openai", "anthropic", "xai", "gemini"}


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def coerce_nonnegative_float(value: Any, *, name: str, error_type: type[Exception]) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise error_type(f"{name} must be a number") from exc
    if parsed < 0:
        raise error_type(f"{name} must be non-negative")
    return parsed


def requires_metered_opt_in(capacity_source: str, estimated_cost_usd: float) -> bool:
    source = (capacity_source or "").strip().lower()
    if estimated_cost_usd > 0:
        return True
    if any(source.startswith(prefix) for prefix in ZERO_DOLLAR_CAPACITY_PREFIXES):
        return False
    return source in METERED_CAPACITY_LABELS


def cost_safety(cost_safety_manager: Any | None) -> Any:
    if cost_safety_manager is not None:
        return cost_safety_manager
    from deepr.experts.cost_safety import get_cost_safety_manager

    return get_cost_safety_manager()


__all__ = [
    "METERED_CAPACITY_LABELS",
    "ZERO_DOLLAR_CAPACITY_PREFIXES",
    "coerce_nonnegative_float",
    "cost_safety",
    "requires_metered_opt_in",
    "sha256_text",
    "stable_json",
]
