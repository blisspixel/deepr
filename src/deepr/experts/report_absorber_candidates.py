"""Candidate-claim normalization for the report absorber (pure, $0, no model).

Turns raw extraction items into ``CandidateClaim`` values and resolves the
source labels a model selected back to replay refs the caller supplied. Form
only: nothing here judges whether a claim is true, grounded, or novel. Those
verdicts stay with the model paths in ``report_absorber``.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from deepr.experts.report_absorber_contracts import (
    CandidateClaim,
    normalize_evidence_items,
    normalize_selected_source_label,
)


def resolve_selected_source_ref(
    raw_label: object,
    source_ref_catalog: Mapping[str, str],
    allowed_replay_refs: set[str],
) -> str | None:
    raw_ref = str(raw_label).strip()
    replay_ref = source_ref_catalog.get(normalize_selected_source_label(raw_ref))
    if replay_ref is None and raw_ref in allowed_replay_refs:
        return raw_ref
    return replay_ref


def selected_source_refs(item: dict[str, Any], source_ref_catalog: Mapping[str, str] | None) -> list[str]:
    if source_ref_catalog is None:
        return []
    raw_source_refs = item.get("source_refs", [])
    if isinstance(raw_source_refs, str):
        raw_source_refs = [raw_source_refs]
    if not isinstance(raw_source_refs, list):
        return []
    allowed_replay_refs = set(source_ref_catalog.values())
    selected: list[str] = []
    for raw_label in raw_source_refs:
        replay_ref = resolve_selected_source_ref(raw_label, source_ref_catalog, allowed_replay_refs)
        if replay_ref and replay_ref not in selected:
            selected.append(replay_ref)
    return selected


def candidate_claim_from_item(
    item: object,
    source_ref_catalog: Mapping[str, str] | None,
) -> CandidateClaim | None:
    if not isinstance(item, dict):
        return None
    statement = str(item.get("statement", "")).strip()
    if not statement:
        return None
    try:
        confidence = float(item.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if not isfinite(confidence):
        confidence = 0.0
    return CandidateClaim(
        statement=statement,
        confidence=max(0.0, min(1.0, confidence)),
        evidence=normalize_evidence_items(item.get("evidence")),
        source_refs=selected_source_refs(item, source_ref_catalog),
    )
