"""Tests for deterministic source-pack compiler artifacts."""

from __future__ import annotations

from unittest.mock import patch

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.graph_commit_apply import apply_graph_commit_envelope
from deepr.experts.graph_commit_envelope import (
    GRAPH_COMMIT_ENVELOPE_KIND,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
    build_graph_commit_envelope,
)
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.semantic_recall import RecallCandidate
from deepr.experts.source_pack_compiler import (
    CLAIM_VERIFICATION_KIND,
    CLAIM_VERIFICATION_SCHEMA_VERSION,
    SEMANTIC_CLAIM_EXTRACTION_KIND,
    SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION,
    SOURCE_NOTE_KIND,
    SOURCE_NOTE_SCHEMA_VERSION,
    SOURCE_PACK_MANIFEST_KIND,
    SOURCE_PACK_MANIFEST_SCHEMA_VERSION,
    build_claim_verification,
    build_semantic_claim_extraction,
    build_source_notes,
    build_source_pack_manifest,
)


def _source_pack_payload():
    return {
        "schema_version": "deepr.sync_source_pack.v1",
        "topic": "compiler topic",
        "query": "What changed?",
        "started_at": "2026-06-27T12:00:00+00:00",
        "source_pack": {
            "schema_version": "deepr.source_pack.v1",
            "mode": "fresh",
            "source_count": 1,
            "retrieved_source_count": 1,
            "search_queries": ["compiler topic"],
            "sources": [
                {
                    "label": "S1",
                    "title": "Release notes",
                    "url": "https://example.com/release",
                    "source": "duckduckgo+builtin",
                    "fetched": True,
                    "excerpt": "Release text",
                    "content_hash": "a" * 64,
                }
            ],
        },
    }


def test_source_pack_manifest_records_hashes_without_semantic_judgment():
    payload = _source_pack_payload()

    manifest = build_source_pack_manifest(payload, source_pack_artifact="sync_artifacts/source_packs/pack.json")

    assert manifest["schema_version"] == SOURCE_PACK_MANIFEST_SCHEMA_VERSION
    assert manifest["kind"] == SOURCE_PACK_MANIFEST_KIND
    assert manifest["contract"]["semantic_judgment"] is False
    assert manifest["contract"]["model_calls"] is False
    assert manifest["manifest"]["ready_for_semantic_compile"] is True
    assert manifest["manifest"]["valid_content_hash_count"] == 1
    assert manifest["manifest"]["invalid_content_hash_count"] == 0
    assert manifest["manifest"]["missing_content_hash_count"] == 0
    assert manifest["sources"][0]["content_hash"] == "a" * 64
    assert manifest["sources"][0]["content_hash_valid"] is True
    assert manifest["sources"][0]["excerpt_hash"]
    assert manifest["compiler"]["next_stage_requires_model_judgment"] is True


def test_source_notes_compile_stable_structural_cards_without_semantic_judgment():
    payload = _source_pack_payload()

    first = build_source_notes(
        payload,
        source_pack_artifact="sync_artifacts/source_packs/pack.json",
        source_pack_manifest_artifact="sync_artifacts/source_pack_manifests/pack.json",
    )
    second = build_source_notes(
        payload,
        source_pack_artifact="sync_artifacts/source_packs/pack.json",
        source_pack_manifest_artifact="sync_artifacts/source_pack_manifests/pack.json",
    )

    assert first == second
    assert first["schema_version"] == SOURCE_NOTE_SCHEMA_VERSION
    assert first["kind"] == SOURCE_NOTE_KIND
    assert first["contract"]["cost_usd"] == 0.0
    assert first["contract"]["semantic_judgment"] is False
    assert first["contract"]["model_calls"] is False
    assert first["summary"]["ready_for_claim_extraction"] is True
    assert first["summary"]["ready_note_count"] == 1
    note = first["notes"][0]
    assert note["note_id"].startswith("sn_")
    assert note["note_hash"]
    assert note["source_pointer"] == "/source_pack/sources/0"
    assert note["artifact_refs"]["source_pack"] == "sync_artifacts/source_packs/pack.json"
    assert note["artifact_refs"]["source_pack_manifest"] == "sync_artifacts/source_pack_manifests/pack.json"
    assert note["windows"][0]["char_start"] == 0
    assert note["windows"][0]["char_end"] == len("Release text")
    assert note["windows"][0]["source_text_ref"] == "excerpt"
    assert note["readiness"]["failure_reasons"] == []
    assert first["compiler"]["next_stage_requires_model_judgment"] is True


