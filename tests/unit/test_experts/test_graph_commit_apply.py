"""Tests for explicit graph commit apply semantics."""

from __future__ import annotations

from copy import deepcopy

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.graph_commit_apply import (
    GRAPH_COMMIT_APPLY_KIND,
    GRAPH_COMMIT_APPLY_SCHEMA_VERSION,
    apply_graph_commit_envelope,
)
from deepr.experts.metacognition import MetaCognitionTracker
from tests.unit.graph_commit_helpers import (
    graph_commit_agenda_operation,
    graph_commit_concept_operation,
    graph_commit_envelope,
    graph_commit_gap_operation,
    graph_commit_hypothesis_operation,
    graph_commit_operation,
)


def test_apply_graph_commit_envelope_writes_and_replays_idempotently(tmp_path):
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64)
    )
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["schema_version"] == GRAPH_COMMIT_APPLY_SCHEMA_VERSION
    assert result["kind"] == GRAPH_COMMIT_APPLY_KIND
    assert result["summary"]["status"] == "applied"
    assert result["summary"]["applied_write_count"] == 1
    assert result["contract"]["writes_graph"] is True
    assert store.beliefs["b1"].claim == "Release text changed the compiler behavior."

    replay_store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    replay = apply_graph_commit_envelope(envelope, replay_store, dry_run=False)

    assert replay["summary"]["status"] == "already_applied"
    assert replay["summary"]["applied_write_count"] == 0
    assert replay["summary"]["already_applied_count"] == 1
    assert len(replay_store.beliefs) == 1


def test_apply_graph_commit_envelope_dry_run_does_not_write(tmp_path):
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64)
    )
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=True)

    assert result["summary"]["status"] == "dry_run"
    assert result["summary"]["planned_write_count"] == 1
    assert result["operation_results"][0]["status"] == "would_apply"
    assert store.beliefs == {}


