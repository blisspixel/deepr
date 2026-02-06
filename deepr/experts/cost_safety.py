"""Cost safety utilities for preventing runaway spending.

Implements circuit breaker pattern to detect and halt rapid cost accumulation.
Provides defense against accidental or malicious cost spikes.

Requirements: 8.2 - Implement rapid cost accumulation detection and circuit breaker
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class CostEvent:
    """Record of a cost-incurring event."""

    timestamp: float
    cost: float
    operation: str
    job_id: Optional[str] = None


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""

    is_open: bool
    reason: Optional[str]
    opened_at: Optional[float]
    total_cost_window: float
    event_count_window: int
    cooldown_remaining: float

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return not self.is_open


class CostCircuitBreaker:
    """Circuit breaker for cost control.

    Monitors cost accumulation and trips when spending exceeds thresholds.
    Implements the circuit breaker pattern with configurable thresholds.

    Example:
        breaker = CostCircuitBreaker(
            cost_threshold=10.0,  # $10 in window
            window_seconds=300,   # 5 minute window
            event_threshold=20    # Max 20 events in window
        )

        # Before each API call
        if not breaker.allow_request():
            raise CostLimitExceeded("Circuit breaker open")

        # After API call
        breaker.record_cost(0.15, "research_job", job_id="job-123")
    """

    def __init__(
        self,
        cost_threshold: float = 10.0,
        window_seconds: float = 300.0,
        event_threshold: int = 50,
        cooldown_seconds: float = 60.0,
        max_single_cost: float = 5.0,
    ):
        """Initialize circuit breaker.

        Args:
            cost_threshold: Maximum total cost allowed in window (default $10)
            window_seconds: Time window for cost tracking (default 5 minutes)
            event_threshold: Maximum events allowed in window (default 50)
            cooldown_seconds: Time to wait before auto-reset (default 60s)
            max_single_cost: Maximum cost for single operation (default $5)
        """
        self.cost_threshold = cost_threshold
        self.window_seconds = window_seconds
        self.event_threshold = event_threshold
        self.cooldown_seconds = cooldown_seconds
        self.max_single_cost = max_single_cost

        # State
        self._events: deque = deque()
        self._is_open = False
        self._opened_at: Optional[float] = None
        self._open_reason: Optional[str] = None

    def _prune_old_events(self) -> None:
        """Remove events outside the time window."""
        cutoff = time.time() - self.window_seconds
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def _calculate_window_cost(self) -> float:
        """Calculate total cost in current window."""
        self._prune_old_events()
        return sum(event.cost for event in self._events)

    def _calculate_window_events(self) -> int:
        """Count events in current window."""
        self._prune_old_events()
        return len(self._events)

    def _check_auto_reset(self) -> bool:
        """Check if circuit should auto-reset after cooldown."""
        if not self._is_open or self._opened_at is None:
            return False

        elapsed = time.time() - self._opened_at
        if elapsed >= self.cooldown_seconds:
            self._is_open = False
            self._opened_at = None
            self._open_reason = None
            return True

        return False

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state.

        Returns:
            CircuitBreakerState with current metrics
        """
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

    def allow_request(self, estimated_cost: float = 0.0) -> tuple[bool, Optional[str]]:
        """Check if a request should be allowed.

        Args:
            estimated_cost: Estimated cost of the operation

        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        # Check auto-reset
        self._check_auto_reset()

        # If circuit is open, deny
        if self._is_open:
            return False, f"Circuit breaker open: {self._open_reason}"

        # Check single operation limit
        if estimated_cost > self.max_single_cost:
            return False, f"Single operation cost ${estimated_cost:.2f} exceeds limit ${self.max_single_cost:.2f}"

        # Check if this would exceed cost threshold
        current_cost = self._calculate_window_cost()
        if current_cost + estimated_cost > self.cost_threshold:
            return (
                False,
                f"Would exceed cost threshold: ${current_cost:.2f} + ${estimated_cost:.2f} > ${self.cost_threshold:.2f}",
            )

        # Check event count
        event_count = self._calculate_window_events()
        if event_count >= self.event_threshold:
            return False, f"Event threshold reached: {event_count} >= {self.event_threshold}"

        return True, None

    def record_cost(self, cost: float, operation: str, job_id: Optional[str] = None) -> bool:
        """Record a cost event and check if circuit should trip.

        Args:
            cost: Cost of the operation
            operation: Description of the operation
            job_id: Optional job ID for tracking

        Returns:
            True if circuit is still closed, False if it tripped
        """
        # Record the event
        event = CostEvent(timestamp=time.time(), cost=cost, operation=operation, job_id=job_id)
        self._events.append(event)

        # Check thresholds
        total_cost = self._calculate_window_cost()
        event_count = self._calculate_window_events()

        # Trip if cost threshold exceeded
        if total_cost > self.cost_threshold:
            self._trip(f"Cost threshold exceeded: ${total_cost:.2f} > ${self.cost_threshold:.2f}")
            return False

        # Trip if event threshold exceeded
        if event_count > self.event_threshold:
            self._trip(f"Event threshold exceeded: {event_count} > {self.event_threshold}")
            return False

        # Trip if single operation too expensive
        if cost > self.max_single_cost:
            self._trip(f"Single operation too expensive: ${cost:.2f} > ${self.max_single_cost:.2f}")
            return False

        return True

    def _trip(self, reason: str) -> None:
        """Trip the circuit breaker."""
        self._is_open = True
        self._opened_at = time.time()
        self._open_reason = reason

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._is_open = False
        self._opened_at = None
        self._open_reason = None

    def force_open(self, reason: str = "Manual override") -> None:
        """Manually open the circuit breaker."""
        self._trip(reason)

    def get_recent_events(self, limit: int = 10) -> list[CostEvent]:
        """Get recent cost events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent CostEvent objects
        """
        self._prune_old_events()
        events = list(self._events)
        return events[-limit:] if len(events) > limit else events


class CostLimitExceeded(Exception):
    """Exception raised when cost limits are exceeded."""

    def __init__(self, message: str, state: Optional[CircuitBreakerState] = None):
        super().__init__(message)
        self.state = state


@dataclass
class CostAlert:
    """Alert generated when cost thresholds are approached or exceeded."""

    level: str  # "warning", "critical"
    message: str
    timestamp: float
    threshold_percent: float
    current_cost: float
    budget_limit: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp,
            "threshold_percent": self.threshold_percent,
            "current_cost": self.current_cost,
            "budget_limit": self.budget_limit,
        }


class CostSession:
    """Tracks costs for a single session with budget limits.

    Provides session-level cost tracking with alerts and circuit breaker.
    Used by ExpertChatSession and ExpertLearner for budget management.

    Example:
        session = CostSession(
            session_id="chat_expert_abc123",
            session_type="chat",
            budget_limit=10.0
        )

        # Check before operation
        can_proceed, reason = session.can_proceed(0.50)

        # Record operation
        session.record_operation("research", 0.45)

        # Check remaining budget
        remaining = session.get_remaining_budget()
    """

    def __init__(
        self,
        session_id: str,
        session_type: str,
        budget_limit: float = 10.0,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.95,
    ):
        """Initialize cost session.

        Args:
            session_id: Unique session identifier
            session_type: Type of session (e.g., "chat", "learning")
            budget_limit: Maximum budget for this session
            warning_threshold: Percentage of budget that triggers warning (0.8 = 80%)
            critical_threshold: Percentage of budget that triggers critical alert (0.95 = 95%)
        """
        self.session_id = session_id
        self.session_type = session_type
        self.budget_limit = budget_limit
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

        # State
        self.total_cost: float = 0.0
        self.operations: list[dict] = []
        self.alerts: list[CostAlert] = []
        self.failures: list[dict] = []
        self.is_circuit_open: bool = False
        self._circuit_open_reason: Optional[str] = None
        self.created_at: float = time.time()

        # Alert tracking to avoid duplicates
        self._warning_sent: bool = False
        self._critical_sent: bool = False

    @property
    def total_cost_property(self) -> float:
        """Alias for total_cost for backward compatibility."""
        return self.total_cost

    def get_remaining_budget(self) -> float:
        """Get remaining budget for this session.

        Returns:
            Remaining budget in dollars
        """
        return max(0.0, self.budget_limit - self.total_cost)

    def can_proceed(self, estimated_cost: float) -> tuple[bool, str]:
        """Check if an operation can proceed within budget.

        Args:
            estimated_cost: Estimated cost of the operation

        Returns:
            Tuple of (can_proceed, reason)
        """
        # Check circuit breaker
        if self.is_circuit_open:
            return False, f"Session circuit breaker open: {self._circuit_open_reason}"

        # Check budget
        remaining = self.get_remaining_budget()
        if estimated_cost > remaining:
            return False, f"Insufficient budget: ${estimated_cost:.2f} > ${remaining:.2f} remaining"

        return True, "OK"

    def record_operation(self, operation_type: str, cost: float, details: Optional[str] = None, **kwargs) -> None:
        """Record a cost-incurring operation.

        Args:
            operation_type: Type of operation
            cost: Cost of the operation
            details: Optional details
            **kwargs: Additional metadata
        """
        self.total_cost += cost

        operation = {
            "timestamp": time.time(),
            "operation_type": operation_type,
            "cost": cost,
            "details": details,
            "cumulative_cost": self.total_cost,
            **kwargs,
        }
        self.operations.append(operation)

        # Check thresholds and generate alerts
        self._check_thresholds()

    def record_failure(self, operation_type: str, error: str) -> None:
        """Record a failed operation.

        Args:
            operation_type: Type of operation that failed
            error: Error message
        """
        failure = {"timestamp": time.time(), "operation_type": operation_type, "error": error}
        self.failures.append(failure)

        # Trip circuit breaker after too many failures
        recent_failures = [
            f
            for f in self.failures
            if time.time() - f["timestamp"] < 300  # Last 5 minutes
        ]
        if len(recent_failures) >= 5:
            self.is_circuit_open = True
            self._circuit_open_reason = f"Too many failures: {len(recent_failures)} in 5 minutes"

    def _check_thresholds(self) -> None:
        """Check budget thresholds and generate alerts."""
        if self.budget_limit <= 0:
            return

        usage_percent = self.total_cost / self.budget_limit

        # Critical alert (95%+)
        if usage_percent >= self.critical_threshold and not self._critical_sent:
            alert = CostAlert(
                level="critical",
                message=f"Session budget critical: {usage_percent:.0%} used (${self.total_cost:.2f}/${self.budget_limit:.2f})",
                timestamp=time.time(),
                threshold_percent=usage_percent,
                current_cost=self.total_cost,
                budget_limit=self.budget_limit,
            )
            self.alerts.append(alert)
            self._critical_sent = True

        # Warning alert (80%+)
        elif usage_percent >= self.warning_threshold and not self._warning_sent:
            alert = CostAlert(
                level="warning",
                message=f"Session budget warning: {usage_percent:.0%} used (${self.total_cost:.2f}/${self.budget_limit:.2f})",
                timestamp=time.time(),
                threshold_percent=usage_percent,
                current_cost=self.total_cost,
                budget_limit=self.budget_limit,
            )
            self.alerts.append(alert)
            self._warning_sent = True

    def get_summary(self) -> dict:
        """Get session summary.

        Returns:
            Dictionary with session statistics
        """
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "total_cost": self.total_cost,
            "budget_limit": self.budget_limit,
            "remaining_budget": self.get_remaining_budget(),
            "usage_percent": (self.total_cost / self.budget_limit * 100) if self.budget_limit > 0 else 0,
            "operation_count": len(self.operations),
            "failure_count": len(self.failures),
            "alert_count": len(self.alerts),
            "is_circuit_open": self.is_circuit_open,
            "duration_seconds": time.time() - self.created_at,
        }

    def reset(self) -> None:
        """Reset session state."""
        self.total_cost = 0.0
        self.operations.clear()
        self.alerts.clear()
        self.failures.clear()
        self.is_circuit_open = False
        self._circuit_open_reason = None
        self._warning_sent = False
        self._critical_sent = False


def create_default_circuit_breaker() -> CostCircuitBreaker:
    """Create a circuit breaker with sensible defaults.

    Returns:
        CostCircuitBreaker configured for typical research usage
    """
    return CostCircuitBreaker(
        cost_threshold=10.0,  # $10 per 5 minutes
        window_seconds=300.0,  # 5 minute window
        event_threshold=50,  # Max 50 API calls per window
        cooldown_seconds=60.0,  # 1 minute cooldown
        max_single_cost=5.0,  # Max $5 per operation
    )


class CostSafetyManager:
    """High-level cost safety manager for research operations.

    Provides a unified interface for cost tracking and safety checks,
    combining circuit breaker functionality with session-based tracking.

    Example:
        manager = get_cost_safety_manager()

        # Create a session for tracking
        session = manager.create_session(
            session_id="session-123",
            session_type="chat",
            budget_limit=10.0
        )

        # Check before operation
        allowed, reason, needs_confirm = manager.check_operation(
            session_id="session-123",
            operation_type="research_submit",
            estimated_cost=0.50
        )

        if not allowed:
            raise ValueError(f"Operation blocked: {reason}")

        # Record after operation
        manager.record_cost(
            session_id="session-123",
            operation_type="research_submit",
            actual_cost=0.45,
            details="Job completed successfully"
        )
    """

    def __init__(self, circuit_breaker: Optional[CostCircuitBreaker] = None):
        """Initialize cost safety manager.

        Args:
            circuit_breaker: Optional custom circuit breaker. If None,
                           uses default configuration.
        """
        self._circuit_breaker = circuit_breaker or create_default_circuit_breaker()
        self._session_costs: dict[str, float] = {}
        self._sessions: dict[str, CostSession] = {}

        # Global daily/monthly tracking
        self.daily_cost: float = 0.0
        self.monthly_cost: float = 0.0
        self.max_daily: float = 50.0  # Default $50/day limit
        self.max_monthly: float = 500.0  # Default $500/month limit
        self._last_daily_reset: float = time.time()
        self._last_monthly_reset: float = time.time()

    @property
    def circuit_breaker(self) -> CostCircuitBreaker:
        """Get the underlying circuit breaker."""
        return self._circuit_breaker

    def create_session(self, session_id: str, session_type: str, budget_limit: float = 10.0) -> CostSession:
        """Create a new cost tracking session.

        Args:
            session_id: Unique session identifier
            session_type: Type of session (e.g., "chat", "learning")
            budget_limit: Maximum budget for this session

        Returns:
            CostSession instance for tracking
        """
        session = CostSession(session_id=session_id, session_type=session_type, budget_limit=budget_limit)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[CostSession]:
        """Get an existing session by ID.

        Args:
            session_id: Session identifier

        Returns:
            CostSession if found, None otherwise
        """
        return self._sessions.get(session_id)

    def check_operation(
        self, session_id: str, operation_type: str, estimated_cost: float, require_confirmation: bool = False
    ) -> tuple[bool, str, bool]:
        """Check if an operation should be allowed.

        Args:
            session_id: Session identifier for tracking
            operation_type: Type of operation (e.g., "research_submit")
            estimated_cost: Estimated cost of the operation
            require_confirmation: Whether to require user confirmation

        Returns:
            Tuple of (allowed, reason, needs_confirmation)
            - allowed: True if operation should proceed
            - reason: Explanation message
            - needs_confirmation: True if user confirmation needed
        """
        # Check circuit breaker
        allowed, reason = self._circuit_breaker.allow_request(estimated_cost)

        if not allowed:
            return False, reason, False

        # Check session budget if session exists
        session = self._sessions.get(session_id)
        if session:
            can_proceed, session_reason = session.can_proceed(estimated_cost)
            if not can_proceed:
                return False, session_reason, False

        # Check if confirmation needed for high-cost operations
        if require_confirmation and estimated_cost > 1.0:
            return True, f"High cost operation: ${estimated_cost:.2f}", True

        return True, "OK", False

    def record_cost(
        self, session_id: str, operation_type: str, actual_cost: float, details: Optional[str] = None
    ) -> bool:
        """Record a cost event.

        Args:
            session_id: Session identifier
            operation_type: Type of operation
            actual_cost: Actual cost incurred
            details: Optional details about the operation

        Returns:
            True if circuit is still closed, False if it tripped
        """
        # Track session cost (legacy)
        self._session_costs[session_id] = self._session_costs.get(session_id, 0.0) + actual_cost

        # Track in session if exists
        session = self._sessions.get(session_id)
        if session:
            session.record_operation(operation_type, actual_cost, details)

        # Track daily/monthly
        self.daily_cost += actual_cost
        self.monthly_cost += actual_cost

        # Record in circuit breaker
        return self._circuit_breaker.record_cost(cost=actual_cost, operation=operation_type, job_id=session_id)

    def record_failure(self, session_id: str, operation_type: str, error: str) -> None:
        """Record a failed operation.

        Args:
            session_id: Session identifier
            operation_type: Type of operation that failed
            error: Error message
        """
        session = self._sessions.get(session_id)
        if session:
            session.record_failure(operation_type, error)

    def get_session_cost(self, session_id: str) -> float:
        """Get total cost for a session.

        Args:
            session_id: Session identifier

        Returns:
            Total cost for the session
        """
        return self._session_costs.get(session_id, 0.0)

    def get_spending_summary(self) -> dict:
        """Get global spending summary.

        Returns:
            Dictionary with daily and monthly spending info
        """
        return {
            "daily": {
                "spent": self.daily_cost,
                "limit": self.max_daily,
                "remaining": max(0, self.max_daily - self.daily_cost),
            },
            "monthly": {
                "spent": self.monthly_cost,
                "limit": self.max_monthly,
                "remaining": max(0, self.max_monthly - self.monthly_cost),
            },
            "active_sessions": len(self._sessions),
        }

    def reset(self) -> None:
        """Reset all tracking state."""
        self._circuit_breaker.reset()
        self._session_costs.clear()
        self._sessions.clear()
        self.daily_cost = 0.0
        self.monthly_cost = 0.0


# Global singleton instance
_cost_safety_manager: Optional[CostSafetyManager] = None


def get_cost_safety_manager() -> CostSafetyManager:
    """Get the global cost safety manager instance.

    Returns:
        CostSafetyManager singleton instance
    """
    global _cost_safety_manager
    if _cost_safety_manager is None:
        _cost_safety_manager = CostSafetyManager()
    return _cost_safety_manager


def reset_cost_safety_manager() -> None:
    """Reset the global cost safety manager.

    Useful for testing or when starting a new session.
    """
    global _cost_safety_manager
    if _cost_safety_manager is not None:
        _cost_safety_manager.reset()
    _cost_safety_manager = None
