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
import math
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast

from deepr.backends.context_building import accepts_keyword_argument, accepts_prior_source_pack
from deepr.experts.beliefs import BeliefStore
from deepr.experts.knowledge_freshness import advance_from_absorption, advance_knowledge_freshness
from deepr.experts.perspective import what_changed
from deepr.experts.sync_contracts import (
    DEFAULT_SUBSCRIPTION_BUDGET,
    ClaimCompilationOutcome,
    Subscription,
    SubscriptionStore,
    SyncOutcome,
    SyncResult,
)
from deepr.experts.sync_support import (
    NO_CHANGES_MARKER,
    RETRIEVAL_FOCUS_MAX_CHARS,
    RETRIEVAL_TOPIC_MAX_CHARS,
    bounded_retrieval_text,
    explicit_retrieval_urls,
    fresh_context_has_no_sources,
    is_no_changes_answer,
    model_metadata,
    nonnegative_float,
    slug,
    source_pack_content_hashes,
    source_pack_from_research,
    source_pack_summary,
    write_source_snapshots,
)
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SUBSCRIPTION_BUDGET",
    "ExpertSyncEngine",
    "Subscription",
    "SubscriptionStore",
    "SyncOutcome",
    "SyncResult",
    "fresh_sources_unchanged",
]

