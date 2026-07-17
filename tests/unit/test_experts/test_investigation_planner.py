from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deepr.experts.conversation.models import ExpertSnapshotInput
from deepr.experts.investigation.models import (
    InvestigationContractError,
    LearningMode,
    ProtocolMode,
    maximum_generation_calls,
    sha256_json,
    validate_plan,
)
from deepr.experts.investigation.planner import build_investigation_plan

NOW = "2026-07-17T00:00:00+00:00"


class FakeStore:
    def __init__(self, profiles: list[Any]) -> None:
        self.profiles = profiles

    def list_all(self) -> list[Any]:
        return list(self.profiles)


class FakeBlueprints:
    def __init__(self, present: set[str] | None = None) -> None:
        self.present = present or set()

    def load_latest(self, expert_name: str) -> object | None:
        return object() if expert_name in self.present else None


def _profile(name: str, *, model: str = "qwen:32b", provider: str = "local") -> Any:
    return SimpleNamespace(name=name, domain=f"{name} domain", description="", model=model, provider=provider)


def _snapshot(profile: Any) -> ExpertSnapshotInput:
    packet = {
        "expert": {
            "name": profile.name,
            "knowledge_cutoff": "2026-07-01T00:00:00+00:00",
            "last_knowledge_refresh": "2026-07-02T00:00:00+00:00",
            "domain_velocity": "fast",
        },
        "summary": {
            "claim_count": 7,
            "verified_claim_count": 4,
            "open_gap_count": 2,
            "contested_open_count": 1,
        },
    }
    digest = sha256_json(packet)
    return ExpertSnapshotInput(
        expert_name=profile.name,
        state_sha256=digest,
        source_position=f"profile:{profile.name}:test",
        packet=packet,
    )


@pytest.fixture
def snapshot_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deepr.experts.investigation.planner.compile_expert_snapshot", _snapshot)


@pytest.mark.parametrize(
    ("protocol", "learning", "expected"),
    [
        (ProtocolMode.INDEPENDENT, LearningMode.OFF, 8),
        (ProtocolMode.DISCUSS, LearningMode.OFF, 11),
        (ProtocolMode.DEEP, LearningMode.OFF, 14),
        (ProtocolMode.DEEP, LearningMode.STAGE, 20),
    ],
)
def test_three_expert_call_formula(protocol: ProtocolMode, learning: LearningMode, expected: int) -> None:
    assert maximum_generation_calls(3, protocol, learning) == expected


def test_plan_is_zero_call_complete_and_hash_bound(tmp_path: Path, snapshot_compiler: None) -> None:
    profiles = [_profile("TKG"), _profile("Consciousness"), _profile("MCP")]
    plan = build_investigation_plan(
        question="How should Deepr connect these domains?",
        expert_names=["TKG", "Consciousness", "MCP"],
        input_root=tmp_path,
        inline_texts=["Prefer reversible designs."],
        urls=["https://example.com/spec"],
        protocol="deep",
        learning="stage",
        profile_store=FakeStore(profiles),
        blueprint_reader=FakeBlueprints({"TKG"}),
        run_id="inv_test",
        created_at=NOW,
    )

    assert validate_plan(plan) is plan
    assert plan["run_id"] == "inv_test"
    assert plan["capacity"] == {
        "class": "local",
        "source": "local_owned",
        "provider": "ollama",
        "model": "qwen:32b",
        "review_model": "qwen:32b",
        "context_window_tokens": 32768,
        "review_context_window_tokens": 32768,
        "fallback": "none",
        "runtime_probe": "not_performed_by_zero_network_preview",
        "recorded_run_cost_usd": 0.0,
    }
    assert plan["bounds"]["max_generation_calls"] == 20
    assert plan["bounds"]["max_search_queries"] == 12
    assert plan["bounds"]["max_page_fetches"] == 24
    assert plan["preview_activity"] == {
        "model_calls": 0,
        "network_requests": 0,
        "provider_process_starts": 0,
        "expert_state_writes": 0,
        "cost_usd": 0.0,
    }
    assert plan["learning_contract"]["human_reviewed"] is False
    assert plan["learning_contract"]["source_pack_evidence_only"] is True
    assert plan["learning_contract"]["dialogue_is_evidence"] is False
    assert plan["learning_contract"]["domain_relevance_required"] is True
    assert plan["learning_contract"]["domain_relevance_judgment"] == "independent_verifier_model"
    assert plan["experts"][0]["readiness"]["blueprint_status"] == "present"
    assert plan["experts"][1]["readiness"]["blueprint_status"] == "absent"
    assert plan["data_egress"][1]["file_or_snapshot_content_sent"] is False


