"""Append-only value-of-spend decision log."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import append_jsonl_durable

SPEND_DECISION_SCHEMA_VERSION = "deepr-spend-decision-v1"
SPEND_DECISION_KIND = "deepr.expert.spend_decision"


def spend_decision_log_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    from deepr.observability.cost_ledger import default_cost_data_dir

    return default_cost_data_dir() / "spend_decisions.jsonl"


@dataclass(frozen=True)
class SpendDecisionRecord:
    """One deterministic value-gate decision for a prospective metered op."""

    timestamp: datetime
    expert_name: str
    operation: str
    topic: str
    capacity_source: str
    estimated_cost: float
    factors: dict[str, float]
    decision: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SPEND_DECISION_SCHEMA_VERSION,
            "kind": SPEND_DECISION_KIND,
            "timestamp": self.timestamp.isoformat(),
            "expert_name": self.expert_name,
            "operation": self.operation,
            "topic": self.topic,
            "capacity_source": self.capacity_source,
            "estimated_cost": round(float(self.estimated_cost), 4),
            "factors": {key: round(float(value), 4) for key, value in self.factors.items()},
            "decision": dict(self.decision),
        }


def record_spend_decision(
    *,
    expert_name: str,
    operation: str,
    topic: str,
    capacity_source: str,
    estimated_cost: float,
    factors: dict[str, float],
    decision: dict[str, Any],
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append and return one value-gate decision record."""
    record = SpendDecisionRecord(
        timestamp=now or datetime.now(UTC),
        expert_name=expert_name,
        operation=operation,
        topic=topic,
        capacity_source=capacity_source,
        estimated_cost=estimated_cost,
        factors=factors,
        decision=decision,
    ).to_dict()
    append_jsonl_durable(spend_decision_log_path(path), record, fsync=True)
    return record


def load_spend_decisions(path: Path | None = None) -> list[dict[str, Any]]:
    resolved = spend_decision_log_path(path)
    if not resolved.exists():
        return []
    records: list[dict[str, Any]] = []
    with resolved.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            records.append(json.loads(text))
    return records
