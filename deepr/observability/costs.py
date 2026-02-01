"""Cost tracking and dashboard for Deepr.

Provides cost tracking, alerts, and reporting:
- Record costs per operation
- Daily and monthly totals
- Breakdown by provider and operation type
- Configurable alerts at thresholds

Usage:
    from deepr.observability.costs import CostDashboard
    
    dashboard = CostDashboard()
    dashboard.record("research", "openai", 0.15, tokens=1500)
    
    print(dashboard.get_daily_total())
    print(dashboard.get_breakdown_by_provider())
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Module logger for debugging persistence and validation issues
logger = logging.getLogger(__name__)

# Configuration constants
MAX_STORED_ENTRIES = 10000  # Maximum cost entries to persist
MAX_STORED_ALERTS = 100  # Maximum alerts to persist


@dataclass
class CostEntry:
    """A cost entry for tracking.
    
    Attributes:
        timestamp: When the cost was incurred
        operation: Type of operation (research, chat, synthesis, etc.)
        provider: Provider used (openai, anthropic, etc.)
        model: Model used
        cost: Cost in dollars
        tokens_input: Input tokens consumed
        tokens_output: Output tokens generated
        task_id: Optional task ID for correlation
        metadata: Additional metadata
    """
    operation: str
    provider: str
    cost: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    task_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_tokens(self) -> int:
        """Get total tokens."""
        return self.tokens_input + self.tokens_output
    
    @property
    def date(self) -> date:
        """Get date of entry."""
        return self.timestamp.date()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "provider": self.provider,
            "model": self.model,
            "cost": self.cost,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "task_id": self.task_id,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CostEntry":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            operation=data["operation"],
            provider=data["provider"],
            model=data.get("model", ""),
            cost=data["cost"],
            tokens_input=data.get("tokens_input", 0),
            tokens_output=data.get("tokens_output", 0),
            task_id=data.get("task_id", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class CostAlert:
    """A cost alert.
    
    Attributes:
        level: Alert level (warning, critical)
        threshold: Threshold that was exceeded
        current_value: Current value
        limit: The limit
        period: Period (daily, monthly)
        triggered_at: When alert was triggered
    """
    level: str
    threshold: float
    current_value: float
    limit: float
    period: str
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "threshold": self.threshold,
            "current_value": self.current_value,
            "limit": self.limit,
            "period": self.period,
            "triggered_at": self.triggered_at.isoformat()
        }


class AlertManager:
    """Manages cost alert threshold checking and deduplication.
    
    Extracted from CostDashboard to follow Single Responsibility Principle.
    Handles:
    - Checking if thresholds are exceeded
    - Preventing duplicate alerts for same threshold/period
    - Determining alert severity levels
    
    Attributes:
        thresholds: List of threshold fractions (e.g., [0.5, 0.8, 0.95])
        triggered_alerts: List of alerts that have been triggered
    """
    
    # Threshold at or above which alerts are considered critical
    CRITICAL_THRESHOLD = 0.95
    
    def __init__(
        self,
        thresholds: Optional[List[float]] = None,
        triggered_alerts: Optional[List[CostAlert]] = None
    ):
        """Initialize alert manager.
        
        Args:
            thresholds: Alert thresholds as fractions (default: [0.5, 0.8, 0.95])
            triggered_alerts: Previously triggered alerts for deduplication
        """
        self.thresholds = thresholds or [0.5, 0.8, 0.95]
        self.triggered_alerts = triggered_alerts or []
    
    def check_daily_alerts(
        self,
        daily_total: float,
        daily_limit: float,
        check_date: date
    ) -> List[CostAlert]:
        """Check for daily threshold violations.
        
        Args:
            daily_total: Current daily spending total
            daily_limit: Daily spending limit
            check_date: Date to check (for deduplication)
            
        Returns:
            List of newly triggered alerts
        """
        new_alerts = []
        
        for threshold in self.thresholds:
            limit_value = daily_limit * threshold
            if daily_total >= limit_value:
                # Check if already triggered today
                if not self._is_already_triggered("daily", threshold, check_date):
                    alert = self._create_alert(
                        threshold=threshold,
                        current_value=daily_total,
                        limit=daily_limit,
                        period="daily"
                    )
                    new_alerts.append(alert)
                    self.triggered_alerts.append(alert)
        
        return new_alerts
    
    def check_monthly_alerts(
        self,
        monthly_total: float,
        monthly_limit: float,
        check_year: int,
        check_month: int
    ) -> List[CostAlert]:
        """Check for monthly threshold violations.
        
        Args:
            monthly_total: Current monthly spending total
            monthly_limit: Monthly spending limit
            check_year: Year to check (for deduplication)
            check_month: Month to check (for deduplication)
            
        Returns:
            List of newly triggered alerts
        """
        new_alerts = []
        
        for threshold in self.thresholds:
            limit_value = monthly_limit * threshold
            if monthly_total >= limit_value:
                # Check if already triggered this month
                if not self._is_already_triggered_monthly(threshold, check_year, check_month):
                    alert = self._create_alert(
                        threshold=threshold,
                        current_value=monthly_total,
                        limit=monthly_limit,
                        period="monthly"
                    )
                    new_alerts.append(alert)
                    self.triggered_alerts.append(alert)
        
        return new_alerts
    
    def get_active_alerts(self, now: datetime) -> List[CostAlert]:
        """Get currently active alerts.
        
        Args:
            now: Current datetime for determining active period
            
        Returns:
            List of active alerts
        """
        active = []
        today = now.date()
        
        for alert in self.triggered_alerts:
            if alert.period == "daily" and alert.triggered_at.date() == today:
                active.append(alert)
            elif alert.period == "monthly":
                if (alert.triggered_at.year == now.year and 
                    alert.triggered_at.month == now.month):
                    active.append(alert)
        
        return active
    
    def _is_already_triggered(
        self,
        period: str,
        threshold: float,
        check_date: date
    ) -> bool:
        """Check if a daily alert was already triggered.
        
        Args:
            period: Alert period (should be "daily")
            threshold: Threshold fraction
            check_date: Date to check
            
        Returns:
            True if already triggered
        """
        return any(
            a.period == period and
            a.threshold == threshold and
            a.triggered_at.date() == check_date
            for a in self.triggered_alerts
        )
    
    def _is_already_triggered_monthly(
        self,
        threshold: float,
        year: int,
        month: int
    ) -> bool:
        """Check if a monthly alert was already triggered.
        
        Args:
            threshold: Threshold fraction
            year: Year to check
            month: Month to check
            
        Returns:
            True if already triggered
        """
        return any(
            a.period == "monthly" and
            a.threshold == threshold and
            a.triggered_at.year == year and
            a.triggered_at.month == month
            for a in self.triggered_alerts
        )
    
    def _create_alert(
        self,
        threshold: float,
        current_value: float,
        limit: float,
        period: str
    ) -> CostAlert:
        """Create a new alert with appropriate severity level.
        
        Args:
            threshold: Threshold that was exceeded
            current_value: Current spending value
            limit: Spending limit
            period: Alert period (daily/monthly)
            
        Returns:
            New CostAlert instance
        """
        level = "critical" if threshold >= self.CRITICAL_THRESHOLD else "warning"
        return CostAlert(
            level=level,
            threshold=threshold,
            current_value=current_value,
            limit=limit,
            period=period
        )


class CostAggregator:
    """Handles cost aggregation and breakdown calculations.
    
    Extracted from CostDashboard to follow Single Responsibility Principle.
    Provides efficient single-pass aggregation for multiple breakdown types.
    
    Attributes:
        entries: Reference to the list of cost entries to aggregate
    """
    
    def __init__(self, entries: List[CostEntry]):
        """Initialize aggregator with entries reference.
        
        Args:
            entries: List of cost entries to aggregate
        """
        self._entries = entries
    
    def get_daily_total(self, target_date: Optional[date] = None) -> float:
        """Get total cost for a day.
        
        Args:
            target_date: Date to check (default: today in UTC)
            
        Returns:
            Total cost for the day
        """
        if target_date is None:
            target_date = datetime.utcnow().date()
        
        return sum(e.cost for e in self._entries if e.date == target_date)
    
    def get_monthly_total(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> float:
        """Get total cost for a month.
        
        Args:
            year: Year (default: current)
            month: Month (default: current)
            
        Returns:
            Total cost for the month
        """
        now = datetime.utcnow()
        if year is None:
            year = now.year
        if month is None:
            month = now.month
        
        return sum(
            e.cost for e in self._entries
            if e.timestamp.year == year and e.timestamp.month == month
        )
    
    def get_breakdown_by_provider(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get cost breakdown by provider.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary mapping provider to total cost
        """
        entries = self._filter_by_date(start_date, end_date)
        return self._aggregate_by_field(entries, lambda e: e.provider)
    
    def get_breakdown_by_operation(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get cost breakdown by operation type.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary mapping operation to total cost
        """
        entries = self._filter_by_date(start_date, end_date)
        return self._aggregate_by_field(entries, lambda e: e.operation)
    
    def get_breakdown_by_model(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get cost breakdown by model.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary mapping model to total cost
        """
        entries = self._filter_by_date(start_date, end_date)
        return self._aggregate_by_field(entries, lambda e: e.model or "unknown")
    
    def get_all_breakdowns(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Dict[str, float]]:
        """Get all breakdowns in a single pass for efficiency.
        
        This method iterates through entries once to compute all breakdowns,
        which is more efficient than calling each breakdown method separately.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary with 'by_provider', 'by_operation', 'by_model' keys
        """
        entries = self._filter_by_date(start_date, end_date)
        
        by_provider: Dict[str, float] = {}
        by_operation: Dict[str, float] = {}
        by_model: Dict[str, float] = {}
        
        for entry in entries:
            # Aggregate by provider
            if entry.provider not in by_provider:
                by_provider[entry.provider] = 0.0
            by_provider[entry.provider] += entry.cost
            
            # Aggregate by operation
            if entry.operation not in by_operation:
                by_operation[entry.operation] = 0.0
            by_operation[entry.operation] += entry.cost
            
            # Aggregate by model
            model = entry.model or "unknown"
            if model not in by_model:
                by_model[model] = 0.0
            by_model[model] += entry.cost
        
        return {
            "by_provider": by_provider,
            "by_operation": by_operation,
            "by_model": by_model
        }
    
    def _filter_by_date(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[CostEntry]:
        """Filter entries by date range.
        
        Args:
            start_date: Start of period (inclusive)
            end_date: End of period (inclusive)
            
        Returns:
            Filtered entries
        """
        entries = self._entries
        
        if start_date:
            entries = [e for e in entries if e.timestamp >= start_date]
        
        if end_date:
            entries = [e for e in entries if e.timestamp <= end_date]
        
        return entries
    
    def _aggregate_by_field(
        self,
        entries: List[CostEntry],
        key_func
    ) -> Dict[str, float]:
        """Aggregate costs by a field extracted via key function.
        
        Args:
            entries: Entries to aggregate
            key_func: Function to extract grouping key from entry
            
        Returns:
            Dictionary mapping key to total cost
        """
        breakdown: Dict[str, float] = {}
        for entry in entries:
            key = key_func(entry)
            if key not in breakdown:
                breakdown[key] = 0.0
            breakdown[key] += entry.cost
        return breakdown


class CostDashboard:
    """Dashboard for cost tracking and alerts.
    
    Coordinates between:
    - CostAggregator: Handles breakdown calculations and totals
    - AlertManager: Handles threshold checking and alert deduplication
    
    Attributes:
        entries: List of cost entries
        daily_limit: Daily spending limit
        monthly_limit: Monthly spending limit
        alert_manager: Manages alert threshold checking
        aggregator: Handles cost aggregation and breakdowns
    """
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        daily_limit: float = 10.0,
        monthly_limit: float = 100.0,
        alert_thresholds: Optional[List[float]] = None
    ):
        """Initialize cost dashboard.
        
        Args:
            storage_path: Path for persistence
            daily_limit: Daily spending limit
            monthly_limit: Monthly spending limit
            alert_thresholds: Alert thresholds (default: 0.5, 0.8, 0.95)
        """
        if storage_path is None:
            storage_path = Path("data/costs/cost_log.json")
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        
        # Store thresholds for backward compatibility
        self.alert_thresholds = alert_thresholds or [0.5, 0.8, 0.95]
        
        self.entries: List[CostEntry] = []
        
        # Initialize collaborators
        self.alert_manager = AlertManager(thresholds=self.alert_thresholds)
        self.aggregator = CostAggregator(self.entries)
        
        self._load()
    
    @property
    def triggered_alerts(self) -> List[CostAlert]:
        """Get triggered alerts (delegates to alert manager).
        
        Provides backward compatibility for code accessing triggered_alerts directly.
        """
        return self.alert_manager.triggered_alerts
    
    def record(
        self,
        operation: str,
        provider: str,
        cost: float,
        model: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        task_id: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> CostEntry:
        """Record a cost entry.
        
        Args:
            operation: Type of operation
            provider: Provider used
            cost: Cost in dollars (negative values clamped to 0)
            model: Model used
            tokens_input: Input tokens
            tokens_output: Output tokens
            task_id: Optional task ID
            metadata: Additional metadata
            
        Returns:
            Created CostEntry
        
        Note:
            Negative costs are clamped to 0 with a warning logged.
        """
        # Validate and sanitize cost: must be non-negative
        if cost < 0:
            logger.warning(
                f"Negative cost={cost} for {operation}/{provider}, clamping to 0"
            )
            cost = 0.0
        
        entry = CostEntry(
            operation=operation,
            provider=provider,
            cost=cost,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            task_id=task_id,
            metadata=metadata or {}
        )
        
        self.entries.append(entry)
        self._save()
        
        # Check alerts
        self.check_alerts()
        
        return entry
    
    def get_daily_total(self, target_date: Optional[date] = None) -> float:
        """Get total cost for a day.
        
        Delegates to CostAggregator.
        
        Args:
            target_date: Date to check (default: today in UTC)
            
        Returns:
            Total cost for the day
        """
        return self.aggregator.get_daily_total(target_date)
    
    def get_monthly_total(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> float:
        """Get total cost for a month.
        
        Delegates to CostAggregator.
        
        Args:
            year: Year (default: current)
            month: Month (default: current)
            
        Returns:
            Total cost for the month
        """
        return self.aggregator.get_monthly_total(year, month)
    
    def get_breakdown_by_provider(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get cost breakdown by provider.
        
        Delegates to CostAggregator.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary mapping provider to total cost
        """
        return self.aggregator.get_breakdown_by_provider(start_date, end_date)
    
    def get_breakdown_by_operation(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get cost breakdown by operation type.
        
        Delegates to CostAggregator.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary mapping operation to total cost
        """
        return self.aggregator.get_breakdown_by_operation(start_date, end_date)
    
    def get_breakdown_by_model(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get cost breakdown by model.
        
        Delegates to CostAggregator.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary mapping model to total cost
        """
        return self.aggregator.get_breakdown_by_model(start_date, end_date)
    
    def check_alerts(self) -> List[CostAlert]:
        """Check for cost alerts.
        
        Delegates to AlertManager for threshold checking and deduplication.
        
        Returns:
            List of newly triggered alerts
        """
        new_alerts = []
        now = datetime.utcnow()
        utc_today = now.date()
        
        # Check daily alerts
        daily_total = self.get_daily_total(utc_today)
        daily_alerts = self.alert_manager.check_daily_alerts(
            daily_total=daily_total,
            daily_limit=self.daily_limit,
            check_date=utc_today
        )
        new_alerts.extend(daily_alerts)
        
        # Check monthly alerts
        monthly_total = self.get_monthly_total()
        monthly_alerts = self.alert_manager.check_monthly_alerts(
            monthly_total=monthly_total,
            monthly_limit=self.monthly_limit,
            check_year=now.year,
            check_month=now.month
        )
        new_alerts.extend(monthly_alerts)
        
        return new_alerts
    
    def get_active_alerts(self) -> List[CostAlert]:
        """Get currently active alerts.
        
        Delegates to AlertManager.
        
        Returns:
            List of active alerts
        """
        return self.alert_manager.get_active_alerts(datetime.utcnow())
    
    def get_daily_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily cost history.
        
        Args:
            days: Number of days to include
            
        Returns:
            List of daily summaries
        """
        history = []
        today = datetime.utcnow().date()
        
        for i in range(days):
            target_date = today - timedelta(days=i)
            total = self.get_daily_total(target_date)
            
            history.append({
                "date": target_date.isoformat(),
                "total": total,
                "limit": self.daily_limit,
                "utilization": total / self.daily_limit if self.daily_limit > 0 else 0
            })
        
        return list(reversed(history))
    
    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary using efficient single-pass aggregation.
        
        Returns:
            Summary dictionary with daily/monthly totals, breakdowns, and alerts
        """
        daily_total = self.get_daily_total()
        monthly_total = self.get_monthly_total()
        
        # Use single-pass aggregation for all breakdowns
        breakdowns = self.aggregator.get_all_breakdowns()
        
        return {
            "daily": {
                "total": daily_total,
                "limit": self.daily_limit,
                "remaining": max(0, self.daily_limit - daily_total),
                "utilization": daily_total / self.daily_limit if self.daily_limit > 0 else 0
            },
            "monthly": {
                "total": monthly_total,
                "limit": self.monthly_limit,
                "remaining": max(0, self.monthly_limit - monthly_total),
                "utilization": monthly_total / self.monthly_limit if self.monthly_limit > 0 else 0
            },
            "by_provider": breakdowns["by_provider"],
            "by_operation": breakdowns["by_operation"],
            "active_alerts": [a.to_dict() for a in self.get_active_alerts()],
            "total_entries": len(self.entries)
        }
    
    def _filter_by_date(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[CostEntry]:
        """Filter entries by date range.
        
        Delegates to CostAggregator for backward compatibility.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Filtered entries
        """
        return self.aggregator._filter_by_date(start_date, end_date)
    
    def _save(self):
        """Save entries to disk using atomic write pattern.
        
        Uses a temporary file and atomic rename to prevent corruption
        if the process is interrupted during write.
        """
        # Keep last MAX_STORED_ENTRIES entries
        entries_to_save = self.entries[-MAX_STORED_ENTRIES:]
        
        data = {
            "entries": [e.to_dict() for e in entries_to_save],
            "alerts": [a.to_dict() for a in self.alert_manager.triggered_alerts[-MAX_STORED_ALERTS:]],
            "saved_at": datetime.utcnow().isoformat()
        }
        
        # Atomic write: write to temp file, then rename
        temp_path = self.storage_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            # Atomic rename (on POSIX systems; best-effort on Windows)
            os.replace(temp_path, self.storage_path)
        except OSError as e:
            logger.error(f"Failed to save cost data: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
    
    def _load(self):
        """Load entries from disk.
        
        Logs errors and starts fresh if loading fails, rather than
        silently ignoring corruption.
        """
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.entries = [
                CostEntry.from_dict(e)
                for e in data.get("entries", [])
            ]
            
            # Load alerts into the alert manager
            loaded_alerts = []
            for alert_data in data.get("alerts", []):
                loaded_alerts.append(CostAlert(
                    level=alert_data["level"],
                    threshold=alert_data["threshold"],
                    current_value=alert_data["current_value"],
                    limit=alert_data["limit"],
                    period=alert_data["period"],
                    triggered_at=datetime.fromisoformat(alert_data["triggered_at"])
                ))
            self.alert_manager.triggered_alerts = loaded_alerts
            
            logger.debug(
                f"Loaded {len(self.entries)} cost entries and "
                f"{len(self.alert_manager.triggered_alerts)} alerts"
            )
        except json.JSONDecodeError as e:
            logger.warning(
                f"Corrupted cost data file at {self.storage_path}: {e}. "
                "Starting fresh."
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"Invalid data in cost data file: {e}. Starting fresh."
            )
        except OSError as e:
            logger.warning(
                f"Failed to read cost data file: {e}. Starting fresh."
            )
