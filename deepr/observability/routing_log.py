"""Routing decision log and analytics.

Logs every auto-mode routing decision to a JSONL file for:
- Cost-vs-quality frontier scatter plots
- Model usage distribution
- Routing drift detection (confidence/cost shifts over time)
- Anomaly alerts (cost outliers, sudden model switches)
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RoutingDecisionEvent:
    """A single logged routing decision."""

    timestamp: datetime = field(default_factory=_utc_now)
    query_hash: str = ""  # SHA-256 prefix of query (privacy-safe)
    provider: str = ""
    model: str = ""
    complexity: str = ""
    task_type: str = ""
    cost_estimate: float = 0.0
    confidence: float = 0.0
    reasoning: str = ""
    actual_cost: float | None = None  # Filled after execution
    success: bool | None = None  # Filled after execution

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(),
            "query_hash": self.query_hash,
            "provider": self.provider,
            "model": self.model,
            "complexity": self.complexity,
            "task_type": self.task_type,
            "cost_estimate": self.cost_estimate,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        if self.actual_cost is not None:
            d["actual_cost"] = self.actual_cost
        if self.success is not None:
            d["success"] = self.success
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingDecisionEvent:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else _utc_now(),
            query_hash=data.get("query_hash", ""),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            complexity=data.get("complexity", ""),
            task_type=data.get("task_type", ""),
            cost_estimate=float(data.get("cost_estimate", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            actual_cost=data.get("actual_cost"),
            success=data.get("success"),
        )

    @classmethod
    def from_auto_mode_decision(cls, decision: Any, query_hash: str = "") -> RoutingDecisionEvent:
        """Create from an AutoModeDecision object."""
        return cls(
            query_hash=query_hash,
            provider=decision.provider,
            model=decision.model,
            complexity=decision.complexity,
            task_type=decision.task_type,
            cost_estimate=decision.cost_estimate,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
        )


class RoutingDecisionLog:
    """Append-only JSONL log of routing decisions with analytics queries."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or Path("data/analytics/routing_decisions.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, event: RoutingDecisionEvent) -> None:
        """Append a routing decision to the log."""
        with self._lock:
            line = json.dumps(event.to_dict(), ensure_ascii=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def get_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 1000,
    ) -> list[RoutingDecisionEvent]:
        """Query logged events with optional filters."""
        if not self.log_path.exists():
            return []

        events: list[RoutingDecisionEvent] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = RoutingDecisionEvent.from_dict(data)
                except (json.JSONDecodeError, KeyError):
                    continue

                if start and event.timestamp < start:
                    continue
                if end and event.timestamp > end:
                    continue
                if provider and event.provider != provider:
                    continue
                if model and event.model != model:
                    continue

                events.append(event)
                if len(events) >= limit:
                    break

        return events

    # ------------------------------------------------------------------
    # Analytics queries
    # ------------------------------------------------------------------

    def cost_distribution(self, last_n: int = 100) -> dict[str, Any]:
        """Cost distribution stats across recent routing decisions."""
        events = self.get_events(limit=last_n)
        if not events:
            return {"count": 0}

        costs = [e.cost_estimate for e in events]
        return {
            "count": len(costs),
            "mean": round(statistics.mean(costs), 4),
            "median": round(statistics.median(costs), 4),
            "stdev": round(statistics.stdev(costs), 4) if len(costs) > 1 else 0.0,
            "min": round(min(costs), 4),
            "max": round(max(costs), 4),
            "p95": round(sorted(costs)[int(len(costs) * 0.95)], 4) if len(costs) >= 20 else None,
        }

    def model_usage(self, last_n: int = 100) -> dict[str, int]:
        """Model usage counts across recent decisions."""
        events = self.get_events(limit=last_n)
        usage: dict[str, int] = {}
        for e in events:
            key = f"{e.provider}/{e.model}"
            usage[key] = usage.get(key, 0) + 1
        return dict(sorted(usage.items(), key=lambda x: x[1], reverse=True))

    def detect_routing_drift(self, window: int = 50) -> dict[str, Any]:
        """Detect if routing confidence or cost has drifted recently.

        Compares the last ``window`` decisions against the preceding ``window``.
        Returns drift indicators.
        """
        events = self.get_events(limit=window * 2)
        if len(events) < window * 2:
            return {"sufficient_data": False}

        older = events[: len(events) - window]
        recent = events[len(events) - window :]

        old_conf = statistics.mean(e.confidence for e in older)
        new_conf = statistics.mean(e.confidence for e in recent)
        old_cost = statistics.mean(e.cost_estimate for e in older)
        new_cost = statistics.mean(e.cost_estimate for e in recent)

        conf_drift = new_conf - old_conf
        cost_drift = new_cost - old_cost

        # Count model switches
        old_models = {f"{e.provider}/{e.model}" for e in older}
        new_models = {f"{e.provider}/{e.model}" for e in recent}
        new_model_entries = new_models - old_models
        dropped_models = old_models - new_models

        return {
            "sufficient_data": True,
            "confidence_drift": round(conf_drift, 4),
            "cost_drift": round(cost_drift, 4),
            "confidence_old": round(old_conf, 4),
            "confidence_new": round(new_conf, 4),
            "cost_old": round(old_cost, 4),
            "cost_new": round(new_cost, 4),
            "new_models": sorted(new_model_entries),
            "dropped_models": sorted(dropped_models),
            "drift_alert": abs(conf_drift) > 0.10 or abs(cost_drift) > 0.05,
        }

    def detect_cost_anomalies(self, threshold_multiplier: float = 3.0, last_n: int = 100) -> list[dict[str, Any]]:
        """Find routing decisions with abnormally high costs.

        Returns events where cost exceeds mean + threshold_multiplier * stdev.
        """
        events = self.get_events(limit=last_n)
        if len(events) < 10:
            return []

        costs = [e.cost_estimate for e in events]
        mean = statistics.mean(costs)
        stdev = statistics.stdev(costs) if len(costs) > 1 else 0.0
        threshold = mean + (threshold_multiplier * stdev)

        anomalies = []
        for e in events:
            if e.cost_estimate > threshold:
                anomalies.append(
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "model": f"{e.provider}/{e.model}",
                        "cost": e.cost_estimate,
                        "threshold": round(threshold, 4),
                        "zscore": round((e.cost_estimate - mean) / stdev, 2) if stdev > 0 else 0.0,
                    }
                )

        return anomalies
