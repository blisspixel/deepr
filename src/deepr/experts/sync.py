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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from deepr.backends.context_building import accepts_prior_source_pack
from deepr.experts.beliefs import BeliefStore
from deepr.experts.perspective import what_changed
from deepr.experts.sync_support import (
    NO_CHANGES_MARKER,
    fresh_context_has_no_sources,
    is_no_changes_answer,
    model_metadata,
    nonnegative_float,
    slug,
    source_pack_content_hashes,
    source_pack_from_research,
    source_pack_summary,
)
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

_NO_CHANGES_MARKER = NO_CHANGES_MARKER

# Default per-subscription research budget when none is set.
DEFAULT_SUBSCRIPTION_BUDGET = 0.50

# Floor below which a sync run refuses to start a subscription (mirrors the
# learner's refuse-before-spending preflight).
MIN_PER_TOPIC_BUDGET = 0.05

ResearchFn = Callable[..., Awaitable[dict[str, Any]]]
SpendDecisionFn = Callable[[Any, float], Any]


class ClaimExtractionService(Protocol):
    async def extract(
        self,
        source_notes: dict[str, Any],
        source_pack_payload: dict[str, Any],
        *,
        source_note_artifact: str = "",
        budget_usd: float = 0.0,
        session_id: str = "semantic_claim_extraction",
        generated_at: str = "",
    ) -> dict[str, Any]: ...


