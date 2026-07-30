"""Shared gates for semantic model stages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isfinite
from typing import Any

ZERO_DOLLAR_CAPACITY_PREFIXES = ("local", "local-", "local_", "plan_quota:")
METERED_CAPACITY_LABELS = {"api_metered", "metered_api", "api", "openai", "anthropic", "xai", "gemini"}

_ZERO_DOLLAR_CLIENT_SEAL = object()


@dataclass(frozen=True)
class _ZeroDollarClientAuthority:
    """Process-local proof attached only by Deepr capacity constructors."""

    capacity_source: str
    seal: object


def _normalize_capacity_source(value: str) -> str:
    return value.strip().casefold()


def _mark_zero_dollar_client(client: Any, *, capacity_source: str) -> Any:
    """Bind a constructed local or safe plan client to its real capacity class."""
    source = _normalize_capacity_source(capacity_source)
    if not any(source.startswith(prefix) for prefix in ZERO_DOLLAR_CAPACITY_PREFIXES):
        raise ValueError("Only local or plan-quota clients can receive zero-dollar capacity authority")
    authority = _ZeroDollarClientAuthority(capacity_source=source, seal=_ZERO_DOLLAR_CLIENT_SEAL)
    try:
        client._deepr_zero_dollar_capacity = authority
    except (AttributeError, TypeError) as exc:
        raise ValueError("The client cannot retain Deepr zero-dollar capacity authority") from exc
    return client


def require_zero_dollar_client(client: Any, *, capacity_source: str | None = None) -> str:
    """Reject caller labels unless the client came from a trusted capacity constructor."""
    authority = getattr(client, "_deepr_zero_dollar_capacity", None)
    if not isinstance(authority, _ZeroDollarClientAuthority) or authority.seal is not _ZERO_DOLLAR_CLIENT_SEAL:
        raise ValueError("The client has no Deepr-minted zero-dollar capacity proof")
    if capacity_source is not None:
        expected = _normalize_capacity_source(capacity_source)
        if authority.capacity_source != expected:
            raise ValueError("The client zero-dollar capacity proof does not match the declared source")
    return authority.capacity_source


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def coerce_nonnegative_float(value: Any, *, name: str, error_type: type[Exception]) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise error_type(f"{name} must be a number") from exc
    if not isfinite(parsed) or parsed < 0:
        raise error_type(f"{name} must be finite and non-negative")
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
    "require_zero_dollar_client",
    "requires_metered_opt_in",
    "sha256_text",
    "stable_json",
]
