"""Recall context helpers for source-pack compiler artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from deepr.experts.source_pack_values import float_0_1 as _float_0_1

_RECALL_ROUTING = "candidate_only"
_RECALL_GUIDANCE = "routing_only"


def _recall_value(candidate: Any, key: str, default: Any = "") -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _recall_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, set):
        values = sorted(value)
    elif isinstance(value, Iterable):
        values = value
    else:
        return []
    return [text for item in values if (text := str(item).strip())]


def _recall_metadata(candidate: Any) -> dict[str, Any]:
    metadata = _recall_value(candidate, "metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    return dict(metadata)


def _recall_candidate_packet(candidate: Any) -> dict[str, Any]:
    return {
        "item_id": str(_recall_value(candidate, "item_id", "") or ""),
        "kind": str(_recall_value(candidate, "kind", "") or ""),
        "domain": str(_recall_value(candidate, "domain", "") or ""),
        "text": str(_recall_value(candidate, "text", "") or ""),
        "score": _float_0_1(_recall_value(candidate, "score", 0.0)),
        "method": str(_recall_value(candidate, "method", "") or ""),
        "matched_terms": _recall_string_list(_recall_value(candidate, "matched_terms", [])),
        "metadata": _recall_metadata(candidate),
        "verdict": _RECALL_ROUTING,
        "guidance": _RECALL_GUIDANCE,
    }


def _recall_candidate_iter(raw_candidates: Any) -> Iterable[Any]:
    if raw_candidates is None or isinstance(raw_candidates, str):
        return []
    if isinstance(raw_candidates, Mapping):
        return [raw_candidates] if "item_id" in raw_candidates else []
    if isinstance(raw_candidates, Iterable):
        return raw_candidates
    return [raw_candidates]


def build_recall_context(raw_candidates: Any) -> dict[str, Any]:
    """Build a read-only recall packet for verifier routing."""
    candidates = [
        packet
        for candidate in _recall_candidate_iter(raw_candidates)
        if (packet := _recall_candidate_packet(candidate))["item_id"]
    ]
    return {
        "routing": _RECALL_ROUTING,
        "semantic_verdict": False,
        "writes_graph": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


__all__ = ["build_recall_context"]
