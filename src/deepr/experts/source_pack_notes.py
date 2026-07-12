"""Pure source-entry and source-note builders for the source-pack compiler."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SHA256_HEX = re.compile(r"^[a-fA-F0-9]{64}$")


def sha256_text(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_hash_material(value: Any) -> str:
    """Stable JSON material for non-cryptographic artifact hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def source_entry(source: dict[str, Any]) -> dict[str, Any]:
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
        "excerpt_hash": sha256_text(excerpt),
        "excerpt_chars": len(excerpt),
    }


def _stable_note_id(source: dict[str, Any], source_index: int) -> str:
    material = "|".join(
        (
            str(source_index),
            str(source.get("label", "") or ""),
            str(source.get("url", "") or ""),
            str(source.get("content_hash", "") or ""),
            sha256_text(str(source.get("excerpt", "") or "")),
        )
    )
    return f"sn_{sha256_text(material)[:20]}"


def _source_window(note_id: str, excerpt: str) -> dict[str, Any]:
    return {
        "window_id": f"{note_id}:w0",
        "char_start": 0,
        "char_end": len(excerpt),
        "text_hash": sha256_text(excerpt),
        "text_chars": len(excerpt),
        "source_text_ref": "excerpt",
    }


def source_note(
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
    source_pointer = f"/source_pack/sources/{index}"
    note: dict[str, Any] = {
        "note_id": note_id,
        "source_index": index,
        "source_pointer": source_pointer,
        "label": str(source.get("label", "") or ""),
        "title": str(source.get("title", "") or ""),
        "url": str(source.get("url", "") or ""),
        "source": str(source.get("source", "") or ""),
        "fetched": bool(source.get("fetched", False)),
        "timestamps": {"source_pack_generated_at": generated_at},
        "hashes": {
            "content_hash": content_hash,
            "content_hash_valid": content_hash_valid,
            "excerpt_hash": sha256_text(excerpt),
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
    note["note_hash"] = sha256_text(
        json_hash_material(
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
