"""Tests for deterministic source-pack compiler artifacts."""

from __future__ import annotations

from deepr.experts.graph_commit_envelope import (
    GRAPH_COMMIT_ENVELOPE_KIND,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
    build_graph_commit_envelope,
)
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
                    "disconfirming_signals": ["No cache-invalidation incidents appear in future notes."],
                }
            ]
        },
    )

    assert candidate["state_policy"]["requires_external_support"] is False
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


def test_graph_commit_envelope_blocks_hypothesis_until_perspective_store_exists():
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
                    "origin": "Synthesis over the source-note window.",
                    "rationale": "The release text suggests a future design pressure.",
                    "uncertainty": "Speculative until follow-up evidence appears.",
                    "disconfirming_signals": ["No cache incidents appear in future notes."],
                }
            ]
        },
    )

    envelope = build_graph_commit_envelope(extraction, verification, domain="compiler")

    assert envelope["summary"]["status"] == "blocked"
    assert envelope["summary"]["ready_write_count"] == 0
    assert envelope["operations"] == []
    assert envelope["blocked_decisions"][0]["failure_reasons"] == [
        "non_factual_state_requires_perspective_store",
        "support_not_verified",
        "temporal_scope_not_valid",
    ]


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