def test_apply_graph_commit_envelope_promotes_gap_and_replays_idempotently(tmp_path):
    topic = "Which verifier failures should become recurring expert gaps?"
    envelope = graph_commit_envelope(graph_commit_gap_operation(topic, "c" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))

    result = apply_graph_commit_envelope(envelope, store, gap_tracker=tracker, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["summary"]["applied_write_count"] == 1
    assert result["contract"]["writes_graph"] is False
    assert result["contract"]["writes_expert_state"] is True
    assert result["operation_results"][0]["gap_topic"] == topic
    assert result["operation_results"][0]["gap_created"] is True
    assert topic in tracker.knowledge_gaps

    replay_tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    replay = apply_graph_commit_envelope(envelope, store, gap_tracker=replay_tracker, dry_run=False)

    assert replay["summary"]["status"] == "already_applied"
    assert replay["summary"]["applied_write_count"] == 0
    assert replay["summary"]["already_applied_count"] == 1
    assert len(replay_tracker.knowledge_gaps) == 1


def test_apply_graph_commit_envelope_blocks_gap_without_tracker(tmp_path):
    envelope = graph_commit_envelope(graph_commit_gap_operation("Missing tracker gap.", "d" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["gap_tracker_missing"]


def test_apply_graph_commit_envelope_promotes_agenda_and_replays_idempotently(tmp_path):
    title = "Map the evidence needed for perspective-state compilation."
    envelope = graph_commit_envelope(graph_commit_agenda_operation(title, "e" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))

    result = apply_graph_commit_envelope(envelope, store, gap_tracker=tracker, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["summary"]["applied_write_count"] == 1
    assert result["contract"]["writes_graph"] is False
    assert result["contract"]["writes_expert_state"] is True
    assert result["operation_results"][0]["agenda_title"] == title
    assert result["operation_results"][0]["agenda_created"] is True
    assert title in tracker.exploration_agendas

    replay_tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    replay = apply_graph_commit_envelope(envelope, store, gap_tracker=replay_tracker, dry_run=False)

    assert replay["summary"]["status"] == "already_applied"
    assert replay["summary"]["applied_write_count"] == 0
    assert replay["summary"]["already_applied_count"] == 1
    assert len(replay_tracker.exploration_agendas) == 1


def test_apply_graph_commit_envelope_blocks_agenda_without_tracker(tmp_path):
    envelope = graph_commit_envelope(graph_commit_agenda_operation("Missing tracker agenda.", "f" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["agenda_tracker_missing"]


def test_apply_graph_commit_envelope_promotes_hypothesis_and_replays_idempotently(tmp_path):
    title = "Statistical variable traces improve expert council verification."
    envelope = graph_commit_envelope(graph_commit_hypothesis_operation(title, "1" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))

    result = apply_graph_commit_envelope(envelope, store, gap_tracker=tracker, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["summary"]["applied_write_count"] == 1
    assert result["contract"]["writes_graph"] is False
    assert result["contract"]["writes_expert_state"] is True
    assert result["operation_results"][0]["hypothesis_title"] == title
    assert result["operation_results"][0]["hypothesis_created"] is True
    assert title in tracker.hypotheses

    replay_tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    replay = apply_graph_commit_envelope(envelope, store, gap_tracker=replay_tracker, dry_run=False)

    assert replay["summary"]["status"] == "already_applied"
    assert replay["summary"]["applied_write_count"] == 0
    assert replay["summary"]["already_applied_count"] == 1
    assert len(replay_tracker.hypotheses) == 1


def test_apply_graph_commit_envelope_blocks_hypothesis_without_tracker(tmp_path):
    envelope = graph_commit_envelope(graph_commit_hypothesis_operation("Missing tracker hypothesis.", "2" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["hypothesis_tracker_missing"]


def test_apply_graph_commit_envelope_promotes_concept_and_replays_idempotently(tmp_path):
    name = "Statistical variable map for expert council plans"
    envelope = graph_commit_envelope(graph_commit_concept_operation(name, "3" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))

    result = apply_graph_commit_envelope(envelope, store, gap_tracker=tracker, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["summary"]["applied_write_count"] == 1
    assert result["contract"]["writes_graph"] is False
    assert result["contract"]["writes_expert_state"] is True
    assert result["operation_results"][0]["concept_name"] == name
    assert result["operation_results"][0]["concept_created"] is True
    assert name in tracker.concepts

    replay_tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    replay = apply_graph_commit_envelope(envelope, store, gap_tracker=replay_tracker, dry_run=False)

    assert replay["summary"]["status"] == "already_applied"
    assert replay["summary"]["applied_write_count"] == 0
    assert replay["summary"]["already_applied_count"] == 1
    assert len(replay_tracker.concepts) == 1


def test_apply_graph_commit_envelope_blocks_concept_without_tracker(tmp_path):
    envelope = graph_commit_envelope(graph_commit_concept_operation("Missing tracker concept.", "4" * 64))
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["concept_tracker_missing"]


def test_apply_graph_commit_envelope_blocks_unready_envelope(tmp_path):
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64),
        status="blocked",
    )
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert "envelope_not_ready_for_commit" in result["summary"]["failure_reasons"]
    assert store.beliefs == {}


def test_apply_graph_commit_envelope_blocks_existing_conflict(tmp_path):
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64)
    )
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    store.add_belief(
        Belief(id="b1", claim="A different claim.", confidence=0.6, evidence_refs=["source_note:note_b1:w0"]),
        check_conflicts=False,
        dedup=False,
    )

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["idempotency_conflict"]
    assert store.beliefs["b1"].claim == "A different claim."


def test_apply_graph_commit_envelope_adds_edges_after_all_beliefs(tmp_path):
    first = graph_commit_operation(
        "b1",
        "The compiler enabled the default behavior.",
        "a" * 64,
        edges=[{"src_id": "b1", "dst_id": "b2", "edge_type": "contradicts", "provenance": "test"}],
    )
    second = graph_commit_operation("b2", "The compiler disabled the default behavior.", "b" * 64)
    envelope = graph_commit_envelope(first, second)
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["operation_results"][0]["edge_count"] == 1
    assert [edge.edge_type for edge in store.edges_for("b1")] == ["contradicts"]
    assert store.beliefs["b1"].contradictions_with == ["b2"]
    assert store.beliefs["b2"].contradictions_with == ["b1"]


def test_apply_graph_commit_envelope_replays_missing_edge_from_partial_apply(tmp_path):
    first = graph_commit_operation(
        "b1",
        "The compiler enabled the default behavior.",
        "a" * 64,
        edges=[{"src_id": "b1", "dst_id": "b2", "edge_type": "contradicts", "provenance": "test"}],
    )
    second = graph_commit_operation("b2", "The compiler disabled the default behavior.", "b" * 64)
    envelope = graph_commit_envelope(first, second)
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    for operation in envelope["operations"]:
        payload = operation["belief"]
        store.add_belief(
            Belief(
                id=payload["id"],
                claim=payload["claim"],
                confidence=payload["confidence"],
                evidence_refs=payload["evidence_refs"],
                domain=payload["domain"],
                source_type=payload["source_type"],
                trust_class=payload["trust_class"],
                grounding_assurance=payload["grounding_assurance"],
            ),
            check_conflicts=False,
            dedup=False,
            change_reason=f"graph_commit_apply:{operation['idempotency_key']}",
        )

    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["summary"]["applied_write_count"] == 1
    assert result["summary"]["already_applied_count"] == 1
    assert result["operation_results"][0]["edge_count"] == 1
    assert store.beliefs["b1"].contradictions_with == ["b2"]
    assert store.beliefs["b2"].contradictions_with == ["b1"]


def test_apply_graph_commit_envelope_detects_replay_drift(tmp_path):
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64)
    )
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    apply_graph_commit_envelope(envelope, store, dry_run=False)
    drifted = deepcopy(envelope)
    drifted["operations"][0]["belief"]["confidence"] = 0.7

    result = apply_graph_commit_envelope(drifted, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["idempotency_conflict"]


def test_apply_graph_commit_envelope_blocks_malformed_replay_without_crashing(tmp_path):
    first = graph_commit_operation(
        "b1",
        "The compiler enabled the default behavior.",
        "a" * 64,
        edges=[{"src_id": "b1", "dst_id": "b2", "edge_type": "contradicts"}],
    )
    second = graph_commit_operation("b2", "The compiler disabled the default behavior.", "b" * 64)
    envelope = graph_commit_envelope(first, second)
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    apply_graph_commit_envelope(envelope, store, dry_run=False)
    malformed = deepcopy(envelope)
    del malformed["operations"][0]["idempotency_key"]

    result = apply_graph_commit_envelope(malformed, store, dry_run=False)

    assert result["summary"]["status"] == "blocked"
    assert result["operation_results"][0]["status"] == "blocked"
    assert result["operation_results"][0]["failure_reasons"] == ["invalid_idempotency_key"]
