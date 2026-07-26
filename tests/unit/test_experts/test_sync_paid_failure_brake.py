"""Paid-failure spend brake: a topic that pays and fails must back off.

A subscription whose absorb step failed deterministically re-paid full
research on every scheduled run, forever - only the daily/monthly caps
bounded the loss. Paid failures now grow an exponential cooldown (capped at
8x cadence) that any successful run resets.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.experts.sync_contracts import Subscription


def _sub(**kwargs) -> Subscription:
    return Subscription(topic="Topic", cadence_days=kwargs.pop("cadence_days", 7.0), **kwargs)


def test_paid_failure_backs_off_exponentially() -> None:
    now = datetime.now(UTC)
    sub = _sub(last_attempted=now - timedelta(days=8), consecutive_paid_failures=1)
    # 1 failure -> 2x cadence (14 days); only 8 elapsed, not due.
    assert sub.is_due(now) is False

    sub.last_attempted = now - timedelta(days=15)
    assert sub.is_due(now) is True


def test_backoff_caps_at_eight_cadences() -> None:
    now = datetime.now(UTC)
    sub = _sub(last_attempted=now - timedelta(days=57), consecutive_paid_failures=10)
    # Cap: 8 * 7 = 56 days; 57 elapsed, so the topic is due again.
    assert sub.is_due(now) is True
    sub.last_attempted = now - timedelta(days=55)
    assert sub.is_due(now) is False


def test_no_failures_keeps_normal_cadence() -> None:
    now = datetime.now(UTC)
    sub = _sub(last_synced=now - timedelta(days=8))
    assert sub.is_due(now) is True
    sub.last_synced = now - timedelta(days=6)
    assert sub.is_due(now) is False


def test_brake_state_round_trips_serialization() -> None:
    now = datetime.now(UTC)
    sub = _sub(last_attempted=now, consecutive_paid_failures=3)
    restored = Subscription.from_dict(sub.to_dict())
    assert restored.consecutive_paid_failures == 3
    assert restored.last_attempted == sub.last_attempted


def test_legacy_records_without_brake_fields_load_cleanly() -> None:
    restored = Subscription.from_dict({"topic": "Legacy", "query": "q"})
    assert restored.consecutive_paid_failures == 0
    assert restored.last_attempted is None
