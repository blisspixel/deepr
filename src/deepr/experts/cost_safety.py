"""Cost safety utilities for preventing runaway spending.

Implements circuit breaker pattern to detect and halt rapid cost accumulation.
Provides defense against accidental or malicious cost spikes.

Requirements: 8.2 - Implement rapid cost accumulation detection and circuit breaker
"""

import os
import threading
import time
from collections import deque
from dataclasses import dataclass

from deepr.observability.cost_ledger import CostLedger


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
        self._opened_at: float | None = None
        self._open_reason: str | None = None

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

    def allow_request(self, estimated_cost: float = 0.0) -> tuple[bool, str | None]:
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

    def record_cost(self, cost: float, operation: str, job_id: str | None = None) -> bool:
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

    def __init__(self, message: str, state: CircuitBreakerState | None = None):
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
        self._circuit_open_reason: str | None = None
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

    def can_proceed(self, estimated_cost: float = 0.0) -> tuple[bool, str]:
        """Check if an operation can proceed within budget.

        Args:
            estimated_cost: Estimated cost of the operation

        Returns:
            Tuple of (can_proceed, reason)
        """
        # Check circuit breaker
        if self.is_circuit_open:
            return False, f"Session circuit breaker open: {self._circuit_open_reason}"

        # Hard per-operation ceiling. check_and_reserve() enforces this at
        # the manager level, but legacy callers using CostSession directly
        # must not bypass the absolute safety limit.
        if estimated_cost > CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION:
            return False, (
                f"Estimated cost ${estimated_cost:.2f} exceeds absolute per-op ceiling "
                f"${CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION:.2f}"
            )

        # Check budget
        remaining = self.get_remaining_budget()
        if estimated_cost > remaining:
            return False, f"Insufficient budget: ${estimated_cost:.2f} > ${remaining:.2f} remaining"

        return True, "OK"

    def record_operation(self, operation_type: str, cost: float, details: str | None = None, **kwargs) -> None:
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

    # Hard ceilings the manager will never permit, regardless of any
    # caller-supplied "budget". These act as a last-line safety net for
    # MCP/CLI surfaces that accept user-controlled budget values.
    # Kept as class attributes so callers (mcp/server.py, cli/commands/
    # budget.py) can reference them without instantiating a manager.
    ABSOLUTE_MAX_PER_OPERATION: float = 10.0
    ABSOLUTE_MAX_DAILY: float = 50.0
    ABSOLUTE_MAX_MONTHLY: float = 500.0

    def __init__(self, circuit_breaker: CostCircuitBreaker | None = None):
        """Initialize cost safety manager.

        Args:
            circuit_breaker: Optional custom circuit breaker. If None,
                           uses default configuration.
        """
        self._circuit_breaker = circuit_breaker or create_default_circuit_breaker()
        self._session_costs: dict[str, float] = {}
        self._sessions: dict[str, CostSession] = {}
        self._ledger = CostLedger()
        self._strict_tracking = os.getenv("DEEPR_COST_TRACKING_STRICT", "0").lower() in {"1", "true", "yes", "on"}

        # Global daily/monthly tracking. Limits honor the same env caps the
        # research budget gate reads (DEEPR_MAX_COST_PER_DAY/_MONTH), so a
        # dev machine capped at $1/day is capped for autonomous expert
        # operations too - one knob, every spender. Values are clamped to
        # the absolute ceilings; unset/invalid env falls back to defaults.
        self.daily_cost: float = 0.0
        self.monthly_cost: float = 0.0
        self.max_daily: float = self._env_limit("DEEPR_MAX_COST_PER_DAY", 50.0, self.ABSOLUTE_MAX_DAILY)
        self.max_monthly: float = self._env_limit("DEEPR_MAX_COST_PER_MONTH", 500.0, self.ABSOLUTE_MAX_MONTHLY)
        self._last_daily_reset: float = time.time()
        self._last_monthly_reset: float = time.time()

        # Cross-thread lock guarding check_operation + record_cost as a single
        # critical section. ExpertCouncil.consult and TaskPlanner.execute_plan
        # both fan out to a shared singleton manager; without this lock N
        # parallel checks all observe the same stale daily_cost and pass,
        # then over-commit by N times. Reservation pattern: reserve in
        # check_operation, settle in record_cost.
        self._budget_lock = threading.Lock()
        # In-flight reservations keyed by (session_id, reservation_id) →
        # estimated_cost. record_cost / refund_reservation drain them.
        self._reserved_daily: float = 0.0
        self._reserved_monthly: float = 0.0
        self._reservations: dict[str, float] = {}

    @staticmethod
    def _env_limit(var: str, default: float, ceiling: float) -> float:
        """Read a spend limit from the environment, clamped to (0, ceiling]."""
        raw = os.getenv(var)
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            return default
        if value <= 0:
            return default
        return min(value, ceiling)

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

    def get_session(self, session_id: str) -> CostSession | None:
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
        """Check if an operation should be allowed (no reservation).

        For new callers that need over-commit protection across parallel
        fan-out (ExpertCouncil, TaskPlanner), prefer ``check_and_reserve``
        which returns a reservation_id you pass back to ``record_cost``.

        Args:
            session_id: Session identifier for tracking
            operation_type: Type of operation (e.g., "research_submit")
            estimated_cost: Estimated cost of the operation
            require_confirmation: Whether to require user confirmation

        Returns:
            Tuple of (allowed, reason, needs_confirmation)
        """
        allowed, reason, needs_confirm, _ = self.check_and_reserve(
            session_id=session_id,
            operation_type=operation_type,
            estimated_cost=estimated_cost,
            require_confirmation=require_confirmation,
            reserve=False,
        )
        return allowed, reason, needs_confirm

    def check_and_reserve(
        self,
        session_id: str,
        operation_type: str,
        estimated_cost: float,
        require_confirmation: bool = False,
        reserve: bool = True,
    ) -> tuple[bool, str, bool, str]:
        """Atomic check + (optional) reservation of estimated_cost.

        Holds ``self._budget_lock`` across the read-modify-write so N parallel
        callers can't all see stale daily/monthly totals. When ``reserve=True``
        and allowed, the cost is added to in-flight daily *and* monthly
        reservation pools that subsequent ``check_operation`` calls treat as
        already-spent (neither cap over-commits). ``record_cost``
        clears the reservation when the actual cost lands; if a caller
        forgets to record, call ``refund_reservation(reservation_id)``.

        Returns ``(allowed, reason, needs_confirmation, reservation_id)``.
        ``reservation_id`` is empty when no reservation was placed.
        """
        with self._budget_lock:
            # Per-op hard ceiling — any caller value above this is silently
            # treated as a denial regardless of session/daily room.
            if estimated_cost > self.ABSOLUTE_MAX_PER_OPERATION:
                return (
                    False,
                    f"Estimated cost ${estimated_cost:.2f} exceeds absolute per-op ceiling ${self.ABSOLUTE_MAX_PER_OPERATION:.2f}",
                    False,
                    "",
                )

            # Circuit breaker
            allowed, reason = self._circuit_breaker.allow_request(estimated_cost)
            if not allowed:
                return False, reason or "circuit breaker tripped", False, ""

            # Session budget
            session = self._sessions.get(session_id)
            if session:
                can_proceed, session_reason = session.can_proceed(estimated_cost)
                if not can_proceed:
                    return False, session_reason, False, ""

            # Daily projection including in-flight reservations
            projected_daily = self.daily_cost + self._reserved_daily + estimated_cost
            if projected_daily > self.max_daily:
                return (
                    False,
                    f"Daily limit ${self.max_daily:.2f} would be exceeded (spent ${self.daily_cost:.2f}, reserved ${self._reserved_daily:.2f}, +${estimated_cost:.2f})",
                    False,
                    "",
                )
            projected_monthly = self.monthly_cost + self._reserved_monthly + estimated_cost
            if projected_monthly > self.max_monthly:
                return (
                    False,
                    f"Monthly limit ${self.max_monthly:.2f} would be exceeded",
                    False,
                    "",
                )

            # Reserve
            reservation_id = ""
            if reserve:
                import uuid as _uuid

                reservation_id = _uuid.uuid4().hex[:16]
                self._reservations[reservation_id] = estimated_cost
                self._reserved_daily += estimated_cost
                self._reserved_monthly += estimated_cost

            # Confirmation needed?
            if require_confirmation and estimated_cost > 1.0:
                return True, f"High cost operation: ${estimated_cost:.2f}", True, reservation_id

            return True, "OK", False, reservation_id

    def refund_reservation(self, reservation_id: str) -> None:
        """Release a reservation without recording a cost (e.g. on caller error)."""
        if not reservation_id:
            return
        with self._budget_lock:
            held = self._reservations.pop(reservation_id, 0.0)
            self._reserved_daily = max(0.0, self._reserved_daily - held)
            self._reserved_monthly = max(0.0, self._reserved_monthly - held)

    def record_cost(
        self,
        session_id: str,
        operation_type: str,
        actual_cost: float,
        details: str | None = None,
        provider: str = "unknown",
        model: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        request_id: str = "",
        idempotency_key: str = "",
        source: str = "cost_safety.record_cost",
        metadata: dict | None = None,
        agent_id: str = "",
        reservation_id: str = "",
    ) -> bool:
        """Record a cost event and settle any reservation.

        Pass ``reservation_id`` returned from ``check_and_reserve`` to
        release the reservation pool slot as part of this commit.
        """
        # Settle reservation + commit daily/monthly atomically.
        with self._budget_lock:
            if reservation_id:
                held = self._reservations.pop(reservation_id, 0.0)
                self._reserved_daily = max(0.0, self._reserved_daily - held)
                self._reserved_monthly = max(0.0, self._reserved_monthly - held)

            # Track session cost (legacy)
            self._session_costs[session_id] = self._session_costs.get(session_id, 0.0) + actual_cost

            # Track in session if exists
            session = self._sessions.get(session_id)
            if session:
                session.record_operation(operation_type, actual_cost, details)

            # Track daily/monthly
            self.daily_cost += actual_cost
            self.monthly_cost += actual_cost

        # Record canonical ledger event
        event_metadata = dict(metadata or {})
        if details:
            event_metadata["details"] = details
        try:
            self._ledger.record_event(
                operation=operation_type,
                provider=provider or "unknown",
                model=model or "",
                cost_usd=actual_cost,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                task_id=session_id,
                session_id=session_id,
                request_id=request_id,
                source=source,
                idempotency_key=idempotency_key,
                metadata=event_metadata,
                agent_id=agent_id,
            )
        except OSError as e:
            if self._strict_tracking:
                raise RuntimeError(f"Cost ledger write failed in strict mode: {e}") from e

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
            Dictionary with daily and monthly spending info (including
            percent_used) plus the configured limits - the exact contract
            `deepr budget safety` renders. The command crashed with
            KeyError before these fields existed; regression-tested now.
        """

        def _percent(spent: float, limit: float) -> float:
            return (spent / limit * 100.0) if limit > 0 else 0.0

        return {
            "daily": {
                "spent": self.daily_cost,
                "limit": self.max_daily,
                "remaining": max(0, self.max_daily - self.daily_cost),
                "percent_used": _percent(self.daily_cost, self.max_daily),
            },
            "monthly": {
                "spent": self.monthly_cost,
                "limit": self.max_monthly,
                "remaining": max(0, self.max_monthly - self.monthly_cost),
                "percent_used": _percent(self.monthly_cost, self.max_monthly),
            },
            "limits": {
                "per_operation": self.ABSOLUTE_MAX_PER_OPERATION,
                "daily": self.max_daily,
                "monthly": self.max_monthly,
            },
            "active_sessions": len(self._sessions),
        }

    def close_session(self, session_id: str) -> dict | None:
        """Close a cost tracking session and return its summary.

        Args:
            session_id: Session identifier to close

        Returns:
            Dictionary with session summary, or None if session not found
        """
        session = self._sessions.pop(session_id, None)
        if session is None:
            # Also clean up legacy cost tracking
            self._session_costs.pop(session_id, None)
            return None

        # Clean up legacy tracking too
        self._session_costs.pop(session_id, None)

        return {
            "session_id": session_id,
            "session_type": session.session_type,
            "total_cost": session.total_cost,
            "budget_limit": session.budget_limit,
            "operations": len(session.operations),
            "failures": len(session.failures),
            "alerts": [{"level": a.level, "message": a.message} for a in session.alerts],
            "duration_seconds": time.time() - session.created_at,
        }

    def reset(self) -> None:
        """Reset all tracking state."""
        self._circuit_breaker.reset()
        self._session_costs.clear()
        self._sessions.clear()
        self.daily_cost = 0.0
        self.monthly_cost = 0.0


# Global singleton instance
_cost_safety_manager: CostSafetyManager | None = None


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


def estimate_curriculum_cost(
    topic_count: int,
    deep_research_count: int = 0,
    quick_research_count: int = 0,
    docs_count: int = 0,
) -> dict:
    """Estimate the cost of executing a learning curriculum.

    Returns dict with expected_cost, min_cost, max_cost.
    """
    # Per-topic cost estimates by research mode
    deep_cost = 2.00  # campaign mode
    quick_cost = 0.25  # focus mode
    docs_cost = 0.15  # documentation

    other_count = max(0, topic_count - deep_research_count - quick_research_count - docs_count)
    expected = (
        deep_research_count * deep_cost
        + quick_research_count * quick_cost
        + docs_count * docs_cost
        + other_count * quick_cost
    )
    return {
        "expected_cost": expected,
        "min_cost": expected * 0.5,
        "max_cost": expected * 1.5,
        "topic_count": topic_count,
    }


def format_cost_warning(expected_cost: float, budget_limit: float | None) -> str:
    """Format a human-readable cost warning for curriculum execution."""
    msg = f"Estimated cost: ${expected_cost:.2f}"
    if budget_limit is not None:
        if expected_cost > budget_limit:
            msg += f" (exceeds ${budget_limit:.2f} budget — will stop at limit)"
        else:
            msg += f" (within ${budget_limit:.2f} budget)"
    return msg


def is_pausable_limit(reason: str) -> bool:
    """Check if a block reason is a pausable limit (daily/monthly) vs a hard stop.

    Pausable limits mean progress can be saved and resumed later.
    """
    if not reason:
        return False
    lower = reason.lower()
    return "daily" in lower or "monthly" in lower


def get_resume_message(reason: str) -> str:
    """Get a human-readable message explaining when learning can resume.

    Args:
        reason: The block reason from check_operation
    """
    lower = (reason or "").lower()
    if "daily" in lower:
        return "Daily spending limit reached. Learning will resume tomorrow."
    elif "monthly" in lower:
        return "Monthly spending limit reached. Learning will resume next month."
    return f"Spending limit reached: {reason}"
