"""
Property-based tests for Circuit Breaker component.

Tests the circuit breaker state machine and fail-fast behavior:
- Property 5: Circuit Breaker State Machine
- Property 6: Circuit Breaker Fail-Fast

Feature: code-quality-security-hardening
Properties: 5 (State Machine), 6 (Fail-Fast)
**Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6**
"""

import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, settings, assume, HealthCheck

from deepr.observability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
)


# =============================================================================
# Test Strategies
# =============================================================================

# Strategy for generating provider names
provider_names = st.sampled_from([
    "openai", "anthropic", "xai", "azure", "gemini", "cohere", "mistral"
])

# Strategy for generating model names
model_names = st.sampled_from([
    "gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "grok-4-fast",
    "gemini-pro", "command-r", "mistral-large"
])

# Strategy for generating error messages
error_messages = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-_",
    min_size=0,
    max_size=100
)

# Strategy for generating failure thresholds
failure_thresholds = st.integers(min_value=1, max_value=20)

# Strategy for generating recovery timeouts
recovery_timeouts = st.integers(min_value=1, max_value=300)

# Strategy for generating sequences of success/failure events
event_strategy = st.sampled_from(["success", "failure"])
event_sequences = st.lists(event_strategy, min_size=1, max_size=50)


# =============================================================================
# Unit Tests for CircuitBreaker
# =============================================================================

