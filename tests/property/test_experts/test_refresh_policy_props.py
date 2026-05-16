"""Property tests for RefreshPolicy.

Feature: mcp-client-agent-interop
Property: 26
Validates: Requirements 12.3
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.experts.skills.refresh_policy import RefreshPolicy

# --- Strategies ---

max_age_st = st.integers(min_value=1, max_value=365)
days_since_st = st.integers(min_value=0, max_value=730)


# --- Property 26: Refresh policy staleness detection ---


@settings(max_examples=100)
@given(
    max_age_days=max_age_st,
    days_since_refresh=days_since_st,
)
def test_staleness_detection(max_age_days: int, days_since_refresh: int) -> None:
    """Property 26: Refresh policy staleness detection.

    For any RefreshPolicy with max_age_days=D and last_refreshed=T,
    the result is stale if and only if (now - T).days > D.

    **Validates: Requirements 12.3**
    """
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    last_refreshed = now - timedelta(days=days_since_refresh)

    policy = RefreshPolicy(
        max_age_days=max_age_days,
        last_refreshed=last_refreshed,
    )

    result = policy.is_stale(now=now)
    expected = days_since_refresh > max_age_days

    assert result == expected, (
        f"is_stale()={result} but expected {expected} (age={days_since_refresh} days, max={max_age_days} days)"
    )


@settings(max_examples=100)
@given(max_age_days=max_age_st)
def test_force_refresh_always_stale(max_age_days: int) -> None:
    """Force refresh always returns stale regardless of age.

    **Validates: Requirements 12.3**
    """
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    # Even if just refreshed
    last_refreshed = now

    policy = RefreshPolicy(
        max_age_days=max_age_days,
        force_refresh=True,
        last_refreshed=last_refreshed,
    )

    assert policy.is_stale(now=now) is True


@settings(max_examples=100)
@given(max_age_days=max_age_st)
def test_never_refreshed_always_stale(max_age_days: int) -> None:
    """Never-refreshed data is always stale.

    **Validates: Requirements 12.3**
    """
    policy = RefreshPolicy(
        max_age_days=max_age_days,
        last_refreshed=None,
    )

    assert policy.is_stale() is True