class ClaimVerificationService(Protocol):
    async def verify(
        self,
        claim_extraction: dict[str, Any],
        source_notes: dict[str, Any],
        source_pack_payload: dict[str, Any],
        *,
        claim_extraction_artifact: str = "",
        source_note_artifact: str = "",
        budget_usd: float = 0.0,
        session_id: str = "claim_verification",
        generated_at: str = "",
        recall_belief_store: Any | None = None,
        recall_domain: str | None = None,
    ) -> dict[str, Any]: ...


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
    current_hashes = source_pack_content_hashes(current)
    if not current_hashes:
        return False
    prior_hashes = source_pack_content_hashes(prior)
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
    source_pack_manifest_artifact: str = ""
    source_note_artifact: str = ""
    claim_extraction_artifact: str = ""
    claim_verification_artifact: str = ""
    graph_commit_envelope_artifact: str = ""
    graph_commit_apply_artifact: str = ""
    graph_commit_apply_status: str = ""
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
            "source_pack_manifest_artifact": self.source_pack_manifest_artifact,
            "source_note_artifact": self.source_note_artifact,
            "claim_extraction_artifact": self.claim_extraction_artifact,
            "claim_verification_artifact": self.claim_verification_artifact,
            "graph_commit_envelope_artifact": self.graph_commit_envelope_artifact,
            "graph_commit_apply_artifact": self.graph_commit_apply_artifact,
            "graph_commit_apply_status": self.graph_commit_apply_status,
            "source_count": self.source_count,
            "context_mode": self.context_mode,
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
        claim_extractor: ClaimExtractionService | None = None,
        claim_verifier: ClaimVerificationService | None = None,
        metacognition_tracker: Any | None = None,
        spend_decision_fn: SpendDecisionFn | None = None,
    ) -> None:
        self.expert = expert
        self._research_fn = research_fn
        self.subscriptions = subscription_store or SubscriptionStore(expert.name)
        self.belief_store = belief_store or BeliefStore(expert.name)
        self._absorber = absorber
        self._claim_extractor = claim_extractor
        self._claim_verifier = claim_verifier
        self._metacognition_tracker = metacognition_tracker
        self._spend_decision_fn = spend_decision_fn

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

    def _get_metacognition_tracker(self) -> Any:
        if self._metacognition_tracker is None:
            from deepr.experts.metacognition import MetaCognitionTracker

            self._metacognition_tracker = MetaCognitionTracker(self.expert.name)
        return self._metacognition_tracker

    def _spend_decision_skip(self, subscription: Subscription, budget: float) -> SyncOutcome | None:
        if self._spend_decision_fn is None:
            return None
        try:
            decision = self._spend_decision_fn(subscription, budget)
        except Exception as exc:
            detail = f"metered deferred: spend decision unavailable ({exc})"
            return SyncOutcome(subscription.topic, "skipped", detail=detail)
        if bool(getattr(decision, "allowed", False)):
            return None
        reason = str(getattr(decision, "reason", "value gate denied"))
        return SyncOutcome(subscription.topic, "skipped", detail=f"metered deferred: {reason}")

    def _pre_research_skip(self, subscription: Subscription, budget: float, *, dry_run: bool) -> SyncOutcome | None:
        if budget < MIN_PER_TOPIC_BUDGET:
            return SyncOutcome(subscription.topic, "skipped", detail=f"run budget exhausted (${budget:.2f} left)")
        if dry_run:
            return SyncOutcome(subscription.topic, "would_sync", detail=self.build_freshness_query(subscription)[:120])
        return self._spend_decision_skip(subscription, budget)

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
        apply_graph_commits: bool = False,
    ) -> SyncResult:
        """Run due subscriptions through research -> verified write boundary -> delta.

        Args:
            budget: Total ceiling for this run (per-topic budgets apply within it).
            only_due: Sync only subscriptions past their cadence window.
            dry_run: Report what would sync; no research, no spend, no writes.
            apply_graph_commits: Apply compiled graph commit envelopes instead
                of calling the legacy absorber. Requires injected claim services.
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
                apply_graph_commits=apply_graph_commits,
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
        apply_graph_commits: bool,
    ) -> tuple[SyncOutcome, float]:
        if skip := self._pre_research_skip(subscription, budget, dry_run=dry_run):
            return skip, 0.0

        # Read the prior pack before this run writes its own, so the
        # change-detection gate compares against the previous sync.
        prior_pack = self._load_latest_source_pack(subscription)

        try:
            research = await self._research(subscription, budget, prior_source_pack=prior_pack)
        except Exception as exc:
            return SyncOutcome(subscription.topic, "failed", detail=str(exc)), 0.0

        if "error" in research:
            return SyncOutcome(subscription.topic, "failed", detail=str(research["error"])), 0.0

        cost = float(research.get("cost", 0.0) or 0.0)
        answer = (research.get("answer") or "").strip()
        current_pack = source_pack_from_research(research)
        source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode = (
            self._persist_source_pack(
                subscription,
                current_pack,
                started_at,
            )
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

        if fresh_context_has_no_sources(research):
            outcome = self._record_no_changes(
                subscription,
                cost,
                detail="fresh context returned no sources",
            )
            self._attach_source_pack_summary(
                outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
            )
            return outcome, cost

        if fresh_sources_unchanged(prior_pack, current_pack):
            outcome = self._record_no_changes(
                subscription,
                cost,
                detail="sources unchanged since last sync",
            )
            self._attach_source_pack_summary(
                outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
            )
            return outcome, cost

        if not answer or is_no_changes_answer(answer):
            outcome = self._record_no_changes(subscription, cost)
            self._attach_source_pack_summary(
                outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
            )
            return outcome, cost

        claim_compile = await self._compile_semantic_claims(
            subscription,
            source_pack_artifact=source_pack_path,
            source_note_artifact=source_note_path,
            budget=max(0.0, budget - cost),
            started_at=started_at,
        )
        cost += claim_compile.cost
        outcome = await self._integrate_sync_answer(
            subscription,
            answer,
            claim_compile,
            cost=cost,
            started_at=started_at,
            apply_graph_commits=apply_graph_commits,
        )
        self._attach_source_pack_summary(
            outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
        )
        self._attach_claim_compilation_summary(outcome, claim_compile)
        if claim_compile.detail:
            outcome.detail = self._append_detail(outcome.detail, claim_compile.detail)
        return outcome, cost

    async def _integrate_sync_answer(
        self,
        subscription: Subscription,
        answer: str,
        claim_compile: ClaimCompilationOutcome,
        *,
        cost: float,
        started_at: datetime,
        apply_graph_commits: bool,
    ) -> SyncOutcome:
        if apply_graph_commits:
            return self._apply_compiled_graph_commit(subscription, claim_compile, cost=cost, started_at=started_at)
        return await self._absorb_sync_answer(subscription, answer, cost=cost, started_at=started_at)

    def _persist_source_pack(
        self,
        subscription: Subscription,
        source_pack: dict[str, Any] | None,
        started_at: datetime,
    ) -> tuple[str | None, str, str, int, str]:
        if source_pack is None:
            return "", "", "", 0, ""

        source_count, context_mode = source_pack_summary(source_pack)
        try:
            path, manifest_path, source_note_path = self._write_source_pack_artifact(
                subscription, source_pack, started_at
            )
        except OSError as exc:
            logger.error("Could not write source pack for %s: %s", subscription.topic, exc)
            return None, "", "", source_count, context_mode
        return path, manifest_path, source_note_path, source_count, context_mode

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
        candidates = sorted(artifact_dir.glob(f"*_{slug(subscription.topic)}.json"))
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
    ) -> tuple[str, str, str]:
        from deepr.experts.source_pack_compiler import build_source_notes, build_source_pack_manifest

        root = self.subscriptions.path.parent
        artifact_dir = root / "sync_artifacts" / "source_packs"
        manifest_dir = root / "sync_artifacts" / "source_pack_manifests"
        source_note_dir = root / "sync_artifacts" / "source_notes"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        manifest_dir.mkdir(parents=True, exist_ok=True)
        source_note_dir.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        path = artifact_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        manifest_path = manifest_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        source_note_path = source_note_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        payload = {
            "schema_version": "deepr.sync_source_pack.v1",
            "expert_name": self.expert.name,
            "topic": subscription.topic,
            "query": self.build_freshness_query(subscription),
            "started_at": started_at.isoformat(),
            "source_pack": source_pack,
        }
        atomic_write_json(path, payload)
        relative_path = path.relative_to(root).as_posix()
        relative_manifest_path = manifest_path.relative_to(root).as_posix()
        manifest = build_source_pack_manifest(payload, source_pack_artifact=relative_path)
        atomic_write_json(manifest_path, manifest)
        source_notes = build_source_notes(
            payload,
            source_pack_artifact=relative_path,
            source_pack_manifest_artifact=relative_manifest_path,
        )
        atomic_write_json(source_note_path, source_notes)
        return relative_path, relative_manifest_path, source_note_path.relative_to(root).as_posix()

    def _read_sync_artifact(self, relative_path: str) -> dict[str, Any]:
        root = self.subscriptions.path.parent
        artifact_path = root / relative_path
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    async def _compile_semantic_claims(
        self,
        subscription: Subscription,
        *,
        source_pack_artifact: str,
        source_note_artifact: str,
        budget: float,
        started_at: datetime,
    ) -> ClaimCompilationOutcome:
        if self._claim_extractor is None or not source_pack_artifact or not source_note_artifact:
            return ClaimCompilationOutcome()

        try:
            source_pack_payload = self._read_sync_artifact(source_pack_artifact)
            source_notes = self._read_sync_artifact(source_note_artifact)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Could not read claim extraction inputs for %s: %s", subscription.topic, exc)
            return ClaimCompilationOutcome(detail=f"claim extraction skipped: could not read inputs ({exc})")

        try:
            extraction = await self._claim_extractor.extract(
                source_notes,
                source_pack_payload,
                source_note_artifact=source_note_artifact,
                budget_usd=budget,
                session_id=f"sync:{self.expert.name}:{slug(subscription.topic)}",
                generated_at=started_at.isoformat(),
            )
        except Exception as exc:
            from deepr.experts.claim_extraction import ClaimExtractionBlocked

            reason = "skipped" if isinstance(exc, ClaimExtractionBlocked) else "failed"
            logger.warning("Claim extraction %s for %s: %s", reason, subscription.topic, exc)
            return ClaimCompilationOutcome(detail=f"claim extraction {reason}: {exc}")

        extraction_cost = nonnegative_float((extraction.get("contract", {}) or {}).get("cost_usd", 0.0))
        root = self.subscriptions.path.parent
        artifact_dir = root / "sync_artifacts" / "claim_extractions"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        artifact_path = artifact_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        try:
            atomic_write_json(artifact_path, extraction)
        except OSError as exc:
            logger.error("Could not write claim extraction for %s: %s", subscription.topic, exc)
            return ClaimCompilationOutcome(cost=extraction_cost, detail=f"claim extraction artifact failed: {exc}")

        extraction_artifact = artifact_path.relative_to(root).as_posix()
        verification = await self._compile_claim_verification(
            subscription,
            extraction,
            source_notes,
            source_pack_payload,
            claim_extraction_artifact=extraction_artifact,
            source_note_artifact=source_note_artifact,
            budget=max(0.0, budget - extraction_cost),
            started_at=started_at,
        )
        return ClaimCompilationOutcome(
            claim_extraction_artifact=extraction_artifact,
            claim_verification_artifact=verification.claim_verification_artifact,
            graph_commit_envelope_artifact=verification.graph_commit_envelope_artifact,
            graph_commit_envelope=verification.graph_commit_envelope,
            cost=extraction_cost + verification.cost,
            detail=verification.detail,
        )

    async def _compile_claim_verification(
        self,
        subscription: Subscription,
        claim_extraction: dict[str, Any],
        source_notes: dict[str, Any],
        source_pack_payload: dict[str, Any],
        *,
        claim_extraction_artifact: str,
        source_note_artifact: str,
        budget: float,
        started_at: datetime,
    ) -> ClaimCompilationOutcome:
        if self._claim_verifier is None:
            return ClaimCompilationOutcome()

        try:
            model_output = await self._claim_verifier.verify(
                claim_extraction,
                source_notes,
                source_pack_payload,
                claim_extraction_artifact=claim_extraction_artifact,
                source_note_artifact=source_note_artifact,
                budget_usd=budget,
                session_id=f"verify:{self.expert.name}:{slug(subscription.topic)}",
                generated_at=started_at.isoformat(),
                recall_belief_store=self.belief_store,
                recall_domain=str(getattr(self.expert, "domain", "") or ""),
            )
        except Exception as exc:
            logger.warning("Claim verification failed for %s: %s", subscription.topic, exc)
            return ClaimCompilationOutcome(detail=f"claim verification failed: {exc}")
        if not isinstance(model_output, dict):
            return ClaimCompilationOutcome(detail="claim verification failed: invalid verifier output")

        from deepr.experts.graph_commit_envelope import build_graph_commit_envelope
        from deepr.experts.source_pack_compiler import build_claim_verification

        verification_cost = nonnegative_float((model_output.get("contract", {}) or {}).get("cost_usd", 0.0))
        prompt_metadata = model_output.get("prompt", {}) if isinstance(model_output.get("prompt"), dict) else {}
        verification = build_claim_verification(
            claim_extraction,
            model_output,
            claim_extraction_artifact=claim_extraction_artifact,
            provider=model_metadata(model_output, "provider"),
            model=model_metadata(model_output, "model"),
            capacity_source=model_metadata(model_output, "capacity_source"),
            cost_usd=verification_cost,
            prompt_ref=str(prompt_metadata.get("prompt_ref", "") or ""),
            prompt_hash=str(prompt_metadata.get("prompt_hash", "") or ""),
            generated_at=started_at.isoformat(),
            recall_belief_store=self.belief_store,
            recall_domain=str(getattr(self.expert, "domain", "") or ""),
        )

        root = self.subscriptions.path.parent
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        verification_dir = root / "sync_artifacts" / "claim_verifications"
        verification_dir.mkdir(parents=True, exist_ok=True)
        verification_path = verification_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        try:
            atomic_write_json(verification_path, verification)
        except OSError as exc:
            logger.error("Could not write claim verification for %s: %s", subscription.topic, exc)
            return ClaimCompilationOutcome(cost=verification_cost, detail=f"claim verification artifact failed: {exc}")

        verification_artifact = verification_path.relative_to(root).as_posix()
        graph_commit = build_graph_commit_envelope(
            claim_extraction,
            verification,
            claim_extraction_artifact=claim_extraction_artifact,
            claim_verification_artifact=verification_artifact,
            expert_name=self.expert.name,
            domain=str(getattr(self.expert, "domain", "") or ""),
            generated_at=started_at.isoformat(),
        )
        graph_dir = root / "sync_artifacts" / "graph_commit_envelopes"
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_path = graph_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        try:
            atomic_write_json(graph_path, graph_commit)
        except OSError as exc:
            logger.error("Could not write graph commit envelope for %s: %s", subscription.topic, exc)
            return ClaimCompilationOutcome(
                claim_verification_artifact=verification_artifact,
                cost=verification_cost,
                detail=f"graph commit envelope artifact failed: {exc}",
            )

        detail = ""
        summary = verification.get("summary", {}) or {}
        if summary.get("status") != "ready_for_commit_envelope":
            reasons = ", ".join(summary.get("failure_reasons", []) or []) or "no ready decisions"
            detail = f"claim verification {summary.get('status', 'blocked')}: {reasons}"
        return ClaimCompilationOutcome(
            claim_verification_artifact=verification_artifact,
            graph_commit_envelope_artifact=graph_path.relative_to(root).as_posix(),
            graph_commit_envelope=graph_commit,
            cost=verification_cost,
            detail=detail,
        )

    def _apply_compiled_graph_commit(
        self,
        subscription: Subscription,
        claim_compile: ClaimCompilationOutcome,
        *,
        cost: float,
        started_at: datetime,
    ) -> SyncOutcome:
        graph_commit = claim_compile.graph_commit_envelope
        if not claim_compile.graph_commit_envelope_artifact or not isinstance(graph_commit, dict):
            return SyncOutcome(
                subscription.topic,
                "failed",
                cost=cost,
                detail="graph commit apply failed: compiled graph commit envelope required",
                graph_commit_apply_status="blocked",
            )

        try:
            from deepr.experts.graph_commit_apply import apply_graph_commit_envelope
            from deepr.experts.loop_lock import expert_verb_lock

            with expert_verb_lock(self.expert.name, "graph-commit-apply") as acquired:
                if not acquired:
                    return SyncOutcome(
                        subscription.topic,
                        "failed",
                        cost=cost,
                        detail="graph commit apply failed: another graph commit apply is already running",
                        graph_commit_apply_status="blocked",
                    )
                apply_result = apply_graph_commit_envelope(
                    graph_commit,
                    self.belief_store,
                    gap_tracker=self._get_metacognition_tracker(),
                    dry_run=False,
                    generated_at=started_at.isoformat(),
                )
        except Exception as exc:
            return SyncOutcome(
                subscription.topic,
                "failed",
                cost=cost,
                detail=f"graph commit apply failed: {exc}",
                graph_commit_apply_status="blocked",
            )

        summary = apply_result.get("summary", {}) if isinstance(apply_result.get("summary"), dict) else {}
        status = str(summary.get("status", "blocked") or "blocked")
        applied_writes = int(nonnegative_float(summary.get("applied_write_count", 0)))
        blocked_operations = int(nonnegative_float(summary.get("blocked_operation_count", 0)))
        detail = ""
        if status == "blocked":
            reasons = ", ".join(str(item) for item in summary.get("failure_reasons", []) or []) or "blocked"
            detail = f"graph commit apply blocked: {reasons}"

        apply_artifact = self._write_graph_commit_apply_artifact(subscription, apply_result, started_at)
        if apply_artifact is None:
            detail = self._append_detail(detail, "graph commit apply artifact failed")

        sync_status = "synced" if status in {"applied", "already_applied"} and apply_artifact is not None else "failed"
        if sync_status == "synced":
            subscription.last_synced = datetime.now(UTC)
            self.subscriptions.save()

        return SyncOutcome(
            subscription.topic,
            sync_status,
            cost=cost,
            absorbed=applied_writes,
            flagged=blocked_operations,
            detail=detail,
            graph_commit_apply_artifact=apply_artifact or "",
            graph_commit_apply_status=status,
        )

    def _write_graph_commit_apply_artifact(
        self,
        subscription: Subscription,
        apply_result: dict[str, Any],
        started_at: datetime,
    ) -> str | None:
        root = self.subscriptions.path.parent
        apply_dir = root / "sync_artifacts" / "graph_commit_apply_results"
        apply_dir.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        apply_path = apply_dir / f"{timestamp}_{slug(subscription.topic)}.json"
        try:
            atomic_write_json(apply_path, apply_result)
        except OSError as exc:
            logger.error("Could not write graph commit apply result for %s: %s", subscription.topic, exc)
            return None
        return apply_path.relative_to(root).as_posix()

    @staticmethod
    def _attach_source_pack_summary(
        outcome: SyncOutcome,
        artifact_path: str,
        manifest_artifact_path: str,
        source_note_artifact_path: str,
        source_count: int,
        context_mode: str,
    ) -> None:
        outcome.source_pack_artifact = artifact_path
        outcome.source_pack_manifest_artifact = manifest_artifact_path
        outcome.source_note_artifact = source_note_artifact_path
        outcome.source_count = source_count
        outcome.context_mode = context_mode

    @staticmethod
    def _attach_claim_compilation_summary(outcome: SyncOutcome, claim_compile: ClaimCompilationOutcome) -> None:
        outcome.claim_extraction_artifact = claim_compile.claim_extraction_artifact
        outcome.claim_verification_artifact = claim_compile.claim_verification_artifact
        outcome.graph_commit_envelope_artifact = claim_compile.graph_commit_envelope_artifact

    @staticmethod
    def _append_detail(current: str, addition: str) -> str:
        if not current:
            return addition
        return f"{current}; {addition}"

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
            report_id = f"sync:{slug(subscription.topic)}:{started_at.strftime('%Y%m%d')}"
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

    async def _research(
        self,
        subscription: Subscription,
        budget: float,
        *,
        prior_source_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = self.build_freshness_query(subscription)
        fn = self._research_fn or self._default_research
        if prior_source_pack is not None and accepts_prior_source_pack(fn):
            return await fn(query, budget, prior_source_pack=prior_source_pack)
        return await fn(query, budget)