def test_source_notes_fail_closed_for_bad_sources():
    payload = {
        "started_at": "2026-06-27T12:00:00+00:00",
        "source_pack": {
            "schema_version": "deepr.source_pack.v1",
            "sources": [
                {
                    "label": "S1",
                    "content_hash": "not-a-sha256",
                    "excerpt": "",
                }
            ],
        },
    }

    notes = build_source_notes(payload)

    assert notes["summary"]["ready_for_claim_extraction"] is False
    assert notes["summary"]["ready_note_count"] == 0
    assert notes["summary"]["blocked_note_count"] == 1
    assert notes["summary"]["failure_reasons"] == ["invalid_or_missing_content_hash", "missing_excerpt"]
    note = notes["notes"][0]
    assert note["windows"] == []
    assert note["readiness"]["ready_for_claim_extraction"] is False
    assert note["readiness"]["has_excerpt"] is False
    assert note["readiness"]["has_valid_content_hash"] is False


def test_semantic_claim_extraction_records_prompt_and_verifier_gates():
    notes = build_source_notes(
        _source_pack_payload(),
        source_pack_artifact="sync_artifacts/source_packs/pack.json",
        source_pack_manifest_artifact="sync_artifacts/source_pack_manifests/pack.json",
    )
    note = notes["notes"][0]
    window = note["windows"][0]
    output = {
        "claims": [
            {
                "statement": "Release text changed the compiler behavior.",
                "claim_kind": "factual_claim",
                "confidence": 1.5,
                "atomicity": "atomic",
                "temporal_scope": "current",
                "support_summary": "The cited source window states the release text.",
                "source_refs": [
                    {
                        "note_id": note["note_id"],
                        "window_id": window["window_id"],
                        "quote": "Release text",
                    }
                ],
            }
        ]
    }

    extraction = build_semantic_claim_extraction(
        notes,
        output,
        source_note_artifact="sync_artifacts/source_notes/pack.json",
        provider="local",
        model="qwen",
        capacity_source="local-ollama",
        cost_usd=0.0,
        prompt_text="Extract claims from source notes.",
        generated_at="2026-06-27T12:01:00+00:00",
    )

    assert extraction["schema_version"] == SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION
    assert extraction["kind"] == SEMANTIC_CLAIM_EXTRACTION_KIND
    assert extraction["contract"]["semantic_judgment"] is True
    assert extraction["contract"]["model_calls"] is True
    assert extraction["contract"]["writes_graph"] is False
    assert extraction["summary"]["status"] == "ready_for_verification"
    assert extraction["summary"]["ready_for_verification_count"] == 1
    assert extraction["prompt"]["prompt_hash"]
    assert extraction["prompt"]["response_schema_version"] == SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION
    candidate = extraction["candidates"][0]
    assert candidate["candidate_id"].startswith("cc_")
    assert candidate["confidence"] == 1.0
    assert candidate["state_policy"]["requires_external_support"] is True
    assert candidate["readiness"]["ready_for_verification"] is True
    assert candidate["readiness"]["failure_reasons"] == []
    assert candidate["evidence_refs"][0]["valid_ref"] is True
    assert candidate["evidence_refs"][0]["source_pointer"] == note["source_pointer"]
    assert "quote" not in candidate["evidence_refs"][0]
    assert candidate["evidence_refs"][0]["quote_hash"]
    assert candidate["evidence_refs"][0]["quote_chars"] == len("Release text")
    assert candidate["verifier_gate"]["status"] == "pending"
    assert candidate["verifier_gate"]["writes_graph"] is False


def test_semantic_claim_extraction_blocks_invalid_source_refs():
    notes = build_source_notes(_source_pack_payload())
    output = {
        "claims": [
            {
                "statement": "A claim with a bad source reference.",
                "confidence": 0.8,
                "source_refs": [{"note_id": "sn_missing", "window_id": "sn_missing:w0"}],
            }
        ]
    }

    extraction = build_semantic_claim_extraction(notes, output)

    assert extraction["summary"]["status"] == "blocked"
    assert extraction["summary"]["ready_for_verification_count"] == 0
    assert extraction["summary"]["invalid_source_ref_count"] == 1
    assert extraction["summary"]["failure_reasons"] == ["no_valid_source_refs", "unknown_note_ref"]
    candidate = extraction["candidates"][0]
    assert candidate["readiness"]["ready_for_verification"] is False
    assert candidate["evidence_refs"][0]["valid_ref"] is False


