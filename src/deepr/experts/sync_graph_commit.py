"""Verified graph-commit application seam for expert sync runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.knowledge_freshness import advance_knowledge_freshness
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.sync_contracts import ClaimCompilationOutcome, Subscription, SubscriptionStore, SyncOutcome
from deepr.experts.sync_support import nonnegative_float

ApplyArtifactWriter = Callable[[Subscription, dict[str, Any], datetime], str | None]
TrackerFactory = Callable[[], MetaCognitionTracker]


def _blocked_outcome(subscription: Subscription, cost: float, detail: str) -> SyncOutcome:
    return SyncOutcome(
        subscription.topic,
        "failed",
        cost=cost,
        detail=detail,
        graph_commit_apply_status="blocked",
    )


def _apply_verified_envelope(
    *,
    expert_name: str,
    expert_root: Path,
    envelope_artifact: str,
    envelope: dict[str, Any],
    belief_store: BeliefStore,
    tracker_factory: TrackerFactory,
    generated_at: str,
) -> dict[str, Any]:
    from deepr.experts.graph_commit_apply import apply_graph_commit_envelope
    from deepr.experts.graph_commit_provenance import require_sync_graph_commit_provenance
    from deepr.experts.loop_lock import expert_verb_lock

    require_sync_graph_commit_provenance(
        expert_root,
        envelope_artifact=envelope_artifact,
        envelope=envelope,
        expected_expert=expert_name,
    )
    with expert_verb_lock(expert_name, "graph-commit-apply") as acquired:
        if not acquired:
            raise RuntimeError("another graph commit apply is already running")
        return apply_graph_commit_envelope(
            envelope,
            belief_store,
            gap_tracker=tracker_factory(),
            dry_run=False,
            generated_at=generated_at,
        )


def apply_compiled_sync_graph_commit(
    *,
    expert: Any,
    subscriptions: SubscriptionStore,
    belief_store: BeliefStore,
    tracker_factory: TrackerFactory,
    write_apply_artifact: ApplyArtifactWriter,
    subscription: Subscription,
    claim_compile: ClaimCompilationOutcome,
    cost: float,
    started_at: datetime,
) -> SyncOutcome:
    """Authenticate, apply, journal, and settle one compiled sync commit."""
    envelope = claim_compile.graph_commit_envelope
    envelope_artifact = claim_compile.graph_commit_envelope_artifact
    if not envelope_artifact or not isinstance(envelope, dict):
        return _blocked_outcome(
            subscription, cost, "graph commit apply failed: compiled graph commit envelope required"
        )
    try:
        apply_result = _apply_verified_envelope(
            expert_name=expert.name,
            expert_root=subscriptions.path.parent,
            envelope_artifact=envelope_artifact,
            envelope=envelope,
            belief_store=belief_store,
            tracker_factory=tracker_factory,
            generated_at=started_at.isoformat(),
        )
    except Exception as exc:
        return _blocked_outcome(subscription, cost, f"graph commit apply failed: {exc}")

    summary = apply_result.get("summary", {}) if isinstance(apply_result.get("summary"), dict) else {}
    status = str(summary.get("status", "blocked") or "blocked")
    applied_writes = int(nonnegative_float(summary.get("applied_write_count", 0)))
    blocked_operations = int(nonnegative_float(summary.get("blocked_operation_count", 0)))
    envelope_summary = envelope.get("summary", {})
    if not isinstance(envelope_summary, dict):
        envelope_summary = {}
    blocked_decisions = int(nonnegative_float(envelope_summary.get("blocked_decision_count", 0)))
    detail = ""
    if status == "blocked":
        reasons = ", ".join(str(item) for item in summary.get("failure_reasons", []) or []) or "blocked"
        detail = f"graph commit apply blocked: {reasons}"

    apply_artifact = write_apply_artifact(subscription, apply_result, started_at)
    if apply_artifact is None:
        detail = f"{detail}; graph commit apply artifact failed" if detail else "graph commit apply artifact failed"
    sync_status = "synced" if status in {"applied", "already_applied"} and apply_artifact is not None else "failed"
    observed_at = None
    if sync_status == "synced":
        observed_at = datetime.now(UTC)
        subscription.last_synced = observed_at
        subscriptions.save()
        if applied_writes > 0 or status == "already_applied":
            advance_knowledge_freshness(expert, observed_at)
        else:
            observed_at = None

    return SyncOutcome(
        subscription.topic,
        sync_status,
        cost=cost,
        absorbed=applied_writes,
        blocked=blocked_operations + blocked_decisions,
        detail=detail,
        graph_commit_apply_artifact=apply_artifact or "",
        graph_commit_apply_status=status,
        knowledge_observed_at=observed_at,
    )


__all__ = ["apply_compiled_sync_graph_commit"]
