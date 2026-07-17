"""Tests for unreviewed drafts and operator-attested blueprints."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deepr.experts.blueprint import (
    BlueprintStorageError,
    ExpertBlueprintDraft,
    ExpertBlueprintStore,
    blueprint_template,
    build_blueprint_preflight,
)
from deepr.experts.profile import ExpertProfile, ExpertStore


def _draft(
    *, mission: str = "Help the platform team make evidence-backed architecture decisions."
) -> ExpertBlueprintDraft:
    return ExpertBlueprintDraft.model_validate(
        {
            "schema_version": "deepr-expert-blueprint-draft-v1",
            "kind": "deepr.expert.blueprint_draft",
            "expert_name": "Platform Expert",
            "mission": mission,
            "non_goals": ["Approve production changes"],
            "decision_use_cases": [
                {
                    "id": "architecture-choice",
                    "question": "Which architecture best fits the stated constraints?",
                    "success_criteria": ["States tradeoffs", "Cites the governing evidence"],
                }
            ],
            "source_policy": {
                "primary_sources_required": True,
                "preferred_source_types": ["Official documentation", "Decision records"],
                "excluded_sources": ["Unsourced summaries"],
            },
            "volatility": "medium",
            "update_cadence_days": 30,
            "initial_questions": ["What decisions recur most often?"],
            "acceptance_cases": [
                {
                    "id": "held-out-architecture",
                    "question": "Recommend an architecture for a constrained migration.",
                    "success_criteria": ["Separates facts from recommendations"],
                    "failure_conditions": ["Invents a requirement"],
                }
            ],
        }
    )


def test_template_requires_operator_completion() -> None:
    with pytest.raises(ValidationError):
        ExpertBlueprintDraft.model_validate(blueprint_template("Platform Expert"))


def test_preflight_is_structural_unreviewed_and_non_authoritative() -> None:
    preflight = build_blueprint_preflight(_draft())

    assert preflight["status"] == "structurally_valid_unreviewed"
    assert preflight["contract"] == {
        "structurally_valid": True,
        "semantic_quality_assessed": False,
        "human_review_claimed": False,
        "operator_attestation_present": False,
        "authoritative_for_scope": False,
        "writes_canonical_state": False,
        "model_calls": 0,
        "provider_calls": 0,
        "network_access": False,
        "cost_usd": 0.0,
    }
    assert preflight["draft"]["schema_version"] == "deepr-expert-blueprint-draft-v1"
    assert len(preflight["review_questions"]) == 6


def test_apply_is_append_only_and_idempotent(tmp_path) -> None:
    store = ExpertBlueprintStore(tmp_path)
    first_time = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    second_time = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)

    first = store.apply(_draft(), attested_by="operator", now=first_time)
    duplicate = store.apply(_draft(), attested_by="another operator", now=second_time)
    changed = store.apply(
        _draft(mission="Support operator-accepted platform architecture choices."),
        attested_by="operator",
        now=second_time,
    )

    assert first.appended is True
    assert duplicate.appended is False
    assert duplicate.blueprint == first.blueprint
    assert changed.appended is True
    assert changed.blueprint.revision == 2
    assert changed.blueprint.created_at == first.blueprint.created_at
    assert changed.blueprint.updated_at == second_time.isoformat()
    assert changed.blueprint.contract.may_authorize_spend is False
    assert changed.blueprint.contract.human_authorship_claimed is False
    assert changed.blueprint.attestation.identity_verified is False
    assert [item.revision for item in store.load_all("Platform Expert")] == [1, 2]
    assert len(store.path_for("Platform Expert").read_text(encoding="utf-8").splitlines()) == 2


def test_load_fails_closed_when_history_is_tampered(tmp_path) -> None:
    store = ExpertBlueprintStore(tmp_path)
    store.apply(_draft(), attested_by="operator")
    path = store.path_for("Platform Expert")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["mission"] = "Tampered mission"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(BlueprintStorageError, match="content hash mismatch"):
        store.load_all("Platform Expert")


def test_duplicate_case_ids_are_rejected() -> None:
    payload = _draft().model_dump(mode="json")
    payload["acceptance_cases"].append(payload["acceptance_cases"][0])

    with pytest.raises(ValidationError, match="acceptance-case ids must be unique"):
        ExpertBlueprintDraft.model_validate(payload)


def test_invalid_expert_path_fails_with_a_domain_error(tmp_path) -> None:
    with pytest.raises(BlueprintStorageError, match="safety validation"):
        ExpertBlueprintStore(tmp_path).load_all("../../")


def test_blueprint_can_precede_profile_creation(tmp_path) -> None:
    blueprint_store = ExpertBlueprintStore(tmp_path)
    applied = blueprint_store.apply(_draft(), attested_by="operator")

    ExpertStore(base_path=str(tmp_path)).save(
        ExpertProfile(name="Platform Expert", vector_store_id="", domain="platform architecture")
    )

    assert ExpertStore(base_path=str(tmp_path), create=False).load("Platform Expert") is not None
    assert blueprint_store.load_latest("Platform Expert") == applied.blueprint


def test_display_name_whitespace_normalizes_on_reload(tmp_path) -> None:
    store = ExpertBlueprintStore(tmp_path)
    applied = store.apply(_draft(), attested_by="operator")

    assert store.load_latest("  Platform   Expert  ") == applied.blueprint
