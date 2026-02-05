"""Autonomous Provider Router for intelligent provider selection.

Provides:
- Performance metrics tracking per (provider, model) tuple
- Intelligent provider selection based on cost, latency, success rate
- Automatic fallback on failures
- Graceful degradation to cheaper models
- Circuit breaker integration for fail-fast behavior

Usage:
    from deepr.observability.provider_router import AutonomousProviderRouter

    router = AutonomousProviderRouter()

    # Select best provider for a task
    provider, model = router.select_provider(task_type="research")

    # Record result
    router.record_result(provider, model, success=True, latency_ms=1500, cost=0.05)
"""

import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from deepr.observability.circuit_breaker import CircuitBreakerRegistry

# Module logger for debugging persistence and validation issues
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string ensuring timezone awareness."""
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# Configuration constants
ROLLING_WINDOW_SIZE = 20  # Number of recent samples for rolling averages
MAX_STORED_FALLBACK_EVENTS = 100  # Maximum fallback events to persist


@dataclass
class ProviderMetrics:
    """Performance metrics for a provider/model combination.

    Attributes:
        provider: Provider name
        model: Model name
        success_count: Number of successful requests
        failure_count: Number of failed requests
        total_latency_ms: Total latency in milliseconds
        total_cost: Total cost in dollars
        last_success: Last successful request time
        last_failure: Last failed request time
        last_error: Last error message
        rolling_latencies: Recent latencies for rolling average
        rolling_costs: Recent costs for rolling average
    """

    provider: str
    model: str
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    total_cost: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error: str = ""
    rolling_latencies: List[float] = field(default_factory=list)
    rolling_costs: List[float] = field(default_factory=list)
    # Task type tracking: {task_type: {"success": count, "failure": count}}
    task_type_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str]:
        """Get unique key for this provider/model."""
        return (self.provider, self.model)

    @property
    def total_requests(self) -> int:
        """Get total request count."""
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        """Get success rate (0-1)."""
        if self.total_requests == 0:
            return 1.0  # Assume success for new providers
        return self.success_count / self.total_requests

    @property
    def avg_latency_ms(self) -> float:
        """Get average latency in milliseconds."""
        if self.success_count == 0:
            return 0.0
        return self.total_latency_ms / self.success_count

    @property
    def avg_cost(self) -> float:
        """Get average cost per request."""
        if self.success_count == 0:
            return 0.0
        return self.total_cost / self.success_count

    @property
    def rolling_avg_latency(self) -> float:
        """Get rolling average latency."""
        if not self.rolling_latencies:
            return self.avg_latency_ms
        return sum(self.rolling_latencies) / len(self.rolling_latencies)

    @property
    def rolling_avg_cost(self) -> float:
        """Get rolling average cost."""
        if not self.rolling_costs:
            return self.avg_cost
        return sum(self.rolling_costs) / len(self.rolling_costs)

    def _percentile(self, values: List[float], p: float) -> float:
        """Calculate percentile from a list of values.

        Args:
            values: List of numeric values
            p: Percentile (0-100)

        Returns:
            Percentile value, or 0.0 if no values
        """
        if not values:
            return 0.0
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_values) else f
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    @property
    def latency_p50(self) -> float:
        """Get 50th percentile (median) latency in milliseconds."""
        return self._percentile(self.rolling_latencies, 50)

    @property
    def latency_p95(self) -> float:
        """Get 95th percentile latency in milliseconds."""
        return self._percentile(self.rolling_latencies, 95)

    @property
    def latency_p99(self) -> float:
        """Get 99th percentile latency in milliseconds."""
        return self._percentile(self.rolling_latencies, 99)

    def get_latency_percentiles(self) -> Dict[str, float]:
        """Get all latency percentiles.

        Returns:
            Dictionary with p50, p95, p99 latency values
        """
        return {
            "p50": self.latency_p50,
            "p95": self.latency_p95,
            "p99": self.latency_p99,
            "avg": self.rolling_avg_latency,
        }

    def get_task_type_success_rate(self, task_type: str) -> float:
        """Get success rate for a specific task type.

        Args:
            task_type: Task type (research, chat, synthesis, etc.)

        Returns:
            Success rate (0-1), or 1.0 if no data
        """
        stats = self.task_type_stats.get(task_type)
        if not stats:
            return 1.0  # Assume success for new task types
        total = stats.get("success", 0) + stats.get("failure", 0)
        if total == 0:
            return 1.0
        return stats.get("success", 0) / total

    def get_all_task_type_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get success rates for all task types.

        Returns:
            Dictionary mapping task_type to stats including success_rate
        """
        result = {}
        for task_type, stats in self.task_type_stats.items():
            success = stats.get("success", 0)
            failure = stats.get("failure", 0)
            total = success + failure
            result[task_type] = {
                "success_count": success,
                "failure_count": failure,
                "total": total,
                "success_rate": success / total if total > 0 else 1.0,
            }
        return result

    def record_success(self, latency_ms: float, cost: float, task_type: Optional[str] = None):
        """Record a successful request.

        Args:
            latency_ms: Request latency (must be finite and non-negative)
            cost: Request cost (must be non-negative)
            task_type: Optional task type for per-task tracking

        Note:
            Invalid latency values (NaN, Inf, negative) are clamped to 0.
            Negative costs are clamped to 0.
        """
        # Validate and sanitize latency: must be finite and non-negative
        if not math.isfinite(latency_ms) or latency_ms < 0:
            logger.warning(f"Invalid latency_ms={latency_ms} for {self.provider}/{self.model}, clamping to 0")
            latency_ms = 0.0

        # Validate and sanitize cost: must be non-negative
        if cost < 0:
            logger.warning(f"Negative cost={cost} for {self.provider}/{self.model}, clamping to 0")
            cost = 0.0

        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.total_cost += cost
        self.last_success = datetime.now(timezone.utc)

        # Update rolling averages (keep last ROLLING_WINDOW_SIZE entries)
        self.rolling_latencies.append(latency_ms)
        self.rolling_costs.append(cost)
        if len(self.rolling_latencies) > ROLLING_WINDOW_SIZE:
            self.rolling_latencies = self.rolling_latencies[-ROLLING_WINDOW_SIZE:]
        if len(self.rolling_costs) > ROLLING_WINDOW_SIZE:
            self.rolling_costs = self.rolling_costs[-ROLLING_WINDOW_SIZE:]

        # Track task type success
        if task_type:
            if task_type not in self.task_type_stats:
                self.task_type_stats[task_type] = {"success": 0, "failure": 0}
            self.task_type_stats[task_type]["success"] += 1

    def record_failure(self, error: str, task_type: Optional[str] = None):
        """Record a failed request.

        Args:
            error: Error message
            task_type: Optional task type for per-task tracking
        """
        self.failure_count += 1
        self.last_failure = datetime.now(timezone.utc)
        self.last_error = error

        # Track task type failure
        if task_type:
            if task_type not in self.task_type_stats:
                self.task_type_stats[task_type] = {"success": 0, "failure": 0}
            self.task_type_stats[task_type]["failure"] += 1

    def is_healthy(self, min_success_rate: float = 0.8, max_age_hours: int = 24) -> bool:
        """Check if provider is healthy.

        Args:
            min_success_rate: Minimum success rate
            max_age_hours: Maximum hours since last success

        Returns:
            True if healthy
        """
        # Check success rate
        if self.total_requests >= 5 and self.success_rate < min_success_rate:
            return False

        # Check recency
        if self.last_failure and not self.last_success:
            return False

        if self.last_failure and self.last_success:
            if self.last_failure > self.last_success:
                # Last request failed
                hours_since = (datetime.now(timezone.utc) - self.last_failure).total_seconds() / 3600
                if hours_since < 1:  # Recent failure
                    return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_latency_ms": self.total_latency_ms,
            "total_cost": self.total_cost,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_error": self.last_error,
            "rolling_latencies": self.rolling_latencies,
            "rolling_costs": self.rolling_costs,
            "task_type_stats": self.task_type_stats,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderMetrics":
        return cls(
            provider=data["provider"],
            model=data["model"],
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            total_latency_ms=data.get("total_latency_ms", 0.0),
            total_cost=data.get("total_cost", 0.0),
            last_success=_parse_datetime(data.get("last_success")),
            last_failure=_parse_datetime(data.get("last_failure")),
            last_error=data.get("last_error", ""),
            rolling_latencies=data.get("rolling_latencies", []),
            rolling_costs=data.get("rolling_costs", []),
            task_type_stats=data.get("task_type_stats", {}),
        )