def test_semantic_claim_extraction_blocks_malformed_model_output():
    notes = build_source_notes(_source_pack_payload())

    extraction = build_semantic_claim_extraction(notes, '{"claims": [')

    assert extraction["summary"]["status"] == "blocked"
    assert extraction["summary"]["parsed_candidate_count"] == 0
    assert extraction["summary"]["failure_reasons"] == ["invalid_json_response"]
    assert extraction["model"]["response_failure"] == "invalid_json_response"
    assert extraction["model"]["raw_response_hash"]
    assert extraction["candidates"] == []


def test_source_pack_manifest_rejects_invalid_hash_shape_for_semantic_compile():
    manifest = build_source_pack_manifest(
        {
            "source_pack": {
                "sources": [
                    {
                        "label": "S1",
                        "content_hash": "not-a-sha256",
                        "excerpt": "Release text",
                    }
                ],
                "search_queries": "not-a-list",
            },
        }
    )

    assert manifest["manifest"]["ready_for_semantic_compile"] is False
    assert manifest["manifest"]["valid_content_hash_count"] == 0
    assert manifest["manifest"]["invalid_content_hash_count"] == 1
    assert manifest["manifest"]["missing_content_hash_count"] == 0
    assert manifest["sources"][0]["content_hash_valid"] is False
    assert manifest["source_pack"]["search_queries"] == []


def test_claim_verification_allows_supported_factual_claim_for_commit_envelope():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Release text changed the compiler behavior.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.9,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    candidate_id = extraction["candidates"][0]["candidate_id"]

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate_id,
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                    "confidence": 0.88,
                    "rationale": "The cited source window supports the claim.",
                }
            ]
        },
        provider="local",
        model="qwen",
        capacity_source="local",
        cost_usd=0.0,
    )

    assert verification["schema_version"] == CLAIM_VERIFICATION_SCHEMA_VERSION
    assert verification["kind"] == CLAIM_VERIFICATION_KIND
    assert verification["contract"]["writes_graph"] is False
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    decision = verification["decisions"][0]
    assert decision["verdicts"]["support"] == "supported"
    assert decision["readiness"]["ready_for_commit_envelope"] is True
    assert decision["commit_gate"]["writes_graph"] is False


def test_claim_verification_blocks_refuted_factual_claim():
    notes = build_source_notes(_source_pack_payload())
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "The release removed the compiler.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.8,
                    "source_refs": [
                        {
                            "note_id": notes["notes"][0]["note_id"],
                            "window_id": notes["notes"][0]["windows"][0]["window_id"],
                        }
                    ],
                }
            ]
        },
    )
    candidate_id = extraction["candidates"][0]["candidate_id"]

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate_id,
                    "support_verdict": "refuted",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["summary"]["failure_reasons"] == ["factual_support_not_verified"]
    assert verification["decisions"][0]["readiness"]["ready_for_commit_envelope"] is False


