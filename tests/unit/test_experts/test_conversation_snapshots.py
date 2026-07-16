"""Tests for frozen expert conversation snapshot compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from deepr.experts.conversation import snapshots as snapshot_module
from deepr.experts.conversation.models import ConsultationMode, ConversationError


@dataclass
class Profile:
    name: str
    domain: str
    description: str = ""


class ProfileStore:
    def __init__(self, profiles: list[Profile]) -> None:
        self.profiles = profiles

    def list_all(self) -> list[Profile]:
        return list(self.profiles)


def _handoff(profile: Profile, **_kwargs: Any) -> dict[str, Any]:
    return {
        "schema_version": "deepr-expert-handoff-v1",
        "kind": "deepr.expert.handoff",
        "generated_at": "volatile-compiler-time",
        "contract": {"read_only": True, "cost_usd": 0.0},
        "expert": {
            "name": profile.name,
            "domain": profile.domain,
            "description": profile.description,
            "updated_at": "2026-07-15T00:00:00+00:00",
        },
        "summary": {"claim_count": 1, "open_gap_count": 1},
        "manifest": {"generated_at": "2026-07-14T00:00:00+00:00"},
        "claims": [{"id": f"claim-{profile.name}", "statement": "Retries require idempotency."}],
        "gaps": [{"id": "gap-1", "topic": "Crash recovery"}],
        "perspective_state": {"counts": {"original_ideas": 0}},
        "loop_status": {"count": 0},
    }


def test_snapshot_packet_is_bounded_and_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "build_expert_handoff", _handoff)
    profile = Profile("Reliability", "distributed systems")

    first = snapshot_module.compile_expert_snapshot(profile)
    second = snapshot_module.compile_expert_snapshot(profile)

    assert first.state_sha256 == second.state_sha256
    assert first.packet_sha256 == second.packet_sha256
    assert "generated_at" not in first.packet
    assert first.source_position == "manifest:2026-07-14T00:00:00+00:00"
    assert set(first.packet) == {
        "schema_version",
        "kind",
        "contract",
        "expert",
        "summary",
        "manifest",
        "claims",
        "gaps",
        "perspective_state",
        "loop_status",
    }


def test_auto_routing_only_selects_relevant_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "build_expert_handoff", _handoff)
    store = ProfileStore(
        [
            Profile("Database Reliability", "database reliability recovery"),
            Profile("Visual Design", "typography and layout"),
        ]
    )

    snapshots = snapshot_module.compile_conversation_snapshots(
        store,
        message="How should database recovery be validated?",
        requested_experts=None,
        max_experts=2,
        mode=ConsultationMode.COUNCIL,
    )

    assert [snapshot.expert_name for snapshot in snapshots] == ["Database Reliability"]


def test_focused_mode_rejects_multiple_explicit_experts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "build_expert_handoff", _handoff)
    store = ProfileStore([Profile("Alpha", "alpha"), Profile("Beta", "beta")])

    with pytest.raises(ConversationError, match="exactly one"):
        snapshot_module.compile_conversation_snapshots(
            store,
            message="question",
            requested_experts=["Alpha", "Beta"],
            max_experts=2,
            mode=ConsultationMode.FOCUSED,
        )


def test_aliases_for_same_profile_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "build_expert_handoff", _handoff)
    store = ProfileStore([Profile("Reliability Expert", "reliability")])

    with pytest.raises(ConversationError, match="Duplicate expert roster"):
        snapshot_module.compile_conversation_snapshots(
            store,
            message="question",
            requested_experts=["Reliability Expert", "reliability_expert"],
            max_experts=2,
            mode=ConsultationMode.COUNCIL,
        )


def test_unavailable_explicit_expert_returns_safe_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "build_expert_handoff", _handoff)

    with pytest.raises(ConversationError, match="unavailable"):
        snapshot_module.compile_conversation_snapshots(
            ProfileStore([Profile("Alpha", "alpha")]),
            message="question",
            requested_experts=["Missing"],
            max_experts=1,
            mode=ConsultationMode.FOCUSED,
        )