@dataclass
class FallbackEvent:
    """Record of a fallback event.

    Attributes:
        timestamp: When fallback occurred
        original_provider: Original provider
        original_model: Original model
        fallback_provider: Fallback provider
        fallback_model: Fallback model
        reason: Reason for fallback
        success: Whether fallback succeeded
    """

    original_provider: str
    original_model: str
    fallback_provider: str
    fallback_model: str
    reason: str
    success: bool
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "original_provider": self.original_provider,
            "original_model": self.original_model,
            "fallback_provider": self.fallback_provider,
            "fallback_model": self.fallback_model,
            "reason": self.reason,
            "success": self.success,
        }


class AutonomousProviderRouter:
    """Intelligent provider router with automatic fallback.

    Selects providers based on:
    - Success rate (weighted heavily)
    - Latency (log-scale normalized)
    - Cost (log-scale normalized)
    - Recency of failures

    Uses exact (provider, model) tuple matching - no substring matching.

    Attributes:
        metrics: Dictionary of provider metrics keyed by (provider, model) tuple
        fallback_events: List of fallback events
        fallback_chain: Ordered list of fallback options
    """

    # Default fallback chain (provider, model) tuples
    # Only includes actually supported providers: openai, azure, gemini, xai
    DEFAULT_FALLBACK_CHAIN = [
        ("openai", "o3-deep-research"),
        ("openai", "o4-mini-deep-research"),
        ("xai", "grok-4-fast"),
        ("gemini", "gemini-2.5-flash"),
    ]

    # Task-specific preferences (only supported providers)
    TASK_PREFERENCES = {
        "research": [("openai", "o3-deep-research"), ("openai", "o4-mini-deep-research")],
        "chat": [("openai", "gpt-4o"), ("xai", "grok-4-fast")],
        "synthesis": [("openai", "gpt-4o"), ("xai", "grok-4-fast")],
        "fact_check": [("xai", "grok-4-fast"), ("openai", "gpt-4o-mini")],
        "quick": [("xai", "grok-4-fast"), ("openai", "gpt-4o-mini")],
    }

    # Auto-disable settings
    AUTO_DISABLE_FAILURE_RATE = 0.5  # Disable at >50% failure rate
    AUTO_DISABLE_MIN_REQUESTS = 5  # Minimum requests before auto-disable kicks in
    AUTO_DISABLE_COOLDOWN_HOURS = 1  # Cooldown period before re-enabling

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        fallback_chain: Optional[List[Tuple[str, str]]] = None,
        min_samples: int = 3,
        circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None,
        exploration_rate: float = 0.1,
    ):
        """Initialize provider router.

        Args:
            storage_path: Path for persistence
            fallback_chain: Custom fallback chain
            min_samples: Minimum samples before using metrics
            circuit_breaker_registry: Optional circuit breaker registry (creates one if not provided)
            exploration_rate: Probability of exploring non-optimal provider (0-1, default 0.1 = 10%)
        """
        if storage_path is None:
            storage_path = Path("data/observability/provider_metrics.json")
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self.fallback_chain = fallback_chain or self.DEFAULT_FALLBACK_CHAIN
        self.min_samples = min_samples
        self.exploration_rate = max(0.0, min(1.0, exploration_rate))  # Clamp to [0, 1]

        # Metrics keyed by (provider, model) tuple
        self.metrics: Dict[Tuple[str, str], ProviderMetrics] = {}
        self.fallback_events: List[FallbackEvent] = []

        # Circuit breaker for fail-fast behavior
        self.circuit_breaker = circuit_breaker_registry or CircuitBreakerRegistry()

        self._load()

    def is_circuit_available(self, provider: str, model: str) -> bool:
        """Check if circuit breaker allows requests to provider/model.

        Args:
            provider: Provider name
            model: Model name

        Returns:
            True if requests should be attempted, False if circuit is open
        """
        return self.circuit_breaker.is_available(provider, model)

    def is_auto_disabled(self, provider: str, model: str) -> Tuple[bool, Optional[str]]:
        """Check if provider is auto-disabled due to high failure rate.

        Auto-disables providers with >50% failure rate after minimum requests,
        with a 1-hour cooldown before re-enabling.

        Args:
            provider: Provider name
            model: Model name

        Returns:
            Tuple of (is_disabled, reason) where reason explains why if disabled
        """
        key = (provider, model)
        metrics = self.metrics.get(key)

        if not metrics:
            return (False, None)

        # Need minimum requests before auto-disable kicks in
        if metrics.total_requests < self.AUTO_DISABLE_MIN_REQUESTS:
            return (False, None)

        # Check failure rate
        if metrics.success_rate < (1 - self.AUTO_DISABLE_FAILURE_RATE):
            # Check if in cooldown period
            if metrics.last_failure:
                hours_since_failure = (
                    datetime.now(timezone.utc) - metrics.last_failure
                ).total_seconds() / 3600

                if hours_since_failure < self.AUTO_DISABLE_COOLDOWN_HOURS:
                    return (
                        True,
                        f"Auto-disabled: {metrics.success_rate*100:.0f}% success rate "
                        f"({hours_since_failure*60:.0f}min cooldown remaining)",
                    )

        return (False, None)

    def get_disabled_providers(self) -> List[Dict[str, Any]]:
        """Get list of all auto-disabled providers.

        Returns:
            List of dicts with provider info and disable reason
        """
        disabled = []
        for key in self.metrics:
            provider, model = key
            is_disabled, reason = self.is_auto_disabled(provider, model)
            if is_disabled:
                disabled.append({
                    "provider": provider,
                    "model": model,
                    "reason": reason,
                })
        return disabled

    def record_result(
        self,
        provider: str,
        model: str,
        success: bool,
        latency_ms: float = 0.0,
        cost: float = 0.0,
        error: str = "",
        task_type: Optional[str] = None,
    ):
        """Record a request result.

        Updates both metrics and circuit breaker state.

        Args:
            provider: Provider name
            model: Model name
            success: Whether request succeeded
            latency_ms: Request latency
            cost: Request cost
            error: Error message if failed
            task_type: Optional task type for per-task tracking
        """
        key = (provider, model)

        if key not in self.metrics:
            self.metrics[key] = ProviderMetrics(provider=provider, model=model)

        if success:
            self.metrics[key].record_success(latency_ms, cost, task_type=task_type)
            # Update circuit breaker on success
            self.circuit_breaker.record_success(provider, model)
        else:
            self.metrics[key].record_failure(error, task_type=task_type)
            # Update circuit breaker on failure
            self.circuit_breaker.record_failure(provider, model, error)

        self._save()

    def select_provider(
        self,
        task_type: str = "general",
        prefer_cost: bool = False,
        prefer_speed: bool = False,
        exclude: Optional[List[Tuple[str, str]]] = None,
        force_exploit: bool = False,
    ) -> Tuple[str, str]:
        """Select best provider for a task.

        Uses exploration vs exploitation strategy:
        - With probability exploration_rate, picks a random non-optimal provider
        - Otherwise, picks the best scored provider

        Excludes providers with open circuits and auto-disabled providers.

        Args:
            task_type: Type of task
            prefer_cost: Prefer cheaper options
            prefer_speed: Prefer faster options
            exclude: Providers to exclude
            force_exploit: If True, skip exploration and always pick best (default False)

        Returns:
            Tuple of (provider, model)
        """
        import random

        exclude = exclude or []

        # Get candidates
        candidates = self._get_candidates(task_type)
        candidates = [c for c in candidates if c not in exclude]

        # Filter out providers with open circuits (fail-fast)
        candidates = [(p, m) for p, m in candidates if self.circuit_breaker.is_available(p, m)]

        # Filter out auto-disabled providers
        candidates = [(p, m) for p, m in candidates if not self.is_auto_disabled(p, m)[0]]

        if not candidates:
            # Fall back to default chain, checking circuit breakers and auto-disable
            for fallback in self.fallback_chain:
                if fallback not in exclude:
                    p, m = fallback
                    if self.circuit_breaker.is_available(p, m) and not self.is_auto_disabled(p, m)[0]:
                        return fallback
            # Last resort - return first available even if circuit is open
            # (better to try than to fail completely)
            for fallback in self.fallback_chain:
                if fallback not in exclude:
                    return fallback
            return ("openai", "o3-deep-research")

        # Score candidates
        scored = []
        for provider, model in candidates:
            score = self._score_provider(provider, model, prefer_cost=prefer_cost, prefer_speed=prefer_speed)
            scored.append((score, provider, model))

        # Sort by score (higher is better)
        scored.sort(reverse=True)

        # Exploration vs exploitation
        # With probability exploration_rate, pick a random non-optimal provider
        # This helps discover better providers and keeps metrics fresh
        if (
            not force_exploit
            and len(scored) > 1
            and self.exploration_rate > 0
            and random.random() < self.exploration_rate
        ):
            # Explore: pick randomly from non-best options
            explore_idx = random.randint(1, len(scored) - 1)
            logger.debug(
                "Exploration: picked %s/%s instead of best %s/%s",
                scored[explore_idx][1],
                scored[explore_idx][2],
                scored[0][1],
                scored[0][2],
            )
            return (scored[explore_idx][1], scored[explore_idx][2])

        # Exploit: return the best provider
        return (scored[0][1], scored[0][2])

    def get_fallback(self, failed_provider: str, failed_model: str, reason: str) -> Optional[Tuple[str, str]]:
        """Get fallback provider after failure.

        Checks circuit breaker state before selecting fallback.

        Args:
            failed_provider: Provider that failed
            failed_model: Model that failed
            reason: Reason for failure

        Returns:
            Fallback (provider, model) or None
        """
        failed_key = (failed_provider, failed_model)

        # Find next healthy provider in chain with available circuit
        for provider, model in self.fallback_chain:
            key = (provider, model)
            if key == failed_key:
                continue

            # Check circuit breaker first (fail-fast)
            if not self.circuit_breaker.is_available(provider, model):
                continue

            metrics = self.metrics.get(key)
            if metrics is None or metrics.is_healthy():
                # Record fallback event
                event = FallbackEvent(
                    original_provider=failed_provider,
                    original_model=failed_model,
                    fallback_provider=provider,
                    fallback_model=model,
                    reason=reason,
                    success=True,  # Will be updated later
                )
                self.fallback_events.append(event)
                self._save()

                return (provider, model)

        return None

    def get_status(self) -> Dict[str, Any]:
        """Get router status.

        Includes both metrics and circuit breaker status.

        Returns:
            Status dictionary
        """
        status = {
            "providers": {},
            "healthy_count": 0,
            "unhealthy_count": 0,
            "total_requests": 0,
            "total_cost": 0.0,
            "recent_fallbacks": [],
            "circuit_breakers": self.circuit_breaker.get_status(),
        }

        for key, metrics in self.metrics.items():
            provider, model = key
            is_healthy = metrics.is_healthy()
            circuit_available = self.circuit_breaker.is_available(provider, model)
            circuit = self.circuit_breaker.get_circuit(provider, model)

            status["providers"][f"{provider}/{model}"] = {
                "healthy": is_healthy,
                "circuit_state": circuit.state.value,
                "circuit_available": circuit_available,
                "success_rate": metrics.success_rate,
                "avg_latency_ms": metrics.rolling_avg_latency,
                "avg_cost": metrics.rolling_avg_cost,
                "total_requests": metrics.total_requests,
                "last_error": metrics.last_error if not is_healthy else None,
                "latency_percentiles": metrics.get_latency_percentiles(),
                "task_type_stats": metrics.get_all_task_type_stats(),
            }

            if is_healthy and circuit_available:
                status["healthy_count"] += 1
            else:
                status["unhealthy_count"] += 1

            status["total_requests"] += metrics.total_requests
            status["total_cost"] += metrics.total_cost

        # Recent fallbacks
        status["recent_fallbacks"] = [e.to_dict() for e in self.fallback_events[-10:]]

        return status

    def get_benchmark_data(self) -> Dict[str, Any]:
        """Get benchmark data for all providers.

        Returns detailed performance metrics suitable for comparison and analysis.

        Returns:
            Dictionary with provider benchmarks and summary statistics
        """
        benchmarks = []

        for key, metrics in self.metrics.items():
            provider, model = key
            percentiles = metrics.get_latency_percentiles()

            benchmark = {
                "provider": provider,
                "model": model,
                "total_requests": metrics.total_requests,
                "success_rate": metrics.success_rate,
                "latency": {
                    "p50_ms": percentiles["p50"],
                    "p95_ms": percentiles["p95"],
                    "p99_ms": percentiles["p99"],
                    "avg_ms": percentiles["avg"],
                },
                "cost": {
                    "avg_usd": metrics.rolling_avg_cost,
                    "total_usd": metrics.total_cost,
                },
                "task_types": metrics.get_all_task_type_stats(),
                "health": {
                    "is_healthy": metrics.is_healthy(),
                    "circuit_available": self.circuit_breaker.is_available(provider, model),
                    "last_success": metrics.last_success.isoformat() if metrics.last_success else None,
                    "last_failure": metrics.last_failure.isoformat() if metrics.last_failure else None,
                    "last_error": metrics.last_error if metrics.last_error else None,
                },
            }
            benchmarks.append(benchmark)

        # Sort by success rate, then total requests
        benchmarks.sort(key=lambda x: (-x["success_rate"], -x["total_requests"]))

        # Summary stats
        total_requests = sum(b["total_requests"] for b in benchmarks)
        total_cost = sum(b["cost"]["total_usd"] for b in benchmarks)
        healthy_count = sum(1 for b in benchmarks if b["health"]["is_healthy"])

        return {
            "benchmarks": benchmarks,
            "summary": {
                "total_providers": len(benchmarks),
                "healthy_providers": healthy_count,
                "unhealthy_providers": len(benchmarks) - healthy_count,
                "total_requests": total_requests,
                "total_cost_usd": total_cost,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_candidates(self, task_type: str) -> List[Tuple[str, str]]:
        """Get candidate providers for a task.

        Args:
            task_type: Type of task

        Returns:
            List of (provider, model) tuples
        """
        # Start with task-specific preferences
        candidates = list(self.TASK_PREFERENCES.get(task_type, []))

        # Add healthy providers from metrics
        for key, metrics in self.metrics.items():
            if key not in candidates and metrics.is_healthy():
                candidates.append(key)

        # Add fallback chain
        for fallback in self.fallback_chain:
            if fallback not in candidates:
                candidates.append(fallback)

        return candidates

    def _score_provider(
        self, provider: str, model: str, prefer_cost: bool = False, prefer_speed: bool = False
    ) -> float:
        """Score a provider for selection.

        Args:
            provider: Provider name
            model: Model name
            prefer_cost: Weight cost more heavily
            prefer_speed: Weight speed more heavily

        Returns:
            Score (higher is better)
        """
        key = (provider, model)
        metrics = self.metrics.get(key)

        if metrics is None or metrics.total_requests < self.min_samples:
            # New provider - give moderate score
            return 0.5

        # Base score from success rate (0-1)
        score = metrics.success_rate

        # Adjust for latency (log-scale normalization)
        # Lower latency = higher score
        if metrics.rolling_avg_latency > 0:
            latency_factor = 1.0 / (1.0 + math.log10(metrics.rolling_avg_latency / 1000 + 1))
            weight = 0.3 if prefer_speed else 0.15
            score += latency_factor * weight

        # Adjust for cost (log-scale normalization)
        # Lower cost = higher score
        if metrics.rolling_avg_cost > 0:
            cost_factor = 1.0 / (1.0 + math.log10(metrics.rolling_avg_cost * 100 + 1))
            weight = 0.3 if prefer_cost else 0.15
            score += cost_factor * weight

        # Penalty for recent failures
        if metrics.last_failure:
            hours_since = (datetime.now(timezone.utc) - metrics.last_failure).total_seconds() / 3600
            if hours_since < 1:
                score *= 0.5
            elif hours_since < 6:
                score *= 0.8

        return score

    def _save(self):
        """Save metrics to disk using atomic write pattern.

        Uses a temporary file and atomic rename to prevent corruption
        if the process is interrupted during write.
        """
        data = {
            "metrics": {f"{k[0]}|{k[1]}": v.to_dict() for k, v in self.metrics.items()},
            "fallback_events": [e.to_dict() for e in self.fallback_events[-MAX_STORED_FALLBACK_EVENTS:]],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Atomic write: write to temp file, then rename
        temp_path = self.storage_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # Atomic rename (on POSIX systems; best-effort on Windows)
            os.replace(temp_path, self.storage_path)
        except OSError as e:
            logger.error(f"Failed to save provider metrics: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def _load(self):
        """Load metrics from disk.

        Logs errors and starts fresh if loading fails, rather than
        silently ignoring corruption.
        """
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key_str, metrics_data in data.get("metrics", {}).items():
                parts = key_str.split("|")
                if len(parts) == 2:
                    key = (parts[0], parts[1])
                    self.metrics[key] = ProviderMetrics.from_dict(metrics_data)

            for event_data in data.get("fallback_events", []):
                self.fallback_events.append(
                    FallbackEvent(
                        original_provider=event_data["original_provider"],
                        original_model=event_data["original_model"],
                        fallback_provider=event_data["fallback_provider"],
                        fallback_model=event_data["fallback_model"],
                        reason=event_data["reason"],
                        success=event_data["success"],
                        timestamp=_parse_datetime(event_data["timestamp"]),
                    )
                )

            logger.debug(f"Loaded {len(self.metrics)} provider metrics and {len(self.fallback_events)} fallback events")
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted provider metrics file at {self.storage_path}: {e}. Starting fresh.")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Invalid data in provider metrics file: {e}. Starting fresh.")
        except OSError as e:
            logger.warning(f"Failed to read provider metrics file: {e}. Starting fresh.")
