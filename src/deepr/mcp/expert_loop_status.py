"""MCP helper for durable expert loop-status reads."""

from __future__ import annotations

from typing import Any

from deepr.experts.loop_runs import ExpertLoopRunStore, LoopRunStatus
from deepr.experts.profile import ExpertStore


def _error(error_code: str, message: str) -> dict[str, Any]:
    return {"error_code": error_code, "message": message}


async def get_expert_loop_status(
    store: ExpertStore,
    *,
    expert_name: str = "",
    limit: int = 5,
    status: str | None = None,
    loop_type: str | None = None,
) -> dict[str, Any]:
    """Return durable loop-run status for an expert. Read-only, cost-$0."""
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        return _error("INVALID_PARAMS", "limit must be an integer between 1 and 50")
    if parsed_limit < 1 or parsed_limit > 50:
        return _error("INVALID_PARAMS", "limit must be between 1 and 50")

    try:
        expert = store.load(expert_name)
        if not expert:
            return _error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

        status_filter: LoopRunStatus | None = None
        if status:
            try:
                status_filter = LoopRunStatus(str(status).strip().lower())
            except ValueError:
                valid = ", ".join(s.value for s in LoopRunStatus)
                return _error("INVALID_LOOP_STATUS", f"status must be one of: {valid}")

        type_filter = str(loop_type).strip() if loop_type else None
        resolved_name = getattr(expert, "name", expert_name)
        if not isinstance(resolved_name, str) or not resolved_name.strip():
            resolved_name = expert_name

        runs = ExpertLoopRunStore(resolved_name).list_runs(
            status=status_filter,
            loop_type=type_filter,
            limit=parsed_limit,
        )
        return {
            "expert_name": resolved_name,
            "count": len(runs),
            "runs": [run.to_dict() for run in runs],
        }
    except (OSError, KeyError, ValueError) as e:
        return _error("LOOP_STATUS_FAILED", str(e))
