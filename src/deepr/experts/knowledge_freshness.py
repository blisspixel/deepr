"""Consistent expert knowledge-observation timestamps.

Freshness is profile metadata derived from verified knowledge activity.  This
module keeps the two public timestamps, the in-memory temporal view, and the
generated expert instructions in agreement.  It does not decide whether a
claim is true.  Callers invoke it only after their existing verifier and write
gates have accepted knowledge, or after a source-backed sync has established
that the expert is current.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_DERIVED_MESSAGE_PREFIX = "You are a specialized domain expert with access to a curated knowledge base"
_DERIVED_TEMPORAL_MARKER = "**IMPORTANT TEMPORAL CONTEXT:**"
_ACCEPTED_EVENT_TYPES = frozenset({"created", "updated", "revised"})


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_derived_expert_system_message(message: str | None) -> bool:
    """Return whether ``message`` is Deepr's regenerable expert template."""
    text = str(message or "")
    return text.startswith(_DERIVED_MESSAGE_PREFIX) and _DERIVED_TEMPORAL_MARKER in text


def _derived_message_needs_refresh(profile: Any, effective: datetime) -> bool:
    message = getattr(profile, "system_message", None)
    if not is_derived_expert_system_message(message):
        return False
    from deepr.experts.profile import get_expert_system_message

    expected = get_expert_system_message(
        knowledge_cutoff_date=effective,
        domain_velocity=str(getattr(profile, "domain_velocity", "medium") or "medium"),
    )
    return message != expected


def advance_knowledge_freshness(profile: Any, observed_at: datetime) -> datetime:
    """Advance all knowledge-time views without allowing timestamp regression.

    ``observed_at`` is record time: when a verified write completed or a
    source-backed sync established currency.  It is deliberately not inferred
    publication time.  Custom system instructions are preserved.  Only the
    known generated template is regenerated.
    """
    observed = _aware_utc(observed_at)
    candidates = [observed]
    for value in (
        getattr(profile, "knowledge_cutoff_date", None),
        getattr(profile, "last_knowledge_refresh", None),
    ):
        if isinstance(value, datetime):
            candidates.append(_aware_utc(value))
    effective = max(candidates)

    profile.knowledge_cutoff_date = effective
    profile.last_knowledge_refresh = effective
    temporal_state = getattr(profile, "_temporal_state", None)
    if temporal_state is not None:
        temporal_state.last_learning = effective

    if is_derived_expert_system_message(getattr(profile, "system_message", None)):
        from deepr.experts.profile import get_expert_system_message

        profile.system_message = get_expert_system_message(
            knowledge_cutoff_date=effective,
            domain_velocity=str(getattr(profile, "domain_velocity", "medium") or "medium"),
        )
    return effective


def advance_from_absorption(profile: Any, result: Any) -> bool:
    """Advance after an absorption result only when it proves a real write."""
    if bool(getattr(result, "dry_run", False)):
        return False
    accepted = len(list(getattr(result, "absorbed", []) or [])) + len(list(getattr(result, "flagged", []) or []))
    observed_at = getattr(result, "generated_at", None)
    if accepted <= 0 or not isinstance(observed_at, datetime):
        return False
    advance_knowledge_freshness(profile, observed_at)
    return True


@dataclass(frozen=True)
class FreshnessReconciliation:
    """A deterministic repair plan backed by an append-only belief event."""

    status: str
    expert_name: str
    evidence_event_count: int
    observed_at: datetime | None = None
    belief_id: str = ""
    event_type: str = ""
    changed: bool = False
    system_message_would_refresh: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "deepr-expert-freshness-reconciliation-v1",
            "kind": "deepr.expert.freshness_reconciliation",
            "status": self.status,
            "expert_name": self.expert_name,
            "evidence_event_count": self.evidence_event_count,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "belief_id": self.belief_id,
            "event_type": self.event_type,
            "changed": self.changed,
            "system_message_would_refresh": self.system_message_would_refresh,
            "cost_usd": 0.0,
            "writes": "profile_metadata_only" if self.changed else "none",
        }


def plan_freshness_reconciliation(profile: Any, belief_store: Any) -> FreshnessReconciliation:
    """Plan a repair from the latest accepted event for a currently live belief."""
    live_ids = set(getattr(belief_store, "beliefs", {}) or {})
    accepted_events = [
        event
        for event in belief_store.iter_events()
        if str(getattr(event, "change_type", "")) in _ACCEPTED_EVENT_TYPES
        and str(getattr(event, "belief_id", "")) in live_ids
        and isinstance(getattr(event, "timestamp", None), datetime)
    ]
    expert_name = str(getattr(profile, "name", "") or "")
    if not accepted_events:
        return FreshnessReconciliation(
            status="no_accepted_event_evidence",
            expert_name=expert_name,
            evidence_event_count=0,
        )

    latest = max(accepted_events, key=lambda event: _aware_utc(event.timestamp))
    observed = _aware_utc(latest.timestamp)
    current_values = [
        _aware_utc(value)
        for value in (
            getattr(profile, "knowledge_cutoff_date", None),
            getattr(profile, "last_knowledge_refresh", None),
        )
        if isinstance(value, datetime)
    ]
    effective = max([observed, *current_values])
    metadata_changed = len(current_values) != 2 or any(value != effective for value in current_values)
    message_refresh = _derived_message_needs_refresh(profile, effective)
    return FreshnessReconciliation(
        status="repair_available" if metadata_changed or message_refresh else "already_reconciled",
        expert_name=expert_name,
        evidence_event_count=len(accepted_events),
        observed_at=observed,
        belief_id=str(latest.belief_id),
        event_type=str(latest.change_type),
        changed=metadata_changed or message_refresh,
        system_message_would_refresh=message_refresh,
    )


def apply_freshness_reconciliation(profile: Any, plan: FreshnessReconciliation) -> bool:
    """Apply a previously built event-backed repair plan in memory."""
    if plan.observed_at is None or plan.status == "no_accepted_event_evidence":
        return False
    advance_knowledge_freshness(profile, plan.observed_at)
    return plan.changed


__all__ = [
    "FreshnessReconciliation",
    "advance_from_absorption",
    "advance_knowledge_freshness",
    "apply_freshness_reconciliation",
    "is_derived_expert_system_message",
    "plan_freshness_reconciliation",
]
