"""Regression test: ``RoutingDecisionLog.get_events`` now returns the
LAST N matching rows. The previous implementation returned the FIRST N
(oldest), which silently broke every analytics query in this module
(cost_distribution, model_usage, detect_routing_drift, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from deepr.observability.routing_log import RoutingDecisionEvent, RoutingDecisionLog


@pytest.fixture
def log(tmp_path: Path):
    return RoutingDecisionLog(log_path=tmp_path / "routing.jsonl")


def _make_event(idx: int) -> RoutingDecisionEvent:
    return RoutingDecisionEvent(
        timestamp=datetime.now(timezone.utc),
        provider="openai",
        model=f"gpt-{idx}",
        complexity="medium",
        confidence=0.9,
        reasoning=f"event {idx}",
        cost_estimate=0.10,
    )


class TestLastNSemantics:
    def test_get_events_returns_most_recent(self, log):
        for i in range(20):
            log.record(_make_event(i))

        events = log.get_events(limit=5)
        # The five returned events must be the LAST five recorded, in
        # insertion order — not the first five.
        assert len(events) == 5
        assert [e.model for e in events] == [f"gpt-{i}" for i in range(15, 20)]

    def test_no_limit_returns_all(self, log):
        for i in range(7):
            log.record(_make_event(i))
        events = log.get_events(limit=1000)
        assert len(events) == 7

    def test_filter_with_limit(self, log):
        for i in range(10):
            log.record(_make_event(i))
        # Filter to specific model — should still return up to ``limit``
        # MOST RECENT matches.
        events = log.get_events(model="gpt-7", limit=5)
        assert len(events) == 1
        assert events[0].model == "gpt-7"
