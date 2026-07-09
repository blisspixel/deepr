"""Review-required recall eval case candidate helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

RECALL_EVAL_CASE_CANDIDATE_SCHEMA_VERSION = "deepr-recall-eval-case-candidate-v1"
RECALL_EVAL_CASE_CANDIDATE_KIND = "deepr.eval.recall_case_candidate"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _preview(text: str, limit: int = 200) -> str:
    normalized = " ".join(text.split())
    return normalized[: limit - 1] + "..." if len(normalized) > limit else normalized


def unique_candidate_belief_ids(raw_ids: Iterable[Any]) -> list[str]:
    """Return de-duplicated non-empty string ids without assigning relevance."""
    belief_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        if not isinstance(raw_id, str):
            continue
        belief_id = raw_id.strip()
        if belief_id and belief_id not in seen:
            seen.add(belief_id)
            belief_ids.append(belief_id)
    return belief_ids


def candidate_belief_ids_from_recall_context(recall_context: Mapping[str, Any]) -> list[str]:
    candidates = recall_context.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    return unique_candidate_belief_ids(
        candidate.get("item_id")
        for candidate in candidates
        if isinstance(candidate, Mapping) and candidate.get("kind") in {"", "belief"}
    )


def build_recall_case_candidate(
    *,
    case_id: str,
    source_id: str,
    source_kind: str,
    source_reason: str,
    query: str,
    candidate_belief_ids: Sequence[Any],
    derived_from: str,
    input_metadata: Mapping[str, Any] | None = None,
    extra_fields: Mapping[str, Any] | None = None,
    operator_instruction: str = (
        "Review candidate_belief_ids before recording any as relevant_belief_ids with deepr eval recall."
    ),
) -> dict[str, Any] | None:
    cleaned_query = " ".join(str(query).split())
    cleaned_belief_ids = unique_candidate_belief_ids(candidate_belief_ids)
    if not cleaned_query or not cleaned_belief_ids:
        return None

    input_block = dict(input_metadata or {})
    input_block.update(
        {
            "query_hash": _sha256(cleaned_query),
            "query_preview": _preview(cleaned_query),
            "candidate_belief_ids": cleaned_belief_ids,
        }
    )

    candidate: dict[str, Any] = {
        "schema_version": RECALL_EVAL_CASE_CANDIDATE_SCHEMA_VERSION,
        "kind": RECALL_EVAL_CASE_CANDIDATE_KIND,
        "case_id": str(case_id or "").strip() or f"{source_id}_{source_reason}_recall",
        "source_id": str(source_id or ""),
        "source_kind": str(source_kind or ""),
        "source_reason": str(source_reason or ""),
        "contract": {
            "cost_usd": 0.0,
            "writes_state": False,
            "writes_graph": False,
            "writes_beliefs": False,
            "writes_belief_vectors": False,
            "semantic_verdict": False,
            "candidate_only": True,
            "requires_operator_relevance_review": True,
            "auto_record": False,
            "derived_from": str(derived_from or ""),
        },
        "input": input_block,
        "operator_instruction": operator_instruction,
    }
    if extra_fields:
        candidate.update(dict(extra_fields))
    return candidate


__all__ = [
    "RECALL_EVAL_CASE_CANDIDATE_KIND",
    "RECALL_EVAL_CASE_CANDIDATE_SCHEMA_VERSION",
    "build_recall_case_candidate",
    "candidate_belief_ids_from_recall_context",
    "unique_candidate_belief_ids",
]
