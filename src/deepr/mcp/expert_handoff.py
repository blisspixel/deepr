"""MCP helper for versioned expert handoff reads."""

from __future__ import annotations

from typing import Any

from deepr.experts.handoff import build_expert_handoff
from deepr.experts.profile import ExpertStore


def _error(error_code: str, message: str) -> dict[str, Any]:
    return {"error_code": error_code, "message": message}


def _parse_int(value: Any, *, name: str, minimum: int, maximum: int) -> tuple[int | None, dict[str, Any] | None]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, _error("INVALID_PARAMS", f"{name} must be an integer between {minimum} and {maximum}")
    if parsed < minimum or parsed > maximum:
        return None, _error("INVALID_PARAMS", f"{name} must be between {minimum} and {maximum}")
    return parsed, None


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


async def get_expert_handoff(
    store: ExpertStore,
    *,
    expert_name: str = "",
    max_claims: int = 10,
    max_gaps: int = 10,
    loop_limit: int = 5,
    include_claims: bool = True,
    include_gaps: bool = True,
    include_decisions: bool = False,
) -> dict[str, Any]:
    """Return a versioned read-only handoff payload for an expert."""
    parsed_claims, err = _parse_int(max_claims, name="max_claims", minimum=0, maximum=100)
    if err:
        return err
    parsed_gaps, err = _parse_int(max_gaps, name="max_gaps", minimum=0, maximum=50)
    if err:
        return err
    parsed_loop_limit, err = _parse_int(loop_limit, name="loop_limit", minimum=1, maximum=50)
    if err:
        return err

    try:
        expert = store.load(expert_name)
        if not expert:
            return _error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

        return build_expert_handoff(
            expert,
            max_claims=parsed_claims if parsed_claims is not None else 10,
            max_gaps=parsed_gaps if parsed_gaps is not None else 10,
            loop_limit=parsed_loop_limit if parsed_loop_limit is not None else 5,
            include_claims=_parse_bool(include_claims, default=True),
            include_gaps=_parse_bool(include_gaps, default=True),
            include_decisions=_parse_bool(include_decisions, default=False),
        )
    except (OSError, KeyError, ValueError) as e:
        return _error("HANDOFF_FAILED", str(e))