def test_claim_verification_treats_hypotheses_as_non_fact_state():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "The compiler may need a new cache invalidation strategy.",
                    "claim_kind": "hypothesis",
                    "confidence": 0.62,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    candidate = extraction["candidates"][0]

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "Synthesis over the source-note window.",
                    "rationale": "The cited release text suggests a plausible future design pressure.",
                    "uncertainty": "Speculative until follow-up evidence appears.",
                    "expected_observations": ["Future notes show repeated cache-invalidation incidents."],
                    "disconfirming_signals": ["No cache-invalidation incidents appear in future notes."],
                }
            ]
        },
    )

    assert candidate["state_policy"]["requires_external_support"] is False
    assert candidate["state_policy"]["requires_expected_observations"] is True
    assert candidate["state_policy"]["must_not_present_as_verified_fact"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    decision = verification["decisions"][0]
    assert decision["state_policy"]["requires_origin_and_rationale"] is True
    assert decision["readiness"]["ready_for_commit_envelope"] is True
    assert decision["verdicts"]["support"] == "not_applicable"


def test_claim_verification_blocks_hypothesis_without_origin_metadata():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "The compiler may need a new cache invalidation strategy.",
                    "claim_kind": "hypothesis",
                    "confidence": 0.62,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "rationale": "Maybe useful.",
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["summary"]["failure_reasons"] == [
        "missing_disconfirming_signals",
        "missing_expected_observations",
        "missing_origin",
        "missing_uncertainty",
    ]


def test_claim_verification_blocks_unknown_candidate_ids():
    notes = build_source_notes(_source_pack_payload())
    extraction = build_semantic_claim_extraction(notes, {"claims": []})

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": "cc_missing",
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["summary"]["failure_reasons"] == ["unknown_candidate_id"]


def test_claim_verification_records_edge_decisions_without_writing_graph():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "The compiler writes stable source notes.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.9,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                },
                {
                    "statement": "Stable source notes support replayable verification.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.88,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                },
            ]
        },
    )
    source_candidate = extraction["candidates"][0]["candidate_id"]
    target_candidate = extraction["candidates"][1]["candidate_id"]

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": source_candidate,
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                    "edge_decisions": [
                        {
                            "target_candidate_id": target_candidate,
                            "edge_type": "supports",
                            "confidence": 0.81,
                            "rationale": "The first claim is required for the second claim's replay guarantee.",
                            "temporal": {
                                "valid_from": "2026-06-01",
                                "valid_until": "2026-06-30",
                                "observed_at": "2026-06-29T00:00:00+00:00",
                                "temporal_scope": "June 2026",
                            },
                        },
                        {
                            "target_candidate_id": "cc_missing",
                            "edge_type": "supports",
                        },
                        {
                            "target_candidate_id": target_candidate,
                            "edge_type": "derived_from",
                            "temporal": {"valid_from": "not a date"},
                        },
                    ],
                },
                {
                    "candidate_id": target_candidate,
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                },
            ]
        },
    )

    decision = verification["decisions"][0]
    assert verification["contract"]["writes_graph"] is False
    assert decision["readiness"]["ready_for_commit_envelope"] is True
    assert decision["edge_decisions"] == [
        {
            "source_candidate_id": source_candidate,
            "target_candidate_id": target_candidate,
            "edge_type": "supports",
            "confidence": 0.81,
            "rationale": "The first claim is required for the second claim's replay guarantee.",
            "temporal": {
                "valid_from": "2026-06-01",
                "valid_until": "2026-06-30",
                "observed_at": "2026-06-29T00:00:00+00:00",
                "temporal_scope": "June 2026",
            },
        }
    ]
    assert decision["edge_decision_failures"] == [
        {"index": 1, "failure_reasons": ["unknown_target_candidate_id"]},
        {"index": 2, "failure_reasons": ["invalid_edge_valid_from"]},
    ]


def test_claim_verification_attaches_recall_context_without_changing_readiness():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "The compiler routes recall candidates before graph writes.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.91,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    candidate_id = extraction["candidates"][0]["candidate_id"]
    recall_candidate = RecallCandidate(
        item_id="belief_recall_1",
        text="The compiler can expose memory candidates for verifier inspection.",
        kind="belief",
        score=0.84,
        method="vector_similarity",
        domain="compiler",
        matched_terms=("compiler", "recall"),
        payload={"must": "not serialize"},
        metadata={"source_type": "report"},
    )

    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate_id,
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                }
            ]
        },
        recall_candidates_by_candidate_id={candidate_id: [recall_candidate]},
    )

    decision = verification["decisions"][0]
    assert decision["readiness"]["ready_for_commit_envelope"] is True
    assert decision["recall_context"]["routing"] == "candidate_only"
    assert decision["recall_context"]["semantic_verdict"] is False
    assert decision["recall_context"]["writes_graph"] is False
    assert decision["recall_context"]["candidate_count"] == 1
    assert decision["recall_context"]["candidates"] == [
        {
            "item_id": "belief_recall_1",
            "kind": "belief",
            "domain": "compiler",
            "text": "The compiler can expose memory candidates for verifier inspection.",
            "score": 0.84,
            "method": "vector_similarity",
            "matched_terms": ["compiler", "recall"],
            "metadata": {"source_type": "report"},
            "verdict": "candidate_only",
            "guidance": "routing_only",
        }
    ]
    assert "payload" not in decision["recall_context"]["candidates"][0]


