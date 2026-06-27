"""Deterministic source-pack compiler primitives."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

SOURCE_PACK_MANIFEST_SCHEMA_VERSION = "deepr-source-pack-manifest-v1"
SOURCE_PACK_MANIFEST_KIND = "deepr.expert.source_pack_manifest"
SOURCE_NOTE_SCHEMA_VERSION = "deepr-source-note-v1"
SOURCE_NOTE_KIND = "deepr.expert.source_notes"
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


def _artifact_generated_at(payload: dict[str, Any], source_pack: dict[str, Any]) -> str:
    for key, source in (("started_at", payload), ("generated_at", source_pack), ("generated_at", payload)):
        value = source.get(key)
        if value:
            return str(value)
    return "1970-01-01T00:00:00+00:00"


def _source_pointer(index: int) -> str:
    return f"/source_pack/sources/{index}"


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


def _stable_note_id(source: dict[str, Any], source_index: int) -> str:
    material = "|".join(
        (
            str(source_index),
            str(source.get("label", "") or ""),
            str(source.get("url", "") or ""),
            str(source.get("content_hash", "") or ""),
            _sha256_text(str(source.get("excerpt", "") or "")),
        )
    )
    return f"sn_{_sha256_text(material)[:20]}"


def _source_window(note_id: str, excerpt: str) -> dict[str, Any]:
    return {
        "window_id": f"{note_id}:w0",
        "char_start": 0,
        "char_end": len(excerpt),
        "text_hash": _sha256_text(excerpt),
        "text_chars": len(excerpt),
        "source_text_ref": "excerpt",
    }


def _source_note(
    source: dict[str, Any],
    *,
    index: int,
    source_pack_artifact: str,
    source_pack_manifest_artifact: str,
    generated_at: str,
) -> dict[str, Any]:
    excerpt = str(source.get("excerpt", "") or "")
    content_hash = str(source.get("content_hash", "") or "")
    content_hash_valid = bool(_SHA256_HEX.fullmatch(content_hash))
    note_id = _stable_note_id(source, index)
    ready = bool(excerpt) and content_hash_valid
    source_pointer = _source_pointer(index)
    note = {
        "note_id": note_id,
        "source_index": index,
        "source_pointer": source_pointer,
        "label": str(source.get("label", "") or ""),
        "title": str(source.get("title", "") or ""),
        "url": str(source.get("url", "") or ""),
        "source": str(source.get("source", "") or ""),
        "fetched": bool(source.get("fetched", False)),
        "timestamps": {
            "source_pack_generated_at": generated_at,
        },
        "hashes": {
            "content_hash": content_hash,
            "content_hash_valid": content_hash_valid,
            "excerpt_hash": _sha256_text(excerpt),
        },
        "windows": [_source_window(note_id, excerpt)] if excerpt else [],
        "artifact_refs": {
            "source_pack": source_pack_artifact,
            "source_pack_manifest": source_pack_manifest_artifact,
            "source_pointer": source_pointer,
        },
        "readiness": {
            "ready_for_claim_extraction": ready,
            "has_excerpt": bool(excerpt),
            "has_valid_content_hash": content_hash_valid,
            "failure_reasons": [],
        },
    }
    if not excerpt:
        note["readiness"]["failure_reasons"].append("missing_excerpt")
    if not content_hash_valid:
        note["readiness"]["failure_reasons"].append("invalid_or_missing_content_hash")
    note["note_hash"] = _sha256_text(
        _json_hash_material(
            {
                "note_id": note["note_id"],
                "source_pointer": source_pointer,
                "hashes": note["hashes"],
                "windows": note["windows"],
                "artifact_refs": note["artifact_refs"],
                "readiness": note["readiness"],
            }
        )
    )
    return note


def _json_hash_material(value: Any) -> str:
    """Stable JSON material for non-cryptographic artifact hashing."""
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def build_source_notes(
    payload: dict[str, Any],
    *,
    source_pack_artifact: str = "",
    source_pack_manifest_artifact: str = "",
) -> dict[str, Any]:
    """Compile source-pack entries into deterministic structural note cards.

    Source notes are the next compiler envelope after the manifest. They point
    at evidence windows and provenance, but do not summarize, judge, cluster,
    extract claims, or decide meaning.
    """
    source_pack = _source_pack_from_payload(payload)
    raw_sources = _sources(source_pack)
    generated_at = _artifact_generated_at(payload, source_pack)
    notes = [
        _source_note(
            source,
            index=index,
            source_pack_artifact=source_pack_artifact,
            source_pack_manifest_artifact=source_pack_manifest_artifact,
            generated_at=generated_at,
        )
        for index, source in enumerate(raw_sources)
    ]
    ready_count = sum(1 for note in notes if note["readiness"]["ready_for_claim_extraction"])
    failure_reasons = sorted({reason for note in notes for reason in note["readiness"]["failure_reasons"]})
    return {
        "schema_version": SOURCE_NOTE_SCHEMA_VERSION,
        "kind": SOURCE_NOTE_KIND,
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
            "manifest_artifact_path": source_pack_manifest_artifact,
            "schema_version": str(source_pack.get("schema_version", "")),
            "query": str(payload.get("query", source_pack.get("query", "")) or ""),
            "topic": str(payload.get("topic", "") or ""),
            "mode": str(source_pack.get("mode", "") or ""),
            "generated_at": str(source_pack.get("generated_at", "") or ""),
            "source_count": _int_or_zero(source_pack.get("source_count"), default=len(notes)),
            "retrieved_source_count": _int_or_zero(source_pack.get("retrieved_source_count"), default=len(notes)),
        },
        "summary": {
            "source_entry_count": len(notes),
            "ready_note_count": ready_count,
            "blocked_note_count": len(notes) - ready_count,
            "ready_for_claim_extraction": bool(notes) and ready_count == len(notes),
            "failure_reasons": failure_reasons,
        },
        "notes": notes,
        "compiler": {
            "stage": "source_notes",
            "previous_stage": "source_pack_manifest",
            "next_stage": "semantic_claim_extraction",
            "next_stage_requires_model_judgment": True,
        },
        "generated_at": generated_at,
    }


__all__ = [
    "SOURCE_NOTE_KIND",
    "SOURCE_NOTE_SCHEMA_VERSION",
    "SOURCE_PACK_MANIFEST_KIND",
    "SOURCE_PACK_MANIFEST_SCHEMA_VERSION",
    "build_source_notes",
    "build_source_pack_manifest",
]
