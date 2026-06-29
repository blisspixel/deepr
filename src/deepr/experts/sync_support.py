"""Pure helpers for expert freshness sync."""

from __future__ import annotations

import re
from typing import Any

NO_CHANGES_MARKER = "no significant changes"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "topic"


def is_no_changes_answer(answer: str) -> bool:
    """True when the model returned the instructed no-change marker.

    Vendor CLIs sometimes wrap short answers in Markdown emphasis or code ticks.
    This strips only formatting wrappers and punctuation around the first line,
    then compares the exact marker. It is a form guard, not a semantic verdict.
    """
    first_line = (answer or "").strip().splitlines()[0] if (answer or "").strip() else ""
    normalized = first_line.lower()
    normalized = normalized.replace("*", "").replace("_", "").replace("`", "").replace("~", "")
    normalized = re.sub(r"\s+", " ", normalized).strip(" .!:;")
    return normalized == NO_CHANGES_MARKER


def fresh_context_has_no_sources(research: dict[str, Any]) -> bool:
    metadata = research.get("fresh_context")
    if not isinstance(metadata, dict):
        return False
    return metadata.get("source_count") == 0


def source_pack_from_research(research: dict[str, Any]) -> dict[str, Any] | None:
    source_pack = research.get("source_pack")
    if isinstance(source_pack, dict):
        return dict(source_pack)

    metadata = research.get("fresh_context")
    if not isinstance(metadata, dict):
        return None
    return {
        "schema_version": "deepr.source_pack.v1",
        "metadata_only": True,
        "mode": metadata.get("mode", "fresh"),
        "generated_at": metadata.get("generated_at"),
        "search_backend": metadata.get("search_backend"),
        "browser_backend": metadata.get("browser_backend"),
        "source_count": metadata.get("source_count", 0),
        "retrieved_source_count": metadata.get("retrieved_source_count", 0),
        "search_queries": metadata.get("search_queries", []),
        "sources": metadata.get("sources", []),
        "errors": metadata.get("errors", []),
    }


def source_pack_summary(source_pack: dict[str, Any]) -> tuple[int, str]:
    source_count = int(source_pack.get("source_count", 0) or 0)
    mode = str(source_pack.get("mode", "") or "")
    return source_count, mode


def nonnegative_float(value: Any) -> float:
    try:
        parsed = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, parsed)


def model_metadata(model_output: dict[str, Any], key: str) -> str:
    contract = model_output.get("contract", {})
    if isinstance(contract, dict) and contract.get(key):
        return str(contract.get(key) or "")
    return str(model_output.get(key, "") or "")


def source_pack_content_hashes(source_pack: dict[str, Any] | None) -> set[str]:
    """Non-empty SHA-256 content hashes of the fetched sources in a pack."""
    if not isinstance(source_pack, dict):
        return set()
    hashes: set[str] = set()
    for source in source_pack.get("sources", []):
        if isinstance(source, dict):
            digest = source.get("content_hash")
            if isinstance(digest, str) and digest:
                hashes.add(digest)
    return hashes
