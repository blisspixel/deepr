"""Circuit breaker for MCP server connections.

Implements the closed → open → half-open → closed state machine
to protect against cascading failures from unhealthy servers.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import threading
import time
from enum import Enum


class CircuitState(str, Enum):
    """Observable circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreaker:
    """Per-server circuit breaker with half-open probe logic.

    State machine:
    - CLOSED: Normal operation. Failures increment counter.
    - OPEN: After threshold failures. All calls rejected.
    - HALF_OPEN: After recovery period. One probe call allowed.
      - Probe success → CLOSED
      - Probe failure → OPEN (timer resets)

    Usage::

        cb = CircuitBreaker(threshold=5, recovery_seconds=60.0)
        if cb.is_available():
            result = await call_server()
            if result.ok:
                cb.record_success()
            else:
                cb.record_failure()
        else:
            # Server temporarily unavailable
            ...
    """

    def __init__(self, threshold: int = 5, recovery_seconds: float = 60.0) -> None:
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self.failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._probe_in_flight = False
        # Single-probe contract requires check + set to be atomic;
        # without this lock two coroutines reaching HALF_OPEN at the
        # same time both see ``_probe_in_flight=False`` and both fire
        # a probe, defeating the per-recovery-window throttle.
        self._probe_lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state, accounting for recovery period."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._opened_at > self.recovery_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def is_open(self) -> bool:
        """True if circuit is in OPEN state (not half-open)."""
        return self._state == CircuitState.OPEN

    def is_available(self) -> bool:
        """Check if a call can be attempted.

        Returns True for CLOSED state.
        Returns True for HALF_OPEN if no probe is already in flight.
        Returns False for OPEN (recovery period not elapsed).

        The HALF_OPEN check + claim happens under a lock so two
        concurrent callers can't both observe ``_probe_in_flight=False``
        and both fire probe requests.
        """
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            with self._probe_lock:
                if not self._probe_in_flight:
                    self._probe_in_flight = True
                    return True
            return False
        return False

    def record_success(self) -> None:
        """Record a successful call. Closes circuit if half-open."""
        self.failure_count = 0
        self._state = CircuitState.CLOSED
        self._probe_in_flight = False

    def record_failure(self) -> None:
        """Record a failed call. Opens circuit if threshold reached."""
        self._probe_in_flight = False
        self.failure_count += 1
        if self._state == CircuitState.HALF_OPEN or self.state == CircuitState.HALF_OPEN:
            # Probe failed — re-open
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
        elif self.failure_count >= self.threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.time()

    def reset(self) -> None:
        """Reset circuit to closed state."""
        self.failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = 0.0
        self._probe_in_flight = False
