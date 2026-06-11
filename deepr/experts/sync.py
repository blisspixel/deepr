"""Expert freshness sync - stay current on subscribed topics over time.

The flagship loop-closer (ROADMAP Phase 4, v2.14): an expert subscribes to
topics with a refresh cadence and budget; ``deepr expert sync`` researches
only what is due, asks only for what changed since the last sync, absorbs
the delta through the verification-gated pipeline (dedup + contradiction
flagging - a poisoned or stale update cannot silently overwrite a belief),
and reports the perspective delta via the temporal ``what_changed`` query.

Schedulable by design: the command is idempotent per cadence window, so a
cron job / host-platform scheduler (Anthropic scheduled deployments,
Antigravity tasks) can run it daily and only due subscriptions spend money.

The research step is injectable (``research_fn``) so the engine is unit-
testable without providers; the default uses the expert chat session's
standard research (agentic web search, near-zero cost).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.perspective import what_changed
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

# A research answer that opens with this marker is treated as "nothing new"
# and skips the (paid) absorb extraction entirely.
_NO_CHANGES_MARKER = "no significant changes"

# Default per-subscription research budget when none is set.
DEFAULT_SUBSCRIPTION_BUDGET = 0.50

# Floor below which a sync run refuses to start a subscription (mirrors the
# learner's refuse-before-spending preflight).
MIN_PER_TOPIC_BUDGET = 0.05

ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "topic"


@dataclass
class Subscription:
    """One topic an expert stays current on."""

    topic: str
    query: str = ""  # optional extra focus for the freshness prompt
    cadence_days: float = 7.0
    budget: float = DEFAULT_SUBSCRIPTION_BUDGET
    last_synced: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_due(self, now: datetime | None = None) -> bool:
        if self.last_synced is None:
            return True
        now = now or datetime.now(UTC)
        return now - self.last_synced >= timedelta(days=self.cadence_days)

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
            self.subscriptions = [Subscription.from_dict(s) for s in data.get("subscriptions", [])]
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            logger.error("Could not load subscriptions for %s: %s", self.expert_name, exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, {"subscriptions": [s.to_dict() for s in self.subscriptions]})

    def add(self, subscription: Subscription) -> None:
        if any(s.topic.lower() == subscription.topic.lower() for s in self.subscriptions):
            raise ValueError(f"Already subscribed to topic: {subscription.topic}")
        self.subscriptions.append(subscription)
        self.save()

    def remove(self, topic: str) -> bool:
        before = len(self.subscriptions)
        self.subscriptions = [s for s in self.subscriptions if s.topic.lower() != topic.lower()]
        if len(self.subscriptions) != before:
            self.save()
            return True
        return False

    def due(self, now: datetime | None = None) -> list[Subscription]:
        return [s for s in self.subscriptions if s.is_due(now)]


@dataclass
class SyncOutcome:
    """Result of syncing one subscription."""

    topic: str
    status: str  # "synced" | "no_changes" | "failed" | "skipped" | "would_sync"
    cost: float = 0.0
    absorbed: int = 0
    flagged: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status,
            "cost": round(self.cost, 4),
            "absorbed": self.absorbed,
            "flagged": self.flagged,
            "detail": self.detail,
        }


@dataclass
class SyncResult:
    """Result of one sync run: per-topic outcomes plus the perspective delta."""

    expert_name: str
    started_at: datetime
    outcomes: list[SyncOutcome] = field(default_factory=list)
    delta: dict[str, Any] = field(default_factory=dict)
    total_cost: float = 0.0

    @property
    def synced_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "synced")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "started_at": self.started_at.isoformat(),
            "outcomes": [o.to_dict() for o in self.outcomes],
            "delta": self.delta,
            "total_cost": round(self.total_cost, 4),
            "synced_count": self.synced_count,
        }


class ExpertSyncEngine:
    """Research due subscriptions, absorb only the delta, report what changed."""

    def __init__(
        self,
        expert: ExpertProfile,
        *,
        research_fn: ResearchFn | None = None,
        subscription_store: SubscriptionStore | None = None,
        belief_store: BeliefStore | None = None,
        absorber: Any | None = None,
    ) -> None:
        self.expert = expert
        self._research_fn = research_fn
        self.subscriptions = subscription_store or SubscriptionStore(expert.name)
        self.belief_store = belief_store or BeliefStore(expert.name)
        self._absorber = absorber

    # ------------------------------------------------------------------ #
    # Defaults (built lazily so tests never touch providers)
    # ------------------------------------------------------------------ #

    async def _default_research(self, query: str, budget: float) -> dict[str, Any]:
        from deepr.experts.chat import ExpertChatSession

        session = ExpertChatSession(self.expert, budget=budget, agentic=True)
        return await session._standard_research(query)

    def _get_absorber(self) -> Any:
        if self._absorber is None:
            from deepr.experts.report_absorber import ReportAbsorber

            self._absorber = ReportAbsorber(self.expert, belief_store=self.belief_store)
        return self._absorber

    # ------------------------------------------------------------------ #
    # The freshness prompt
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_freshness_query(subscription: Subscription) -> str:
        """Ask only for what changed - the delta, not a re-survey."""
        if subscription.last_synced:
            since = subscription.last_synced.strftime("%Y-%m-%d")
            window = f"since {since}"
        else:
            window = "in the last 30 days"
        focus = f" Focus: {subscription.query}" if subscription.query else ""
        return (
            f"What has changed regarding '{subscription.topic}' {window}?{focus} "
            "Report ONLY new developments: announcements, releases, pricing or policy changes, "
            "deprecations, retractions, or significant new evidence - each with its date and source. "
            f"If nothing meaningful changed, reply exactly: '{_NO_CHANGES_MARKER}'."
        )

    # ------------------------------------------------------------------ #
    # Sync
    # ------------------------------------------------------------------ #

    async def sync(
        self,
        *,
        budget: float = 2.0,
        only_due: bool = True,
        dry_run: bool = False,
    ) -> SyncResult:
        """Run due subscriptions through research -> verified absorb -> delta.

        Args:
            budget: Total ceiling for this run (per-topic budgets apply within it).
            only_due: Sync only subscriptions past their cadence window.
            dry_run: Report what would sync; no research, no spend, no writes.
        """
        started_at = datetime.now(UTC)
        result = SyncResult(expert_name=self.expert.name, started_at=started_at)

        targets = self.subscriptions.due() if only_due else list(self.subscriptions.subscriptions)
        if not targets:
            return result

        remaining = budget
        for sub in targets:
            per_topic = min(sub.budget, remaining)
            if per_topic < MIN_PER_TOPIC_BUDGET:
                result.outcomes.append(
                    SyncOutcome(sub.topic, "skipped", detail=f"run budget exhausted (${remaining:.2f} left)")
                )
                continue

            if dry_run:
                result.outcomes.append(
                    SyncOutcome(sub.topic, "would_sync", detail=self.build_freshness_query(sub)[:120])
                )
                continue

            try:
                research = await self._research(sub, per_topic)
            except Exception as exc:
                result.outcomes.append(SyncOutcome(sub.topic, "failed", detail=str(exc)))
                continue

            if "error" in research:
                result.outcomes.append(SyncOutcome(sub.topic, "failed", detail=str(research["error"])))
                continue

            cost = float(research.get("cost", 0.0) or 0.0)
            remaining -= cost
            result.total_cost += cost
            answer = (research.get("answer") or "").strip()

            if not answer or answer.lower().startswith(_NO_CHANGES_MARKER):
                sub.last_synced = datetime.now(UTC)
                self.subscriptions.save()
                result.outcomes.append(SyncOutcome(sub.topic, "no_changes", cost=cost))
                continue

            try:
                report_id = f"sync:{_slug(sub.topic)}:{started_at.strftime('%Y%m%d')}"
                absorption = await self._get_absorber().absorb(
                    report_id,
                    answer,
                    flag_contradictions=True,
                )
                sub.last_synced = datetime.now(UTC)
                self.subscriptions.save()
                result.outcomes.append(
                    SyncOutcome(
                        sub.topic,
                        "synced",
                        cost=cost,
                        absorbed=len(absorption.absorbed),
                        flagged=len(absorption.flagged),
                    )
                )
            except Exception as exc:
                result.outcomes.append(SyncOutcome(sub.topic, "failed", cost=cost, detail=f"absorb failed: {exc}"))

        if not dry_run:
            # what_changed is strictly-after; nudge the window back 1ms so a
            # belief written in the same clock tick as started_at (coarse
            # Windows timer granularity) is not excluded from the delta.
            since = started_at - timedelta(milliseconds=1)
            result.delta = what_changed(self.belief_store, since, expert_name=self.expert.name).to_dict()

        return result

    async def _research(self, subscription: Subscription, budget: float) -> dict[str, Any]:
        query = self.build_freshness_query(subscription)
        fn = self._research_fn or self._default_research
        return await fn(query, budget)
