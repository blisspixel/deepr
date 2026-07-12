"""Rolling-window circuit breaker for cost-incurring operations."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from math import isfinite


def _validated_nonnegative_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


@dataclass
class CostEvent:
    """Record of a cost-incurring event."""

    timestamp: float
    cost: float
    operation: str
    job_id: str | None = None


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""

    is_open: bool
    reason: str | None
    opened_at: float | None
    total_cost_window: float
    event_count_window: int
    cooldown_remaining: float

    @property
    def is_closed(self) -> bool:
        """Check if the circuit is closed for normal operation."""
        return not self.is_open


class CostCircuitBreaker:
    """Stop requests when recent spend or event volume exceeds a bound."""

    def __init__(
        self,
        cost_threshold: float = 10.0,
        window_seconds: float = 300.0,
        event_threshold: int = 50,
        cooldown_seconds: float = 60.0,
        max_single_cost: float = 5.0,
    ) -> None:
        self.cost_threshold = _validated_nonnegative_number(cost_threshold, field_name="cost_threshold")
        self.window_seconds = _validated_nonnegative_number(window_seconds, field_name="window_seconds")
        if isinstance(event_threshold, bool) or not isinstance(event_threshold, int) or event_threshold < 0:
            raise ValueError("event_threshold must be a non-negative integer")
        self.event_threshold = event_threshold
        self.cooldown_seconds = _validated_nonnegative_number(cooldown_seconds, field_name="cooldown_seconds")
        self.max_single_cost = _validated_nonnegative_number(max_single_cost, field_name="max_single_cost")
        self._events: deque[CostEvent] = deque()
        self._is_open = False
        self._opened_at: float | None = None
        self._open_reason: str | None = None

    def _prune_old_events(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def _calculate_window_cost(self) -> float:
        self._prune_old_events()
        return sum(event.cost for event in self._events)

    def _calculate_window_events(self) -> int:
        self._prune_old_events()
        return len(self._events)

    def _check_auto_reset(self) -> bool:
        if not self._is_open or self._opened_at is None:
            return False
        if time.time() - self._opened_at < self.cooldown_seconds:
            return False
        self._is_open = False
        self._opened_at = None
        self._open_reason = None
        return True

    def get_state(self) -> CircuitBreakerState:
        """Return current rolling-window and cooldown state."""
        self._check_auto_reset()
        self._prune_old_events()
        cooldown_remaining = 0.0
        if self._is_open and self._opened_at:
            elapsed = time.time() - self._opened_at
            cooldown_remaining = max(0.0, self.cooldown_seconds - elapsed)
        return CircuitBreakerState(
            is_open=self._is_open,
            reason=self._open_reason,
            opened_at=self._opened_at,
            total_cost_window=self._calculate_window_cost(),
            event_count_window=len(self._events),
            cooldown_remaining=cooldown_remaining,
        )

    def allow_request(self, estimated_cost: float = 0.0) -> tuple[bool, str | None]:
        """Check whether one estimated operation fits all circuit bounds."""
        estimated_cost = _validated_nonnegative_number(estimated_cost, field_name="estimated_cost")
        self._check_auto_reset()
        if self._is_open:
            return False, f"Circuit breaker open: {self._open_reason}"
        if estimated_cost > self.max_single_cost:
            return False, f"Single operation cost ${estimated_cost:.2f} exceeds limit ${self.max_single_cost:.2f}"
        current_cost = self._calculate_window_cost()
        if current_cost + estimated_cost > self.cost_threshold:
            return (
                False,
                f"Would exceed cost threshold: ${current_cost:.2f} + ${estimated_cost:.2f} > ${self.cost_threshold:.2f}",
            )
        event_count = self._calculate_window_events()
        if event_count >= self.event_threshold:
            return False, f"Event threshold reached: {event_count} >= {self.event_threshold}"
        return True, None

    def record_cost(self, cost: float, operation: str, job_id: str | None = None) -> bool:
        """Record one finite non-negative charge and trip if necessary."""
        cost = _validated_nonnegative_number(cost, field_name="cost")
        self._events.append(CostEvent(timestamp=time.time(), cost=cost, operation=operation, job_id=job_id))
        total_cost = self._calculate_window_cost()
        event_count = self._calculate_window_events()
        if total_cost > self.cost_threshold:
            self._trip(f"Cost threshold exceeded: ${total_cost:.2f} > ${self.cost_threshold:.2f}")
            return False
        if event_count > self.event_threshold:
            self._trip(f"Event threshold exceeded: {event_count} > {self.event_threshold}")
            return False
        if cost > self.max_single_cost:
            self._trip(f"Single operation too expensive: ${cost:.2f} > ${self.max_single_cost:.2f}")
            return False
        return True

    def _trip(self, reason: str) -> None:
        self._is_open = True
        self._opened_at = time.time()
        self._open_reason = reason

    def reset(self) -> None:
        """Close the circuit without discarding rolling-window events."""
        self._is_open = False
        self._opened_at = None
        self._open_reason = None

    def force_open(self, reason: str = "Manual override") -> None:
        """Open the circuit immediately."""
        self._trip(reason)

    def get_recent_events(self, limit: int = 10) -> list[CostEvent]:
        """Return the newest recorded events up to the requested limit."""
        self._prune_old_events()
        events = list(self._events)
        return events[-limit:] if len(events) > limit else events


class CostLimitExceeded(Exception):
    """Exception raised when cost limits are exceeded."""

    def __init__(self, message: str, state: CircuitBreakerState | None = None) -> None:
        super().__init__(message)
        self.state = state


__all__ = [
    "CircuitBreakerState",
    "CostCircuitBreaker",
    "CostEvent",
    "CostLimitExceeded",
]