def test_claim_verification_builds_read_only_recall_from_belief_store(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Release text changed the compiler behavior.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.91,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    belief, _ = store.add_belief(
        Belief(
            claim="Release text changed compiler behavior for source note verification.",
            confidence=0.82,
            domain="compiler",
            source_type="report",
        ),
        check_conflicts=False,
    )

    with (
        patch.object(store, "_record_change", side_effect=AssertionError("recall must not write changes")),
        patch.object(store, "_save", side_effect=AssertionError("recall must not write beliefs")),
    ):
        verification = build_claim_verification(
            extraction,
            {
                "verifications": [
                    {
                        "candidate_id": extraction["candidates"][0]["candidate_id"],
                        "support_verdict": "supported",
                        "contradiction_verdict": "none",
                        "dedup_verdict": "new",
                        "temporal_scope_verdict": "valid",
                    }
                ]
            },
            recall_belief_store=store,
            recall_domain="compiler",
            recall_top_k=3,
        )

    decision = verification["decisions"][0]
    recall_context = decision["recall_context"]
    assert decision["readiness"]["ready_for_commit_envelope"] is True
    assert recall_context["routing"] == "candidate_only"
    assert recall_context["semantic_verdict"] is False
    assert recall_context["writes_graph"] is False
    assert recall_context["candidate_count"] == 1
    candidate = recall_context["candidates"][0]
    assert candidate["item_id"] == belief.id
    assert candidate["kind"] == "belief"
    assert candidate["domain"] == "compiler"
    assert candidate["text"] == belief.claim
    assert candidate["method"] == "lexical_router"
    assert candidate["verdict"] == "candidate_only"
    assert candidate["guidance"] == "routing_only"
    assert candidate["metadata"]["recall_role"] == "memory_quality_candidate"
    assert candidate["metadata"]["verifier_bands"] == ["deduplication", "contradiction", "temporal_scope"]
    assert candidate["metadata"]["source_type"] == "report"
    assert "payload" not in candidate


def test_graph_commit_envelope_plans_idempotent_factual_belief_write():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Release text changed the compiler behavior.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.84,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                    "confidence": 0.91,
                    "rationale": "The cited source window supports the claim.",
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )

    assert envelope["schema_version"] == GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION
    assert envelope["kind"] == GRAPH_COMMIT_ENVELOPE_KIND
    assert envelope["contract"]["semantic_judgment"] is False
    assert envelope["contract"]["model_calls"] is False
    assert envelope["contract"]["writes_graph"] is False
    assert envelope["contract"]["apply_requires_explicit_command"] is True
    assert envelope["summary"]["status"] == "ready_for_commit"
    assert envelope["summary"]["ready_write_count"] == 1
    op = envelope["operations"][0]
    assert op["operation"] == "add_belief"
    assert op["belief"]["claim"] == "Release text changed the compiler behavior."
    assert op["belief"]["confidence"] == 0.91
    assert op["belief"]["domain"] == "compiler"
    assert op["belief"]["evidence_refs"] == [
        f"source_note:{note['note_id']}:{window['window_id']}",
    ]
    assert op["idempotency_key"]
    assert op["provenance"]["claim_verification_artifact"] == "sync_artifacts/claim_verifications/pack.json"
    assert envelope["compiler"]["next_stage_requires_model_judgment"] is False


def test_graph_commit_envelope_applies_verifier_edge_decisions(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "The compiler writes stable source notes.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.9,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                },
                {
                    "statement": "Stable source notes support replayable verification.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.88,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                },
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    source_candidate = extraction["candidates"][0]["candidate_id"]
    target_candidate = extraction["candidates"][1]["candidate_id"]
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": source_candidate,
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                    "edge_decisions": [
                        {
                            "target_candidate_id": target_candidate,
                            "edge_type": "derived_from",
                            "confidence": 0.77,
                            "rationale": "Replayable verification derives from stable source-note inputs.",
                            "temporal": {
                                "valid_from": "2026-06-01",
                                "valid_until": "2026-06-30",
                                "observed_at": "2026-06-29T00:00:00+00:00",
                                "temporal_scope": "June 2026",
                            },
                        }
                    ],
                },
                {
                    "candidate_id": target_candidate,
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                },
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
    )

    assert envelope["summary"]["status"] == "ready_for_commit"
    assert envelope["summary"]["ready_write_count"] == 2
    assert envelope["summary"]["ready_edge_count"] == 1
    source_operation = envelope["operations"][0]
    target_operation = envelope["operations"][1]
    assert source_operation["edges"] == [
        {
            "src_id": source_operation["belief"]["id"],
            "dst_id": target_operation["belief"]["id"],
            "edge_type": "derived_from",
            "source_candidate_id": source_candidate,
            "target_candidate_id": target_candidate,
            "provenance": (
                "claim_verification:sync_artifacts/claim_verifications/pack.json:"
                f"{source_candidate}:{target_candidate}:derived_from"
            ),
            "confidence": 0.77,
            "rationale": "Replayable verification derives from stable source-note inputs.",
            "temporal": {
                "valid_from": "2026-06-01",
                "valid_until": "2026-06-30",
                "observed_at": "2026-06-29T00:00:00+00:00",
                "temporal_scope": "June 2026",
            },
        }
    ]

    store = BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs")
    result = apply_graph_commit_envelope(envelope, store, dry_run=False)

    assert result["summary"]["status"] == "applied"
    assert result["operation_results"][0]["edge_count"] == 1
    assert len(store.edges) == 1
    edge = next(iter(store.edges.values()))
    assert edge.src_id == source_operation["belief"]["id"]
    assert edge.dst_id == target_operation["belief"]["id"]
    assert edge.edge_type == "derived_from"
    assert edge.temporal_contexts == [
        {
            "valid_from": "2026-06-01",
            "valid_until": "2026-06-30",
            "observed_at": "2026-06-29T00:00:00+00:00",
            "temporal_scope": "June 2026",
        }
    ]


