"""Defensive cost controls for autonomous expert operations.

This module provides hard budget caps and safety mechanisms to prevent
runaway costs from autonomous agents (learning, chat, curriculum execution).

Key safety features:
1. Hard budget caps that cannot be bypassed
2. Session-level cost tracking with alerts
3. Confirmation prompts before expensive operations
4. Dry-run mode for cost estimation
5. Circuit breakers for repeated failures
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Callable
from enum import Enum
import json
from pathlib import Path


class CostAlertLevel(Enum):
    """Alert levels for cost warnings."""
    INFO = "info"           # Under 50% of budget
    WARNING = "warning"     # 50-80% of budget
    CRITICAL = "critical"   # 80-95% of budget
    BLOCKED = "blocked"     # Over 95% or hard limit
    PAUSED = "paused"       # Hit daily/monthly limit - can resume later


@dataclass
class CostAlert:
    """A cost alert event."""
    level: CostAlertLevel
    message: str
    current_cost: float
    budget_limit: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "message": self.message,
            "current_cost": self.current_cost,
            "budget_limit": self.budget_limit,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class SessionCostTracker:
    """Track costs within a single session (chat, learning, etc.)."""
    
    session_id: str
    session_type: str  # "chat", "learning", "curriculum"
    budget_limit: float
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cost tracking
    total_cost: float = 0.0
    operation_count: int = 0
    operations: List[Dict] = field(default_factory=list)
    
    # Alerts
    alerts: List[CostAlert] = field(default_factory=list)
    last_alert_level: CostAlertLevel = CostAlertLevel.INFO
    
    # Circuit breaker
    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    is_circuit_open: bool = False
    
    def record_operation(self, operation_type: str, cost: float, details: str = ""):
        """Record a cost-incurring operation."""
        self.total_cost += cost
        self.operation_count += 1
        
        self.operations.append({
            "type": operation_type,
            "cost": cost,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cumulative_cost": self.total_cost
        })
        
        # Reset failure counter on success
        self.consecutive_failures = 0
        
        # Check for alerts
        self._check_alerts()
    
    def record_failure(self, operation_type: str, error: str):
        """Record a failed operation (for circuit breaker)."""
        self.consecutive_failures += 1
        
        self.operations.append({
            "type": operation_type,
            "cost": 0.0,
            "details": f"FAILED: {error}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cumulative_cost": self.total_cost
        })
        
        # Check circuit breaker
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.is_circuit_open = True
            self.alerts.append(CostAlert(
                level=CostAlertLevel.BLOCKED,
                message=f"Circuit breaker opened after {self.consecutive_failures} consecutive failures",
                current_cost=self.total_cost,
                budget_limit=self.budget_limit
            ))
    
    def _check_alerts(self):
        """Check if cost thresholds have been crossed and generate alerts."""
        if self.budget_limit <= 0:
            return
        
        ratio = self.total_cost / self.budget_limit
        
        if ratio >= 0.95:
            new_level = CostAlertLevel.BLOCKED
            message = f"Budget nearly exhausted: ${self.total_cost:.2f} / ${self.budget_limit:.2f} (95%+)"
        elif ratio >= 0.80:
            new_level = CostAlertLevel.CRITICAL
            message = f"Budget critical: ${self.total_cost:.2f} / ${self.budget_limit:.2f} (80%+)"
        elif ratio >= 0.50:
            new_level = CostAlertLevel.WARNING
            message = f"Budget warning: ${self.total_cost:.2f} / ${self.budget_limit:.2f} (50%+)"
        else:
            new_level = CostAlertLevel.INFO
            message = None
        
        # Only alert on level changes (avoid spam)
        if new_level != self.last_alert_level and message:
            self.alerts.append(CostAlert(
                level=new_level,
                message=message,
                current_cost=self.total_cost,
                budget_limit=self.budget_limit
            ))
            self.last_alert_level = new_level
    
    def can_proceed(self, estimated_cost: float = 0.0) -> tuple[bool, Optional[str]]:
        """Check if an operation can proceed given current costs.
        
        Args:
            estimated_cost: Estimated cost of the next operation
            
        Returns:
            (can_proceed, reason) - reason is None if can proceed
        """
        # Check circuit breaker
        if self.is_circuit_open:
            return False, f"Circuit breaker open after {self.consecutive_failures} failures. Reset session to continue."
        
        # Check hard budget limit
        if self.budget_limit > 0:
            projected_cost = self.total_cost + estimated_cost
            
            if projected_cost > self.budget_limit:
                return False, (
                    f"Operation would exceed budget: "
                    f"${self.total_cost:.2f} + ${estimated_cost:.2f} = ${projected_cost:.2f} > ${self.budget_limit:.2f}"
                )
            
            # Warn if getting close
            if projected_cost > self.budget_limit * 0.95:
                return False, (
                    f"Budget nearly exhausted (95%+): "
                    f"${self.total_cost:.2f} spent, ${self.budget_limit - self.total_cost:.2f} remaining"
                )
        
        return True, None
    
    def get_remaining_budget(self) -> float:
        """Get remaining budget."""
        if self.budget_limit <= 0:
            return float('inf')
        return max(0, self.budget_limit - self.total_cost)
    
    def get_summary(self) -> dict:
        """Get session cost summary."""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "total_cost": round(self.total_cost, 4),
            "budget_limit": self.budget_limit,
            "remaining": round(self.get_remaining_budget(), 4),
            "operation_count": self.operation_count,
            "alerts": [a.to_dict() for a in self.alerts],
            "circuit_breaker_open": self.is_circuit_open,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": (datetime.now(timezone.utc) - self.started_at).total_seconds()
        }


class CostSafetyManager:
    """Global cost safety manager for all expert operations.
    
    Provides:
    - Hard daily/monthly limits that cannot be bypassed
    - Per-operation cost caps
    - Confirmation requirements for expensive operations
    - Audit logging of all costs
    """
    
    # Hard limits that cannot be overridden (safety net)
    ABSOLUTE_MAX_PER_OPERATION = 10.0   # $10 max per single operation
    ABSOLUTE_MAX_DAILY = 50.0           # $50 max per day
    ABSOLUTE_MAX_MONTHLY = 500.0        # $500 max per month
    
    # Thresholds for confirmation prompts
    CONFIRM_THRESHOLD = 1.0             # Confirm operations over $1
    WARN_THRESHOLD = 0.50               # Warn for operations over $0.50
    
    def __init__(
        self,
        max_per_operation: float = 5.0,
        max_daily: float = 25.0,
        max_monthly: float = 200.0,
        audit_log_path: Optional[Path] = None
    ):
        """Initialize cost safety manager.
        
        Args:
            max_per_operation: Max cost per single operation (default $5)
            max_daily: Max daily spending (default $25)
            max_monthly: Max monthly spending (default $200)
            audit_log_path: Optional path for audit log
        """
        # Apply hard limits
        self.max_per_operation = min(max_per_operation, self.ABSOLUTE_MAX_PER_OPERATION)
        self.max_daily = min(max_daily, self.ABSOLUTE_MAX_DAILY)
        self.max_monthly = min(max_monthly, self.ABSOLUTE_MAX_MONTHLY)
        
        # Tracking
        self.daily_cost = 0.0
        self.monthly_cost = 0.0
        self.last_reset_date = datetime.now(timezone.utc).date()
        self.last_reset_month = datetime.now(timezone.utc).month
        
        # Audit log
        self.audit_log_path = audit_log_path
        self.audit_entries: List[Dict] = []
        
        # Active sessions
        self.active_sessions: Dict[str, SessionCostTracker] = {}
    
    def _reset_if_needed(self):
        """Reset daily/monthly counters if needed."""
        now = datetime.now(timezone.utc)
        
        # Reset daily
        if now.date() > self.last_reset_date:
            self.daily_cost = 0.0
            self.last_reset_date = now.date()
        
        # Reset monthly
        if now.month != self.last_reset_month:
            self.monthly_cost = 0.0
            self.last_reset_month = now.month
    
    def create_session(
        self,
        session_id: str,
        session_type: str,
        budget_limit: float
    ) -> SessionCostTracker:
        """Create a new cost tracking session.
        
        Args:
            session_id: Unique session identifier
            session_type: Type of session (chat, learning, curriculum)
            budget_limit: Budget limit for this session
            
        Returns:
            SessionCostTracker instance
        """
        # Apply hard limits to session budget
        effective_budget = min(budget_limit, self.max_daily - self.daily_cost)
        
        session = SessionCostTracker(
            session_id=session_id,
            session_type=session_type,
            budget_limit=effective_budget
        )
        
        self.active_sessions[session_id] = session
        
        self._audit_log("session_created", {
            "session_id": session_id,
            "session_type": session_type,
            "budget_limit": effective_budget,
            "original_budget": budget_limit
        })
        
        return session
    
    def check_operation(
        self,
        session_id: str,
        operation_type: str,
        estimated_cost: float,
        require_confirmation: bool = True
    ) -> tuple[bool, Optional[str], bool]:
        """Check if an operation can proceed.
        
        Args:
            session_id: Session ID
            operation_type: Type of operation
            estimated_cost: Estimated cost
            require_confirmation: Whether to require confirmation for expensive ops
            
        Returns:
            (allowed, reason, needs_confirmation)
            
        Note: When hitting daily/monthly limits, the reason will include
        "DAILY_LIMIT" or "MONTHLY_LIMIT" to indicate this is a pausable
        condition (can resume tomorrow/next month) vs a hard block.
        """
        self._reset_if_needed()
        
        # Check absolute per-operation limit
        if estimated_cost > self.ABSOLUTE_MAX_PER_OPERATION:
            return False, (
                f"Operation cost ${estimated_cost:.2f} exceeds absolute maximum "
                f"${self.ABSOLUTE_MAX_PER_OPERATION:.2f}"
            ), False
        
        # Check configured per-operation limit
        if estimated_cost > self.max_per_operation:
            return False, (
                f"Operation cost ${estimated_cost:.2f} exceeds limit "
                f"${self.max_per_operation:.2f}"
            ), False
        
        # Check daily limit - this is PAUSABLE (can resume tomorrow)
        if self.daily_cost + estimated_cost > self.max_daily:
            return False, (
                f"DAILY_LIMIT: Daily limit would be exceeded: "
                f"${self.daily_cost:.2f} + ${estimated_cost:.2f} > ${self.max_daily:.2f}. "
                f"Progress saved - resume tomorrow when daily limit resets."
            ), False
        
        # Check monthly limit - this is PAUSABLE (can resume next month)
        if self.monthly_cost + estimated_cost > self.max_monthly:
            return False, (
                f"MONTHLY_LIMIT: Monthly limit would be exceeded: "
                f"${self.monthly_cost:.2f} + ${estimated_cost:.2f} > ${self.max_monthly:.2f}. "
                f"Progress saved - resume next month when monthly limit resets."
            ), False
        
        # Check session budget
        session = self.active_sessions.get(session_id)
        if session:
            can_proceed, reason = session.can_proceed(estimated_cost)
            if not can_proceed:
                return False, reason, False
        
        # Check if confirmation needed
        needs_confirmation = (
            require_confirmation and 
            estimated_cost >= self.CONFIRM_THRESHOLD
        )
        
        return True, None, needs_confirmation
    
    def record_cost(
        self,
        session_id: str,
        operation_type: str,
        actual_cost: float,
        details: str = ""
    ):
        """Record actual cost after operation completes.
        
        Args:
            session_id: Session ID
            operation_type: Type of operation
            actual_cost: Actual cost incurred
            details: Optional details
        """
        self._reset_if_needed()
        
        # Update global counters
        self.daily_cost += actual_cost
        self.monthly_cost += actual_cost
        
        # Update session
        session = self.active_sessions.get(session_id)
        if session:
            session.record_operation(operation_type, actual_cost, details)
        
        # Audit log
        self._audit_log("cost_recorded", {
            "session_id": session_id,
            "operation_type": operation_type,
            "cost": actual_cost,
            "details": details,
            "daily_total": self.daily_cost,
            "monthly_total": self.monthly_cost
        })
    
    def record_failure(self, session_id: str, operation_type: str, error: str):
        """Record a failed operation.
        
        Args:
            session_id: Session ID
            operation_type: Type of operation
            error: Error message
        """
        session = self.active_sessions.get(session_id)
        if session:
            session.record_failure(operation_type, error)
        
        self._audit_log("operation_failed", {
            "session_id": session_id,
            "operation_type": operation_type,
            "error": error
        })
    
    def get_spending_summary(self) -> dict:
        """Get current spending summary."""
        self._reset_if_needed()
        
        return {
            "daily": {
                "spent": round(self.daily_cost, 4),
                "limit": self.max_daily,
                "remaining": round(max(0, self.max_daily - self.daily_cost), 4),
                "percent_used": round(self.daily_cost / self.max_daily * 100, 1) if self.max_daily > 0 else 0
            },
            "monthly": {
                "spent": round(self.monthly_cost, 4),
                "limit": self.max_monthly,
                "remaining": round(max(0, self.max_monthly - self.monthly_cost), 4),
                "percent_used": round(self.monthly_cost / self.max_monthly * 100, 1) if self.max_monthly > 0 else 0
            },
            "limits": {
                "per_operation": self.max_per_operation,
                "daily": self.max_daily,
                "monthly": self.max_monthly
            },
            "active_sessions": len(self.active_sessions)
        }
    
    def close_session(self, session_id: str) -> Optional[dict]:
        """Close a session and return its summary.
        
        Args:
            session_id: Session ID to close
            
        Returns:
            Session summary or None if not found
        """
        session = self.active_sessions.pop(session_id, None)
        if session:
            summary = session.get_summary()
            self._audit_log("session_closed", summary)
            return summary
        return None
    
    def _audit_log(self, event_type: str, data: dict):
        """Add entry to audit log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "data": data
        }
        
        self.audit_entries.append(entry)
        
        # Write to file if configured
        if self.audit_log_path:
            try:
                self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.audit_log_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass  # Don't fail on audit log errors


