"""Subscriptions and result contracts for expert freshness sync."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

DEFAULT_SUBSCRIPTION_BUDGET = 0.50


@dataclass
class Subscription:
    """One topic an expert stays current on."""

    topic: str
    query: str = ""
    cadence_days: float = 7.0
    budget: float = DEFAULT_SUBSCRIPTION_BUDGET
    last_synced: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_due(self, now: datetime | None = None) -> bool:
        if self.last_synced is None:
            return True
        return (now or datetime.now(UTC)) - self.last_synced >= timedelta(days=self.cadence_days)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "query": self.query,
            "cadence_days": self.cadence_days,
            "budget": self.budget,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subscription:
        return cls(
            topic=data["topic"],
            query=data.get("query", ""),
            cadence_days=float(data.get("cadence_days", 7.0)),
            budget=float(data.get("budget", DEFAULT_SUBSCRIPTION_BUDGET)),
            last_synced=datetime.fromisoformat(data["last_synced"]) if data.get("last_synced") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
        )


class SubscriptionStore:
    """JSON sidecar of an expert's topic subscriptions."""

    def __init__(self, expert_name: str, storage_dir: Path | None = None):
        self.expert_name = expert_name
        if storage_dir is None:
            from deepr.experts.profile import ExpertStore

            storage_dir = ExpertStore().get_knowledge_dir(expert_name)
        self.path = Path(storage_dir) / "subscriptions.json"
        self.subscriptions: list[Subscription] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.subscriptions = [Subscription.from_dict(item) for item in data.get("subscriptions", [])]
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            logger.error("Could not load subscriptions for %s: %s", self.expert_name, exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, {"subscriptions": [item.to_dict() for item in self.subscriptions]})

    def add(self, subscription: Subscription) -> None:
        if any(item.topic.lower() == subscription.topic.lower() for item in self.subscriptions):
            raise ValueError(f"Already subscribed to topic: {subscription.topic}")
        self.subscriptions.append(subscription)
        self.save()

    def remove(self, topic: str) -> bool:
        before = len(self.subscriptions)
        self.subscriptions = [item for item in self.subscriptions if item.topic.lower() != topic.lower()]
        if len(self.subscriptions) == before:
            return False
        self.save()
        return True

    def due(self, now: datetime | None = None) -> list[Subscription]:
        return [item for item in self.subscriptions if item.is_due(now)]


@dataclass
class SyncOutcome:
    """Result of syncing one subscription."""

    topic: str
    status: str
    cost: float = 0.0
    absorbed: int = 0
    flagged: int = 0
    blocked: int = 0
    detail: str = ""
    source_pack_artifact: str = ""
    source_pack_manifest_artifact: str = ""
    source_note_artifact: str = ""
    claim_extraction_artifact: str = ""
    claim_verification_artifact: str = ""
    graph_commit_envelope_artifact: str = ""
    graph_commit_apply_artifact: str = ""
    graph_commit_apply_status: str = ""
    source_count: int = 0
    context_mode: str = ""
    error_code: str = ""
    retryable: bool = False
    no_metered_fallback: bool = False
    knowledge_observed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status,
            "cost": round(self.cost, 4),
            "absorbed": self.absorbed,
            "flagged": self.flagged,
            "blocked": self.blocked,
            "detail": self.detail,
            "source_pack_artifact": self.source_pack_artifact,
            "source_pack_manifest_artifact": self.source_pack_manifest_artifact,
            "source_note_artifact": self.source_note_artifact,
            "claim_extraction_artifact": self.claim_extraction_artifact,
            "claim_verification_artifact": self.claim_verification_artifact,
            "graph_commit_envelope_artifact": self.graph_commit_envelope_artifact,
            "graph_commit_apply_artifact": self.graph_commit_apply_artifact,
            "graph_commit_apply_status": self.graph_commit_apply_status,
            "source_count": self.source_count,
            "context_mode": self.context_mode,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "no_metered_fallback": self.no_metered_fallback,
            "knowledge_observed_at": self.knowledge_observed_at.isoformat() if self.knowledge_observed_at else None,
        }


@dataclass
class ClaimCompilationOutcome:
    claim_extraction_artifact: str = ""
    claim_verification_artifact: str = ""
    graph_commit_envelope_artifact: str = ""
    graph_commit_envelope: dict[str, Any] | None = None
    cost: float = 0.0
    detail: str = ""


@dataclass
class SyncResult:
    """Result of one sync run plus its perspective delta."""

    expert_name: str
    started_at: datetime
    outcomes: list[SyncOutcome] = field(default_factory=list)
    delta: dict[str, Any] = field(default_factory=dict)
    total_cost: float = 0.0

    @property
    def knowledge_observed_at(self) -> datetime | None:
        observations = [outcome.knowledge_observed_at for outcome in self.outcomes if outcome.knowledge_observed_at]
        return max(observations) if observations else None

    @property
    def synced_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == "synced")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "started_at": self.started_at.isoformat(),
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "delta": self.delta,
            "total_cost": round(self.total_cost, 4),
            "synced_count": self.synced_count,
            "knowledge_observed_at": (self.knowledge_observed_at.isoformat() if self.knowledge_observed_at else None),
        }
