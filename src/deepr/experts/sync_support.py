"""Pure helpers for expert freshness sync."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

NO_CHANGES_MARKER = "no significant changes"

# Retrieval receives a concise route, not the full synthesis prompt. These are
# form and transport bounds only; they do not judge topical meaning.
RETRIEVAL_TOPIC_MAX_CHARS = 240
RETRIEVAL_FOCUS_MAX_CHARS = 320
RETRIEVAL_EXPLICIT_URL_MAX_COUNT = 4
RETRIEVAL_EXPLICIT_URL_MAX_TOTAL_CHARS = 2048
_RETRIEVAL_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
_RETRIEVAL_TRAILING_PUNCTUATION = ".,;:!?"

# Snapshots above this size are skipped (never truncated - truncation would
# break the re-hash invariant). Fetched pages are usually well under this;
# the cap only bounds pathological pages so the snapshot store cannot balloon.
MAX_SNAPSHOT_CHARS = 2_000_000


def bounded_retrieval_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[: max(0, limit - 3)].rstrip()
    return f"{clipped}..."


def explicit_retrieval_urls(*values: str) -> tuple[str, ...]:
    urls: list[str] = []
    seen: set[str] = set()
    total_chars = 0
    for value in values:
        for match in _RETRIEVAL_URL_RE.findall(value):
            url = match.rstrip(_RETRIEVAL_TRAILING_PUNCTUATION)
            if not url or url in seen:
                continue
            projected = total_chars + len(url)
            if len(url) > RETRIEVAL_EXPLICIT_URL_MAX_TOTAL_CHARS or projected > RETRIEVAL_EXPLICIT_URL_MAX_TOTAL_CHARS:
                continue
            seen.add(url)
            urls.append(url)
            total_chars = projected
            if len(urls) >= RETRIEVAL_EXPLICIT_URL_MAX_COUNT:
                return tuple(urls)
    return tuple(urls)


def write_source_snapshots(source_pack: dict[str, Any], root: Path) -> None:
    """Write content-addressed raw snapshots and strip transient content.

    Each fetched source's full text is stored once under
    ``sync_artifacts/snapshots/<content_hash>.txt`` (identical content dedupes
    to one file), and the pack entry gains a ``snapshot_ref`` so excerpt-based
    evidence stays re-verifiable: re-hashing the snapshot file must reproduce
    ``content_hash``. A snapshot is written only when the carried text
    actually hashes to ``content_hash`` - conditional 304 reuse carries the
    prior excerpt with the prior full-content hash, and writing that excerpt
    under the full-content hash would silently corrupt the content-addressed
    store forever (the exists() dedupe would preserve it). The equality check
    also guarantees the filename is a plain sha256 hex, never a path.
    Snapshot write failures record a per-source error instead of failing the
    sync, because the pack and content hash already persist fail-closed.
    """
    sources = source_pack.get("sources")
    if not isinstance(sources, list):
        return
    snapshot_dir = root / "sync_artifacts" / "snapshots"
    for source in sources:
        if not isinstance(source, dict):
            continue
        content = str(source.pop("content", "") or "").strip()
        content_hash = str(source.get("content_hash", "") or "")
        if not content or not content_hash or len(content) > MAX_SNAPSHOT_CHARS:
            continue
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash:
            continue
        snapshot_path = snapshot_dir / f"{content_hash}.txt"
        try:
            if not snapshot_path.exists():
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                atomic_write_text(snapshot_path, content)
            source["snapshot_ref"] = snapshot_path.relative_to(root).as_posix()
        except OSError as exc:
            logger.warning("Could not write source snapshot %s: %s", snapshot_path, exc)
            source["snapshot_error"] = str(exc)


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