_NO_CHANGES_MARKER = NO_CHANGES_MARKER

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
    current content, or any hash the prior run did not already have). A model
    may route a semantic no-op, but its assertion alone never advances
    freshness. See docs/design/change-detection-gate.md.
    """
    current_hashes = source_pack_content_hashes(current)
    if not current_hashes:
        return False
    prior_hashes = source_pack_content_hashes(prior)
    if not prior_hashes:
        return False
    return current_hashes <= prior_hashes


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
        recall_route_preference: Mapping[str, Any] | None = None,
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
        self._recall_route_preference = dict(recall_route_preference) if recall_route_preference else None
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

    @staticmethod
    def build_retrieval_query(subscription: Subscription) -> str:
        """Build a concise source-retrieval route for one subscription.

        The full freshness prompt remains the generation query. This route is
        bounded transport input for search and direct URL extraction only.
        """
        topic = bounded_retrieval_text(subscription.topic, RETRIEVAL_TOPIC_MAX_CHARS)
        focus = bounded_retrieval_text(subscription.query, RETRIEVAL_FOCUS_MAX_CHARS)
        parts = [topic]
        if focus:
            parts.append(f"Focus: {focus}")
        route = " ".join(part for part in parts if part)
        explicit_urls = explicit_retrieval_urls(subscription.topic, subscription.query)
        missing_urls = [url for url in explicit_urls if url not in route]
        if missing_urls:
            route = f"{route} Sources: {' '.join(missing_urls)}".strip()
        return route

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
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(float(budget)):
            raise ValueError("budget must be a finite non-negative number")
        budget = float(budget)
        if budget < 0.0:
            raise ValueError("budget must be a finite non-negative number")
        started_at = datetime.now(UTC)
        result = SyncResult(expert_name=self.expert.name, started_at=started_at)

        targets = self.subscriptions.due() if only_due else list(self.subscriptions.subscriptions)
        if not targets:
            return result

        remaining = budget
        for sub in targets:
            if (
                isinstance(sub.budget, bool)
                or not isinstance(sub.budget, (int, float))
                or not math.isfinite(float(sub.budget))
                or float(sub.budget) < 0.0
            ):
                raise ValueError(f"subscription budget for {sub.topic!r} must be a finite non-negative number")
            allocation = min(float(sub.budget), remaining)
            outcome, spent = await self._sync_subscription(
                sub,
                budget=allocation,
                started_at=started_at,
                dry_run=dry_run,
                apply_graph_commits=apply_graph_commits,
            )
            if isinstance(spent, bool) or not isinstance(spent, (int, float)) or not math.isfinite(float(spent)):
                raise RuntimeError(f"sync returned invalid spend for {sub.topic!r}")
            spent = float(spent)
            if spent < 0.0:
                raise RuntimeError(f"sync returned invalid spend for {sub.topic!r}")
            if spent > allocation + 1e-9:
                raise RuntimeError(f"sync spend exceeded the allocated ceiling for {sub.topic!r}")
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

    def _absorption_budget_preflight(
        self,
        subscription: Subscription,
        budget: float,
        *,
        apply_graph_commits: bool,
    ) -> tuple[float, SyncOutcome | None]:
        if apply_graph_commits:
            return 0.0, None

        from deepr.experts.report_absorber import absorber_estimated_cost

        absorption_estimate = absorber_estimated_cost(self._get_absorber())
        if budget - absorption_estimate >= MIN_PER_TOPIC_BUDGET:
            return absorption_estimate, None
        return absorption_estimate, SyncOutcome(
            subscription.topic,
            "skipped",
            detail=(f"run budget leaves less than ${MIN_PER_TOPIC_BUDGET:.2f} for research after reserving absorption"),
        )

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

        absorption_estimate, budget_skip = self._absorption_budget_preflight(
            subscription,
            budget,
            apply_graph_commits=apply_graph_commits,
        )
        if budget_skip is not None:
            return budget_skip, 0.0

        # Read the prior pack before this run writes its own, so the
        # change-detection gate compares against the previous sync.
        prior_pack = self._load_latest_source_pack(subscription)

        try:
            research = await self._research(
                subscription,
                max(0.0, budget - absorption_estimate),
                prior_source_pack=prior_pack,
            )
        except Exception as exc:
            return SyncOutcome(subscription.topic, "failed", detail=str(exc)), 0.0

        try:
            cost = float(research.get("cost", 0.0) or 0.0)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"research returned invalid spend for {subscription.topic!r}") from exc
        if not math.isfinite(cost) or cost < 0.0:
            raise RuntimeError(f"research returned invalid spend for {subscription.topic!r}")
        if cost > budget + 1e-9:
            raise RuntimeError(f"research spend exceeded the allocated ceiling for {subscription.topic!r}")
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

        if "error" in research:
            outcome = SyncOutcome(
                subscription.topic,
                "failed",
                cost=cost,
                detail=str(research["error"]),
                error_code=str(research.get("error_code", "") or ""),
                retryable=bool(research.get("retryable", False)),
                no_metered_fallback=bool(research.get("no_metered_fallback", False)),
            )
            self._attach_source_pack_summary(
                outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
            )
            return outcome, cost

        if fresh_context_has_no_sources(research):
            outcome = self._record_no_changes(
                subscription,
                cost,
                detail="fresh context returned no sources",
                advance_profile=False,
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
            outcome = self._unverified_no_changes(subscription, cost, answer_present=bool(answer))
            self._attach_source_pack_summary(
                outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
            )
            return outcome, cost

        claim_compile = await self._compile_semantic_claims(
            subscription,
            source_pack_artifact=source_pack_path,
            source_note_artifact=source_note_path,
            budget=max(0.0, budget - cost - absorption_estimate),
            started_at=started_at,
        )
        cost += claim_compile.cost
        outcome = await self._integrate_sync_answer(
            subscription,
            answer,
            claim_compile,
            cost=cost,
            absorption_budget=max(0.0, budget - cost),
            started_at=started_at,
            apply_graph_commits=apply_graph_commits,
        )
        self._attach_source_pack_summary(
            outcome, source_pack_path, source_pack_manifest_path, source_note_path, source_count, context_mode
        )
        self._attach_claim_compilation_summary(outcome, claim_compile)
        if claim_compile.detail:
            outcome.detail = self._append_detail(outcome.detail, claim_compile.detail)
        # Legacy absorption has its own model call after research. The absorber
        # reports that estimate on the outcome, and its metered provider calls
        # are independently settled in the canonical ledger. Return the full
        # outcome cost so the run budget and loop record no longer omit the
        # shared absorption step.
        return outcome, outcome.cost

    @staticmethod
    def _unverified_no_changes(subscription: Subscription, cost: float, *, answer_present: bool) -> SyncOutcome:
        """Keep a subscription due when only model output claims no change."""
        cause = "model reported no significant changes" if answer_present else "research returned an empty answer"
        return SyncOutcome(
            subscription.topic,
            "failed",
            cost=cost,
            detail=f"{cause}, but source fingerprints did not independently verify it; freshness was not advanced",
            error_code="unverified_no_changes",
            retryable=True,
        )

    async def _integrate_sync_answer(
        self,
        subscription: Subscription,
        answer: str,
        claim_compile: ClaimCompilationOutcome,
        *,
        cost: float,
        absorption_budget: float,
        started_at: datetime,
        apply_graph_commits: bool,
    ) -> SyncOutcome:
        if apply_graph_commits:
            return self._apply_compiled_graph_commit(subscription, claim_compile, cost=cost, started_at=started_at)
        return await self._absorb_sync_answer(
            subscription,
            answer,
            cost=cost,
            absorption_budget=absorption_budget,
            started_at=started_at,
        )

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
        write_source_snapshots(source_pack, root)
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
            "answer_query": self.build_freshness_query(subscription),
            "retrieval_query": str(source_pack.get("query", "") or self.build_retrieval_query(subscription)),
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
        # Persist the exact recall packets the verifier prompt used when the
        # verifier reports them; only a verifier without that metadata falls
        # back to re-resolving recall from the store. This keeps the durable
        # artifact identical to what the model actually judged against,
        # including per-packet vector-vs-lexical routing.
        recall_metadata = model_output.get("recall", {}) if isinstance(model_output.get("recall"), dict) else {}
        prompt_recall_context = recall_metadata.get("context_by_candidate_id")
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
            recall_candidates_by_candidate_id=(
                prompt_recall_context if isinstance(prompt_recall_context, dict) else None
            ),
            recall_belief_store=self.belief_store,
            recall_domain=str(getattr(self.expert, "domain", "") or ""),
            recall_route_preference=self._recall_route_preference,
        )

        # Replay honesty: when the verifier replayed memoized decisions, the
        # persisted sidecar records which candidates were replayed vs freshly
        # judged, so an auditor can trace a decision to its original dispatch.
        memo_metadata = model_output.get("memo")
        if isinstance(memo_metadata, dict):
            verification["memo"] = memo_metadata

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
        try:
            from deepr.experts.graph_commit_provenance import persist_sync_graph_commit_envelope

            graph_artifact = persist_sync_graph_commit_envelope(
                root,
                envelope_artifact=f"sync_artifacts/graph_commit_envelopes/{timestamp}_{slug(subscription.topic)}.json",
                envelope=graph_commit,
                claim_extraction=claim_extraction,
                claim_verification=verification,
            )
        except Exception as exc:
            logger.error("Could not persist graph commit provenance for %s: %s", subscription.topic, exc)
            return ClaimCompilationOutcome(
                claim_verification_artifact=verification_artifact,
                cost=verification_cost,
                detail=f"graph commit provenance persistence failed: {exc}",
            )

        detail = ""
        summary = verification.get("summary", {}) or {}
        if summary.get("status") != "ready_for_commit_envelope":
            reasons = ", ".join(summary.get("failure_reasons", []) or []) or "no ready decisions"
            ready_count = int(nonnegative_float(summary.get("ready_for_commit_envelope_count", 0)))
            blocked_count = int(nonnegative_float(summary.get("blocked_decision_count", 0)))
            if ready_count:
                detail = f"claim verification partial: {ready_count} ready, {blocked_count} blocked: {reasons}"
            else:
                detail = f"claim verification {summary.get('status', 'blocked')}: {reasons}"
        return ClaimCompilationOutcome(
            claim_verification_artifact=verification_artifact,
            graph_commit_envelope_artifact=graph_artifact,
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
        from deepr.experts.sync_graph_commit import apply_compiled_sync_graph_commit

        return apply_compiled_sync_graph_commit(
            expert=self.expert,
            subscriptions=self.subscriptions,
            belief_store=self.belief_store,
            tracker_factory=self._get_metacognition_tracker,
            write_apply_artifact=self._write_graph_commit_apply_artifact,
            subscription=subscription,
            claim_compile=claim_compile,
            cost=cost,
            started_at=started_at,
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
        advance_profile: bool = True,
    ) -> SyncOutcome:
        observed_at = datetime.now(UTC)
        subscription.last_synced = observed_at
        self.subscriptions.save()
        if advance_profile:
            advance_knowledge_freshness(self.expert, observed_at)
        return SyncOutcome(
            subscription.topic,
            "no_changes",
            cost=cost,
            detail=detail,
            knowledge_observed_at=observed_at if advance_profile else None,
        )

    async def _absorb_sync_answer(
        self,
        subscription: Subscription,
        answer: str,
        *,
        cost: float,
        absorption_budget: float,
        started_at: datetime,
    ) -> SyncOutcome:
        try:
            from deepr.experts.report_absorber import ReportAbsorberCostError, absorption_result_cost

            report_id = f"sync:{slug(subscription.topic)}:{started_at.strftime('%Y%m%d')}"
            absorption = await self._get_absorber().absorb(
                report_id,
                answer,
                flag_contradictions=True,
                budget=absorption_budget,
            )
            total_cost = cost + absorption_result_cost(absorption)
            observed_at = datetime.now(UTC)
            subscription.last_synced = observed_at
            self.subscriptions.save()
            knowledge_changed = advance_from_absorption(self.expert, absorption)
            return SyncOutcome(
                subscription.topic,
                "synced",
                cost=total_cost,
                absorbed=len(absorption.absorbed),
                flagged=len(absorption.flagged),
                knowledge_observed_at=(self.expert.last_knowledge_refresh if knowledge_changed else None),
            )
        except ReportAbsorberCostError as exc:
            return SyncOutcome(
                subscription.topic,
                "failed",
                cost=cost + exc.actual_cost,
                detail=f"absorb failed: {exc}",
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
        retrieval_query = self.build_retrieval_query(subscription)
        fn = self._research_fn or self._default_research
        call_kwargs: dict[str, Any] = {}
        if prior_source_pack is not None and accepts_prior_source_pack(fn):
            call_kwargs["prior_source_pack"] = prior_source_pack
        if accepts_keyword_argument(fn, "retrieval_query"):
            call_kwargs["retrieval_query"] = retrieval_query
        if call_kwargs:
            prior_aware_fn = cast(Any, fn)
            result = await prior_aware_fn(query, budget, **call_kwargs)
            return cast(dict[str, Any], result)
        return await fn(query, budget)
