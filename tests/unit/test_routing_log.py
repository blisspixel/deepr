"""Tests for routing decision log and analytics."""

import pytest

from deepr.observability.routing_log import (
    RoutingDecisionEvent,
    RoutingDecisionLog,
)


@pytest.fixture
def log(tmp_path):
    return RoutingDecisionLog(log_path=tmp_path / "routing.jsonl")


def _make_event(provider="openai", model="gpt-5.4", cost=0.30, confidence=0.85, **kwargs):
    return RoutingDecisionEvent(
        provider=provider,
        model=model,
        complexity="moderate",
        task_type="reasoning",
        cost_estimate=cost,
        confidence=confidence,
        reasoning="test",
        **kwargs,
    )


class TestRoutingDecisionEvent:
    def test_to_dict(self):
        e = _make_event()
        d = e.to_dict()
        assert d["provider"] == "openai"
        assert d["cost_estimate"] == 0.30
        assert "actual_cost" not in d  # None excluded

    def test_to_dict_with_actuals(self):
        e = _make_event(actual_cost=0.25, success=True)
        d = e.to_dict()
        assert d["actual_cost"] == 0.25
        assert d["success"] is True

    def test_roundtrip(self):
        original = _make_event(query_hash="abc123")
        restored = RoutingDecisionEvent.from_dict(original.to_dict())
        assert restored.provider == "openai"
        assert restored.query_hash == "abc123"
        assert restored.cost_estimate == 0.30


class TestRoutingDecisionLog:
    def test_record_and_read(self, log):
        log.record(_make_event())
        log.record(_make_event(provider="xai", model="grok-4.20"))

        events = log.get_events()
        assert len(events) == 2

    def test_filter_by_provider(self, log):
        log.record(_make_event(provider="openai"))
        log.record(_make_event(provider="xai"))
        log.record(_make_event(provider="openai"))

        events = log.get_events(provider="openai")
        assert len(events) == 2

    def test_filter_by_model(self, log):
        log.record(_make_event(model="gpt-5.4"))
        log.record(_make_event(model="gpt-4.1"))

        events = log.get_events(model="gpt-4.1")
        assert len(events) == 1

    def test_limit(self, log):
        for _ in range(10):
            log.record(_make_event())

        events = log.get_events(limit=3)
        assert len(events) == 3

    def test_empty_log(self, log):
        assert log.get_events() == []
        assert log.cost_distribution() == {"count": 0}
        assert log.model_usage() == {}


class TestCostDistribution:
    def test_basic_stats(self, log):
        for cost in [0.10, 0.20, 0.30, 0.40, 0.50]:
            log.record(_make_event(cost=cost))

        dist = log.cost_distribution()
        assert dist["count"] == 5
        assert dist["mean"] == 0.30
        assert dist["min"] == 0.10
        assert dist["max"] == 0.50


class TestModelUsage:
    def test_counts(self, log):
        log.record(_make_event(provider="openai", model="gpt-5.4"))
        log.record(_make_event(provider="openai", model="gpt-5.4"))
        log.record(_make_event(provider="xai", model="grok-4.20"))

        usage = log.model_usage()
        assert usage["openai/gpt-5.4"] == 2
        assert usage["xai/grok-4.20"] == 1


class TestRoutingDrift:
    def test_insufficient_data(self, log):
        log.record(_make_event())
        result = log.detect_routing_drift(window=50)
        assert result["sufficient_data"] is False

    def test_detects_confidence_drift(self, log):
        # 50 high-confidence events followed by 50 low-confidence
        for _ in range(50):
            log.record(_make_event(confidence=0.90, cost=0.10))
        for _ in range(50):
            log.record(_make_event(confidence=0.60, cost=0.10))

        result = log.detect_routing_drift(window=50)
        assert result["sufficient_data"] is True
        assert result["confidence_drift"] < -0.20
        assert result["drift_alert"] is True

    def test_no_drift(self, log):
        for _ in range(100):
            log.record(_make_event(confidence=0.80, cost=0.20))

        result = log.detect_routing_drift(window=50)
        assert result["sufficient_data"] is True
        assert abs(result["confidence_drift"]) < 0.01
        assert result["drift_alert"] is False


class TestCostAnomalies:
    def test_detects_outliers(self, log):
        # 19 normal + 1 extreme — enough data for stable stdev
        for _ in range(19):
            log.record(_make_event(cost=0.10))
        log.record(_make_event(cost=5.00))

        anomalies = log.detect_cost_anomalies(last_n=20)
        assert len(anomalies) >= 1
        assert anomalies[0]["cost"] == 5.00

    def test_no_anomalies_when_uniform(self, log):
        for _ in range(20):
            log.record(_make_event(cost=0.10))

        anomalies = log.detect_cost_anomalies(last_n=20)
        assert len(anomalies) == 0