def test_plan_requires_explicit_model_for_mixed_roster(tmp_path: Path, snapshot_compiler: None) -> None:
    profiles = [_profile("TKG", model="qwen:32b"), _profile("MCP", model="other:27b")]

    with pytest.raises(InvestigationContractError, match="different local models"):
        build_investigation_plan(
            question="Question",
            expert_names=["TKG", "MCP"],
            input_root=tmp_path,
            profile_store=FakeStore(profiles),
            blueprint_reader=FakeBlueprints(),
            created_at=NOW,
        )

    plan = build_investigation_plan(
        question="Question",
        expert_names=["TKG", "MCP"],
        input_root=tmp_path,
        local_model="chosen:latest",
        profile_store=FakeStore(profiles),
        blueprint_reader=FakeBlueprints(),
        created_at=NOW,
    )
    assert plan["capacity"]["model"] == "chosen:latest"


def test_plan_pins_optional_review_model(tmp_path: Path, snapshot_compiler: None) -> None:
    plan = build_investigation_plan(
        question="Question",
        expert_names=["TKG"],
        input_root=tmp_path,
        local_model="fast:14b",
        review_model="strong:32b",
        context_window_tokens=24_576,
        review_context_window_tokens=16_384,
        profile_store=FakeStore([_profile("TKG")]),
        blueprint_reader=FakeBlueprints(),
        created_at=NOW,
    )

    assert plan["capacity"]["model"] == "fast:14b"
    assert plan["capacity"]["review_model"] == "strong:32b"
    assert plan["capacity"]["context_window_tokens"] == 24_576
    assert plan["capacity"]["review_context_window_tokens"] == 16_384
    assert plan["bounds"]["max_prompt_bytes_per_call"] == (16_384 - 4_096) * 4


def test_plan_rejects_missing_profile(tmp_path: Path) -> None:
    with pytest.raises(InvestigationContractError, match="not found"):
        build_investigation_plan(
            question="Question",
            expert_names=["Missing"],
            input_root=tmp_path,
            local_model="qwen:32b",
            profile_store=FakeStore([]),
            blueprint_reader=FakeBlueprints(),
            created_at=NOW,
        )


def test_plan_rejects_snapshot_and_plan_tampering(tmp_path: Path, snapshot_compiler: None) -> None:
    plan = build_investigation_plan(
        question="Question",
        expert_names=["TKG"],
        input_root=tmp_path,
        profile_store=FakeStore([_profile("TKG")]),
        blueprint_reader=FakeBlueprints(),
        created_at=NOW,
    )
    snapshot_tampered = copy.deepcopy(plan)
    snapshot_tampered["experts"][0]["snapshot"]["summary"]["claim_count"] = 99
    snapshot_material = {key: value for key, value in snapshot_tampered.items() if key != "plan_sha256"}
    snapshot_tampered["plan_sha256"] = sha256_json(snapshot_material)
    with pytest.raises(InvestigationContractError, match="snapshot hash"):
        validate_plan(snapshot_tampered)

    plan_tampered = copy.deepcopy(plan)
    plan_tampered["question"] = "Changed"
    with pytest.raises(InvestigationContractError, match="plan hash"):
        validate_plan(plan_tampered)

    review_label_tampered = copy.deepcopy(plan)
    review_label_tampered["learning_contract"]["human_reviewed"] = True
    review_material = {key: value for key, value in review_label_tampered.items() if key != "plan_sha256"}
    review_label_tampered["plan_sha256"] = sha256_json(review_material)
    with pytest.raises(InvestigationContractError, match="human_reviewed"):
        validate_plan(review_label_tampered)


def test_plan_rejects_retrieval_bounds_that_escape_parent_envelope(
    tmp_path: Path,
    snapshot_compiler: None,
) -> None:
    plan = build_investigation_plan(
        question="Question",
        expert_names=["TKG"],
        input_root=tmp_path,
        profile_store=FakeStore([_profile("TKG")]),
        blueprint_reader=FakeBlueprints(),
        created_at=NOW,
    )
    plan["retrieval"]["max_pages_per_expert"] = 9
    material = {key: value for key, value in plan.items() if key != "plan_sha256"}
    plan["plan_sha256"] = sha256_json(material)

    with pytest.raises(InvestigationContractError, match="retrieval page bounds"):
        validate_plan(plan)
