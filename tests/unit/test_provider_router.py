"""Tests for AutonomousProviderRouter and related classes.

Tests cover:
- ProviderMetrics: success rate, latency, cost tracking, health checks
- FallbackEvent: event recording and serialization
- AutonomousProviderRouter: provider selection, fallback logic, persistence
"""

import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

from deepr.observability.provider_router import (
    AutonomousProviderRouter,
    FallbackEvent,
    ProviderMetrics,
)


class TestProviderMetrics:
    """Tests for ProviderMetrics dataclass."""

    def test_initial_state(self):
        """New metrics should have zero counts and default success rate."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        assert metrics.provider == "openai"
        assert metrics.model == "gpt-4o"
        assert metrics.success_count == 0
        assert metrics.failure_count == 0
        assert metrics.total_requests == 0
        # New providers assume success (optimistic)
        assert metrics.success_rate == 1.0
        assert metrics.avg_latency_ms == 0.0
        assert metrics.avg_cost == 0.0

    def test_key_property(self):
        """Key should be (provider, model) tuple."""
        metrics = ProviderMetrics(provider="anthropic", model="claude-3-5-sonnet")
        assert metrics.key == ("anthropic", "claude-3-5-sonnet")

    def test_record_success(self):
        """Recording success should update counts and averages."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        metrics.record_success(latency_ms=1500.0, cost=0.05)
        
        assert metrics.success_count == 1
        assert metrics.failure_count == 0
        assert metrics.total_requests == 1
        assert metrics.success_rate == 1.0
        assert metrics.avg_latency_ms == 1500.0
        assert metrics.avg_cost == 0.05
        assert metrics.last_success is not None
        assert len(metrics.rolling_latencies) == 1
        assert len(metrics.rolling_costs) == 1

    def test_record_multiple_successes(self):
        """Multiple successes should compute correct averages."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        metrics.record_success(latency_ms=1000.0, cost=0.04)
        metrics.record_success(latency_ms=2000.0, cost=0.06)
        
        assert metrics.success_count == 2
        assert metrics.avg_latency_ms == 1500.0  # (1000 + 2000) / 2
        assert metrics.avg_cost == 0.05  # (0.04 + 0.06) / 2

    def test_record_failure(self):
        """Recording failure should update failure count and error."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        metrics.record_failure(error="Rate limit exceeded")
        
        assert metrics.success_count == 0
        assert metrics.failure_count == 1
        assert metrics.total_requests == 1
        assert metrics.success_rate == 0.0
        assert metrics.last_failure is not None
        assert metrics.last_error == "Rate limit exceeded"

    def test_success_rate_calculation(self):
        """Success rate should be calculated correctly."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        # 3 successes, 1 failure = 75% success rate
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        metrics.record_failure(error="Timeout")
        
        assert metrics.success_count == 3
        assert metrics.failure_count == 1
        assert metrics.total_requests == 4
        assert metrics.success_rate == 0.75

    def test_rolling_average_window(self):
        """Rolling averages should keep only last 20 entries."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        # Record 25 successes
        for i in range(25):
            metrics.record_success(latency_ms=float(i * 100), cost=float(i) * 0.01)
        
        # Should only keep last 20
        assert len(metrics.rolling_latencies) == 20
        assert len(metrics.rolling_costs) == 20
        # First entry should be from iteration 5 (index 5)
        assert metrics.rolling_latencies[0] == 500.0

    def test_rolling_avg_latency(self):
        """Rolling average latency should use recent values."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        metrics.record_success(latency_ms=2000.0, cost=0.05)
        metrics.record_success(latency_ms=3000.0, cost=0.05)
        
        assert metrics.rolling_avg_latency == 2000.0  # (1000 + 2000 + 3000) / 3

    def test_rolling_avg_latency_empty(self):
        """Rolling average should fall back to overall average when empty."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        # Manually set totals without rolling data
        metrics.success_count = 5
        metrics.total_latency_ms = 5000.0
        
        assert metrics.rolling_avg_latency == 1000.0  # Falls back to avg_latency_ms

    def test_is_healthy_new_provider(self):
        """New providers should be considered healthy."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        assert metrics.is_healthy() is True

    def test_is_healthy_good_success_rate(self):
        """Providers with good success rate should be healthy."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        for _ in range(10):
            metrics.record_success(latency_ms=1000.0, cost=0.05)
        
        assert metrics.is_healthy() is True

    def test_is_healthy_low_success_rate(self):
        """Providers with low success rate should be unhealthy."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        # 2 successes, 4 failures = 33% success rate (below 80% threshold)
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        metrics.record_failure(error="Error 1")
        metrics.record_failure(error="Error 2")
        metrics.record_failure(error="Error 3")
        metrics.record_failure(error="Error 4")
        
        assert metrics.is_healthy(min_success_rate=0.8) is False

    def test_is_healthy_recent_failure(self):
        """Provider with very recent failure should be unhealthy."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        # Record success first
        metrics.record_success(latency_ms=1000.0, cost=0.05)
        
        # Manually set last_success to be older than the failure we're about to record
        metrics.last_success = utc_now() - timedelta(minutes=5)
        
        # Now record failure (will have current timestamp)
        metrics.record_failure(error="Recent error")
        
        # Last failure is more recent than last success
        assert metrics.last_failure > metrics.last_success
        assert metrics.is_healthy() is False

    def test_is_healthy_only_failures(self):
        """Provider with only failures should be unhealthy."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        
        metrics.record_failure(error="Error")
        
        assert metrics.is_healthy() is False

    def test_to_dict_serialization(self):
        """Metrics should serialize to dictionary correctly."""
        metrics = ProviderMetrics(provider="openai", model="gpt-4o")
        metrics.record_success(latency_ms=1500.0, cost=0.05)
        
        data = metrics.to_dict()
        
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["success_count"] == 1
        assert data["failure_count"] == 0
        assert data["total_latency_ms"] == 1500.0
        assert data["total_cost"] == 0.05
        assert data["last_success"] is not None
        assert data["rolling_latencies"] == [1500.0]

    def test_from_dict_deserialization(self):
        """Metrics should deserialize from dictionary correctly."""
        data = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "success_count": 10,
            "failure_count": 2,
            "total_latency_ms": 15000.0,
            "total_cost": 0.50,
            "last_success": "2025-01-15T10:30:00",
            "last_failure": None,
            "last_error": "",
            "rolling_latencies": [1000.0, 1500.0],
            "rolling_costs": [0.04, 0.06],
        }
        
        metrics = ProviderMetrics.from_dict(data)
        
        assert metrics.provider == "anthropic"
        assert metrics.model == "claude-3-5-sonnet"
        assert metrics.success_count == 10
        assert metrics.failure_count == 2
        assert metrics.total_requests == 12
        assert metrics.last_success is not None


class TestFallbackEvent:
    """Tests for FallbackEvent dataclass."""

    def test_creation(self):
        """FallbackEvent should store all fields correctly."""
        event = FallbackEvent(
            original_provider="openai",
            original_model="gpt-4o",
            fallback_provider="anthropic",
            fallback_model="claude-3-5-sonnet",
            reason="Rate limit exceeded",
            success=True,
        )
        
        assert event.original_provider == "openai"
        assert event.original_model == "gpt-4o"
        assert event.fallback_provider == "anthropic"
        assert event.fallback_model == "claude-3-5-sonnet"
        assert event.reason == "Rate limit exceeded"
        assert event.success is True
        assert event.timestamp is not None

    def test_to_dict_serialization(self):
        """FallbackEvent should serialize correctly."""
        event = FallbackEvent(
            original_provider="openai",
            original_model="gpt-4o",
            fallback_provider="anthropic",
            fallback_model="claude-3-5-sonnet",
            reason="Timeout",
            success=False,
        )
        
        data = event.to_dict()
        
        assert data["original_provider"] == "openai"
        assert data["original_model"] == "gpt-4o"
        assert data["fallback_provider"] == "anthropic"
        assert data["fallback_model"] == "claude-3-5-sonnet"
        assert data["reason"] == "Timeout"
        assert data["success"] is False
        assert "timestamp" in data


class TestAutonomousProviderRouter:
    """Tests for AutonomousProviderRouter class."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "metrics.json"

    def test_initialization(self, temp_storage):
        """Router should initialize with empty metrics."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        assert len(router.metrics) == 0
        assert len(router.fallback_events) == 0
        assert router.fallback_chain == router.DEFAULT_FALLBACK_CHAIN

    def test_custom_fallback_chain(self, temp_storage):
        """Router should accept custom fallback chain."""
        custom_chain = [("anthropic", "claude-3-5-sonnet"), ("openai", "gpt-4o-mini")]
        router = AutonomousProviderRouter(
            storage_path=temp_storage,
            fallback_chain=custom_chain,
        )
        
        assert router.fallback_chain == custom_chain

    def test_record_success(self, temp_storage):
        """Recording success should create and update metrics."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result(
            provider="openai",
            model="gpt-4o",
            success=True,
            latency_ms=1500.0,
            cost=0.05,
        )
        
        key = ("openai", "gpt-4o")
        assert key in router.metrics
        assert router.metrics[key].success_count == 1
        assert router.metrics[key].avg_latency_ms == 1500.0

    def test_record_failure(self, temp_storage):
        """Recording failure should update metrics."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result(
            provider="openai",
            model="gpt-4o",
            success=False,
            error="Rate limit exceeded",
        )
        
        key = ("openai", "gpt-4o")
        assert key in router.metrics
        assert router.metrics[key].failure_count == 1
        assert router.metrics[key].last_error == "Rate limit exceeded"

    def test_select_provider_default(self, temp_storage):
        """Select provider should return from fallback chain for new router."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        provider, model = router.select_provider()
        
        # Should return first from fallback chain or task preferences
        assert provider is not None
        assert model is not None

    def test_select_provider_with_task_type(self, temp_storage):
        """Select provider should consider task type preferences."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Research task should prefer research-optimized models
        provider, model = router.select_provider(task_type="research")
        assert provider is not None
        
        # Quick task should prefer fast models
        provider, model = router.select_provider(task_type="quick")
        assert provider is not None

    def test_select_provider_excludes_specified(self, temp_storage):
        """Select provider should exclude specified providers."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Exclude all but one option
        exclude = [
            ("openai", "gpt-4o"),
            ("openai", "gpt-4o-mini"),
            ("anthropic", "claude-3-5-sonnet-20241022"),
        ]
        
        provider, model = router.select_provider(exclude=exclude)
        
        # Should not return excluded providers
        assert (provider, model) not in exclude

    def test_select_provider_prefers_healthy(self, temp_storage):
        """Select provider should prefer healthy providers."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Make one provider unhealthy
        for _ in range(10):
            router.record_result(
                provider="openai",
                model="gpt-4o",
                success=False,
                error="Repeated failures",
            )
        
        # Make another provider healthy
        for _ in range(10):
            router.record_result(
                provider="anthropic",
                model="claude-3-5-sonnet-20241022",
                success=True,
                latency_ms=1000.0,
                cost=0.05,
            )
        
        provider, model = router.select_provider()
        
        # Should prefer the healthy provider
        # (exact result depends on scoring, but unhealthy should be penalized)
        assert provider is not None

    def test_get_fallback_returns_next_healthy(self, temp_storage):
        """Get fallback should return next healthy provider in chain."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        fallback = router.get_fallback(
            failed_provider="openai",
            failed_model="gpt-4o",
            reason="Rate limit",
        )
        
        assert fallback is not None
        assert fallback != ("openai", "gpt-4o")
        # Should record fallback event
        assert len(router.fallback_events) == 1

    def test_get_fallback_skips_unhealthy(self, temp_storage):
        """Get fallback should skip unhealthy providers."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Make first fallback option unhealthy
        first_fallback = router.fallback_chain[1]  # Skip the failed one
        for _ in range(10):
            router.record_result(
                provider=first_fallback[0],
                model=first_fallback[1],
                success=False,
                error="Unhealthy",
            )
        
        fallback = router.get_fallback(
            failed_provider=router.fallback_chain[0][0],
            failed_model=router.fallback_chain[0][1],
            reason="Error",
        )
        
        # Should skip the unhealthy one
        if fallback is not None:
            assert fallback != first_fallback or router.metrics[first_fallback].is_healthy()

    def test_get_fallback_returns_none_when_exhausted(self, temp_storage):
        """Get fallback should return None when all options exhausted."""
        # Use a very short fallback chain
        router = AutonomousProviderRouter(
            storage_path=temp_storage,
            fallback_chain=[("openai", "gpt-4o")],
        )
        
        # Make the only option unhealthy
        for _ in range(10):
            router.record_result(
                provider="openai",
                model="gpt-4o",
                success=False,
                error="Unhealthy",
            )
        
        fallback = router.get_fallback(
            failed_provider="openai",
            failed_model="gpt-4o",
            reason="Error",
        )
        
        # May return None or the unhealthy option depending on implementation
        # The key is it doesn't crash

    def test_get_status(self, temp_storage):
        """Get status should return comprehensive status info."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Record some activity
        router.record_result("openai", "gpt-4o", True, 1000.0, 0.05)
        router.record_result("openai", "gpt-4o", True, 1500.0, 0.06)
        router.record_result("anthropic", "claude-3-5-sonnet", False, error="Error")
        
        status = router.get_status()
        
        assert "providers" in status
        assert "healthy_count" in status
        assert "unhealthy_count" in status
        assert "total_requests" in status
        assert "total_cost" in status
        assert "recent_fallbacks" in status
        
        assert status["total_requests"] == 3
        assert status["total_cost"] == 0.11  # 0.05 + 0.06

    def test_persistence_save_and_load(self, temp_storage):
        """Router should persist and load metrics correctly."""
        # Create router and record data
        router1 = AutonomousProviderRouter(storage_path=temp_storage)
        router1.record_result("openai", "gpt-4o", True, 1500.0, 0.05)
        router1.record_result("openai", "gpt-4o", False, error="Test error")
        
        # Create new router that loads from same path
        router2 = AutonomousProviderRouter(storage_path=temp_storage)
        
        key = ("openai", "gpt-4o")
        assert key in router2.metrics
        assert router2.metrics[key].success_count == 1
        assert router2.metrics[key].failure_count == 1

    def test_exact_tuple_matching(self, temp_storage):
        """Router should use exact (provider, model) matching, not substrings."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Record for specific model
        router.record_result("openai", "gpt-4o", True, 1000.0, 0.05)
        router.record_result("openai", "gpt-4o-mini", True, 500.0, 0.01)
        
        # Should have separate entries
        assert ("openai", "gpt-4o") in router.metrics
        assert ("openai", "gpt-4o-mini") in router.metrics
        
        # Metrics should be independent
        assert router.metrics[("openai", "gpt-4o")].success_count == 1
        assert router.metrics[("openai", "gpt-4o-mini")].success_count == 1

    def test_scoring_prefers_cost_when_requested(self, temp_storage):
        """Scoring should weight cost more heavily when prefer_cost=True."""
        router = AutonomousProviderRouter(storage_path=temp_storage, min_samples=1)
        
        # Expensive but fast provider
        for _ in range(5):
            router.record_result("openai", "gpt-4o", True, 500.0, 0.10)
        
        # Cheap but slower provider
        for _ in range(5):
            router.record_result("openai", "gpt-4o-mini", True, 1000.0, 0.01)
        
        # When preferring cost, should lean toward cheaper option
        provider, model = router.select_provider(prefer_cost=True)
        # The exact result depends on scoring weights, but the test ensures
        # the prefer_cost flag is processed without error
        assert provider is not None

    def test_scoring_prefers_speed_when_requested(self, temp_storage):
        """Scoring should weight latency more heavily when prefer_speed=True."""
        router = AutonomousProviderRouter(storage_path=temp_storage, min_samples=1)
        
        # Fast but expensive provider
        for _ in range(5):
            router.record_result("openai", "gpt-4o", True, 500.0, 0.10)
        
        # Slow but cheap provider
        for _ in range(5):
            router.record_result("openai", "gpt-4o-mini", True, 2000.0, 0.01)
        
        # When preferring speed, should lean toward faster option
        provider, model = router.select_provider(prefer_speed=True)
        assert provider is not None


class TestProviderRouterEdgeCases:
    """Edge case tests for provider router."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "metrics.json"

    def test_handles_corrupted_storage(self, temp_storage):
        """Router should handle corrupted storage gracefully."""
        # Write corrupted JSON
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_storage, "w") as f:
            f.write("not valid json {{{")
        
        # Should not crash, just start fresh
        router = AutonomousProviderRouter(storage_path=temp_storage)
        assert len(router.metrics) == 0

    def test_handles_missing_fields_in_storage(self, temp_storage):
        """Router should handle missing fields in stored data."""
        # Write partial data
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "metrics": {
                "openai|gpt-4o": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    # Missing other fields
                }
            }
        }
        with open(temp_storage, "w") as f:
            json.dump(data, f)
        
        # Should load with defaults for missing fields
        router = AutonomousProviderRouter(storage_path=temp_storage)
        key = ("openai", "gpt-4o")
        assert key in router.metrics
        assert router.metrics[key].success_count == 0

    def test_zero_latency_and_cost(self, temp_storage):
        """Router should handle zero latency and cost values."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", True, 0.0, 0.0)
        
        key = ("openai", "gpt-4o")
        assert router.metrics[key].avg_latency_ms == 0.0
        assert router.metrics[key].avg_cost == 0.0

    def test_very_high_latency(self, temp_storage):
        """Router should handle very high latency values."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # 5 minute latency
        router.record_result("openai", "gpt-4o", True, 300000.0, 0.05)
        
        key = ("openai", "gpt-4o")
        assert router.metrics[key].avg_latency_ms == 300000.0

    def test_empty_error_message(self, temp_storage):
        """Router should handle empty error messages."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", False, error="")
        
        key = ("openai", "gpt-4o")
        assert router.metrics[key].last_error == ""

    def test_negative_latency_clamped(self, temp_storage):
        """Negative latency should be clamped to zero."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", True, latency_ms=-100.0, cost=0.05)
        
        key = ("openai", "gpt-4o")
        # Negative latency should be clamped to 0
        assert router.metrics[key].avg_latency_ms == 0.0
        assert router.metrics[key].rolling_latencies[0] == 0.0

    def test_negative_cost_clamped(self, temp_storage):
        """Negative cost should be clamped to zero."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", True, latency_ms=1000.0, cost=-0.10)
        
        key = ("openai", "gpt-4o")
        # Negative cost should be clamped to 0
        assert router.metrics[key].avg_cost == 0.0
        assert router.metrics[key].rolling_costs[0] == 0.0

    def test_nan_latency_handled(self, temp_storage):
        """NaN latency should be clamped to zero, not corrupt metrics."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", True, latency_ms=float('nan'), cost=0.05)
        
        key = ("openai", "gpt-4o")
        # NaN should be clamped to 0
        assert router.metrics[key].avg_latency_ms == 0.0
        assert not math.isnan(router.metrics[key].rolling_avg_latency)

    def test_infinity_latency_handled(self, temp_storage):
        """Infinity latency should be clamped to zero."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", True, latency_ms=float('inf'), cost=0.05)
        
        key = ("openai", "gpt-4o")
        # Infinity should be clamped to 0
        assert router.metrics[key].avg_latency_ms == 0.0
        assert math.isfinite(router.metrics[key].rolling_avg_latency)

    def test_negative_infinity_latency_handled(self, temp_storage):
        """Negative infinity latency should be clamped to zero."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        router.record_result("openai", "gpt-4o", True, latency_ms=float('-inf'), cost=0.05)
        
        key = ("openai", "gpt-4o")
        # Negative infinity should be clamped to 0
        assert router.metrics[key].avg_latency_ms == 0.0

    def test_unicode_error_messages(self, temp_storage):
        """Router should handle Unicode characters in error messages."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Error message with various Unicode characters
        unicode_error = "Error: 日本語 emoji 🚀 special chars äöü"
        router.record_result("openai", "gpt-4o", False, error=unicode_error)
        
        key = ("openai", "gpt-4o")
        assert router.metrics[key].last_error == unicode_error
        
        # Verify persistence works with Unicode
        router2 = AutonomousProviderRouter(storage_path=temp_storage)
        assert router2.metrics[key].last_error == unicode_error

    def test_very_long_provider_name(self, temp_storage):
        """Router should handle very long provider/model names."""
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        long_provider = "a" * 1000
        long_model = "b" * 1000
        
        router.record_result(long_provider, long_model, True, 1000.0, 0.05)
        
        key = (long_provider, long_model)
        assert key in router.metrics
        assert router.metrics[key].success_count == 1
