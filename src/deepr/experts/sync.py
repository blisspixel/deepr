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


def _fresh_context_has_no_sources(research: dict[str, Any]) -> bool:
    metadata = research.get("fresh_context")
    if not isinstance(metadata, dict):
        return False
    return metadata.get("source_count") == 0


def _source_pack_from_research(research: dict[str, Any]) -> dict[str, Any] | None:
    source_pack = research.get("source_pack")
    if isinstance(source_pack, dict):
        return dict(source_pack)

    metadata = research.get("fresh_context")
    if not isinstance(metadata, dict):
        return None
    return {
        "schema_version": "deepr.source_pack.v1",
        "metadata_only": True,
        "mode": metadata.get("mode", "fresh"),
        "generated_at": metadata.get("generated_at"),
        "search_backend": metadata.get("search_backend"),
        "browser_backend": metadata.get("browser_backend"),
        "source_count": metadata.get("source_count", 0),
        "retrieved_source_count": metadata.get("retrieved_source_count", 0),
        "search_queries": metadata.get("search_queries", []),
        "sources": metadata.get("sources", []),
        "errors": metadata.get("errors", []),
    }


def _source_pack_summary(source_pack: dict[str, Any]) -> tuple[int, str]:
    source_count = int(source_pack.get("source_count", 0) or 0)
    mode = str(source_pack.get("mode", "") or "")
    return source_count, mode


def _source_pack_content_hashes(source_pack: dict[str, Any] | None) -> set[str]:
    """Non-empty SHA-256 content hashes of the fetched sources in a pack."""
    if not isinstance(source_pack, dict):
        return set()
    hashes: set[str] = set()
    for source in source_pack.get("sources", []):
        if isinstance(source, dict):
            digest = source.get("content_hash")
            if isinstance(digest, str) and digest:
                hashes.add(digest)
    return hashes


