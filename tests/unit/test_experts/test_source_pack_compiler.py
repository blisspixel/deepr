"""Tests for deterministic source-pack compiler artifacts."""

from __future__ import annotations

from deepr.experts.source_pack_compiler import (
    SEMANTIC_CLAIM_EXTRACTION_KIND,
    SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION,
    SOURCE_NOTE_KIND,
    SOURCE_NOTE_SCHEMA_VERSION,
    SOURCE_PACK_MANIFEST_KIND,
    SOURCE_PACK_MANIFEST_SCHEMA_VERSION,
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
