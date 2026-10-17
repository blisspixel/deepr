"""World time for a belief, kept apart from the store's record clock.

A missing end means the store does not know whether the claim still holds.
Decay, an unused-belief archive, and a position leaving the brief do not
answer that question. Closing a claim requires an explicit end instant and
a basis that says where the instant came from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from deepr.experts.beliefs import Belief, BeliefChange, BeliefStore
from deepr.experts.mutation_audit import belief_snapshot

WORLD_TIME_KIND = "world_time"
SCHEMA = "deepr-world-validity-v1"
CLOSE_BASES = frozenset({"observed", "source_resolved"})
AFFIRM_BASIS = "operator_affirmed"
UNKNOWN = "unknown"
IN_FORCE = "in_force"
CLOSED = "closed"
CLOSED_ON_LIVE = "closed_mark_on_live_belief"


class WorldValidityError(ValueError):
    """The caller asked for a world-time write the store must refuse."""


def parse_utc(value: str, *, field_name: str) -> datetime:
    """Parse an aware ISO-8601 instant. Naive values are refused."""
    text = value.strip()
    if not text:
        raise WorldValidityError(f"{field_name} is empty.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorldValidityError(f"{field_name} is not an ISO-8601 instant.") from exc
    if parsed.tzinfo is None:
        raise WorldValidityError(f"{field_name} needs a timezone. A naive clock is not world time.")
    return parsed.astimezone(UTC)


def latest_world_mark(belief: Belief) -> dict[str, Any] | None:
    """Last explicit world-time mark on a belief, if one was admitted."""
    for item in reversed(belief.history):
        if isinstance(item, dict) and item.get("kind") == WORLD_TIME_KIND:
            return item
    return None


def live_status(belief: Belief) -> str:
    """Status of a belief that is still in the live store.

    Absence is unknown. An operator affirmation is the only in-force mark.
    A closed mark left on a live belief is reported as a defect.
    """
    mark = latest_world_mark(belief)
    if mark is None:
        return UNKNOWN
    status = str(mark.get("status") or "")
    basis = str(mark.get("basis") or "")
    ended = mark.get("invalidated_at")
    if status == IN_FORCE and basis == AFFIRM_BASIS and not ended:
        return IN_FORCE
    if status == CLOSED:
        return CLOSED_ON_LIVE
    return UNKNOWN


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def project_world_validity(store: BeliefStore) -> dict[str, Any]:
    """Read live beliefs and the event log. This function does not write."""
    live_rows: list[dict[str, Any]] = []
    counts = {UNKNOWN: 0, IN_FORCE: 0, CLOSED_ON_LIVE: 0}
    for belief in store.beliefs.values():
        status = live_status(belief)
        counts[status] = counts.get(status, 0) + 1
        mark = latest_world_mark(belief)
        live_rows.append(
            {
                "belief_id": belief.id,
                "status": status,
                "valid_from": mark.get("valid_from") if mark else None,
                "displayed_confidence": round(belief.get_current_confidence(), 6),
            }
        )
    live_rows.sort(key=lambda row: str(row["belief_id"]))

    closed_ends: list[dict[str, Any]] = []
    retirements_without_end: list[dict[str, Any]] = []
    for change in store.iter_events():
        if change.change_type == "archived":
            row = {
                "belief_id": change.belief_id,
                "record_time": _iso(change.timestamp),
                "invalidated_at": _iso(change.invalidated_at),
                "reason": change.reason,
            }
            if change.invalidated_at is None:
                retirements_without_end.append(row)
            else:
                closed_ends.append(row)
        elif change.change_type == "revised" and change.invalidated_at is not None:
            closed_ends.append(
                {
                    "belief_id": change.belief_id,
                    "record_time": _iso(change.timestamp),
                    "invalidated_at": _iso(change.invalidated_at),
                    "reason": change.reason,
                    "successor_kept_live": True,
                }
            )

    pairs: set[tuple[str, str]] = set()
    for belief in store.beliefs.values():
        for other_id in belief.contradictions_with:
            if other_id in store.beliefs and other_id != belief.id:
                left, right = sorted((belief.id, other_id))
                pairs.add((left, right))
    open_contradictions = [{"belief_ids": [left, right]} for left, right in sorted(pairs)]

    return {
        "schema": SCHEMA,
        "missing_end_means": UNKNOWN,
        "decay_does_not_end_a_claim": True,
        "live_beliefs": live_rows,
        "live_counts": {
            "live": len(live_rows),
            "unknown": counts.get(UNKNOWN, 0),
            "in_force": counts.get(IN_FORCE, 0),
            "closed_mark_on_live_belief": counts.get(CLOSED_ON_LIVE, 0),
        },
        "closed_ends": closed_ends,
        "store_retirements_without_world_end": retirements_without_end,
        "open_contradictions": open_contradictions,
        "contradictions_auto_resolved": False,
    }


def _require_live(store: BeliefStore, belief_id: str) -> Belief:
    belief = store.beliefs.get(belief_id)
    if belief is None:
        raise WorldValidityError(f"Belief {belief_id} is not in the live store.")
    return belief


def close_claim(
    store: BeliefStore,
    belief_id: str,
    *,
    ended_at: datetime,
    basis: str,
    evidence: str,
) -> BeliefChange:
    """Archive one live belief and record when the claim stopped holding.

    The previous claim stays in the archival snapshot. Decay is not a basis.
    """
    if basis not in CLOSE_BASES:
        raise WorldValidityError("A world end requires basis 'observed' or 'source_resolved'.")
    if ended_at.tzinfo is None:
        raise WorldValidityError("ended_at needs a timezone.")
    ended = ended_at.astimezone(UTC)
    reason_text = evidence.strip()
    if not reason_text:
        raise WorldValidityError("A world end requires the evidence that dated it.")
    belief = _require_live(store, belief_id)
    belief.history.append(
        {
            "kind": WORLD_TIME_KIND,
            "status": CLOSED,
            "basis": basis,
            "invalidated_at": ended.isoformat(),
            "evidence": reason_text,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
    )
    change = store.archive_belief(
        belief_id,
        reason=f"world_end:{basis}",
        invalidated_at=ended,
    )
    if change is None or change.invalidated_at is None:
        raise WorldValidityError("The store did not record a world end.")
    return change


def affirm_in_force(
    store: BeliefStore,
    belief_id: str,
    *,
    evidence: str,
    valid_from: datetime | None = None,
) -> BeliefChange:
    """Mark a live claim in force without moving its confidence or decay clock.

    This is an operator admission. It is not inferred from a missing end.
    """
    reason_text = evidence.strip()
    if not reason_text:
        raise WorldValidityError("An in-force mark requires the evidence that supports it.")
    if valid_from is not None and valid_from.tzinfo is None:
        raise WorldValidityError("valid_from needs a timezone.")
    belief = _require_live(store, belief_id)
    if live_status(belief) == CLOSED_ON_LIVE:
        raise WorldValidityError("Refusing to affirm a live belief that already carries a closed mark.")
    started = valid_from.astimezone(UTC).isoformat() if valid_from is not None else None
    before = belief_snapshot(belief)
    belief.history.append(
        {
            "kind": WORLD_TIME_KIND,
            "status": IN_FORCE,
            "basis": AFFIRM_BASIS,
            "valid_from": started,
            "invalidated_at": None,
            "evidence": reason_text,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
    )
    change = BeliefChange(
        belief_id=belief_id,
        change_type="updated",
        old_claim=belief.claim,
        new_claim=belief.claim,
        old_confidence=belief.confidence,
        new_confidence=belief.confidence,
        reason="world_time:in_force",
        evidence=reason_text,
    )
    store._record_change(
        change,
        before=before,
        after=belief_snapshot(belief),
        operation="world_time_affirm",
    )
    store._save()
    return change


def status_at(belief: Belief, moment: datetime) -> str:
    """What the admitted marks say about one live belief at one instant.

    A closed end without a start does not imply the claim was true before
    the end. The interval before an unknown start stays unknown.
    """
    if moment.tzinfo is None:
        raise WorldValidityError("moment needs a timezone.")
    when = moment.astimezone(UTC)
    mark = latest_world_mark(belief)
    if mark is None:
        return UNKNOWN
    status = str(mark.get("status") or "")
    start_text = mark.get("valid_from")
    end_text = mark.get("invalidated_at")
    start = parse_utc(str(start_text), field_name="valid_from") if start_text else None
    end = parse_utc(str(end_text), field_name="invalidated_at") if end_text else None
    if status == CLOSED and end is not None:
        if when >= end:
            return CLOSED
        if start is not None and start <= when < end:
            return IN_FORCE
        return UNKNOWN
    if status == IN_FORCE and str(mark.get("basis") or "") == AFFIRM_BASIS and end is None:
        if start is not None and when < start:
            return UNKNOWN
        return IN_FORCE
    return UNKNOWN
