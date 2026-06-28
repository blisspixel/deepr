"""Claim-kind policies for source-pack compilation."""

from __future__ import annotations

from typing import Any

from deepr.experts.source_pack_values import normalized_key

FACTUAL_KINDS = {"factual_claim", "fact", "external_fact", "current_fact"}
HYPOTHESIS_KINDS = {"hypothesis", "private_hypothesis", "theory"}
CONCEPT_KINDS = {"concept", "mental_model", "framework"}
STANCE_KINDS = {"stance", "position", "judgment"}
IDEA_KINDS = {"proposal", "original_idea", "original_synthesis"}
GAP_KINDS = {"gap", "knowledge_gap", "research_gap"}
AGENDA_KINDS = {"exploration_agenda", "research_agenda"}


def is_gap_kind(claim_kind: str) -> bool:
    return claim_kind in GAP_KINDS


def is_agenda_kind(claim_kind: str) -> bool:
    return claim_kind in AGENDA_KINDS


def is_hypothesis_kind(claim_kind: str) -> bool:
    return claim_kind in HYPOTHESIS_KINDS


def is_concept_kind(claim_kind: str) -> bool:
    return claim_kind in CONCEPT_KINDS


def is_stance_kind(claim_kind: str) -> bool:
    return claim_kind in STANCE_KINDS


def claim_kind_policy(claim_kind: str) -> dict[str, Any]:
    kind = normalized_key(claim_kind, default="factual_claim")
    if kind in GAP_KINDS:
        return {
            "state_type": "knowledge_gap",
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": False,
            "must_not_present_as_verified_fact": True,
            "writes_gap_backlog": True,
        }
    if kind in AGENDA_KINDS:
        return {
            "state_type": "exploration_agenda",
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": True,
            "requires_expected_observations": True,
            "must_not_present_as_verified_fact": True,
            "writes_exploration_agenda": True,
        }
    if kind in HYPOTHESIS_KINDS:
        return {
            "state_type": "hypothesis",
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": True,
            "requires_expected_observations": True,
            "must_not_present_as_verified_fact": True,
            "writes_hypothesis": True,
        }
    if kind in CONCEPT_KINDS:
        return {
            "state_type": "concept",
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": True,
            "requires_expected_observations": True,
            "must_not_present_as_verified_fact": True,
            "writes_concept": True,
        }
    if kind in STANCE_KINDS:
        return {
            "state_type": "stance",
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": True,
            "requires_expected_observations": True,
            "must_not_present_as_verified_fact": True,
            "writes_stance": True,
        }
    if kind in IDEA_KINDS:
        return {
            "state_type": kind,
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": True,
            "must_not_present_as_verified_fact": True,
        }
    if kind not in FACTUAL_KINDS:
        kind = "factual_claim"
    return {
        "state_type": kind,
        "requires_external_support": True,
        "requires_origin_and_rationale": False,
        "requires_disconfirming_signals": False,
        "must_not_present_as_verified_fact": False,
    }