# Global instance (lazy initialization)
_cost_safety_manager: Optional[CostSafetyManager] = None


def get_cost_safety_manager() -> CostSafetyManager:
    """Get the global cost safety manager instance."""
    global _cost_safety_manager
    
    if _cost_safety_manager is None:
        from deepr.config import load_config
        
        config = load_config()
        budget = config.get("budget", {})
        
        # Get audit log path
        data_dir = Path(config.get("data_dir", "data"))
        audit_log_path = data_dir / "logs" / "cost_audit.jsonl"
        
        _cost_safety_manager = CostSafetyManager(
            max_per_operation=budget.get("max_cost_per_job", 5.0),
            max_daily=budget.get("max_daily_cost", 25.0),
            max_monthly=budget.get("max_monthly_cost", 200.0),
            audit_log_path=audit_log_path
        )
    
    return _cost_safety_manager


def estimate_curriculum_cost(
    topic_count: int,
    deep_research_count: int = 0,
    quick_research_count: int = 0,
    docs_count: int = 0
) -> dict:
    """Estimate cost for curriculum execution.
    
    Args:
        topic_count: Total number of topics
        deep_research_count: Number of deep research topics
        quick_research_count: Number of quick research topics
        docs_count: Number of documentation topics
        
    Returns:
        Cost estimate with min/max/expected
    """
    # Cost estimates per topic type
    DEEP_RESEARCH_COST = 1.0      # $0.50-1.50 per deep research
    QUICK_RESEARCH_COST = 0.002   # ~$0.002 per quick research (Grok free beta)
    DOCS_COST = 0.0               # Free (just scraping)
    
    # Calculate
    deep_cost = deep_research_count * DEEP_RESEARCH_COST
    quick_cost = quick_research_count * QUICK_RESEARCH_COST
    docs_cost = docs_count * DOCS_COST
    
    # If counts not specified, estimate from total
    if deep_research_count == 0 and quick_research_count == 0 and docs_count == 0:
        # Assume 30% deep, 40% quick, 30% docs
        deep_cost = int(topic_count * 0.3) * DEEP_RESEARCH_COST
        quick_cost = int(topic_count * 0.4) * QUICK_RESEARCH_COST
        docs_cost = int(topic_count * 0.3) * DOCS_COST
    
    expected = deep_cost + quick_cost + docs_cost
    
    return {
        "min_cost": round(expected * 0.5, 2),
        "max_cost": round(expected * 2.0, 2),
        "expected_cost": round(expected, 2),
        "breakdown": {
            "deep_research": round(deep_cost, 2),
            "quick_research": round(quick_cost, 4),
            "documentation": round(docs_cost, 2)
        }
    }