def test_graph_commit_envelope_promotes_verified_knowledge_gap(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    topic = "What statistical signals should drive expert gap prioritization?"
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": topic,
                    "claim_kind": "knowledge_gap",
                    "confidence": 0.72,
                    "priority": 5,
                    "expected_value": 0.9,
                    "estimated_cost": 0.0,
                    "questions": [topic],
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    candidate = extraction["candidates"][0]
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "The source note exposed an unresolved prioritization question.",
                    "rationale": "The expert should retain the gap until a grounded scoring model exists.",
                    "uncertainty": "The best statistical signal mix is not established by the cited source.",
                    "confidence": 0.8,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    result = apply_graph_commit_envelope(
        envelope,
        BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs"),
        gap_tracker=tracker,
        dry_run=False,
    )

    assert candidate["state_policy"]["state_type"] == "knowledge_gap"
    assert candidate["state_policy"]["writes_gap_backlog"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["summary"]["status"] == "ready_for_commit"
    assert envelope["summary"]["ready_write_count"] == 1
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_gap"
    assert operation["gap"]["topic"] == topic
    assert operation["gap"]["priority"] == 5
    assert operation["gap"]["expected_value"] == 0.9
    assert result["summary"]["status"] == "applied"
    assert topic in tracker.knowledge_gaps


def test_graph_commit_envelope_promotes_verified_exploration_agenda(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    title = "Explore statistical signals for expert agenda prioritization."
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": title,
                    "claim_kind": "exploration_agenda",
                    "confidence": 0.76,
                    "priority": 4,
                    "expected_value": 0.8,
                    "estimated_cost": 0.0,
                    "questions": ["Which uncertainty and usage signals should drive agenda priority?"],
                    "success_criteria": ["A follow-up verifier accepts agenda priority evidence."],
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    candidate = extraction["candidates"][0]
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "The source note exposed a recurring unresolved prioritization direction.",
                    "rationale": "The expert should retain an agenda before any perspective write broadens.",
                    "uncertainty": "The optimal statistical signal mix is still unsettled.",
                    "expected_observations": ["Future source packs reveal repeated priority conflicts."],
                    "disconfirming_signals": ["No future consult trace needs prioritization evidence."],
                    "confidence": 0.81,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    result = apply_graph_commit_envelope(
        envelope,
        BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs"),
        gap_tracker=tracker,
        dry_run=False,
    )

    assert candidate["state_policy"]["state_type"] == "exploration_agenda"
    assert candidate["state_policy"]["writes_exploration_agenda"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["schema_version"] == GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION
    assert envelope["summary"]["status"] == "ready_for_commit"
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_exploration_agenda"
    assert operation["agenda"]["title"] == title
    assert operation["agenda"]["expected_observations"] == ["Future source packs reveal repeated priority conflicts."]
    assert result["summary"]["status"] == "applied"
    assert title in tracker.exploration_agendas


def test_exploration_agenda_verification_requires_expected_observations():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Explore compiler perspective-state risks.",
                    "claim_kind": "exploration_agenda",
                    "confidence": 0.7,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "Reviewed compiler output.",
                    "rationale": "The expert needs a future exploration lane.",
                    "uncertainty": "The target evidence is not yet known.",
                    "disconfirming_signals": ["No later trace needs this lane."],
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["decisions"][0]["readiness"]["failure_reasons"] == ["missing_expected_observations"]


def test_graph_commit_envelope_promotes_verified_hypothesis(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    title = "Statistical trace variables improve expert council verification."
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": title,
                    "claim_kind": "hypothesis",
                    "confidence": 0.74,
                    "priority": 4,
                    "assumptions": ["Consult traces preserve variables and scored outcomes."],
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "The source note exposed an unresolved but testable council-quality idea.",
                    "rationale": "The expert should retain the hypothesis without promoting it as fact.",
                    "uncertainty": "The expected improvement has not been measured.",
                    "expected_observations": ["Review packets include clearer statistical acceptance criteria."],
                    "disconfirming_signals": ["Review scores do not improve after trace variables are added."],
                    "confidence": 0.72,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    result = apply_graph_commit_envelope(
        envelope,
        BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs"),
        gap_tracker=tracker,
        dry_run=False,
    )

    candidate = extraction["candidates"][0]
    assert candidate["state_policy"]["state_type"] == "hypothesis"
    assert candidate["state_policy"]["writes_hypothesis"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["summary"]["status"] == "ready_for_commit"
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_hypothesis"
    assert operation["hypothesis"]["title"] == title
    assert operation["hypothesis"]["expected_observations"] == [
        "Review packets include clearer statistical acceptance criteria."
    ]
    assert result["summary"]["status"] == "applied"
    assert title in tracker.hypotheses


def test_hypothesis_verification_requires_expected_observations():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Trace variables may improve council math review.",
                    "claim_kind": "hypothesis",
                    "confidence": 0.7,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "Reviewed source-note evidence.",
                    "rationale": "The idea should stay testable rather than factual.",
                    "uncertainty": "The expected effect is unknown.",
                    "disconfirming_signals": ["No quality score change appears."],
                    "confidence": 0.75,
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["decisions"][0]["readiness"]["failure_reasons"] == ["missing_expected_observations"]


def test_graph_commit_envelope_promotes_verified_concept(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    name = "Statistical variable map"
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "A statistical variable map makes expert council plans reviewable.",
                    "title": name,
                    "claim_kind": "concept",
                    "confidence": 0.73,
                    "priority": 4,
                    "key_properties": ["Variables are explicit.", "Outcomes are reviewable."],
                    "related_terms": ["consult trace", "quality review"],
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    candidate = extraction["candidates"][0]
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "The source note exposed a reusable council-quality concept.",
                    "rationale": "The expert should retain the concept without promoting it as fact.",
                    "uncertainty": "The concept has not been calibrated across domains.",
                    "expected_observations": ["Future plans cite the variable map."],
                    "disconfirming_signals": ["Plans become harder to review when it is used."],
                    "confidence": 0.7,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    result = apply_graph_commit_envelope(
        envelope,
        BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs"),
        gap_tracker=tracker,
        dry_run=False,
    )

    assert candidate["state_policy"]["state_type"] == "concept"
    assert candidate["state_policy"]["writes_concept"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["summary"]["status"] == "ready_for_commit"
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_concept"
    assert operation["concept"]["name"] == name
    assert operation["concept"]["key_properties"] == ["Variables are explicit.", "Outcomes are reviewable."]
    assert result["summary"]["status"] == "applied"
    assert name in tracker.concepts


def test_concept_verification_requires_expected_observations():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "A variable map may make plans reviewable.",
                    "claim_kind": "concept",
                    "confidence": 0.7,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "Reviewed source-note evidence.",
                    "rationale": "The concept should stay testable rather than factual.",
                    "uncertainty": "The expected effect is unknown.",
                    "disconfirming_signals": ["No quality score change appears."],
                    "confidence": 0.75,
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["decisions"][0]["readiness"]["failure_reasons"] == ["missing_expected_observations"]


def test_graph_commit_envelope_promotes_verified_stance(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    title = "Prefer variable-first expert council plans"
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Expert council plans should expose statistical variables before synthesis.",
                    "title": title,
                    "claim_kind": "stance",
                    "confidence": 0.7,
                    "priority": 4,
                    "tradeoffs": ["Higher reviewability can add planning overhead."],
                    "decision_criteria": ["Prefer plans with explicit variables and measured outcomes."],
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    candidate = extraction["candidates"][0]
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "The source note exposed a reusable expert position.",
                    "rationale": "The expert should retain the stance without promoting it as fact.",
                    "uncertainty": "The stance has not been calibrated across project types.",
                    "expected_observations": ["Future plans expose variables before synthesis."],
                    "disconfirming_signals": ["Variable-first plans do not improve review quality."],
                    "confidence": 0.68,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    result = apply_graph_commit_envelope(
        envelope,
        BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs"),
        gap_tracker=tracker,
        dry_run=False,
    )

    assert candidate["state_policy"]["state_type"] == "stance"
    assert candidate["state_policy"]["writes_stance"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["summary"]["status"] == "ready_for_commit"
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_stance"
    assert operation["stance"]["title"] == title
    assert operation["stance"]["tradeoffs"] == ["Higher reviewability can add planning overhead."]
    assert result["summary"]["status"] == "applied"
    assert title in tracker.stances


def test_stance_verification_requires_expected_observations():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Expert council plans should expose variables before synthesis.",
                    "claim_kind": "stance",
                    "confidence": 0.7,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "Reviewed source-note evidence.",
                    "rationale": "The stance should stay testable rather than factual.",
                    "uncertainty": "The expected effect is unknown.",
                    "disconfirming_signals": ["Review quality is unchanged."],
                    "confidence": 0.68,
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["decisions"][0]["readiness"]["failure_reasons"] == ["missing_expected_observations"]


def test_graph_commit_envelope_promotes_verified_original_idea(tmp_path):
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    title = "Statistician council packets"
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Use a statistician council to turn agent consults into measurable review packets.",
                    "title": title,
                    "claim_kind": "original_idea",
                    "confidence": 0.68,
                    "priority": 4,
                    "assumptions": ["Consult traces can expose variables, outcomes, and tradeoffs."],
                    "implications": ["Future expert councils can emit more measurable plans."],
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
        source_note_artifact="sync_artifacts/source_notes/pack.json",
    )
    candidate = extraction["candidates"][0]
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "The source note exposed a new synthesis direction.",
                    "rationale": "The expert should retain the original idea without promoting it as fact.",
                    "uncertainty": "The idea has not been validated across repeated consult traces.",
                    "expected_observations": ["Future consult plans cite variables and acceptance criteria."],
                    "disconfirming_signals": ["Consult quality does not improve after the idea is used."],
                    "confidence": 0.66,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(
        extraction,
        verification,
        claim_extraction_artifact="sync_artifacts/claim_extractions/pack.json",
        claim_verification_artifact="sync_artifacts/claim_verifications/pack.json",
        expert_name="Compiler Expert",
        domain="compiler",
        generated_at="2026-06-26T12:03:00+00:00",
    )
    tracker = MetaCognitionTracker("Compiler Expert", base_path=str(tmp_path / "experts"))
    result = apply_graph_commit_envelope(
        envelope,
        BeliefStore("Compiler Expert", storage_dir=tmp_path / "beliefs"),
        gap_tracker=tracker,
        dry_run=False,
    )

    assert candidate["state_policy"]["state_type"] == "original_idea"
    assert candidate["state_policy"]["writes_original_idea"] is True
    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["summary"]["status"] == "ready_for_commit"
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_original_idea"
    assert operation["original_idea"]["title"] == title
    assert operation["original_idea"]["implications"] == ["Future expert councils can emit more measurable plans."]
    assert result["summary"]["status"] == "applied"
    assert title in tracker.original_ideas


def test_original_idea_verification_requires_expected_observations():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Use a statistician council to make consult plans measurable.",
                    "claim_kind": "original_idea",
                    "confidence": 0.68,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "not_applicable",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "not_applicable",
                    "origin": "Reviewed source-note evidence.",
                    "rationale": "The original idea should stay testable rather than factual.",
                    "uncertainty": "The expected effect is unknown.",
                    "disconfirming_signals": ["Review quality is unchanged."],
                    "confidence": 0.66,
                }
            ]
        },
    )

    assert verification["summary"]["status"] == "blocked"
    assert verification["decisions"][0]["readiness"]["failure_reasons"] == ["missing_expected_observations"]


def test_graph_commit_envelope_blocks_uncertain_deduplication():
    notes = build_source_notes(_source_pack_payload())
    note = notes["notes"][0]
    window = note["windows"][0]
    extraction = build_semantic_claim_extraction(
        notes,
        {
            "claims": [
                {
                    "statement": "Release text changed the compiler behavior.",
                    "claim_kind": "factual_claim",
                    "confidence": 0.84,
                    "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
                }
            ]
        },
    )
    verification = build_claim_verification(
        extraction,
        {
            "verifications": [
                {
                    "candidate_id": extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "uncertain",
                    "temporal_scope_verdict": "valid",
                    "confidence": 0.9,
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(extraction, verification)

    assert verification["summary"]["status"] == "ready_for_commit_envelope"
    assert envelope["summary"]["status"] == "blocked"
    assert envelope["summary"]["failure_reasons"] == ["deduplication_not_new"]
    assert envelope["operations"] == []
