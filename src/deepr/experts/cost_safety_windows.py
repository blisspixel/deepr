"""Pure projection checks for metered spend windows."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from math import isfinite


@dataclass
class NarrowingSpendLimit:
    """Track mutable caller narrowing separately from operator authority."""

    authority: float
    caller_override: float | None = None
    effective: float = field(init=False)

    def __post_init__(self) -> None:
        self.effective = self.authority

    def refresh(self, current: float, authority: float) -> float:
        """Observe a public-field override, then apply new authority safely."""
        if not isfinite(current) or current < 0:
            raise ValueError("Spend limits must be finite and non-negative")
        if current != self.effective:
            self.caller_override = current if self.caller_override is None else min(self.caller_override, current)
        self.authority = authority
        self.effective = min(authority, self.caller_override) if self.caller_override is not None else authority
        return self.effective


def projected_window_limit_reason(
    estimated_cost: float,
    windows: Iterable[tuple[str, float, float, float]],
) -> str:
    """Return the first window denial, ordered from narrowest to widest."""
    for label, spent, reserved, limit in windows:
        if spent + reserved + estimated_cost > limit:
            return (
                f"{label} limit ${limit:.2f} would be exceeded "
                f"(spent ${spent:.2f}, reserved ${reserved:.2f}, +${estimated_cost:.2f})"
            )
    return ""
