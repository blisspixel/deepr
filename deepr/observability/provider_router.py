"""Autonomous Provider Router for intelligent provider selection.

Provides:
- Performance metrics tracking per (provider, model) tuple
- Intelligent provider selection based on cost, latency, success rate
- Automatic fallback on failures
- Graceful degradation to cheaper models

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
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Module logger for debugging persistence and validation issues
logger = logging.getLogger(__name__)

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
    
    def record_success(self, latency_ms: float, cost: float):
        """Record a successful request.
        
        Args:
            latency_ms: Request latency (must be finite and non-negative)
            cost: Request cost (must be non-negative)
        
        Note:
            Invalid latency values (NaN, Inf, negative) are clamped to 0.
            Negative costs are clamped to 0.
        """
        # Validate and sanitize latency: must be finite and non-negative
        if not math.isfinite(latency_ms) or latency_ms < 0:
            logger.warning(
                f"Invalid latency_ms={latency_ms} for {self.provider}/{self.model}, "
                "clamping to 0"
            )
            latency_ms = 0.0
        
        # Validate and sanitize cost: must be non-negative
        if cost < 0:
            logger.warning(
                f"Negative cost={cost} for {self.provider}/{self.model}, "
                "clamping to 0"
            )
            cost = 0.0
        
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.total_cost += cost
        self.last_success = datetime.utcnow()
        
        # Update rolling averages (keep last ROLLING_WINDOW_SIZE entries)
        self.rolling_latencies.append(latency_ms)
        self.rolling_costs.append(cost)
        if len(self.rolling_latencies) > ROLLING_WINDOW_SIZE:
            self.rolling_latencies = self.rolling_latencies[-ROLLING_WINDOW_SIZE:]
        if len(self.rolling_costs) > ROLLING_WINDOW_SIZE:
            self.rolling_costs = self.rolling_costs[-ROLLING_WINDOW_SIZE:]
    
    def record_failure(self, error: str):
        """Record a failed request.
        
        Args:
            error: Error message
        """
        self.failure_count += 1
        self.last_failure = datetime.utcnow()
        self.last_error = error
    
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
                hours_since = (datetime.utcnow() - self.last_failure).total_seconds() / 3600
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
            "rolling_costs": self.rolling_costs
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
            last_success=datetime.fromisoformat(data["last_success"]) if data.get("last_success") else None,
            last_failure=datetime.fromisoformat(data["last_failure"]) if data.get("last_failure") else None,
            last_error=data.get("last_error", ""),
            rolling_latencies=data.get("rolling_latencies", []),
            rolling_costs=data.get("rolling_costs", [])
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
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "original_provider": self.original_provider,
            "original_model": self.original_model,
            "fallback_provider": self.fallback_provider,
            "fallback_model": self.fallback_model,
            "reason": self.reason,
            "success": self.success
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
    DEFAULT_FALLBACK_CHAIN = [
        ("openai", "gpt-4o"),
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-3-5-sonnet-20241022"),
        ("xai", "grok-4-fast"),
    ]
    
    # Task-specific preferences
    TASK_PREFERENCES = {
        "research": [("openai", "o4-mini-deep-research"), ("openai", "gpt-4o")],
        "chat": [("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet-20241022")],
        "synthesis": [("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet-20241022")],
        "fact_check": [("xai", "grok-4-fast"), ("openai", "gpt-4o-mini")],
        "quick": [("xai", "grok-4-fast"), ("openai", "gpt-4o-mini")],
    }
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        fallback_chain: Optional[List[Tuple[str, str]]] = None,
        min_samples: int = 3
    ):
        """Initialize provider router.
        
        Args:
            storage_path: Path for persistence
            fallback_chain: Custom fallback chain
            min_samples: Minimum samples before using metrics
        """
        if storage_path is None:
            storage_path = Path("data/observability/provider_metrics.json")
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.fallback_chain = fallback_chain or self.DEFAULT_FALLBACK_CHAIN
        self.min_samples = min_samples
        
        # Metrics keyed by (provider, model) tuple
        self.metrics: Dict[Tuple[str, str], ProviderMetrics] = {}
        self.fallback_events: List[FallbackEvent] = []
        
        self._load()
    
    def record_result(
        self,
        provider: str,
        model: str,
        success: bool,
        latency_ms: float = 0.0,
        cost: float = 0.0,
        error: str = ""
    ):
        """Record a request result.
        
        Args:
            provider: Provider name
            model: Model name
            success: Whether request succeeded
            latency_ms: Request latency
            cost: Request cost
            error: Error message if failed
        """
        key = (provider, model)
        
        if key not in self.metrics:
            self.metrics[key] = ProviderMetrics(provider=provider, model=model)
        
        if success:
            self.metrics[key].record_success(latency_ms, cost)
        else:
            self.metrics[key].record_failure(error)
        
        self._save()
    
    def select_provider(
        self,
        task_type: str = "general",
        prefer_cost: bool = False,
        prefer_speed: bool = False,
        exclude: Optional[List[Tuple[str, str]]] = None
    ) -> Tuple[str, str]:
        """Select best provider for a task.
        
        Args:
            task_type: Type of task
            prefer_cost: Prefer cheaper options
            prefer_speed: Prefer faster options
            exclude: Providers to exclude
            
        Returns:
            Tuple of (provider, model)
        """
        exclude = exclude or []
        
        # Get candidates
        candidates = self._get_candidates(task_type)
        candidates = [c for c in candidates if c not in exclude]
        
        if not candidates:
            # Fall back to default chain
            for fallback in self.fallback_chain:
                if fallback not in exclude:
                    return fallback
            # Last resort
            return ("openai", "gpt-4o")
        
        # Score candidates
        scored = []
        for provider, model in candidates:
            score = self._score_provider(
                provider, model,
                prefer_cost=prefer_cost,
                prefer_speed=prefer_speed
            )
            scored.append((score, provider, model))
        
        # Sort by score (higher is better)
        scored.sort(reverse=True)
        
        return (scored[0][1], scored[0][2])
    
    def get_fallback(
        self,
        failed_provider: str,
        failed_model: str,
        reason: str
    ) -> Optional[Tuple[str, str]]:
        """Get fallback provider after failure.
        
        Args:
            failed_provider: Provider that failed
            failed_model: Model that failed
            reason: Reason for failure
            
        Returns:
            Fallback (provider, model) or None
        """
        failed_key = (failed_provider, failed_model)
        
        # Find next healthy provider in chain
        for provider, model in self.fallback_chain:
            key = (provider, model)
            if key == failed_key:
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
                    success=True  # Will be updated later
                )
                self.fallback_events.append(event)
                self._save()
                
                return (provider, model)
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get router status.
        
        Returns:
            Status dictionary
        """
        status = {
            "providers": {},
            "healthy_count": 0,
            "unhealthy_count": 0,
            "total_requests": 0,
            "total_cost": 0.0,
            "recent_fallbacks": []
        }
        
        for key, metrics in self.metrics.items():
            provider, model = key
            is_healthy = metrics.is_healthy()
            
            status["providers"][f"{provider}/{model}"] = {
                "healthy": is_healthy,
                "success_rate": metrics.success_rate,
                "avg_latency_ms": metrics.rolling_avg_latency,
                "avg_cost": metrics.rolling_avg_cost,
                "total_requests": metrics.total_requests,
                "last_error": metrics.last_error if not is_healthy else None
            }
            
            if is_healthy:
                status["healthy_count"] += 1
            else:
                status["unhealthy_count"] += 1
            
            status["total_requests"] += metrics.total_requests
            status["total_cost"] += metrics.total_cost
        
        # Recent fallbacks
        status["recent_fallbacks"] = [
            e.to_dict() for e in self.fallback_events[-10:]
        ]
        
        return status
    
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
        self,
        provider: str,
        model: str,
        prefer_cost: bool = False,
        prefer_speed: bool = False
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
            hours_since = (datetime.utcnow() - metrics.last_failure).total_seconds() / 3600
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
            "metrics": {
                f"{k[0]}|{k[1]}": v.to_dict()
                for k, v in self.metrics.items()
            },
            "fallback_events": [
                e.to_dict() for e in self.fallback_events[-MAX_STORED_FALLBACK_EVENTS:]
            ],
            "saved_at": datetime.utcnow().isoformat()
        }
        
        # Atomic write: write to temp file, then rename
        temp_path = self.storage_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
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
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for key_str, metrics_data in data.get("metrics", {}).items():
                parts = key_str.split("|")
                if len(parts) == 2:
                    key = (parts[0], parts[1])
                    self.metrics[key] = ProviderMetrics.from_dict(metrics_data)
            
            for event_data in data.get("fallback_events", []):
                self.fallback_events.append(FallbackEvent(
                    original_provider=event_data["original_provider"],
                    original_model=event_data["original_model"],
                    fallback_provider=event_data["fallback_provider"],
                    fallback_model=event_data["fallback_model"],
                    reason=event_data["reason"],
                    success=event_data["success"],
                    timestamp=datetime.fromisoformat(event_data["timestamp"])
                ))
            
            logger.debug(
                f"Loaded {len(self.metrics)} provider metrics and "
                f"{len(self.fallback_events)} fallback events"
            )
        except json.JSONDecodeError as e:
            logger.warning(
                f"Corrupted provider metrics file at {self.storage_path}: {e}. "
                "Starting fresh."
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"Invalid data in provider metrics file: {e}. Starting fresh."
            )
        except OSError as e:
            logger.warning(
                f"Failed to read provider metrics file: {e}. Starting fresh."
            )
