"""Tests for bounded deterministic conversation context assembly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deepr.experts.conversation.context import build_bounded_turn_context, build_frozen_snapshot
from deepr.experts.conversation.models import ConversationError, ErrorCode
from tests.unit.conversation_fixtures import answer_artifact, expert_snapshot


def _snapshot() -> dict[str, object]:
    return build_frozen_snapshot(
        conversation_id="conv_" + "a" * 32,
        snapshot_id="snap_" + "b" * 32,
        expert_snapshots=(expert_snapshot(),),
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )


def _turn(index: int, *, padding: int = 0) -> dict[str, object]:
    artifact = answer_artifact(direct_answer=f"answer {index}" + "x" * padding)
    return {"turn_id": f"turn_{index:032x}", "request": f"question {index}", "artifact": artifact}


def test_frozen_snapshot_is_deterministic_and_source_linked() -> None:
    first = _snapshot()
    second = _snapshot()

    assert first == second
    assert first["roster_hash"]
    assert first["snapshot_sha256"]
    assert first["content_available"] is True
    expert = first["expert_snapshots"][0]  # type: ignore[index]
    assert expert["state_sha256"] == "4" * 64
    assert expert["source_position"] == "belief-events:42"


def test_context_keeps_only_six_newest_exact_turns() -> None:
    candidates = [_turn(index) for index in range(10)]
    context = build_bounded_turn_context(
        snapshot=_snapshot(),
        decision_brief="decision",
        message="follow up",
        recent_turn_candidates=candidates,
        max_context_bytes=200_000,
    )

    assert context.recent_turn_ids == tuple(turn["turn_id"] for turn in candidates[-6:])
    assert context.context_bytes <= 200_000
    assert len(context.context_sha256) == 64


def test_context_uses_contiguous_newest_suffix_when_byte_bound_hits() -> None:
    candidates = [_turn(index, padding=3000) for index in range(4)]
    one_turn = build_bounded_turn_context(
        snapshot=_snapshot(),
        decision_brief=None,
        message="follow up",
        recent_turn_candidates=[candidates[-1]],
        max_context_bytes=20_000,
    )
    context = build_bounded_turn_context(
        snapshot=_snapshot(),
        decision_brief=None,
        message="follow up",
        recent_turn_candidates=candidates,
        max_context_bytes=one_turn.context_bytes + 100,
    )

    assert context.recent_turn_ids == (candidates[-1]["turn_id"],)


def test_decision_ledger_copies_provenance_without_confirming_decisions() -> None:
    turn = _turn(1)
    context = build_bounded_turn_context(
        snapshot=_snapshot(),
        decision_brief="decision",
        message="follow up",
        recent_turn_candidates=[turn],
        max_context_bytes=100_000,
    )

    assert context.decision_ledger["assumptions"][0]["source_turn_id"] == turn["turn_id"]
    assert context.decision_ledger["dissent"][0]["source_turn_id"] == turn["turn_id"]
    assert context.decision_ledger["decision_proposals"][0]["value"]["authority"] == "proposal_only"
    assert context.decision_ledger["host_confirmed_decisions"] == []


def test_context_does_not_semantically_deduplicate_repeated_text() -> None:
    first = _turn(1)
    second = _turn(2)
    second["artifact"]["assumptions"] = first["artifact"]["assumptions"]  # type: ignore[index]
    context = build_bounded_turn_context(
        snapshot=_snapshot(),
        decision_brief=None,
        message="follow up",
        recent_turn_candidates=[first, second],
        max_context_bytes=100_000,
    )

    assert len(context.decision_ledger["assumptions"]) == 2


def test_context_rejects_deleted_snapshot_and_oversized_base() -> None:
    deleted = _snapshot()
    deleted["content_available"] = False
    deleted["expert_snapshots"] = None
    with pytest.raises(ConversationError) as deleted_error:
        build_bounded_turn_context(
            snapshot=deleted,
            decision_brief=None,
            message="follow up",
            recent_turn_candidates=[],
            max_context_bytes=100_000,
        )
    assert deleted_error.value.code is ErrorCode.CONTENT_DELETED

    with pytest.raises(ConversationError) as bounded_error:
        build_bounded_turn_context(
            snapshot=_snapshot(),
            decision_brief=None,
            message="x" * 10_000,
            recent_turn_candidates=[],
            max_context_bytes=1024,
        )
    assert bounded_error.value.code is ErrorCode.CAPACITY_EXHAUSTED


def test_context_payload_and_lineage_are_explicit_derived_views() -> None:
    context = build_bounded_turn_context(
        snapshot=_snapshot(),
        decision_brief="decision",
        message="follow up",
        recent_turn_candidates=[_turn(1)],
        max_context_bytes=100_000,
    )

    payload = context.execution_payload()
    lineage = context.lineage_payload()
    assert payload["message"] == "follow up"
    assert payload["recent_turns"][0]["turn_id"] == context.recent_turn_ids[0]
    assert lineage["context_sha256"] == context.context_sha256
    assert lineage["recent_turn_ids"] == list(context.recent_turn_ids)
