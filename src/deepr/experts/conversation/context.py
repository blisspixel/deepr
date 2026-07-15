"""Deterministic bounded context assembly for expert conversations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from deepr.experts.conversation.models import (
    CONTEXT_BUILDER_VERSION,
    MAX_RECENT_TURNS,
    SNAPSHOT_KIND,
    SNAPSHOT_SCHEMA_VERSION,
    ConversationError,
    ErrorCode,
    ExpertSnapshotInput,
    canonical_json,
    sha256_json,
    utf8_size,
)


@dataclass(frozen=True)
class BoundedTurnContext:
    """Selected exact context and its replay hash."""

    snapshot: dict[str, Any]
    decision_brief: str | None
    message: str
    recent_turns: tuple[dict[str, Any], ...]
    decision_ledger: dict[str, Any]
    context_bytes: int
    context_sha256: str

    @property
    def recent_turn_ids(self) -> tuple[str, ...]:
        return tuple(str(turn["turn_id"]) for turn in self.recent_turns)

    def execution_payload(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot,
            "decision_brief": self.decision_brief,
            "message": self.message,
            "recent_turns": list(self.recent_turns),
            "decision_ledger": self.decision_ledger,
        }

    def lineage_payload(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot["snapshot_id"],
            "snapshot_sha256": self.snapshot["snapshot_sha256"],
            "recent_turn_ids": list(self.recent_turn_ids),
            "context_bytes": self.context_bytes,
            "context_sha256": self.context_sha256,
        }


def build_frozen_snapshot(
    *,
    conversation_id: str,
    snapshot_id: str,
    expert_snapshots: Sequence[ExpertSnapshotInput],
    created_at: datetime,
) -> dict[str, Any]:
    """Build the immutable v1 snapshot without reading live expert state."""
    packets = [snapshot.to_dict() for snapshot in expert_snapshots]
    roster_hash = sha256_json([snapshot.expert_name for snapshot in expert_snapshots])
    snapshot_material = {
        "conversation_id": conversation_id,
        "context_builder_version": CONTEXT_BUILDER_VERSION,
        "roster_hash": roster_hash,
        "expert_snapshots": packets,
    }
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": SNAPSHOT_KIND,
        "snapshot_id": snapshot_id,
        "conversation_id": conversation_id,
        "created_at": created_at.isoformat(),
        "context_builder_version": CONTEXT_BUILDER_VERSION,
        "roster_hash": roster_hash,
        "snapshot_sha256": sha256_json(snapshot_material),
        "total_bytes": utf8_size(canonical_json(packets)),
        "content_available": True,
        "content_deleted_at": None,
        "expert_snapshots": packets,
    }


def _derive_decision_ledger(recent_turns: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Copy source-linked proposal fields without making semantic judgments."""
    ledger: dict[str, list[dict[str, Any]]] = {
        "assumptions": [],
        "evidence": [],
        "dissent": [],
        "decision_proposals": [],
        "open_questions": [],
        "host_confirmed_decisions": [],
    }
    for turn in recent_turns:
        turn_id = str(turn["turn_id"])
        artifact = turn.get("artifact")
        if not isinstance(artifact, dict):
            continue
        for field_name in ("assumptions", "evidence", "dissent"):
            values = artifact.get(field_name, [])
            if isinstance(values, list):
                ledger[field_name].extend({"source_turn_id": turn_id, "value": value} for value in values)
        implications = artifact.get("decision_implications", [])
        if isinstance(implications, list):
            ledger["decision_proposals"].extend({"source_turn_id": turn_id, "value": value} for value in implications)
        gaps = artifact.get("unresolved_gaps", [])
        if isinstance(gaps, list):
            ledger["open_questions"].extend({"source_turn_id": turn_id, "value": value} for value in gaps)
        next_question = artifact.get("recommended_next_question")
        if isinstance(next_question, str) and next_question:
            ledger["open_questions"].append({"source_turn_id": turn_id, "value": next_question})
    return ledger


def _context_material(
    *,
    snapshot: dict[str, Any],
    decision_brief: str | None,
    message: str,
    recent_turns: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = _derive_decision_ledger(recent_turns)
    material = {
        "snapshot": snapshot,
        "decision_brief": decision_brief,
        "message": message,
        "recent_turns": list(recent_turns),
        "decision_ledger": ledger,
    }
    return material, ledger


def build_bounded_turn_context(
    *,
    snapshot: dict[str, Any],
    decision_brief: str | None,
    message: str,
    recent_turn_candidates: Sequence[dict[str, Any]],
    max_context_bytes: int,
) -> BoundedTurnContext:
    """Select a contiguous newest suffix under both turn and byte ceilings."""
    if snapshot.get("content_available") is not True or snapshot.get("expert_snapshots") is None:
        raise ConversationError(ErrorCode.CONTENT_DELETED, "Conversation content has been deleted.")

    selected_newest_first: list[dict[str, Any]] = []
    material, ledger = _context_material(
        snapshot=snapshot,
        decision_brief=decision_brief,
        message=message,
        recent_turns=(),
    )
    encoded = canonical_json(material)
    if utf8_size(encoded) > max_context_bytes:
        raise ConversationError(
            ErrorCode.CAPACITY_EXHAUSTED,
            "The frozen snapshot and current request exceed the context ceiling.",
        )

    for candidate in reversed(recent_turn_candidates[-MAX_RECENT_TURNS:]):
        proposed_newest_first = [*selected_newest_first, candidate]
        proposed = tuple(reversed(proposed_newest_first))
        proposed_material, proposed_ledger = _context_material(
            snapshot=snapshot,
            decision_brief=decision_brief,
            message=message,
            recent_turns=proposed,
        )
        proposed_encoded = canonical_json(proposed_material)
        if utf8_size(proposed_encoded) > max_context_bytes:
            break
        selected_newest_first = proposed_newest_first
        material = proposed_material
        ledger = proposed_ledger
        encoded = proposed_encoded

    selected = tuple(reversed(selected_newest_first))
    return BoundedTurnContext(
        snapshot=snapshot,
        decision_brief=decision_brief,
        message=message,
        recent_turns=selected,
        decision_ledger=ledger,
        context_bytes=utf8_size(encoded),
        context_sha256=sha256_json(material),
    )
