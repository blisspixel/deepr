"""Deterministic source-pack compiler primitives."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

SOURCE_PACK_MANIFEST_SCHEMA_VERSION = "deepr-source-pack-manifest-v1"
SOURCE_PACK_MANIFEST_KIND = "deepr.expert.source_pack_manifest"
_SHA256_HEX = re.compile(r"^[a-fA-F0-9]{64}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256_text(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _int_or_zero(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _source_pack_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_pack = payload.get("source_pack")
    if isinstance(source_pack, dict):
        return source_pack
    return payload


def _sources(source_pack: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sources = source_pack.get("sources", [])
    if not isinstance(raw_sources, list):
        return []
    return [source for source in raw_sources if isinstance(source, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _source_entry(source: dict[str, Any]) -> dict[str, Any]:
    excerpt = str(source.get("excerpt", "") or "")
    content_hash = str(source.get("content_hash", "") or "")
    content_hash_valid = bool(_SHA256_HEX.fullmatch(content_hash))
    return {
        "label": str(source.get("label", "") or ""),
        "title": str(source.get("title", "") or ""),
        "url": str(source.get("url", "") or ""),
        "source": str(source.get("source", "") or ""),
        "fetched": bool(source.get("fetched", False)),
        "content_hash": content_hash,
        "has_content_hash": bool(content_hash),
        "content_hash_valid": content_hash_valid,
        "excerpt_hash": _sha256_text(excerpt),
        "excerpt_chars": len(excerpt),
    }


def build_source_pack_manifest(
    payload: dict[str, Any],
    *,
    source_pack_artifact: str = "",
) -> dict[str, Any]:
    """Compile a source pack into a replayable structural manifest.

    This is the workflow envelope for later semantic compilation. It records
    provenance shape and hashes only; claim extraction, grounding, contradiction,
    and gap selection remain model-judgment stages downstream.
    """
    source_pack = _source_pack_from_payload(payload)
    sources = [_source_entry(source) for source in _sources(source_pack)]
    missing_content_hash_count = sum(1 for source in sources if not source["has_content_hash"])
    valid_content_hash_count = sum(1 for source in sources if source["content_hash_valid"])
    invalid_content_hash_count = sum(
        1 for source in sources if source["has_content_hash"] and not source["content_hash_valid"]
    )
    return {
        "schema_version": SOURCE_PACK_MANIFEST_SCHEMA_VERSION,
        "kind": SOURCE_PACK_MANIFEST_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "derived_view": True,
            "semantic_judgment": False,
            "model_calls": False,
            "breaking_changes_require_new_schema_version": True,
        },
        "source_pack": {
            "artifact_path": source_pack_artifact,
            "schema_version": str(source_pack.get("schema_version", "")),
            "query": str(payload.get("query", source_pack.get("query", "")) or ""),
            "topic": str(payload.get("topic", "") or ""),
            "mode": str(source_pack.get("mode", "") or ""),
            "generated_at": str(source_pack.get("generated_at", "") or ""),
            "search_backend": str(source_pack.get("search_backend", "") or ""),
            "browser_backend": str(source_pack.get("browser_backend", "") or ""),
            "source_count": _int_or_zero(source_pack.get("source_count"), default=len(sources)),
            "retrieved_source_count": _int_or_zero(source_pack.get("retrieved_source_count"), default=len(sources)),
            "search_queries": _string_list(source_pack.get("search_queries", [])),
        },
        "manifest": {
            "source_entry_count": len(sources),
            "content_hash_count": valid_content_hash_count,
            "valid_content_hash_count": valid_content_hash_count,
            "missing_content_hash_count": missing_content_hash_count,
            "invalid_content_hash_count": invalid_content_hash_count,
            "ready_for_semantic_compile": bool(sources) and valid_content_hash_count == len(sources),
        },
        "sources": sources,
        "compiler": {
            "stage": "source_pack_manifest",
            "next_stage": "semantic_claim_extraction",
            "next_stage_requires_model_judgment": True,
        },
        "generated_at": _utc_now().isoformat(),
    }


__all__ = [
    "SOURCE_PACK_MANIFEST_KIND",
    "SOURCE_PACK_MANIFEST_SCHEMA_VERSION",
    "build_source_pack_manifest",
]