def fresh_sources_unchanged(prior: dict[str, Any] | None, current: dict[str, Any] | None) -> bool:
    """Whether the current retrieval adds no new content versus the prior sync.

    Deterministic and form-only: it compares SHA-256 hashes of fetched source
    content, never their meaning. It fails safe toward "changed" - returning
    ``False`` whenever it cannot prove no-change (no prior pack, no hashable
    current content, or any hash the prior run did not already have) - so a real
    update is never skipped; the worst case is one wasted, already-gated
    extraction. The model-side "no significant changes" reply is the second
    backstop for semantic no-ops the hash cannot see. See
    docs/design/change-detection-gate.md.
    """
    current_hashes = _source_pack_content_hashes(current)
    if not current_hashes:
        return False
    prior_hashes = _source_pack_content_hashes(prior)
    if not prior_hashes:
        return False
    return current_hashes <= prior_hashes


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
    source_pack_artifact: str = ""
    source_count: int = 0
    context_mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status,
            "cost": round(self.cost, 4),
            "absorbed": self.absorbed,
            "flagged": self.flagged,
            "detail": self.detail,
            "source_pack_artifact": self.source_pack_artifact,
            "source_count": self.source_count,
            "context_mode": self.context_mode,
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
        """The research query for one subscription.

        First sync (no ``last_synced``) establishes the baseline: a comprehensive,
        sourced overview, so a brand-new expert is actually populated - including
        evergreen topics where "what changed lately" is correctly nothing.
        Subsequent syncs ask only for the delta since the last sync.
        """
        focus = f" Focus: {subscription.query}" if subscription.query else ""
        if subscription.last_synced is None:
            return (
                f"Provide a comprehensive, well-sourced overview of '{subscription.topic}'.{focus} "
                "Cover the key facts, core concepts, and current state of the art, each grounded in the "
                "provided sources (include dates where relevant). Be specific and factual; do not speculate."
            )
        since = subscription.last_synced.strftime("%Y-%m-%d")
        return (
            f"What has changed regarding '{subscription.topic}' since {since}?{focus} "
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
            outcome, spent = await self._sync_subscription(
                sub,
                budget=min(sub.budget, remaining),
                started_at=started_at,
                dry_run=dry_run,
            )
            remaining -= spent
            result.total_cost += spent
            result.outcomes.append(outcome)

        if not dry_run:
            # what_changed is strictly-after; nudge the window back 1ms so a
            # belief written in the same clock tick as started_at (coarse
            # Windows timer granularity) is not excluded from the delta.
            since = started_at - timedelta(milliseconds=1)
            result.delta = what_changed(self.belief_store, since, expert_name=self.expert.name).to_dict()

        return result

    async def _sync_subscription(
        self,
        subscription: Subscription,
        *,
        budget: float,
        started_at: datetime,
        dry_run: bool,
    ) -> tuple[SyncOutcome, float]:
        if budget < MIN_PER_TOPIC_BUDGET:
            return SyncOutcome(subscription.topic, "skipped", detail=f"run budget exhausted (${budget:.2f} left)"), 0.0

        if dry_run:
            return SyncOutcome(
                subscription.topic, "would_sync", detail=self.build_freshness_query(subscription)[:120]
            ), 0.0

        # Read the prior pack before this run writes its own, so the
        # change-detection gate compares against the previous sync.
        prior_pack = self._load_latest_source_pack(subscription)

        try:
            research = await self._research(subscription, budget)
        except Exception as exc:
            return SyncOutcome(subscription.topic, "failed", detail=str(exc)), 0.0

        if "error" in research:
            return SyncOutcome(subscription.topic, "failed", detail=str(research["error"])), 0.0

        cost = float(research.get("cost", 0.0) or 0.0)
        answer = (research.get("answer") or "").strip()
        current_pack = _source_pack_from_research(research)
        source_pack_path, source_count, context_mode = self._persist_source_pack(
            subscription,
            current_pack,
            started_at,
        )
        if source_pack_path is None:
            return (
                SyncOutcome(
                    subscription.topic,
                    "failed",
                    cost=cost,
                    detail="source pack artifact failed",
                    source_count=source_count,
                    context_mode=context_mode,
                ),
                cost,
            )

        if _fresh_context_has_no_sources(research):
            outcome = self._record_no_changes(
                subscription,
                cost,
                detail="fresh context returned no sources",
            )
            self._attach_source_pack_summary(outcome, source_pack_path, source_count, context_mode)
            return outcome, cost

        if fresh_sources_unchanged(prior_pack, current_pack):
            outcome = self._record_no_changes(
                subscription,
                cost,
                detail="sources unchanged since last sync",
            )
            self._attach_source_pack_summary(outcome, source_pack_path, source_count, context_mode)
            return outcome, cost

        if not answer or answer.lower().startswith(_NO_CHANGES_MARKER):
            outcome = self._record_no_changes(subscription, cost)
            self._attach_source_pack_summary(outcome, source_pack_path, source_count, context_mode)
            return outcome, cost

        outcome = await self._absorb_sync_answer(subscription, answer, cost=cost, started_at=started_at)
        self._attach_source_pack_summary(outcome, source_pack_path, source_count, context_mode)
        return outcome, cost

    def _persist_source_pack(
        self,
        subscription: Subscription,
        source_pack: dict[str, Any] | None,
        started_at: datetime,
    ) -> tuple[str | None, int, str]:
        if source_pack is None:
            return "", 0, ""

        source_count, context_mode = _source_pack_summary(source_pack)
        try:
            path = self._write_source_pack_artifact(subscription, source_pack, started_at)
        except OSError as exc:
            logger.error("Could not write source pack for %s: %s", subscription.topic, exc)
            return None, source_count, context_mode
        return path, source_count, context_mode

    def _load_latest_source_pack(self, subscription: Subscription) -> dict[str, Any] | None:
        """Most recent persisted source pack for this topic, or None.

        Called before the current run writes its own artifact, so the result is
        the previous sync's pack. The timestamped filenames sort lexically in
        chronological order, so the last match is the newest. Returns the inner
        ``source_pack`` payload (the part carrying per-source content hashes).
        """
        artifact_dir = self.subscriptions.path.parent / "sync_artifacts" / "source_packs"
        if not artifact_dir.is_dir():
            return None
        candidates = sorted(artifact_dir.glob(f"*_{_slug(subscription.topic)}.json"))
        if not candidates:
            return None
        try:
            data = json.loads(candidates[-1].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Could not read prior source pack %s: %s", candidates[-1], exc)
            return None
        source_pack = data.get("source_pack")
        return source_pack if isinstance(source_pack, dict) else None

    def _write_source_pack_artifact(
        self,
        subscription: Subscription,
        source_pack: dict[str, Any],
        started_at: datetime,
    ) -> str:
        root = self.subscriptions.path.parent
        artifact_dir = root / "sync_artifacts" / "source_packs"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        path = artifact_dir / f"{timestamp}_{_slug(subscription.topic)}.json"
        payload = {
            "schema_version": "deepr.sync_source_pack.v1",
            "expert_name": self.expert.name,
            "topic": subscription.topic,
            "query": self.build_freshness_query(subscription),
            "started_at": started_at.isoformat(),
            "source_pack": source_pack,
        }
        atomic_write_json(path, payload)
        return path.relative_to(root).as_posix()

    @staticmethod
    def _attach_source_pack_summary(
        outcome: SyncOutcome,
        artifact_path: str,
        source_count: int,
        context_mode: str,
    ) -> None:
        outcome.source_pack_artifact = artifact_path
        outcome.source_count = source_count
        outcome.context_mode = context_mode

    def _record_no_changes(
        self,
        subscription: Subscription,
        cost: float,
        *,
        detail: str = "",
    ) -> SyncOutcome:
        subscription.last_synced = datetime.now(UTC)
        self.subscriptions.save()
        return SyncOutcome(subscription.topic, "no_changes", cost=cost, detail=detail)

    async def _absorb_sync_answer(
        self,
        subscription: Subscription,
        answer: str,
        *,
        cost: float,
        started_at: datetime,
    ) -> SyncOutcome:
        try:
            report_id = f"sync:{_slug(subscription.topic)}:{started_at.strftime('%Y%m%d')}"
            absorption = await self._get_absorber().absorb(
                report_id,
                answer,
                flag_contradictions=True,
            )
            subscription.last_synced = datetime.now(UTC)
            self.subscriptions.save()
            return SyncOutcome(
                subscription.topic,
                "synced",
                cost=cost,
                absorbed=len(absorption.absorbed),
                flagged=len(absorption.flagged),
            )
        except Exception as exc:
            return SyncOutcome(subscription.topic, "failed", cost=cost, detail=f"absorb failed: {exc}")

    async def _research(self, subscription: Subscription, budget: float) -> dict[str, Any]:
        query = self.build_freshness_query(subscription)
        fn = self._research_fn or self._default_research
        return await fn(query, budget)