def format_cost_warning(estimated_cost: float, budget_limit: float) -> str:
    """Format a cost warning message.
    
    Args:
        estimated_cost: Estimated cost
        budget_limit: Budget limit
        
    Returns:
        Formatted warning message
    """
    if budget_limit <= 0:
        return f"Estimated cost: ${estimated_cost:.2f} (no budget limit set)"
    
    percent = (estimated_cost / budget_limit) * 100
    remaining = budget_limit - estimated_cost
    
    if percent > 100:
        return (
            f"Estimated cost ${estimated_cost:.2f} EXCEEDS budget ${budget_limit:.2f}\n"
            f"Over budget by: ${estimated_cost - budget_limit:.2f}"
        )
    elif percent > 80:
        return (
            f"Estimated cost: ${estimated_cost:.2f} / ${budget_limit:.2f} ({percent:.0f}%)\n"
            f"Remaining after: ${remaining:.2f}"
        )
    else:
        return f"Estimated cost: ${estimated_cost:.2f} / ${budget_limit:.2f} ({percent:.0f}%)"


def is_pausable_limit(reason: str) -> bool:
    """Check if a block reason is a pausable limit (can resume later).
    
    Daily and monthly limits are pausable - the user can resume tomorrow
    or next month when the limit resets. This is different from hard blocks
    like exceeding per-operation limits.
    
    Args:
        reason: The block reason from check_operation()
        
    Returns:
        True if this is a pausable limit (daily/monthly), False otherwise
    """
    if not reason:
        return False
    return "DAILY_LIMIT" in reason or "MONTHLY_LIMIT" in reason


def get_resume_message(reason: str) -> str:
    """Get a user-friendly resume message for a pausable limit.
    
    Args:
        reason: The block reason from check_operation()
        
    Returns:
        User-friendly message about when they can resume
    """
    if "DAILY_LIMIT" in reason:
        return "Daily spending limit reached. Your progress has been saved. Resume tomorrow when the daily limit resets."
    elif "MONTHLY_LIMIT" in reason:
        return "Monthly spending limit reached. Your progress has been saved. Resume next month when the monthly limit resets."
    else:
        return "Operation blocked. Check the error message for details."
