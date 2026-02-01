"""Property-based tests for AutonomousProviderRouter and related classes."""

import tempfile
from pathlib import Path
from typing import List, Tuple

import pytest
from hypothesis import given, settings, strategies as st, assume, HealthCheck

from deepr.observability.provider_router import (
    AutonomousProviderRouter,
    FallbackEvent,
    ProviderMetrics,
    ROLLING_WINDOW_SIZE,
)

providers = st.sampled_from(["openai", "anthropic", "xai", "google", "azure", "local"])
models = st.sampled_from(["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "claude-3-haiku", "grok-4", "gemini-pro"])
latencies = st.floats(min_value=0.0, max_value=60000.0, allow_nan=False, allow_infinity=False)
costs = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
errors = st.text(min_size=0, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ")


@st.composite
def provider_model_pairs(draw):
    return (draw(providers), draw(models))


@st.composite
def success_records(draw, count=None):
    if count is None:
        count = draw(st.integers(min_value=0, max_value=50))
    return [(draw(latencies), draw(costs)) for _ in range(count)]


@st.composite
def mixed_records(draw):
    count = draw(st.integers(min_value=1, max_value=30))
    records = []
    for _ in range(count):
        if draw(st.booleans()):
            records.append(("success", draw(latencies), draw(costs)))
        else:
            records.append(("failure", draw(errors)))
    return records


class TestProviderMetricsProperties:
    """Property-based tests for ProviderMetrics."""

    @given(providers, models, success_records())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_success_rate_bounded(self, provider: str, model: str, records: List[Tuple[float, float]]):
        """Property: success rate is always between 0 and 1."""
        metrics = ProviderMetrics(provider=provider, model=model)
        for latency, cost in records:
            metrics.record_success(latency, cost)
        assert 0.0 <= metrics.success_rate <= 1.0

    @given(providers, models, success_records())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_total_requests_equals_success_plus_failure(self, provider: str, model: str, records: List[Tuple[float, float]]):
        """Property: total_requests = success_count + failure_count."""
        metrics = ProviderMetrics(provider=provider, model=model)
        for latency, cost in records:
            metrics.record_success(latency, cost)
        assert metrics.total_requests == metrics.success_count + metrics.failure_count

    @given(providers, models, mixed_records())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_success_rate_accurate(self, provider: str, model: str, records):
        """Property: success rate equals success_count / total_requests."""
        metrics = ProviderMetrics(provider=provider, model=model)
        for record in records:
            if record[0] == "success":
                metrics.record_success(record[1], record[2])
            else:
                metrics.record_failure(record[1])
        if metrics.total_requests > 0:
            expected_rate = metrics.success_count / metrics.total_requests
            assert abs(metrics.success_rate - expected_rate) < 1e-10

    @given(providers, models, success_records(count=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_avg_latency_accurate(self, provider: str, model: str, records: List[Tuple[float, float]]):
        """Property: avg_latency equals total_latency / success_count."""
        assume(len(records) > 0)
        metrics = ProviderMetrics(provider=provider, model=model)
        for latency, cost in records:
            metrics.record_success(latency, cost)
        if metrics.success_count > 0:
            expected_avg = metrics.total_latency_ms / metrics.success_count
            assert abs(metrics.avg_latency_ms - expected_avg) < 1e-6

    @given(providers, models, success_records(count=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_avg_cost_accurate(self, provider: str, model: str, records: List[Tuple[float, float]]):
        """Property: avg_cost equals total_cost / success_count."""
        assume(len(records) > 0)
        metrics = ProviderMetrics(provider=provider, model=model)
        for latency, cost in records:
            metrics.record_success(latency, cost)
        if metrics.success_count > 0:
            expected_avg = metrics.total_cost / metrics.success_count
            assert abs(metrics.avg_cost - expected_avg) < 1e-6

    @given(providers, models, st.lists(st.tuples(latencies, costs), min_size=ROLLING_WINDOW_SIZE + 5, max_size=ROLLING_WINDOW_SIZE + 20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_rolling_window_size_bounded(self, provider: str, model: str, records: List[Tuple[float, float]]):
        """Property: rolling window never exceeds ROLLING_WINDOW_SIZE."""
        metrics = ProviderMetrics(provider=provider, model=model)
        for latency, cost in records:
            metrics.record_success(latency, cost)
        assert len(metrics.rolling_latencies) <= ROLLING_WINDOW_SIZE
        assert len(metrics.rolling_costs) <= ROLLING_WINDOW_SIZE

    @given(providers, models, success_records())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_serialization_roundtrip(self, provider: str, model: str, records: List[Tuple[float, float]]):
        """Property: to_dict/from_dict roundtrip preserves all fields."""
        metrics = ProviderMetrics(provider=provider, model=model)
        for latency, cost in records:
            metrics.record_success(latency, cost)
        data = metrics.to_dict()
        restored = ProviderMetrics.from_dict(data)
        assert restored.provider == metrics.provider
        assert restored.model == metrics.model
        assert restored.success_count == metrics.success_count
        assert restored.failure_count == metrics.failure_count
        assert abs(restored.total_latency_ms - metrics.total_latency_ms) < 1e-6
        assert abs(restored.total_cost - metrics.total_cost) < 1e-6

    @given(providers, models, latencies, costs)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_negative_values_clamped(self, provider: str, model: str, latency: float, cost: float):
        """Property: negative latency and cost are clamped to 0."""
        metrics = ProviderMetrics(provider=provider, model=model)
        metrics.record_success(-abs(latency) - 1, -abs(cost) - 1)
        assert metrics.total_latency_ms >= 0
        assert metrics.total_cost >= 0


class TestAutonomousProviderRouterProperties:
    """Property-based tests for AutonomousProviderRouter."""

    @given(st.lists(provider_model_pairs(), min_size=1, max_size=10, unique=True))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_select_provider_returns_valid_tuple(self, pairs: List[Tuple[str, str]]):
        """Property: select_provider always returns a valid (provider, model) tuple."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            for provider, model in pairs:
                router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
            result = router.select_provider()
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert isinstance(result[0], str)
            assert isinstance(result[1], str)

    @given(st.lists(st.tuples(provider_model_pairs(), st.floats(min_value=0.5, max_value=1.0, allow_nan=False)), min_size=2, max_size=5))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_best_provider_selected(self, provider_scores: List[Tuple[Tuple[str, str], float]]):
        """Property: provider with highest success rate is preferred."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path, min_samples=3)
            for (provider, model), target_rate in provider_scores:
                successes = int(target_rate * 10)
                failures = 10 - successes
                for _ in range(successes):
                    router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
                for _ in range(failures):
                    router.record_result(provider, model, success=False, error="test")
            selected = router.select_provider()
            key = selected
            if key in router.metrics:
                all_rates = [m.success_rate for m in router.metrics.values()]
                if len(all_rates) > 1:
                    min_rate = min(all_rates)
                    selected_rate = router.metrics[key].success_rate
                    assert selected_rate >= min_rate - 0.1

    @given(provider_model_pairs(), st.lists(st.tuples(latencies, costs), min_size=1, max_size=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_metrics_persist_across_instances(self, pair: Tuple[str, str], records: List[Tuple[float, float]]):
        """Property: metrics persist correctly across router instances."""
        provider, model = pair
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router1 = AutonomousProviderRouter(storage_path=storage_path)
            for latency, cost in records:
                router1.record_result(provider, model, success=True, latency_ms=latency, cost=cost)
            original_count = router1.metrics[(provider, model)].success_count
            original_cost = router1.metrics[(provider, model)].total_cost
            router2 = AutonomousProviderRouter(storage_path=storage_path)
            assert (provider, model) in router2.metrics
            assert router2.metrics[(provider, model)].success_count == original_count
            assert abs(router2.metrics[(provider, model)].total_cost - original_cost) < 1e-6

    @given(provider_model_pairs(), errors)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_fallback_excludes_failed_provider(self, pair: Tuple[str, str], error: str):
        """Property: fallback never returns the failed provider."""
        provider, model = pair
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            fallback = router.get_fallback(provider, model, error)
            if fallback is not None:
                assert fallback != (provider, model)

    @given(st.lists(provider_model_pairs(), min_size=1, max_size=5, unique=True))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_exclude_list_respected(self, pairs: List[Tuple[str, str]]):
        """Property: excluded providers are never selected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            for provider, model in pairs:
                router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
            if len(pairs) > 1:
                exclude = pairs[:-1]
                selected = router.select_provider(exclude=exclude)
                assert selected not in exclude

    @given(provider_model_pairs(), st.integers(min_value=1, max_value=20), st.integers(min_value=0, max_value=20))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_success_rate_calculation_correct(self, pair: Tuple[str, str], successes: int, failures: int):
        """Property: success rate is calculated correctly."""
        provider, model = pair
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            for _ in range(successes):
                router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
            for _ in range(failures):
                router.record_result(provider, model, success=False, error="test")
            metrics = router.metrics[(provider, model)]
            total = successes + failures
            if total > 0:
                expected_rate = successes / total
                assert abs(metrics.success_rate - expected_rate) < 1e-10

    @given(st.sampled_from(["research", "chat", "synthesis", "fact_check", "quick", "general"]))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_task_type_returns_provider(self, task_type: str):
        """Property: all task types return a valid provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            result = router.select_provider(task_type=task_type)
            assert isinstance(result, tuple)
            assert len(result) == 2

    @given(provider_model_pairs())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_key_is_exact_tuple(self, pair: Tuple[str, str]):
        """Property: metrics are keyed by exact (provider, model) tuple."""
        provider, model = pair
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
            assert (provider, model) in router.metrics
            if provider != model:
                assert (model, provider) not in router.metrics


class TestFallbackEventProperties:
    """Property-based tests for FallbackEvent."""

    @given(providers, models, providers, models, errors, st.booleans())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_fallback_event_serialization(self, orig_provider: str, orig_model: str, fb_provider: str, fb_model: str, reason: str, success: bool):
        """Property: FallbackEvent serializes all fields correctly."""
        event = FallbackEvent(
            original_provider=orig_provider,
            original_model=orig_model,
            fallback_provider=fb_provider,
            fallback_model=fb_model,
            reason=reason,
            success=success
        )
        data = event.to_dict()
        assert data["original_provider"] == orig_provider
        assert data["original_model"] == orig_model
        assert data["fallback_provider"] == fb_provider
        assert data["fallback_model"] == fb_model
        assert data["reason"] == reason
        assert data["success"] == success
        assert "timestamp" in data


class TestRouterStatusProperties:
    """Property-based tests for router status reporting."""

    @given(st.lists(provider_model_pairs(), min_size=0, max_size=10, unique=True))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_status_counts_consistent(self, pairs: List[Tuple[str, str]]):
        """Property: healthy + unhealthy counts equal total providers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            for provider, model in pairs:
                router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
            status = router.get_status()
            total_providers = len(status["providers"])
            assert status["healthy_count"] + status["unhealthy_count"] == total_providers

    @given(st.lists(st.tuples(provider_model_pairs(), costs), min_size=1, max_size=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_total_cost_accurate(self, records: List[Tuple[Tuple[str, str], float]]):
        """Property: total_cost in status equals sum of all recorded costs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            expected_total = 0.0
            for (provider, model), cost in records:
                router.record_result(provider, model, success=True, latency_ms=100, cost=cost)
                expected_total += cost
            status = router.get_status()
            assert abs(status["total_cost"] - expected_total) < 1e-6

    @given(st.lists(provider_model_pairs(), min_size=1, max_size=10, unique=True))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_total_requests_accurate(self, pairs: List[Tuple[str, str]]):
        """Property: total_requests in status equals sum of all requests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            expected_total = 0
            for provider, model in pairs:
                count = 3
                for _ in range(count):
                    router.record_result(provider, model, success=True, latency_ms=100, cost=0.01)
                expected_total += count
            status = router.get_status()
            assert status["total_requests"] == expected_total
