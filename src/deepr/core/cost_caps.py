"""Unified spend-cap resolution for every metered entry point.

DEEPR_MAX_COST_PER_JOB, DEEPR_MAX_COST_PER_DAY, and DEEPR_MAX_COST_PER_MONTH
are the user's documented hard ceilings and must bind every dispatch path.
The web dashboard and REST API historically read a different family
(DEEPR_PER_JOB_LIMIT / DEEPR_DAILY_LIMIT / DEEPR_MONTHLY_LIMIT), so a user
who set the documented caps got no protection on those surfaces - part of
how a $10/month cap coexisted with a $38 month.

Resolution rules, paranoid by construction:
- Both families are honored; when both are set the TIGHTER bound wins.
- A malformed or non-positive value is ignored (falls back to the other
  family or the built-in default), never treated as unlimited.
"""

from __future__ import annotations

import os

_DEFAULTS: dict[str, float] = {"per_job": 5.0, "daily": 10.0, "monthly": 20.0}
_PRIMARY: dict[str, str] = {
    "per_job": "DEEPR_MAX_COST_PER_JOB",
    "daily": "DEEPR_MAX_COST_PER_DAY",
    "monthly": "DEEPR_MAX_COST_PER_MONTH",
}
_LEGACY: dict[str, str] = {
    "per_job": "DEEPR_PER_JOB_LIMIT",
    "daily": "DEEPR_DAILY_LIMIT",
    "monthly": "DEEPR_MONTHLY_LIMIT",
}


def _parse_positive(env_name: str) -> float | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def resolve_spend_caps() -> dict[str, float]:
    """Effective per_job/daily/monthly caps in USD, always positive."""
    caps: dict[str, float] = {}
    for key, default in _DEFAULTS.items():
        candidates = [v for v in (_parse_positive(_PRIMARY[key]), _parse_positive(_LEGACY[key])) if v is not None]
        caps[key] = min(candidates) if candidates else default
    return caps


__all__ = ["resolve_spend_caps"]
