"""Budget management for expert learning operations.

This module extracts budget tracking logic from ExpertProfile to reduce
god class complexity. Handles monthly budget tracking, spending validation,
and refresh history management.

Requirements: 5.2 - Extract monthly budget tracking logic
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


@dataclass
class BudgetManager:
    """Manages monthly learning budget for an expert.

    Tracks spending against a monthly budget, handles automatic monthly
    resets, and maintains a history of refresh operations.

    Attributes:
        monthly_budget: Maximum monthly spending limit in USD
        monthly_spending: Current month's spending in USD
        total_spending: All-time total spending in USD
        reset_date: Date when monthly spending resets
        refresh_history: List of past refresh operations
    """

    monthly_budget: float = 5.0
    monthly_spending: float = 0.0
    total_spending: float = 0.0
    reset_date: Optional[datetime] = None
    refresh_history: List[Dict] = field(default_factory=list)

    # Maximum history entries to retain
    MAX_HISTORY_ENTRIES: int = field(default=100, repr=False)

    def __post_init__(self):
        """Initialize reset date if not set."""
        if self.reset_date is None:
            self._initialize_reset_date()

    def _initialize_reset_date(self) -> None:
        """Set reset date to first of next month."""
        now = datetime.now(timezone.utc)
        if now.month == 12:
            self.reset_date = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            self.reset_date = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    def check_and_reset_if_needed(self) -> bool:
        """Check if monthly reset is needed and perform it.

        Returns:
            True if reset was performed, False otherwise
        """
        now = datetime.now(timezone.utc)

        if self.reset_date is None:
            self._initialize_reset_date()
            return False

        if now >= self.reset_date:
            self.monthly_spending = 0.0

            # Set next reset date
            if now.month == 12:
                self.reset_date = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                self.reset_date = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

            return True

        return False

    def get_remaining_budget(self) -> float:
        """Get remaining budget for current month.

        Returns:
            Remaining budget in USD (never negative)
        """
        self.check_and_reset_if_needed()
        return max(0.0, self.monthly_budget - self.monthly_spending)

    def get_usage_percent(self) -> float:
        """Get budget usage as percentage.

        Returns:
            Usage percentage (0-100+)
        """
        if self.monthly_budget <= 0:
            return 0.0
        return (self.monthly_spending / self.monthly_budget) * 100

    def can_spend(self, amount: float) -> Tuple[bool, str]:
        """Check if spending amount is within budget.

        Args:
            amount: Amount to spend in USD

        Returns:
            Tuple of (can_spend, reason_message)
        """
        self.check_and_reset_if_needed()

        if amount <= 0:
            return True, "No cost"

        remaining = self.get_remaining_budget()

        if remaining <= 0:
            return False, f"Monthly learning budget exhausted (${self.monthly_budget:.2f} limit)"

        if amount > remaining:
            return False, f"Amount ${amount:.2f} exceeds remaining budget ${remaining:.2f}"

        return True, f"Within budget (${remaining - amount:.2f} remaining after)"

    def record_spending(self, amount: float, operation: str, details: Optional[str] = None) -> None:
        """Record spending against budget.

        Args:
            amount: Amount spent in USD
            operation: Type of operation (refresh, research, etc.)
            details: Optional details about the operation
        """
        self.check_and_reset_if_needed()

        self.monthly_spending += amount
        self.total_spending += amount

        # Record in history
        self.refresh_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
                "amount": amount,
                "details": details,
                "budget_remaining": self.get_remaining_budget(),
            }
        )

        # Trim history if needed
        if len(self.refresh_history) > self.MAX_HISTORY_ENTRIES:
            self.refresh_history = self.refresh_history[-self.MAX_HISTORY_ENTRIES :]

    def get_status(self) -> Dict[str, any]:
        """Get comprehensive budget status.

        Returns:
            Dictionary with budget status information
        """
        self.check_and_reset_if_needed()

        return {
            "monthly_budget": self.monthly_budget,
            "monthly_spent": self.monthly_spending,
            "monthly_remaining": self.get_remaining_budget(),
            "usage_percent": self.get_usage_percent(),
            "reset_date": self.reset_date.isoformat() if self.reset_date else None,
            "can_spend": self.get_remaining_budget() > 0,
            "total_spent": self.total_spending,
            "refresh_count_this_month": self._count_this_month_refreshes(),
        }

    def _count_this_month_refreshes(self) -> int:
        """Count refresh operations in current month.

        Returns:
            Number of refreshes this month
        """
        now = datetime.now(timezone.utc)
        count = 0

        for entry in self.refresh_history:
            timestamp_str = entry.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    if timestamp.year == now.year and timestamp.month == now.month:
                        count += 1
                except (ValueError, TypeError):
                    continue

        return count

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "monthly_budget": self.monthly_budget,
            "monthly_spending": self.monthly_spending,
            "total_spending": self.total_spending,
            "reset_date": self.reset_date.isoformat() if self.reset_date else None,
            "refresh_history": self.refresh_history,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "BudgetManager":
        """Create from dictionary.

        Args:
            data: Dictionary with budget data

        Returns:
            BudgetManager instance
        """
        reset_date = None
        if data.get("reset_date"):
            reset_date = datetime.fromisoformat(data["reset_date"])

        return cls(
            monthly_budget=data.get("monthly_budget", 5.0),
            monthly_spending=data.get("monthly_spending", 0.0),
            total_spending=data.get("total_spending", 0.0),
            reset_date=reset_date,
            refresh_history=data.get("refresh_history", []),
        )
