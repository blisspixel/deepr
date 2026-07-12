"""Pure bounds and progress parsing for consult lifecycle events."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import NotRequired, TypedDict

_BOUNDS_REQUIRED_KEYS = frozenset({"dispatch_scope", "max_cost_usd", "max_dispatches"})
_BOUNDS_OPTIONAL_KEYS = frozenset({"max_output_tokens", "max_context_bytes"})
_DISPATCH_SCOPES = frozenset({"council_work_item", "provider_call"})
_PROGRESS_REQUIRED_KEYS = frozenset({"cost_usd_observed", "dispatches_completed"})
_PROGRESS_OPTIONAL_KEYS = frozenset({"output_tokens_observed", "context_bytes_observed"})
_MAX_COST_USD = 1_000_000_000_000.0


class _Bounds(TypedDict):
    dispatch_scope: str
    max_cost_usd: float
    max_dispatches: int
    max_context_bytes: NotRequired[int]
    max_output_tokens: NotRequired[int]


class _Progress(TypedDict):
    cost_usd_observed: float
    dispatches_completed: int
    context_bytes_observed: NotRequired[int]
    output_tokens_observed: NotRequired[int]


def _mapping_with_optional(
    value: Mapping[str, object],
    *,
    required: frozenset[str],
    optional: frozenset[str],
    name: str,
) -> dict[str, object]:
    result = dict(value)
    extras = set(result) - required - optional
    missing = required - set(result)
    if extras or missing:
        raise ValueError(
            f"{name} must contain exactly required {sorted(required)} and optional {sorted(optional)} fields"
        )
    return result


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _normalize_cost(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0 or normalized > _MAX_COST_USD:
        raise ValueError(f"{name} must be finite, non-negative, and no greater than {_MAX_COST_USD:g}")
    return normalized


def _normalize_bounds(value: Mapping[str, object]) -> _Bounds:
    raw = _mapping_with_optional(
        value,
        required=_BOUNDS_REQUIRED_KEYS,
        optional=_BOUNDS_OPTIONAL_KEYS,
        name="bounds",
    )
    dispatch_scope = raw["dispatch_scope"]
    if not isinstance(dispatch_scope, str) or dispatch_scope not in _DISPATCH_SCOPES:
        raise ValueError(f"bounds.dispatch_scope must be one of {sorted(_DISPATCH_SCOPES)}")
    max_dispatches = _nonnegative_int(raw["max_dispatches"], "bounds.max_dispatches")
    if max_dispatches < 1:
        raise ValueError("bounds.max_dispatches must be at least 1")
    bounds: _Bounds = {
        "dispatch_scope": dispatch_scope,
        "max_cost_usd": _normalize_cost(raw["max_cost_usd"], "bounds.max_cost_usd"),
        "max_dispatches": max_dispatches,
    }
    if "max_context_bytes" in raw:
        bounds["max_context_bytes"] = _nonnegative_int(raw["max_context_bytes"], "bounds.max_context_bytes")
    if "max_output_tokens" in raw:
        bounds["max_output_tokens"] = _nonnegative_int(raw["max_output_tokens"], "bounds.max_output_tokens")
    return bounds


def _normalize_progress(value: Mapping[str, object] | None, bounds: _Bounds) -> _Progress:
    raw = (
        {"cost_usd_observed": 0.0, "dispatches_completed": 0}
        if value is None
        else _mapping_with_optional(
            value,
            required=_PROGRESS_REQUIRED_KEYS,
            optional=_PROGRESS_OPTIONAL_KEYS,
            name="progress",
        )
    )
    progress: _Progress = {
        "cost_usd_observed": _normalize_cost(raw["cost_usd_observed"], "progress.cost_usd_observed"),
        "dispatches_completed": _nonnegative_int(raw["dispatches_completed"], "progress.dispatches_completed"),
    }
    if "context_bytes_observed" in raw:
        if "max_context_bytes" not in bounds:
            raise ValueError("progress.context_bytes_observed requires bounds.max_context_bytes")
        progress["context_bytes_observed"] = _nonnegative_int(
            raw["context_bytes_observed"], "progress.context_bytes_observed"
        )
    if "output_tokens_observed" in raw:
        if "max_output_tokens" not in bounds:
            raise ValueError("progress.output_tokens_observed requires bounds.max_output_tokens")
        progress["output_tokens_observed"] = _nonnegative_int(
            raw["output_tokens_observed"], "progress.output_tokens_observed"
        )
    if progress["dispatches_completed"] > bounds["max_dispatches"]:
        raise ValueError("progress.dispatches_completed exceeds its configured bound")
    if progress.get("output_tokens_observed", 0) > bounds.get("max_output_tokens", 0):
        raise ValueError("progress.output_tokens_observed exceeds its configured bound")
    if progress.get("context_bytes_observed", 0) > bounds.get("max_context_bytes", 0):
        raise ValueError("progress.context_bytes_observed exceeds its configured bound")
    return progress
