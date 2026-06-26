"""Property-based tests for circuit breaker state machine.

Feature: mcp-client-agent-interop
- Property 11: Circuit breaker state machine
- Property 12: Health report completeness
"""

from __future__ import annotations

import time

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule

from deepr.mcp.client.circuit_breaker import CircuitBreaker, CircuitState
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile

# --- Strategies ---

thresholds = st.integers(min_value=1, max_value=10)
recovery_times = st.floats(min_value=0.1, max_value=120.0, allow_nan=False, allow_infinity=False)


# --- Property 11: Circuit breaker state machine ---


class CircuitBreakerStateMachine(RuleBasedStateMachine):
    """State machine test for circuit breaker transitions.

    Verifies all valid state transitions:
    - CLOSED + threshold failures → OPEN
    - OPEN + recovery elapsed → HALF_OPEN
    - HALF_OPEN + success → CLOSED
    - HALF_OPEN + failure → OPEN
    - Any state + success → CLOSED

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
    """

    def __init__(self) -> None:
        super().__init__()
        self.cb = CircuitBreaker(threshold=3, recovery_seconds=1.0)
        self.expected_failures = 0

    @rule()
    def record_success(self) -> None:
        """Record a success - should always close the circuit."""
        prev_state = self.cb.state
        was_available = self.cb.is_available()
        self.cb.record_success()
        assert self.cb.state == CircuitState.CLOSED
        assert self.cb.failure_count == 0
        assert self.cb.is_available()
        self.expected_failures = 0

    @rule()
    def record_failure(self) -> None:
        """Record a failure - may open circuit if threshold reached."""
        prev_state = self.cb.state
        self.cb.record_failure()
        self.expected_failures += 1

        if prev_state == CircuitState.HALF_OPEN:
            # Probe failed → re-open
            assert self.cb.state == CircuitState.OPEN
        elif self.expected_failures >= self.cb.threshold:
            assert self.cb.state == CircuitState.OPEN
        else:
            assert self.cb.state == CircuitState.CLOSED

    @rule()
    def elapse_recovery(self) -> None:
        """Simulate recovery period elapsing."""
        if self.cb._state == CircuitState.OPEN:
            # Move opened_at to the past
            self.cb._opened_at = time.time() - self.cb.recovery_seconds - 1
            assert self.cb.state == CircuitState.HALF_OPEN

    @rule()
    def check_availability(self) -> None:
        """Verify availability matches state."""
        state = self.cb.state
        if state == CircuitState.CLOSED:
            assert self.cb.is_available()
        elif state == CircuitState.OPEN:
            assert not self.cb.is_available()
        # HALF_OPEN: available for first probe only

    @rule()
    def reset(self) -> None:
        """Reset the circuit breaker."""
        self.cb.reset()
        self.expected_failures = 0
        assert self.cb.state == CircuitState.CLOSED
        assert self.cb.failure_count == 0
        assert self.cb.is_available()


TestCircuitBreakerStateMachine = CircuitBreakerStateMachine.TestCase
TestCircuitBreakerStateMachine.settings = settings(max_examples=200, stateful_step_count=20)


# --- Additional property tests for circuit breaker ---


@settings(max_examples=100)
@given(
    threshold=thresholds,
    num_failures=st.integers(min_value=0, max_value=15),
)
def test_property_11_threshold_opens_circuit(
    threshold: int,
    num_failures: int,
) -> None:
    """Circuit opens if and only if failure_count >= threshold.

    **Validates: Requirements 5.1**
    """
    cb = CircuitBreaker(threshold=threshold, recovery_seconds=60.0)

    for _ in range(num_failures):
        cb.record_failure()

    if num_failures >= threshold:
        assert cb._state == CircuitState.OPEN
        assert not cb.is_available()
    else:
        assert cb._state == CircuitState.CLOSED
        assert cb.is_available()


@settings(max_examples=100)
@given(threshold=thresholds)
def test_property_11_half_open_success_closes(threshold: int) -> None:
    """A successful probe in half-open state closes the circuit.

    **Validates: Requirements 5.4**
    """
    cb = CircuitBreaker(threshold=threshold, recovery_seconds=0.01)

    # Open the circuit
    for _ in range(threshold):
        cb.record_failure()
    assert cb._state == CircuitState.OPEN

    # Elapse recovery
    cb._opened_at = time.time() - 1.0
    assert cb.state == CircuitState.HALF_OPEN

    # Probe succeeds
    assert cb.is_available()  # allows probe
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@settings(max_examples=100)
@given(threshold=thresholds)
def test_property_11_half_open_failure_reopens(threshold: int) -> None:
    """A failed probe in half-open state re-opens the circuit.

    **Validates: Requirements 5.3, 5.4**
    """
    cb = CircuitBreaker(threshold=threshold, recovery_seconds=0.01)

    # Open the circuit
    for _ in range(threshold):
        cb.record_failure()

    # Elapse recovery
    cb._opened_at = time.time() - 1.0
    assert cb.state == CircuitState.HALF_OPEN

    # Allow probe
    assert cb.is_available()

    # Probe fails
    cb.record_failure()
    assert cb._state == CircuitState.OPEN


# --- Property 12: Health report completeness ---


@settings(max_examples=100)
@given(
    server_names=st.lists(
        st.from_regex(r"[a-z][a-z0-9\-]{1,8}", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
def test_property_12_health_report_completeness(
    server_names: list[str],
) -> None:
    """health() SHALL return per-server status including circuit state
    for every registered server.

    **Validates: Requirements 5.5**
    """
    pool = MCPClientPool()

    for name in server_names:
        profile = MCPClientProfile(name=name, command="echo", args=["test"])
        pool.register(profile)

    report = pool.health()

    assert report["total_servers"] == len(server_names)
    assert "servers" in report

    for name in server_names:
        assert name in report["servers"]
        server_health = report["servers"][name]
        assert "circuit_state" in server_health
        assert server_health["circuit_state"] in {"closed", "open", "half-open"}
