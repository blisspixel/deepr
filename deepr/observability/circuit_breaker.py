"""Circuit Breaker pattern implementation for provider resilience.

Provides:
- CircuitState enum for state machine states (CLOSED, OPEN, HALF_OPEN)
- CircuitBreaker dataclass for individual provider/model circuits
- CircuitBreakerRegistry for managing multiple circuits

The circuit breaker prevents cascading failures by:
- Tracking consecutive failures per provider/model
- Opening the circuit after threshold failures (fail-fast)
- Automatically testing recovery after timeout
- Closing the circuit on successful recovery

Usage:
    from deepr.observability.circuit_breaker import CircuitBreakerRegistry
    
    registry = CircuitBreakerRegistry()
    
    # Check if provider is available
    if registry.is_available("openai", "gpt-4o"):
        try:
            result = call_provider()
            registry.record_success("openai", "gpt-4o")
        except Exception as e:
            registry.record_failure("openai", "gpt-4o", str(e))
    else:
        # Circuit is open - fail fast
        raise CircuitOpenError("openai", "gpt-4o")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from deepr.core.constants import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class CircuitState(Enum):
    """Circuit breaker states.
    
    State machine:
        CLOSED -> OPEN: After failure_threshold consecutive failures
        OPEN -> HALF_OPEN: After recovery_timeout seconds
        HALF_OPEN -> CLOSED: On successful request
        HALF_OPEN -> OPEN: On failed request
    """
    CLOSED = "closed"      # Normal operation - requests allowed
    OPEN = "open"          # Failing fast - requests blocked
    HALF_OPEN = "half_open"  # Testing recovery - single request allowed


@dataclass
class CircuitBreaker:
    """Circuit breaker for a single provider/model combination.
    
    Implements the circuit breaker pattern to prevent cascading failures
    when a provider becomes unhealthy.
    
    Attributes:
        provider: Provider name (e.g., "openai", "anthropic")
        model: Model name (e.g., "gpt-4o", "claude-3-5-sonnet")
        state: Current circuit state
        failure_count: Consecutive failure count
        last_failure_time: Time of last failure
        last_state_change: Time of last state transition
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before trying half-open
    """
    provider: str
    model: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime = field(default_factory=_utc_now)
    failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD
    recovery_timeout: int = CIRCUIT_BREAKER_RECOVERY_TIMEOUT
    
    @property
    def key(self) -> tuple:
        """Get unique key for this circuit.
        
        Returns:
            Tuple of (provider, model)
        """
        return (self.provider, self.model)
    
    @property
    def is_available(self) -> bool:
        """Check if circuit allows requests.
        
        This property checks for recovery before returning availability.
        
        Returns:
            True if requests should be attempted (CLOSED or HALF_OPEN)
            False if circuit is OPEN
        """
        self._check_recovery()
        return self.state != CircuitState.OPEN
    
    @property
    def time_until_recovery(self) -> Optional[int]:
        """Get seconds until circuit may recover.
        
        Returns:
            Seconds until half-open transition, or None if not in OPEN state
        """
        if self.state != CircuitState.OPEN:
            return None
        
        elapsed = (datetime.now(timezone.utc) - self.last_state_change).total_seconds()
        remaining = self.recovery_timeout - elapsed
        return max(0, int(remaining))
    
    def record_success(self) -> None:
        """Record a successful request.
        
        If in HALF_OPEN state, transitions to CLOSED (recovery successful).
        Resets failure count in all cases.
        """
        if self.state == CircuitState.HALF_OPEN:
            # Recovery successful - close the circuit
            self._transition_to(CircuitState.CLOSED)
            logger.info(
                f"Circuit CLOSED for {self.provider}/{self.model} - recovery successful"
            )
        
        # Reset failure count on any success
        self.failure_count = 0
    
    def record_failure(self, error: str = "") -> None:
        """Record a failed request.
        
        Args:
            error: Error message for logging
            
        State transitions:
            - HALF_OPEN -> OPEN: Recovery failed
            - CLOSED -> OPEN: If failure_count >= failure_threshold
        """
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.state == CircuitState.HALF_OPEN:
            # Recovery failed - reopen the circuit
            self._transition_to(CircuitState.OPEN)
            logger.warning(
                f"Circuit OPEN (recovery failed) for {self.provider}/{self.model}: {error}"
            )
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                # Threshold reached - open the circuit
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"Circuit OPEN (threshold {self.failure_threshold} reached) "
                    f"for {self.provider}/{self.model}: {error}"
                )
    
    def _check_recovery(self) -> None:
        """Check if circuit should transition to half-open.
        
        Called automatically by is_available property.
        Transitions OPEN -> HALF_OPEN after recovery_timeout seconds.
        """
        if self.state != CircuitState.OPEN:
            return
        
        elapsed = (datetime.now(timezone.utc) - self.last_state_change).total_seconds()
        if elapsed >= self.recovery_timeout:
            self._transition_to(CircuitState.HALF_OPEN)
            logger.info(
                f"Circuit HALF_OPEN for {self.provider}/{self.model} - "
                f"testing recovery after {self.recovery_timeout}s"
            )
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state.
        
        Args:
            new_state: Target state
        """
        old_state = self.state
        self.state = new_state
        self.last_state_change = datetime.now(timezone.utc)
        
        # Reset failure count when closing circuit
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
        
        logger.debug(
            f"Circuit {self.provider}/{self.model}: {old_state.value} -> {new_state.value}"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize circuit state for monitoring.
        
        Returns:
            Dictionary with circuit state information
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": (
                self.last_failure_time.isoformat() 
                if self.last_failure_time else None
            ),
            "last_state_change": self.last_state_change.isoformat(),
            "time_until_recovery": self.time_until_recovery,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class CircuitBreakerRegistry:
    """Registry managing circuit breakers for all providers.
    
    Provides a centralized interface for managing circuit breakers
    across multiple provider/model combinations.
    
    Attributes:
        circuits: Dictionary of circuit breakers keyed by (provider, model)
        failure_threshold: Default failure threshold for new circuits
        recovery_timeout: Default recovery timeout for new circuits
    """
    
    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: int = CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    ):
        """Initialize the circuit breaker registry.
        
        Args:
            failure_threshold: Default failures before opening circuit
            recovery_timeout: Default seconds before testing recovery
        """
        self.circuits: Dict[tuple, CircuitBreaker] = {}
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
    
    def get_circuit(self, provider: str, model: str) -> CircuitBreaker:
        """Get or create circuit breaker for provider/model.
        
        Args:
            provider: Provider name
            model: Model name
            
        Returns:
            CircuitBreaker instance for the provider/model combination
        """
        key = (provider, model)
        if key not in self.circuits:
            self.circuits[key] = CircuitBreaker(
                provider=provider,
                model=model,
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
            )
        return self.circuits[key]
    
    def is_available(self, provider: str, model: str) -> bool:
        """Check if provider/model is available.
        
        Args:
            provider: Provider name
            model: Model name
            
        Returns:
            True if requests should be attempted
        """
        return self.get_circuit(provider, model).is_available
    
    def record_success(self, provider: str, model: str) -> None:
        """Record successful request for provider/model.
        
        Args:
            provider: Provider name
            model: Model name
        """
        self.get_circuit(provider, model).record_success()
    
    def record_failure(self, provider: str, model: str, error: str = "") -> None:
        """Record failed request for provider/model.
        
        Args:
            provider: Provider name
            model: Model name
            error: Error message for logging
        """
        self.get_circuit(provider, model).record_failure(error)
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all circuits.
        
        Returns:
            Dictionary with status of all registered circuits
        """
        return {
            f"{p}/{m}": cb.to_dict()
            for (p, m), cb in self.circuits.items()
        }
    
    def reset_circuit(self, provider: str, model: str) -> None:
        """Reset a circuit to CLOSED state.
        
        Useful for manual intervention or testing.
        
        Args:
            provider: Provider name
            model: Model name
        """
        circuit = self.get_circuit(provider, model)
        circuit._transition_to(CircuitState.CLOSED)
        circuit.failure_count = 0
        circuit.last_failure_time = None
        logger.info(f"Circuit manually reset for {provider}/{model}")
    
    def reset_all(self) -> None:
        """Reset all circuits to CLOSED state.
        
        Useful for testing or recovery scenarios.
        """
        for (provider, model) in list(self.circuits.keys()):
            self.reset_circuit(provider, model)
        logger.info("All circuits reset")
