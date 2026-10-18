"""Decision packets preserve advice and observations without inventing revisions."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.experts.consult_traces import build_consult_trace
from deepr.experts.decision_review import build_decision_review, render_decision_review, review_trace_ids
from deepr.experts.outcomes import ExpertOutcomeDraft, ExpertOutcomeStore


@pytest.fixture
def outcomes(tmp_path):
    store = ExpertOutcomeStore(tmp_path / "experts")
    for identity, supersedes, observation in (
        ("first", None, "Cutover failed its recovery target."),
        ("corrected", "first", "Corrected measurement: recovery took 20 minutes."),
    ):
        store.record(
            ExpertOutcomeDraft(
                expert_name="Platform Expert",
                decision_id="migration",
                decision_summary="Select an architecture",
                result="mixed",
                observation=observation,
                observed_at="2026-10-01T00:00:00Z",
                attested_by="maintainer",
                consult_trace_id="original",
                supersedes_outcome_id=supersedes,
            ),
            outcome_id=identity,
        )
    return store.load_all("Platform Expert")


def trace(identity="original", *, expert="Platform Expert", question="How should we migrate?", sha="old"):
    return build_consult_trace(
        trace_id=identity,
        recorded_at=datetime(2026, 9, 1, tzinfo=UTC),
        question=question,
        requested_experts=[expert],
        max_experts=1,
        budget=0,
        capacity={"model": "pinned-local", "provider": "local"},
        payload={
            "experts_consulted": [expert],
            "answer": "Use phased cutover. ``` Preserve rollback.",
            "synthesis_status": "completed",
            "synthesis_stop_reason": "stop",
            "context_delivery": {"user_prompt": f"Question: {question}; source {sha}; [omitted block]"},
            "perspectives": [
                {"expert": expert, "context": {"passages": [{"sha256": sha, "origin": "retained", "text": "bytes"}]}}
            ],
        },
    )


def review(outcomes, traces, **kwargs):
    return build_decision_review("Platform Expert", outcomes=outcomes, traces=traces, outcome_id="first", **kwargs)


def test_correction_preserves_original_advice_context_and_observations(outcomes):
    original = trace()
    before = copy.deepcopy(original)
    packet = review(outcomes, [original])
    cases = packet["cases"]
    assert [item["outcome"]["outcome_id"] for item in cases] == ["first", "corrected"]
    assert cases[0]["superseded_by"] == ["corrected"]
    assert cases[1]["outcome"]["supersedes_outcome_id"] == "first"
    assert cases[0]["consultation"]["record"] == original == before
    assert packet["review"]["status"] == "unreviewed"
    assert packet["contract"]["model_calls"] == 0
    assert packet["contract"]["writes_state"] is False
    packet["cases"][0]["consultation"]["record"]["output"]["answer"] = "changed view"
    assert original == before


def test_unrelated_comparison_only_reports_recorded_input_changes(outcomes):
    packet = review(
        outcomes,
        [trace(), trace("other", question="Which database for another region?", sha="new")],
        compare_trace_id="other",
    )
    delta = packet["input_changes"][0]
    assert delta["same_decision_inferred"] is False
    assert delta["advice_supersession_inferred"] is False
    assert delta["recorded_source_identities"]["added"] == [{"origin": "retained", "sha256": "new"}]
    assert delta["recorded_source_identities"]["removed"] == [{"origin": "retained", "sha256": "old"}]
    assert delta["delivery_receipt_changed"] is True
    assert packet["comparison"]["link"]["question"] == "Which database for another region?"
    assert len(packet["cases"]) == 2


@pytest.mark.parametrize(
    ("traces", "status"),
    [
        ([], "missing"),
        ([trace(), trace()], "ambiguous_duplicate"),
        ([trace(expert="Another Expert")], "expert_mismatch"),
        ([{"trace_id": "original", "output": {"answer": "private"}}], "roster_unknown"),
    ],
)
def test_unresolved_join_never_exposes_an_answer(outcomes, traces, status):
    snapshot = review(outcomes, traces)["cases"][0]["consultation"]
    assert snapshot["link"]["status"] == status
    assert snapshot["record"] is None
    assert snapshot["record_sha256"] is None


def test_failed_truncated_and_legacy_context_are_explicit(outcomes):
    failed = trace()
    failed["status"] = "failed"
    failed["failure"] = {"error_type": "OutputLimit"}
    failed["output"].update(synthesis_status="truncated", synthesis_stop_reason="length")
    failed["output"].pop("context_delivery")
    failed.pop("context_packet")
    packet = review(outcomes, [failed], compare_trace_id="original")
    snapshot = packet["cases"][0]["consultation"]
    assert "delivered prompt receipt" in snapshot["unavailable"]
    assert "selected source context" in snapshot["unavailable"]
    assert packet["input_changes"][0]["recorded_source_identities"]["status"] == "unavailable"
    assert packet["input_changes"][0]["delivery_receipt_changed"] is None
    rendered = render_decision_review(packet)
    assert "trace status: failed" in rendered and "Answer status: truncated" in rendered
    assert '"error_type": "OutputLimit"' in rendered


def test_markdown_retains_exact_json_packet_despite_embedded_fences(outcomes):
    packet = review(outcomes, [trace()])
    rendered = render_decision_review(packet)
    receipt = rendered.split("## Complete frozen packet receipt\n\n", 1)[1]
    first_line, rest = receipt.split("\n", 1)
    fence = first_line.removesuffix("json")
    encoded, ending = rest.rsplit("\n" + fence, 1)
    assert ending.strip() == ""
    assert json.loads(encoded) == packet
    assert "[omitted block]" in rendered
    assert "Original answer:" in rendered


@pytest.mark.parametrize(
    "selection",
    [{}, {"decision_id": "missing"}, {"outcome_id": "missing"}, {"decision_id": "migration", "outcome_id": "first"}],
)
def test_selection_refuses_missing_or_ambiguous_identity(outcomes, selection):
    with pytest.raises(ValueError):
        build_decision_review("Platform Expert", outcomes=outcomes, traces=[], **selection)


def test_decision_selection_matches_outcome_snapshot(outcomes):
    records = [trace()]
    first = review(outcomes, records)
    second = build_decision_review("Platform Expert", outcomes=outcomes, traces=records, decision_id="migration")
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert first["cases"] == second["cases"]


def test_wrong_expert_and_duplicate_outcomes_refused(outcomes):
    with pytest.raises(ValueError, match="expert"):
        build_decision_review("Wrong", outcomes=outcomes, traces=[], outcome_id="first")
    with pytest.raises(ValueError, match="Duplicate outcome"):
        review([*outcomes, outcomes[0]], [])


def test_trace_budget_refuses_omitting_history(outcomes):
    large = [outcomes[0].model_copy(update={"consult_trace_id": f"trace-{i}"}) for i in range(101)]
    with pytest.raises(ValueError, match="100"):
        review_trace_ids(large)


def test_missing_comparison_and_unlinked_outcome_are_explicit(outcomes):
    unlinked = [item.model_copy(update={"consult_trace_id": None}) for item in outcomes]
    packet = review(unlinked, [], compare_trace_id="absent")
    assert packet["cases"][0]["consultation"]["link"]["status"] == "not_linked"
    assert packet["comparison"]["link"]["status"] == "missing"
    assert packet["input_changes"][0]["status"] == "unavailable"


@pytest.mark.parametrize("records", [[trace()], []])
def test_published_packet_schema_and_no_quality_authority(outcomes, records):
    from jsonschema import Draft202012Validator, FormatChecker, ValidationError
    from referencing import Registry, Resource

    root = Path(__file__).resolve().parents[3] / "docs/schemas"
    schema = json.loads((root / "decision-review-v1.json").read_text())
    outcome_schema = json.loads((root / "expert-outcome-v1.json").read_text())
    registry = Registry().with_resource(outcome_schema["$id"], Resource.from_contents(outcome_schema))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    packet = review(outcomes, records, compare_trace_id="original")
    validator.validate(packet)
    packet["contract"]["semantic_quality_verdict"] = True
    with pytest.raises(ValidationError):
        validator.validate(packet)
