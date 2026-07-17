"""Published contract tests for expert purpose and outcome records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.experts.blueprint import ExpertBlueprintDraft, ExpertBlueprintStore, build_blueprint_preflight
from deepr.experts.outcomes import ExpertOutcomeDraft, ExpertOutcomeStore, build_outcome_summary

jsonschema = pytest.importorskip("jsonschema")
Draft202012Validator = jsonschema.Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"


def _schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _blueprint_draft() -> ExpertBlueprintDraft:
    return ExpertBlueprintDraft.model_validate(
        {
            "schema_version": "deepr-expert-blueprint-draft-v1",
            "kind": "deepr.expert.blueprint_draft",
            "expert_name": "Contract Expert",
            "mission": "Support reviewed contract decisions.",
            "non_goals": ["Authorize changes"],
            "decision_use_cases": [
                {
                    "id": "contract-choice",
                    "question": "Which contract should be selected?",
                    "success_criteria": ["Cites governing evidence"],
                }
            ],
            "source_policy": {
                "primary_sources_required": True,
                "preferred_source_types": ["Executed agreements"],
                "excluded_sources": [],
            },
            "volatility": "slow",
            "update_cadence_days": 90,
            "initial_questions": ["Which terms govern the decision?"],
            "acceptance_cases": [
                {
                    "id": "held-out-contract",
                    "question": "Compare two contract options.",
                    "success_criteria": ["Separates evidence from recommendation"],
                    "failure_conditions": [],
                }
            ],
        }
    )


def test_blueprint_record_validates_against_published_schema(tmp_path) -> None:
    record = (
        ExpertBlueprintStore(tmp_path)
        .apply(
            _blueprint_draft(),
            attested_by="operator",
            now=datetime(2026, 7, 16, tzinfo=UTC),
        )
        .blueprint
    )
    schema = _schema("expert-blueprint-v1.json")

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(record.model_dump(mode="json"))


def test_blueprint_draft_and_preflight_validate_against_published_schemas() -> None:
    draft = _blueprint_draft()
    draft_schema = _schema("expert-blueprint-draft-v1.json")
    preflight_schema = _schema("expert-blueprint-preflight-v1.json")

    Draft202012Validator.check_schema(draft_schema)
    Draft202012Validator(draft_schema).validate(draft.model_dump(mode="json"))
    Draft202012Validator.check_schema(preflight_schema)
    Draft202012Validator(preflight_schema).validate(build_blueprint_preflight(draft))


def test_outcome_and_summary_validate_against_published_schemas(tmp_path) -> None:
    draft = ExpertOutcomeDraft(
        expert_name="Contract Expert",
        decision_id="contract-2026",
        decision_summary="Select the governing contract",
        result="succeeded",
        observation="The selected contract produced the reviewed result.",
        observed_at="2026-07-15T12:00:00+00:00",
        attested_by="operator",
        consult_trace_id="trace:contract",
        belief_ids=["belief-1"],
        source_refs=["agreement-7"],
        evidence_refs=["outcome-review-7"],
    )
    store = ExpertOutcomeStore(tmp_path)
    outcome = store.record(
        draft,
        outcome_id="outcome-contract-1",
        now=datetime(2026, 7, 16, tzinfo=UTC),
    ).outcome
    outcome_schema = _schema("expert-outcome-v1.json")
    summary_schema = _schema("expert-outcome-summary-v1.json")
    summary_schema["properties"]["recent_outcomes"]["items"] = outcome_schema
    summary = build_outcome_summary("Contract Expert", [outcome])

    Draft202012Validator.check_schema(outcome_schema)
    Draft202012Validator(outcome_schema).validate(outcome.model_dump(mode="json"))
    Draft202012Validator.check_schema(summary_schema)
    Draft202012Validator(summary_schema).validate(summary)
