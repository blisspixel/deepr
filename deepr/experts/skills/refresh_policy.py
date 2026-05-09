"""Staleness detection for cached external tool results.

Determines when previously fetched data should be refreshed based
on configurable age thresholds.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RefreshPolicy:
    """When to consider cached tool results stale.

    A result is stale if:
    - force_refresh is True, OR
    - last_refreshed is None (never fetched), OR
    - (now - last_refreshed).days > max_age_days

    Usage::

        policy = RefreshPolicy(max_age_days=30, last_refreshed=some_datetime)
        if policy.is_stale():
            # re-fetch data
            ...
    """

    max_age_days: int = 30
    force_refresh: bool = False
    last_refreshed: datetime | None = None

    def is_stale(self, now: datetime | None = None) -> bool:
        """Check if the cached data is stale.

        Args:
            now: Current time. Defaults to UTC now.

        Returns:
            True if data should be refreshed.
        """
        if self.force_refresh:
            return True

        if self.last_refreshed is None:
            return True

        current = now or datetime.now(timezone.utc)

        # Ensure both datetimes are timezone-aware for comparison
        last = self.last_refreshed
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        age_days = (current - last).days
        return age_days > self.max_age_days
