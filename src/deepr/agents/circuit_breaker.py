"""Circuit breaker for bounded parallel fan-out operations.

Guards fan-out operations against runaway cost and cascading failures
by monitoring aggregate cost and failure rates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepr.agents.contract import AgentResult
    from deepr.agents.runtime import FanOutConfig


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""

    total_dispatched: int = 0
    total_completed: int = 0
    total_failed: int = 0
    aggregate_cost: float = 0.0
    tripped: bool = False
    trip_reason: str = ""
    trip_timestamp: datetime | None = None
    affected_trace_ids: list[str] = field(default_factory=list)


class CircuitBreaker:
    """Guards fan-out operations against runaway cost and cascading failures.

    Trips when:
    - aggregate_cost > operation_budget
    - failure_rate > failure_rate_threshold (default 50%)
    """

    def __init__(self, config: FanOutConfig) -> None:
        self.config = config
        self.state = CircuitBreakerState()

    def record_completion(self, result: AgentResult) -> None:
        """Record a completed agent, update aggregate cost."""
        self.state.total_completed += 1
        self.state.aggregate_cost += result.cost

    def record_failure(self, result: AgentResult) -> None:
        """Record a failed agent, update failure count and aggregate cost."""
        self.state.total_failed += 1
        self.state.aggregate_cost += result.cost

    def should_halt(self) -> tuple[bool, str]:
        """Check if circuit breaker should trip.

        Returns:
            (should_halt, reason) tuple.
        """
        if self.state.tripped:
            return True, self.state.trip_reason

        # Check cost threshold
        if self.state.aggregate_cost > self.config.operation_budget:
            reason = (
                f"Aggregate cost ${self.state.aggregate_cost:.4f} "
                f"exceeds operation budget ${self.config.operation_budget:.4f}"
            )
            return True, reason

        # Check failure rate threshold
        total_resolved = self.state.total_completed + self.state.total_failed
        if total_resolved > 0:
            failure_rate = self.state.total_failed / total_resolved
            if failure_rate > self.config.failure_rate_threshold:
                reason = (
                    f"Failure rate {failure_rate:.2%} exceeds threshold "
                    f"{self.config.failure_rate_threshold:.2%} "
                    f"({self.state.total_failed}/{total_resolved} failed)"
                )
                return True, reason

        return False, ""

    def trip(self, reason: str, affected_trace_ids: list[str]) -> None:
        """Trip the circuit breaker and record the event.

        Idempotent: if already tripped, appends new trace IDs but
        preserves the original reason and timestamp.
        """
        if self.state.tripped:
            # Already tripped — merge trace IDs
            existing = set(self.state.affected_trace_ids)
            existing.update(affected_trace_ids)
            self.state.affected_trace_ids = list(existing)
            return

        self.state.tripped = True
        self.state.trip_reason = reason
        self.state.trip_timestamp = datetime.now(UTC)
        self.state.affected_trace_ids = list(affected_trace_ids)

    def reset(self) -> None:
        """Reset state for reuse."""
        self.state = CircuitBreakerState()