@pytest.mark.unit
class TestCircuitBreakerBasics:
    """Basic unit tests for CircuitBreaker."""
    
    def test_initial_state_is_closed(self):
        """New circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker(provider="openai", model="gpt-4o")
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.is_available is True
    
    def test_key_property(self):
        """Key should be (provider, model) tuple."""
        cb = CircuitBreaker(provider="anthropic", model="claude-3-5-sonnet")
        assert cb.key == ("anthropic", "claude-3-5-sonnet")
    
    def test_record_success_resets_failure_count(self):
        """Recording success should reset failure count."""
        cb = CircuitBreaker(provider="openai", model="gpt-4o")
        
        # Record some failures
        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        assert cb.failure_count == 2
        
        # Record success
        cb.record_success()
        assert cb.failure_count == 0
    
    def test_record_failure_increments_count(self):
        """Recording failure should increment failure count."""
        cb = CircuitBreaker(provider="openai", model="gpt-4o")
        
        cb.record_failure("Error 1")
        assert cb.failure_count == 1
        
        cb.record_failure("Error 2")
        assert cb.failure_count == 2
    
    def test_to_dict_serialization(self):
        """Circuit breaker should serialize to dictionary correctly."""
        cb = CircuitBreaker(provider="openai", model="gpt-4o")
        cb.record_failure("Test error")
        
        data = cb.to_dict()
        
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["state"] == "closed"
        assert data["failure_count"] == 1
        assert data["failure_threshold"] == CIRCUIT_BREAKER_FAILURE_THRESHOLD
        assert data["recovery_timeout"] == CIRCUIT_BREAKER_RECOVERY_TIMEOUT


# =============================================================================
# Property 5: Circuit Breaker State Machine
# =============================================================================

@pytest.mark.unit
class TestCircuitBreakerStateMachineProperty:
    """Property 5: Circuit Breaker State Machine
    
    For any sequence of success/failure events, the circuit breaker state 
    transitions SHALL follow the defined state machine:
    - CLOSED + (failures >= threshold) → OPEN
    - OPEN + (timeout elapsed) → HALF_OPEN
    - HALF_OPEN + success → CLOSED
    - HALF_OPEN + failure → OPEN
    
    Feature: code-quality-security-hardening, Property 5: State Machine
    **Validates: Requirements 6.2, 6.4, 6.5, 6.6**
    """
    
    @given(
        provider=provider_names,
        model=model_names,
        threshold=failure_thresholds
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_closed_to_open_on_threshold_failures(self, provider, model, threshold):
        """CLOSED → OPEN: After failure_threshold consecutive failures.
        
        **Validates: Requirements 6.2**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=threshold
        )
        
        # Initial state should be CLOSED
        assert cb.state == CircuitState.CLOSED
        
        # Record failures up to threshold - 1
        for i in range(threshold - 1):
            cb.record_failure(f"Error {i}")
            assert cb.state == CircuitState.CLOSED, \
                f"Circuit should remain CLOSED with {i+1} failures (threshold={threshold})"
        
        # Record the threshold-th failure
        cb.record_failure("Final error")
        assert cb.state == CircuitState.OPEN, \
            f"Circuit should be OPEN after {threshold} failures"
    
    @given(
        provider=provider_names,
        model=model_names,
        timeout=recovery_timeouts
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_open_to_half_open_after_timeout(self, provider, model, timeout):
        """OPEN → HALF_OPEN: After recovery_timeout seconds.
        
        **Validates: Requirements 6.4**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=1,  # Open immediately on first failure
            recovery_timeout=timeout
        )
        
        # Open the circuit
        cb.record_failure("Error")
        assert cb.state == CircuitState.OPEN
        
        # Simulate time passing (less than timeout)
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=timeout - 1)
        cb._check_recovery()
        assert cb.state == CircuitState.OPEN, \
            "Circuit should remain OPEN before timeout"
        
        # Simulate time passing (at or after timeout)
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=timeout)
        cb._check_recovery()
        assert cb.state == CircuitState.HALF_OPEN, \
            "Circuit should be HALF_OPEN after timeout"
    
    @given(
        provider=provider_names,
        model=model_names
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_half_open_to_closed_on_success(self, provider, model):
        """HALF_OPEN → CLOSED: On successful request.
        
        **Validates: Requirements 6.5**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=1,
            recovery_timeout=1
        )
        
        # Open the circuit
        cb.record_failure("Error")
        assert cb.state == CircuitState.OPEN
        
        # Transition to HALF_OPEN
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=2)
        cb._check_recovery()
        assert cb.state == CircuitState.HALF_OPEN
        
        # Record success - should close
        cb.record_success()
        assert cb.state == CircuitState.CLOSED, \
            "Circuit should be CLOSED after success in HALF_OPEN state"
        assert cb.failure_count == 0, \
            "Failure count should be reset after closing"
    
    @given(
        provider=provider_names,
        model=model_names,
        error=error_messages
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_half_open_to_open_on_failure(self, provider, model, error):
        """HALF_OPEN → OPEN: On failed request.
        
        **Validates: Requirements 6.6**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=1,
            recovery_timeout=1
        )
        
        # Open the circuit
        cb.record_failure("Initial error")
        assert cb.state == CircuitState.OPEN
        
        # Transition to HALF_OPEN
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=2)
        cb._check_recovery()
        assert cb.state == CircuitState.HALF_OPEN
        
        # Record failure - should reopen
        cb.record_failure(error)
        assert cb.state == CircuitState.OPEN, \
            "Circuit should be OPEN after failure in HALF_OPEN state"
    
    @given(events=event_sequences)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_state_machine_invariants(self, events):
        """State machine should always be in a valid state.
        
        **Validates: Requirements 6.2, 6.4, 6.5, 6.6**
        """
        cb = CircuitBreaker(
            provider="openai",
            model="gpt-4o",
            failure_threshold=3,
            recovery_timeout=1
        )
        
        for event in events:
            # State should always be valid
            assert cb.state in [CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN]
            
            if event == "success":
                cb.record_success()
            else:
                cb.record_failure("Error")
            
            # State should still be valid after event
            assert cb.state in [CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN]
            
            # Failure count should never be negative
            assert cb.failure_count >= 0
    
    @given(
        threshold=failure_thresholds,
        extra_failures=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_failures_beyond_threshold_keep_circuit_open(self, threshold, extra_failures):
        """Additional failures after threshold should keep circuit OPEN.
        
        **Validates: Requirements 6.2**
        """
        cb = CircuitBreaker(
            provider="openai",
            model="gpt-4o",
            failure_threshold=threshold
        )
        
        # Open the circuit
        for i in range(threshold):
            cb.record_failure(f"Error {i}")
        
        assert cb.state == CircuitState.OPEN
        
        # Record additional failures
        for i in range(extra_failures):
            cb.record_failure(f"Extra error {i}")
            assert cb.state == CircuitState.OPEN, \
                "Circuit should remain OPEN with additional failures"


# =============================================================================
# Property 6: Circuit Breaker Fail-Fast
# =============================================================================

@pytest.mark.unit
class TestCircuitBreakerFailFastProperty:
    """Property 6: Circuit Breaker Fail-Fast
    
    For any request when circuit breaker is in OPEN state, the request 
    SHALL fail immediately without attempting the actual provider call.
    
    Feature: code-quality-security-hardening, Property 6: Fail-Fast
    **Validates: Requirements 6.3**
    """
    
    @given(
        provider=provider_names,
        model=model_names
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_open_circuit_is_not_available(self, provider, model):
        """OPEN circuit should report as not available.
        
        **Validates: Requirements 6.3**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=1,
            recovery_timeout=60  # Long timeout to ensure we stay OPEN
        )
        
        # Open the circuit
        cb.record_failure("Error")
        assert cb.state == CircuitState.OPEN
        
        # Circuit should not be available
        assert cb.is_available is False, \
            "OPEN circuit should not be available"
    
    @given(
        provider=provider_names,
        model=model_names
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_closed_circuit_is_available(self, provider, model):
        """CLOSED circuit should report as available.
        
        **Validates: Requirements 6.3**
        """
        cb = CircuitBreaker(provider=provider, model=model)
        
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True, \
            "CLOSED circuit should be available"
    
    @given(
        provider=provider_names,
        model=model_names
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_half_open_circuit_is_available(self, provider, model):
        """HALF_OPEN circuit should report as available (to test recovery).
        
        **Validates: Requirements 6.3**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=1,
            recovery_timeout=1
        )
        
        # Open the circuit
        cb.record_failure("Error")
        
        # Transition to HALF_OPEN
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=2)
        cb._check_recovery()
        
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_available is True, \
            "HALF_OPEN circuit should be available to test recovery"
    
    @given(
        provider=provider_names,
        model=model_names,
        timeout=recovery_timeouts
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_time_until_recovery_when_open(self, provider, model, timeout):
        """OPEN circuit should report time until recovery.
        
        **Validates: Requirements 6.3, 6.7**
        """
        cb = CircuitBreaker(
            provider=provider,
            model=model,
            failure_threshold=1,
            recovery_timeout=timeout
        )
        
        # Open the circuit
        cb.record_failure("Error")
        assert cb.state == CircuitState.OPEN
        
        # Time until recovery should be approximately the timeout
        time_remaining = cb.time_until_recovery
        assert time_remaining is not None
        assert 0 <= time_remaining <= timeout
    
    @given(
        provider=provider_names,
        model=model_names
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_time_until_recovery_none_when_not_open(self, provider, model):
        """Non-OPEN circuit should report None for time until recovery.
        
        **Validates: Requirements 6.7**
        """
        cb = CircuitBreaker(provider=provider, model=model)
        
        # CLOSED state
        assert cb.state == CircuitState.CLOSED
        assert cb.time_until_recovery is None
        
        # HALF_OPEN state
        cb.failure_threshold = 1
        cb.recovery_timeout = 1
        cb.record_failure("Error")
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=2)
        cb._check_recovery()
        
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.time_until_recovery is None


# =============================================================================
# CircuitBreakerRegistry Tests
# =============================================================================

@pytest.mark.unit
class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry."""
    
    def test_get_circuit_creates_new(self):
        """get_circuit should create new circuit if not exists."""
        registry = CircuitBreakerRegistry()
        
        circuit = registry.get_circuit("openai", "gpt-4o")
        
        assert circuit is not None
        assert circuit.provider == "openai"
        assert circuit.model == "gpt-4o"
        assert circuit.state == CircuitState.CLOSED
    
    def test_get_circuit_returns_existing(self):
        """get_circuit should return existing circuit."""
        registry = CircuitBreakerRegistry()
        
        circuit1 = registry.get_circuit("openai", "gpt-4o")
        circuit1.record_failure("Error")
        
        circuit2 = registry.get_circuit("openai", "gpt-4o")
        
        assert circuit1 is circuit2
        assert circuit2.failure_count == 1
    
    def test_is_available_delegates_to_circuit(self):
        """is_available should delegate to circuit's is_available."""
        registry = CircuitBreakerRegistry(failure_threshold=1)
        
        # Initially available
        assert registry.is_available("openai", "gpt-4o") is True
        
        # Open the circuit
        registry.record_failure("openai", "gpt-4o", "Error")
        
        # Now not available
        assert registry.is_available("openai", "gpt-4o") is False
    
    def test_record_success_delegates_to_circuit(self):
        """record_success should delegate to circuit."""
        registry = CircuitBreakerRegistry()
        
        # Record some failures
        registry.record_failure("openai", "gpt-4o", "Error 1")
        registry.record_failure("openai", "gpt-4o", "Error 2")
        
        circuit = registry.get_circuit("openai", "gpt-4o")
        assert circuit.failure_count == 2
        
        # Record success
        registry.record_success("openai", "gpt-4o")
        assert circuit.failure_count == 0
    
    def test_record_failure_delegates_to_circuit(self):
        """record_failure should delegate to circuit."""
        registry = CircuitBreakerRegistry()
        
        registry.record_failure("openai", "gpt-4o", "Test error")
        
        circuit = registry.get_circuit("openai", "gpt-4o")
        assert circuit.failure_count == 1
    
    def test_get_status_returns_all_circuits(self):
        """get_status should return status of all circuits."""
        registry = CircuitBreakerRegistry()
        
        # Create some circuits
        registry.record_success("openai", "gpt-4o")
        registry.record_failure("anthropic", "claude-3-5-sonnet", "Error")
        
        status = registry.get_status()
        
        assert "openai/gpt-4o" in status
        assert "anthropic/claude-3-5-sonnet" in status
        assert status["openai/gpt-4o"]["state"] == "closed"
    
    def test_reset_circuit(self):
        """reset_circuit should reset circuit to CLOSED state."""
        registry = CircuitBreakerRegistry(failure_threshold=1)
        
        # Open the circuit
        registry.record_failure("openai", "gpt-4o", "Error")
        assert registry.is_available("openai", "gpt-4o") is False
        
        # Reset
        registry.reset_circuit("openai", "gpt-4o")
        
        circuit = registry.get_circuit("openai", "gpt-4o")
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert registry.is_available("openai", "gpt-4o") is True
    
    def test_reset_all(self):
        """reset_all should reset all circuits."""
        registry = CircuitBreakerRegistry(failure_threshold=1)
        
        # Open multiple circuits
        registry.record_failure("openai", "gpt-4o", "Error")
        registry.record_failure("anthropic", "claude-3-5-sonnet", "Error")
        
        assert registry.is_available("openai", "gpt-4o") is False
        assert registry.is_available("anthropic", "claude-3-5-sonnet") is False
        
        # Reset all
        registry.reset_all()
        
        assert registry.is_available("openai", "gpt-4o") is True
        assert registry.is_available("anthropic", "claude-3-5-sonnet") is True
    
    @given(
        provider=provider_names,
        model=model_names,
        threshold=failure_thresholds,
        timeout=recovery_timeouts
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_registry_uses_configured_defaults(self, provider, model, threshold, timeout):
        """Registry should use configured defaults for new circuits.
        
        **Validates: Requirements 6.2, 6.4**
        """
        registry = CircuitBreakerRegistry(
            failure_threshold=threshold,
            recovery_timeout=timeout
        )
        
        circuit = registry.get_circuit(provider, model)
        
        assert circuit.failure_threshold == threshold
        assert circuit.recovery_timeout == timeout


# =============================================================================
# Integration Tests with ProviderRouter
# =============================================================================

@pytest.mark.unit
class TestCircuitBreakerProviderRouterIntegration:
    """Tests for circuit breaker integration with ProviderRouter."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "metrics.json"
    
    def test_router_creates_circuit_breaker_registry(self, temp_storage):
        """Router should create circuit breaker registry."""
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        assert router.circuit_breaker is not None
        assert isinstance(router.circuit_breaker, CircuitBreakerRegistry)
    
    def test_router_accepts_custom_registry(self, temp_storage):
        """Router should accept custom circuit breaker registry."""
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        custom_registry = CircuitBreakerRegistry(failure_threshold=10)
        router = AutonomousProviderRouter(
            storage_path=temp_storage,
            circuit_breaker_registry=custom_registry
        )
        
        assert router.circuit_breaker is custom_registry
    
    def test_router_updates_circuit_on_success(self, temp_storage):
        """Router should update circuit breaker on success."""
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Record some failures first
        for _ in range(3):
            router.record_result("openai", "gpt-4o", False, error="Error")
        
        circuit = router.circuit_breaker.get_circuit("openai", "gpt-4o")
        assert circuit.failure_count == 3
        
        # Record success
        router.record_result("openai", "gpt-4o", True, latency_ms=1000, cost=0.05)
        
        assert circuit.failure_count == 0
    
    def test_router_updates_circuit_on_failure(self, temp_storage):
        """Router should update circuit breaker on failure."""
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        registry = CircuitBreakerRegistry(failure_threshold=3)
        router = AutonomousProviderRouter(
            storage_path=temp_storage,
            circuit_breaker_registry=registry
        )
        
        # Record failures to open circuit
        for i in range(3):
            router.record_result("openai", "gpt-4o", False, error=f"Error {i}")
        
        circuit = registry.get_circuit("openai", "gpt-4o")
        assert circuit.state == CircuitState.OPEN
    
    def test_router_excludes_open_circuits_from_selection(self, temp_storage):
        """Router should exclude providers with open circuits from selection."""
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        registry = CircuitBreakerRegistry(failure_threshold=1)
        router = AutonomousProviderRouter(
            storage_path=temp_storage,
            circuit_breaker_registry=registry,
            fallback_chain=[
                ("openai", "gpt-4o"),
                ("anthropic", "claude-3-5-sonnet"),
            ]
        )
        
        # Open circuit for first provider
        router.record_result("openai", "gpt-4o", False, error="Error")
        
        # Selection should prefer the available provider
        provider, model = router.select_provider()
        
        # Should not select the provider with open circuit
        # (unless it's the only option)
        if provider == "openai" and model == "gpt-4o":
            # This is acceptable only if anthropic is also unavailable
            assert not registry.is_available("anthropic", "claude-3-5-sonnet")
    
    def test_router_status_includes_circuit_breaker_info(self, temp_storage):
        """Router status should include circuit breaker information."""
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        router = AutonomousProviderRouter(storage_path=temp_storage)
        
        # Record some activity
        router.record_result("openai", "gpt-4o", True, latency_ms=1000, cost=0.05)
        
        status = router.get_status()
        
        assert "circuit_breakers" in status
        assert "openai/gpt-4o" in status["providers"]
        assert "circuit_state" in status["providers"]["openai/gpt-4o"]
        assert "circuit_available" in status["providers"]["openai/gpt-4o"]
