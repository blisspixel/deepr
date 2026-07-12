"""Compatibility stub for the removed unreserved documentation batch script."""

from __future__ import annotations

BLOCK_CODE = "research_parent_budget_unavailable"


def main() -> int:
    """Refuse legacy fan-out before provider construction or filesystem writes."""
    print(
        "Blocked: documentation batch submission requires one durable parent "
        "reservation with exact child settlement "
        f"({BLOCK_CODE})."
    )
    print("Use `deepr research ... --dry-run` and submit separately approved bounded jobs one at a time.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
