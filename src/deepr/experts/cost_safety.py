"""Cost safety utilities for preventing runaway spending.

Implements circuit breaker pattern to detect and halt rapid cost accumulation.
Provides defense against accidental or malicious cost spikes.

Requirements: 8.2 - Implement rapid cost accumulation detection and circuit breaker
"""

import os
import threading
import time
from dataclasses import dataclass
from math import isfinite
from typing import Any

from deepr.experts.cost_circuit_breaker import (
    CircuitBreakerState as CircuitBreakerState,
)
from deepr.experts.cost_circuit_breaker import (
    CostCircuitBreaker,
)
from deepr.experts.cost_circuit_breaker import (
    CostEvent as CostEvent,
)
from deepr.experts.cost_circuit_breaker import (
    CostLimitExceeded as CostLimitExceeded,
)
from deepr.experts.cost_safety_ledger import (
    CostLedgerCommitError,
    CostRecord,
    DurableCostReservationError,
    append_cost_record,
)
from deepr.experts.research_reservation_store import (
    ResearchReservationLimitExceeded,
    ResearchReservationStore,
)
from deepr.observability.cost_ledger import CostLedger, CostLedgerDurabilityError


def _validated_money(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


def _validate_durable_request(enabled: bool, reserve: bool, job_id: str) -> None:
    if enabled and (not reserve or not job_id.strip()):
        raise ValueError("durable reservations require reserve=True and a reservation_job_id")


@dataclass
class CostAlert:
    """Alert generated when cost thresholds are approached or exceeded."""

    level: str  # "warning", "critical"
    message: str
    timestamp: float
    threshold_percent: float
    current_cost: float
    budget_limit: float

    def to_dict(self) -> dict[str, Any]:
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
        self.operations: list[dict[str, Any]] = []
        self.alerts: list[CostAlert] = []
        self.failures: list[dict[str, Any]] = []
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
        estimated_cost = _validated_money(estimated_cost, field_name="estimated_cost")

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

    def record_operation(
        self,
        operation_type: str,
        cost: float,
        details: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Record a cost-incurring operation.

        Args:
            operation_type: Type of operation
            cost: Cost of the operation
            details: Optional details
            **kwargs: Additional metadata
        """
        cost = _validated_money(cost, field_name="cost")
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

    def get_summary(self) -> dict[str, Any]:
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
    """High-level cost safety: circuit breaker + per-session tracking + atomic
    daily/monthly caps with a reserve-then-settle pattern.

    Use ``check_and_reserve`` -> ``record_cost(reservation_id=...)`` (or
    ``refund_reservation`` on caller error) so parallel callers cannot
    over-commit a cap. A reservation that is never settled or refunded (e.g. a
    crash between the two) is released by the TTL sweep on the next check, so a
    leak cannot permanently shrink a tight pool. Contract: see
    ``test_cost_safety_reservations.py``.
    """

    # Hard ceilings the manager will never permit, regardless of any
    # caller-supplied "budget". These act as a last-line safety net for
    # MCP/CLI surfaces that accept user-controlled budget values.
    # Kept as class attributes so callers (mcp/server.py, cli/commands/
    # budget.py) can reference them without instantiating a manager.
    ABSOLUTE_MAX_PER_OPERATION: float = 10.0
    ABSOLUTE_MAX_DAILY: float = 50.0
    ABSOLUTE_MAX_MONTHLY: float = 500.0

    # A reservation is presumed leaked (caller crashed between reserve and
    # settle) once it outlives this, and is swept so it stops shrinking the pool.
    # Longer than any real operation, so a live op is never swept.
    RESERVATION_TTL_SECONDS: float = 3600.0

    def __init__(self, circuit_breaker: CostCircuitBreaker | None = None):
        """Initialize cost safety manager.

        Args:
            circuit_breaker: Optional custom circuit breaker. If None,
                           uses default configuration.
        """
        self._circuit_breaker = circuit_breaker or create_default_circuit_breaker()
        self._session_costs: dict[str, float] = {}
        self._sessions: dict[str, CostSession] = {}
        self._ledger = CostLedger(lock_timeout_seconds=5.0)
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
        # In-flight reservations keyed by (session_id, reservation_id) ->
        # estimated_cost. record_cost / refund_reservation drain them.
        self._reserved_daily: float = 0.0
        self._reserved_monthly: float = 0.0
        self._reservations: dict[str, float] = {}
        # reservation_id -> creation time, for the leaked-reservation TTL sweep.
        self._reservation_started: dict[str, float] = {}
        # Stable event keys already reflected in this process's counters.
        # The canonical ledger remains authoritative across processes.
        self._locally_accounted_idempotency_keys: set[str] = set()
        # Required appends that wrote a line but could not confirm fsync. A
        # successful idempotent replay may account these locally exactly once.
        self._pending_local_durability_keys: set[str] = set()
        self._durable_reservation_jobs: dict[str, str] = {}
        self._provider_work_may_have_run: set[str] = set()
        self._unresolved_durable_reservations: set[str] = set()
        self._reservation_store: ResearchReservationStore | None = None

    def _get_reservation_store(self) -> ResearchReservationStore:
        if self._reservation_store is None:
            self._reservation_store = ResearchReservationStore(lock_timeout_seconds=5.0)
        return self._reservation_store

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
        if not isfinite(value) or value <= 0:
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
        budget_limit = _validated_money(budget_limit, field_name="budget_limit")
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
        durable_reservation: bool = False,
        reservation_job_id: str = "",
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
        estimated_cost = _validated_money(estimated_cost, field_name="estimated_cost")
        _validate_durable_request(durable_reservation, reserve, reservation_job_id)
        with self._budget_lock:
            # Release any leaked reservations before projecting, so a crashed
            # caller's stale hold cannot keep blocking the pool.
            self._sweep_stale_reservations(time.time())

            # Per-op hard ceiling - any caller value above this is silently
            # treated as a denial regardless of session/daily room.
            if estimated_cost > self.ABSOLUTE_MAX_PER_OPERATION:
                return (
                    False,
                    f"Estimated cost ${estimated_cost:.2f} exceeds absolute per-op ceiling ${self.ABSOLUTE_MAX_PER_OPERATION:.2f}",
                    False,
                    "",
                )

            # Circuit breaker
            allowed, reason = self._circuit_breaker.allow_request(
                estimated_cost,
                reserved_cost=self._reserved_daily,
                reserved_events=len(self._reservations),
            )
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
                placed, placement_reason, reservation_id = self._place_reservation(
                    estimated_cost=estimated_cost,
                    durable_reservation=durable_reservation,
                    reservation_job_id=reservation_job_id,
                )
                if not placed:
                    return False, placement_reason, False, ""

            # Confirmation needed?
            if require_confirmation and estimated_cost > 1.0:
                return True, f"High cost operation: ${estimated_cost:.2f}", True, reservation_id

            return True, "OK", False, reservation_id

    def _place_reservation(
        self,
        *,
        estimated_cost: float,
        durable_reservation: bool,
        reservation_job_id: str,
    ) -> tuple[bool, str, str]:
        import uuid as _uuid

        reservation_id = _uuid.uuid4().hex[:16]
        if durable_reservation:
            try:
                self._get_reservation_store().reserve(
                    reservation_id=reservation_id,
                    job_id=reservation_job_id,
                    reserved_cost=estimated_cost,
                    max_daily_cost=self.max_daily,
                    max_monthly_cost=self.max_monthly,
                )
            except ResearchReservationLimitExceeded as error:
                return False, str(error), ""
            except Exception as error:
                raise DurableCostReservationError("durable cost reservation failed") from error
            self._durable_reservation_jobs[reservation_id] = reservation_job_id
        self._reservations[reservation_id] = estimated_cost
        self._reservation_started[reservation_id] = time.time()
        self._reserved_daily += estimated_cost
        self._reserved_monthly += estimated_cost
        return True, "OK", reservation_id

    def _sweep_stale_reservations(self, now: float) -> None:
        """Release reservations older than the TTL. Caller holds ``_budget_lock``.

        A reservation that is never settled or refunded (a crash between reserve
        and record) would otherwise hold its slice of the daily/monthly pool
        forever; on a tight monthly reserve that silently starves the fleet.
        """
        stale = [
            rid
            for rid, started in self._reservation_started.items()
            if rid not in self._durable_reservation_jobs and now - started > self.RESERVATION_TTL_SECONDS
        ]
        for rid in stale:
            held = self._reservations.pop(rid, 0.0)
            self._reservation_started.pop(rid, None)
            self._reserved_daily = max(0.0, self._reserved_daily - held)
            self._reserved_monthly = max(0.0, self._reserved_monthly - held)

    def mark_provider_work_may_have_run(self, reservation_id: str) -> None:
        """Persist that a durable hold can no longer be safely auto-refunded."""
        if not reservation_id:
            return
        with self._budget_lock:
            durable = reservation_id in self._durable_reservation_jobs
        if not durable:
            return
        try:
            self._get_reservation_store().mark_provider_work_may_have_run(reservation_id)
        except Exception as error:
            raise DurableCostReservationError("durable reservation dispatch mark failed") from error
        with self._budget_lock:
            self._provider_work_may_have_run.add(reservation_id)

    def mark_reservation_unresolved(self, reservation_id: str) -> None:
        """Keep a durable hold active after required accounting failure."""
        if not reservation_id:
            return
        with self._budget_lock:
            if reservation_id in self._durable_reservation_jobs:
                self._unresolved_durable_reservations.add(reservation_id)

    def refund_reservation(self, reservation_id: str, *, provider_work_did_not_run: bool = False) -> None:
        """Release a reservation without recording a cost (e.g. on caller error)."""
        if not reservation_id:
            return
        with self._budget_lock:
            durable = reservation_id in self._durable_reservation_jobs
            provider_work_possible = reservation_id in self._provider_work_may_have_run
            unresolved = reservation_id in self._unresolved_durable_reservations
        if durable and (provider_work_possible or unresolved) and not provider_work_did_not_run:
            return
        if durable:
            try:
                store = self._get_reservation_store()
                refunded = store.refund(
                    reservation_id,
                    provider_work_did_not_run=provider_work_did_not_run,
                )
            except Exception as error:
                raise DurableCostReservationError("durable reservation refund failed") from error
            if not refunded and store.is_active(reservation_id):
                return
        with self._budget_lock:
            held = self._reservations.pop(reservation_id, 0.0)
            self._reservation_started.pop(reservation_id, None)
            self._reserved_daily = max(0.0, self._reserved_daily - held)
            self._reserved_monthly = max(0.0, self._reserved_monthly - held)
            self._durable_reservation_jobs.pop(reservation_id, None)
            self._provider_work_may_have_run.discard(reservation_id)
            self._unresolved_durable_reservations.discard(reservation_id)

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
        metadata: dict[str, Any] | None = None,
        agent_id: str = "",
        reservation_id: str = "",
        require_ledger: bool = False,
    ) -> bool:
        """Record a cost event and settle any reservation.

        Pass ``reservation_id`` returned from ``check_and_reserve`` to
        release the reservation pool slot as part of this commit. Set
        ``require_ledger`` for spend boundaries that must not settle unless the
        canonical append succeeds. An idempotent duplicate releases its
        reservation but does not increment process-local totals again.
        """
        actual_cost = _validated_money(actual_cost, field_name="actual_cost")
        with self._budget_lock:
            durable_job_id = self._durable_reservation_jobs.get(reservation_id, "")
        event_metadata = dict(metadata or {})
        if durable_job_id:
            event_metadata["cost_reservation_id"] = reservation_id
            event_metadata["cost_reservation_job_id"] = durable_job_id
        record = CostRecord(
            session_id=session_id,
            operation_type=operation_type,
            actual_cost=actual_cost,
            details=details,
            provider=provider,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            request_id=request_id,
            idempotency_key=idempotency_key,
            source=source,
            metadata=event_metadata,
            agent_id=agent_id,
            reservation_id=reservation_id,
            require_ledger=require_ledger or bool(durable_job_id),
        )
        return self._settle_durable_record(record) if durable_job_id else self._record_cost_once(record)

    def _settle_durable_record(self, record: CostRecord) -> bool:
        callback_ran = False
        ledger_appended = False

        def append_only() -> None:
            nonlocal callback_ran, ledger_appended
            callback_ran = True
            ledger_appended = append_cost_record(self._ledger, record, strict_tracking=self._strict_tracking)

        try:
            outcome = self._get_reservation_store().settle(
                record.reservation_id,
                record.actual_cost,
                append_only,
            )
        except CostLedgerCommitError as error:
            self._remember_durability_failure(record, error)
            self.mark_reservation_unresolved(record.reservation_id)
            raise
        except Exception as error:
            self.mark_reservation_unresolved(record.reservation_id)
            raise DurableCostReservationError("durable cost reservation settlement failed") from error
        if outcome != "settled":
            self.mark_reservation_unresolved(record.reservation_id)
            raise DurableCostReservationError(f"durable cost reservation is {outcome}")
        if not callback_ran:
            self.mark_reservation_unresolved(record.reservation_id)
            raise DurableCostReservationError("durable cost reservation settlement was not verified")
        result = self._account_cost_record(record, ledger_appended)
        with self._budget_lock:
            self._durable_reservation_jobs.pop(record.reservation_id, None)
            self._provider_work_may_have_run.discard(record.reservation_id)
            self._unresolved_durable_reservations.discard(record.reservation_id)
        return result

    def _record_cost_once(self, record: CostRecord) -> bool:
        try:
            ledger_appended = append_cost_record(self._ledger, record, strict_tracking=self._strict_tracking)
        except CostLedgerCommitError as error:
            self._remember_durability_failure(record, error)
            raise
        return self._account_cost_record(record, ledger_appended)

    def _remember_durability_failure(self, record: CostRecord, error: CostLedgerCommitError) -> None:
        if (
            record.require_ledger
            and record.idempotency_key
            and isinstance(error.ledger_error, CostLedgerDurabilityError)
        ):
            with self._budget_lock:
                self._pending_local_durability_keys.add(record.idempotency_key)

    def _account_cost_record(self, record: CostRecord, ledger_appended: bool) -> bool:
        """Apply one committed event to process-local accounting."""
        with self._budget_lock:
            if record.reservation_id:
                held = self._reservations.pop(record.reservation_id, 0.0)
                self._reservation_started.pop(record.reservation_id, None)
                self._reserved_daily = max(0.0, self._reserved_daily - held)
                self._reserved_monthly = max(0.0, self._reserved_monthly - held)
                self._unresolved_durable_reservations.discard(record.reservation_id)

            recovering_durability = bool(
                record.idempotency_key and record.idempotency_key in self._pending_local_durability_keys
            )
            if record.idempotency_key:
                self._pending_local_durability_keys.discard(record.idempotency_key)
            already_accounted = bool(
                record.idempotency_key and record.idempotency_key in self._locally_accounted_idempotency_keys
            )
            if already_accounted:
                return True
            if not ledger_appended and not recovering_durability:
                return True
            if record.idempotency_key:
                self._locally_accounted_idempotency_keys.add(record.idempotency_key)

            self._session_costs[record.session_id] = (
                self._session_costs.get(record.session_id, 0.0) + record.actual_cost
            )
            session = self._sessions.get(record.session_id)
            if session:
                session.record_operation(record.operation_type, record.actual_cost, record.details)
            self.daily_cost += record.actual_cost
            self.monthly_cost += record.actual_cost

        return self._circuit_breaker.record_cost(
            cost=record.actual_cost,
            operation=record.operation_type,
            job_id=record.session_id,
        )

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

    def get_spending_summary(self) -> dict[str, Any]:
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

    def close_session(self, session_id: str) -> dict[str, Any] | None:
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
        self._reserved_daily = 0.0
        self._reserved_monthly = 0.0
        self._reservations.clear()
        self._reservation_started.clear()
        self._locally_accounted_idempotency_keys.clear()
        self._pending_local_durability_keys.clear()
        self._durable_reservation_jobs.clear()
        self._provider_work_may_have_run.clear()
        self._unresolved_durable_reservations.clear()


# Global singleton instance
_cost_safety_manager: CostSafetyManager | None = None
_cost_safety_manager_lock = threading.Lock()


def get_cost_safety_manager() -> CostSafetyManager:
    """Get the global cost safety manager instance.

    Returns:
        CostSafetyManager singleton instance
    """
    global _cost_safety_manager
    if _cost_safety_manager is None:
        with _cost_safety_manager_lock:
            if _cost_safety_manager is None:
                _cost_safety_manager = CostSafetyManager()
    return _cost_safety_manager


def reset_cost_safety_manager() -> None:
    """Reset the global cost safety manager.

    Useful for testing or when starting a new session.
    """
    global _cost_safety_manager
    with _cost_safety_manager_lock:
        if _cost_safety_manager is not None:
            _cost_safety_manager.reset()
        _cost_safety_manager = None


def estimate_curriculum_cost(
    topic_count: int,
    deep_research_count: int = 0,
    quick_research_count: int = 0,
    docs_count: int = 0,
) -> dict[str, float | int]:
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
            msg += f" (exceeds ${budget_limit:.2f} budget - will stop at limit)"
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
