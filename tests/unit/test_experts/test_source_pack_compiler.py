"""Tests for deterministic source-pack compiler artifacts."""

from __future__ import annotations

from deepr.experts.source_pack_compiler import (
    SOURCE_PACK_MANIFEST_KIND,
    SOURCE_PACK_MANIFEST_SCHEMA_VERSION,
    build_source_pack_manifest,
)


def test_source_pack_manifest_records_hashes_without_semantic_judgment():
    payload = {
        "schema_version": "deepr.sync_source_pack.v1",
        "topic": "compiler topic",
        "query": "What changed?",
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
