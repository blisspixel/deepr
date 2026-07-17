"""Deterministic source-pack compiler primitives."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from deepr.experts import source_pack_recall as _recall
from deepr.experts.belief_edges import EDGE_TYPES
from deepr.experts.recall_case_candidates import (
    build_recall_case_candidate,
    candidate_belief_ids_from_recall_context,
)
from deepr.experts.source_pack_edges import edge_decision_sets as _edge_decision_sets
from deepr.experts.source_pack_notes import json_hash_material as _json_hash_material
from deepr.experts.source_pack_notes import sha256_text as _sha256_text
from deepr.experts.source_pack_notes import source_entry as _source_entry
from deepr.experts.source_pack_notes import source_note as _source_note
from deepr.experts.source_pack_payloads import artifact_generated_at as _artifact_generated_at
from deepr.experts.source_pack_payloads import source_pack_from_payload as _source_pack_from_payload
from deepr.experts.source_pack_payloads import sources_from_pack as _sources
from deepr.experts.source_pack_policies import claim_kind_policy as _claim_kind_policy
from deepr.experts.source_pack_policies import is_agenda_kind as _is_agenda_kind
from deepr.experts.source_pack_policies import is_concept_kind as _is_concept_kind
from deepr.experts.source_pack_policies import is_gap_kind as _is_gap_kind
from deepr.experts.source_pack_policies import is_hypothesis_kind as _is_hypothesis_kind
from deepr.experts.source_pack_policies import is_original_idea_kind as _is_original_idea_kind
from deepr.experts.source_pack_policies import is_stance_kind as _is_stance_kind
from deepr.experts.source_pack_values import enum_value as _enum_value
from deepr.experts.source_pack_values import float_0_1 as _float_0_1
from deepr.experts.source_pack_values import float_nonnegative as _float_nonnegative
from deepr.experts.source_pack_values import int_or_zero as _int_or_zero
from deepr.experts.source_pack_values import int_range as _int_range
from deepr.experts.source_pack_values import normalized_key as _normalized_key
from deepr.experts.source_pack_values import string_field as _string_field
from deepr.experts.source_pack_values import string_list as _string_list
from deepr.experts.source_pack_values import string_list_field as _string_list_field

SOURCE_PACK_MANIFEST_SCHEMA_VERSION = "deepr-source-pack-manifest-v1"
SOURCE_PACK_MANIFEST_KIND = "deepr.expert.source_pack_manifest"
SOURCE_NOTE_SCHEMA_VERSION = "deepr-source-note-v1"
SOURCE_NOTE_KIND = "deepr.expert.source_notes"
SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION = "deepr-semantic-claim-extraction-v1"
SEMANTIC_CLAIM_EXTRACTION_KIND = "deepr.expert.semantic_claim_extraction"
SEMANTIC_CLAIM_EXTRACTION_PROMPT_VERSION = "deepr-semantic-claim-extraction-prompt-v1"
CLAIM_VERIFICATION_SCHEMA_VERSION = "deepr-claim-verification-v1"
CLAIM_VERIFICATION_KIND = "deepr.expert.claim_verification"
CLAIM_VERIFICATION_PROMPT_VERSION = "deepr-claim-verification-prompt-v1"
_SHA256_HEX = re.compile(r"^[a-fA-F0-9]{64}$")
_SUPPORT_VERDICTS = {"supported", "refuted", "insufficient", "not_applicable", "unverified"}
_CONTRADICTION_VERDICTS = {"none", "possible", "contradiction", "unverified"}
_DEDUP_VERDICTS = {"new", "same_as_existing", "uncertain", "unverified"}
_TEMPORAL_VERDICTS = {"valid", "unclear", "outdated", "not_applicable"}
_DOMAIN_RELEVANCE_VERDICTS = {"relevant", "peripheral", "irrelevant", "uncertain", "not_evaluated"}
_EDGE_TYPES = set(EDGE_TYPES)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _note_index(source_notes: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    notes: dict[str, dict[str, Any]] = {}
    windows_by_note: dict[str, set[str]] = {}
    for raw_note in source_notes.get("notes", []) or []:
        if not isinstance(raw_note, dict):
            continue
        note_id = str(raw_note.get("note_id", "") or "")
        if not note_id:
            continue
        notes[note_id] = raw_note
        windows_by_note[note_id] = {
            str(window.get("window_id", "") or "")
            for window in raw_note.get("windows", []) or []
            if isinstance(window, dict)
        }
    return notes, windows_by_note


def _candidate_source_refs(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_refs = item.get("source_refs", item.get("evidence_refs", item.get("sources", [])))
    if isinstance(raw_refs, dict):
        raw_refs = [raw_refs]
    if not isinstance(raw_refs, list):
        return []

    refs: list[dict[str, Any]] = []
    for raw_ref in raw_refs:
        if isinstance(raw_ref, dict):
            refs.append(
                {
                    "note_id": str(raw_ref.get("note_id", "") or ""),
                    "window_id": str(raw_ref.get("window_id", "") or ""),
                    "quote": str(raw_ref.get("quote", "") or ""),
                }
            )
        elif isinstance(raw_ref, str):
            refs.append({"note_id": raw_ref, "window_id": "", "quote": ""})
    return refs


def _validated_source_refs(
    item: dict[str, Any],
    *,
    notes: dict[str, dict[str, Any]],
    windows_by_note: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    failure_reasons: list[str] = []
    raw_refs = _candidate_source_refs(item)
    if not raw_refs:
        failure_reasons.append("missing_source_refs")
        return refs, failure_reasons

    for raw_ref in raw_refs:
        note_id = raw_ref["note_id"]
        window_id = raw_ref["window_id"]
        note = notes.get(note_id)
        note_exists = note is not None
        window_exists = bool(window_id and window_id in windows_by_note.get(note_id, set()))
        if not note_exists:
            failure_reasons.append("unknown_note_ref")
        elif not window_exists:
            failure_reasons.append("unknown_window_ref")
        refs.append(
            {
                "note_id": note_id,
                "window_id": window_id,
                "valid_ref": bool(note_exists and window_exists),
                "source_pointer": str((note or {}).get("source_pointer", "") or ""),
                "source_index": _int_or_zero((note or {}).get("source_index")),
                "quote_hash": _sha256_text(raw_ref["quote"]),
                "quote_chars": len(raw_ref["quote"]),
            }
        )
    return refs, sorted(set(failure_reasons))


def _candidate_id(statement: str, source_refs: list[dict[str, Any]]) -> str:
    material = {
        "statement": statement,
        "source_refs": [
            {
                "note_id": ref.get("note_id", ""),
                "window_id": ref.get("window_id", ""),
            }
            for ref in source_refs
        ],
    }
    return f"cc_{_sha256_text(_json_hash_material(material))[:20]}"


def _gap_candidate(item: dict[str, Any], statement: str) -> dict[str, Any]:
    topic = str(item.get("topic", statement) or statement).strip()
    estimated_cost = _float_nonnegative(item.get("estimated_cost"))
    expected_value = _float_0_1(item.get("expected_value"))
    return {
        "topic": topic or statement,
        "questions": _string_list_field(item, "questions"),
        "priority": _int_range(item.get("priority"), default=3, minimum=1, maximum=5),
        "estimated_cost": estimated_cost,
        "expected_value": expected_value,
        "ev_cost_ratio": expected_value / max(estimated_cost, 0.001) if expected_value else 0.0,
        "times_asked": max(1, _int_or_zero(item.get("times_asked"), default=1)),
    }


def _agenda_candidate(item: dict[str, Any], statement: str) -> dict[str, Any]:
    title = str(item.get("title", statement) or statement).strip()
    estimated_cost = _float_nonnegative(item.get("estimated_cost"))
    expected_value = _float_0_1(item.get("expected_value"))
    return {
        "title": title or statement,
        "questions": _string_list_field(item, "questions"),
        "priority": _int_range(item.get("priority"), default=3, minimum=1, maximum=5),
        "estimated_cost": estimated_cost,
        "expected_value": expected_value,
        "ev_cost_ratio": expected_value / max(estimated_cost, 0.001) if expected_value else 0.0,
        "success_criteria": _string_list_field(item, "success_criteria"),
        "expected_observations": _string_list_field(item, "expected_observations"),
        "disconfirming_signals": _string_list_field(item, "disconfirming_signals"),
    }


def _hypothesis_candidate(item: dict[str, Any], statement: str) -> dict[str, Any]:
    title = str(item.get("title", statement) or statement).strip()
    return {
        "title": title or statement,
        "statement": statement,
        "assumptions": _string_list_field(item, "assumptions"),
        "priority": _int_range(item.get("priority"), default=3, minimum=1, maximum=5),
    }


def _concept_candidate(item: dict[str, Any], statement: str) -> dict[str, Any]:
    name = str(item.get("title", item.get("name", statement)) or statement).strip()
    return {
        "name": name or statement,
        "description": str(item.get("description", statement) or statement).strip(),
        "key_properties": _string_list_field(item, "key_properties"),
        "related_terms": _string_list_field(item, "related_terms"),
        "priority": _int_range(item.get("priority"), default=3, minimum=1, maximum=5),
    }


def _stance_candidate(item: dict[str, Any], statement: str) -> dict[str, Any]:
    title = str(item.get("title", statement) or statement).strip()
    position = str(item.get("position", statement) or statement).strip()
    return {
        "title": title or statement,
        "position": position or statement,
        "tradeoffs": _string_list_field(item, "tradeoffs"),
        "decision_criteria": _string_list_field(item, "decision_criteria"),
        "priority": _int_range(item.get("priority"), default=3, minimum=1, maximum=5),
    }


def _original_idea_candidate(item: dict[str, Any], statement: str) -> dict[str, Any]:
    title = str(item.get("title", statement) or statement).strip()
    return {
        "title": title or statement,
        "statement": statement,
        "assumptions": _string_list_field(item, "assumptions"),
        "implications": _string_list_field(item, "implications"),
        "priority": _int_range(item.get("priority"), default=3, minimum=1, maximum=5),
    }


def _response_from_model_output(model_output: dict[str, Any] | str) -> tuple[dict[str, Any], str, str]:
    if isinstance(model_output, str):
        raw = model_output
        try:
            parsed = json.loads(model_output)
        except json.JSONDecodeError:
            return {}, _sha256_text(raw), "invalid_json_response"
        if not isinstance(parsed, dict):
            return {}, _sha256_text(raw), "non_object_response"
        return parsed, _sha256_text(raw), ""
    return model_output, _sha256_text(_json_hash_material(model_output)), ""


def _raw_claim_items(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw_claims = parsed.get("claims", [])
    if not isinstance(raw_claims, list):
        return []
    return [item for item in raw_claims if isinstance(item, dict)]


def _claim_response_shape_failure(parsed: dict[str, Any]) -> str:
    if "claims" not in parsed:
        return "missing_claims_field"
    if not isinstance(parsed.get("claims"), list):
        return "invalid_claims_field"
    return ""


def _claim_candidate(
    item: dict[str, Any],
    *,
    notes: dict[str, dict[str, Any]],
    windows_by_note: dict[str, set[str]],
) -> dict[str, Any]:
    statement = str(item.get("statement", item.get("claim", "")) or "").strip()
    claim_kind = _normalized_key(item.get("claim_kind", item.get("type", "factual_claim")), default="factual_claim")
    evidence_refs, ref_failures = _validated_source_refs(item, notes=notes, windows_by_note=windows_by_note)
    valid_source_ref_count = sum(1 for ref in evidence_refs if ref["valid_ref"])
    failure_reasons = list(ref_failures)
    if not statement:
        failure_reasons.append("missing_statement")
    if valid_source_ref_count == 0:
        failure_reasons.append("no_valid_source_refs")
    failure_reasons = sorted(set(failure_reasons))
    ready = bool(statement) and valid_source_ref_count > 0
    candidate: dict[str, Any] = {
        "candidate_id": _candidate_id(statement, evidence_refs),
        "statement": statement,
        "claim_kind": claim_kind,
        "state_policy": _claim_kind_policy(claim_kind),
        "confidence": _float_0_1(item.get("confidence")),
        "model_judgment": {
            "atomicity": str(item.get("atomicity", "") or ""),
            "temporal_scope": str(item.get("temporal_scope", "") or ""),
            "support_summary": str(item.get("support_summary", item.get("rationale", "")) or ""),
        },
        "evidence_refs": evidence_refs,
        "readiness": {
            "ready_for_verification": ready,
            "valid_source_ref_count": valid_source_ref_count,
            "invalid_source_ref_count": len(evidence_refs) - valid_source_ref_count,
            "failure_reasons": failure_reasons,
        },
        "verifier_gate": {
            "status": "pending",
            "required_checks": ["grounding", "contradiction", "deduplication", "temporal_scope"],
            "writes_graph": False,
        },
    }
    if _is_gap_kind(claim_kind):
        candidate["gap"] = _gap_candidate(item, statement)
    if _is_agenda_kind(claim_kind):
        candidate["agenda"] = _agenda_candidate(item, statement)
    if _is_hypothesis_kind(claim_kind):
        candidate["hypothesis"] = _hypothesis_candidate(item, statement)
    if _is_concept_kind(claim_kind):
        candidate["concept"] = _concept_candidate(item, statement)
    if _is_stance_kind(claim_kind):
        candidate["stance"] = _stance_candidate(item, statement)
    if _is_original_idea_kind(claim_kind):
        candidate["original_idea"] = _original_idea_candidate(item, statement)
    return candidate


def _raw_verification_items(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw = parsed.get("verifications", parsed.get("decisions", []))
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _verification_response_shape_failure(parsed: dict[str, Any]) -> str:
    if "verifications" not in parsed and "decisions" not in parsed:
        return "missing_verifications_field"
    raw = parsed.get("verifications", parsed.get("decisions"))
    if not isinstance(raw, list):
        return "invalid_verifications_field"
    return ""


def _candidate_by_id(extraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for raw_candidate in extraction.get("candidates", []) or []:
        if not isinstance(raw_candidate, dict):
            continue
        candidate_id = str(raw_candidate.get("candidate_id", "") or "")
        if candidate_id:
            candidates[candidate_id] = raw_candidate
    return candidates


def _candidate_policy(candidate: dict[str, Any] | None) -> dict[str, Any]:
    policy = (candidate or {}).get("state_policy", {})
    if isinstance(policy, dict):
        return policy
    return _claim_kind_policy(str((candidate or {}).get("claim_kind", "factual_claim") or "factual_claim"))


def _verification_verdicts(item: dict[str, Any]) -> dict[str, str]:
    return {
        "support": _enum_value(item.get("support_verdict"), _SUPPORT_VERDICTS, default="unverified"),
        "contradiction": _enum_value(item.get("contradiction_verdict"), _CONTRADICTION_VERDICTS, default="unverified"),
        "deduplication": _enum_value(item.get("dedup_verdict"), _DEDUP_VERDICTS, default="unverified"),
        "temporal_scope": _enum_value(item.get("temporal_scope_verdict"), _TEMPORAL_VERDICTS, default="unclear"),
        "domain_relevance": _enum_value(
            item.get("domain_relevance_verdict"),
            _DOMAIN_RELEVANCE_VERDICTS,
            default="not_evaluated",
        ),
    }


def _verification_model_judgment(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": _float_0_1(item.get("confidence")),
        "rationale": _string_field(item, "rationale"),
        "support_summary": _string_field(item, "support_summary"),
        "domain_relevance_rationale": _string_field(item, "domain_relevance_rationale"),
        "origin": _string_field(item, "origin"),
        "uncertainty": _string_field(item, "uncertainty"),
        "expected_observations": _string_list_field(item, "expected_observations"),
        "disconfirming_signals": _string_list_field(item, "disconfirming_signals"),
    }


def _candidate_verification_failures(candidate_id: str, candidate: dict[str, Any] | None) -> list[str]:
    failure_reasons: list[str] = []
    if not candidate_id:
        failure_reasons.append("missing_candidate_id")
    if candidate is None:
        failure_reasons.append("unknown_candidate_id")
    elif (candidate.get("readiness", {}) or {}).get("ready_for_verification") is not True:
        failure_reasons.append("candidate_not_ready_for_verification")
    return failure_reasons


def _idea_policy_failures(policy: dict[str, Any], model_judgment: dict[str, Any]) -> list[str]:
    if not policy.get("requires_origin_and_rationale"):
        return []
    failures: list[str] = []
    for field, reason in (
        ("origin", "missing_origin"),
        ("rationale", "missing_rationale"),
        ("uncertainty", "missing_uncertainty"),
    ):
        if not model_judgment[field]:
            failures.append(reason)
    return failures


def _policy_verification_failures(
    policy: dict[str, Any],
    verdicts: dict[str, str],
    model_judgment: dict[str, Any],
    *,
    required_domain: str,
) -> list[str]:
    failure_reasons: list[str] = []
    if policy.get("requires_external_support") and verdicts["support"] != "supported":
        failure_reasons.append("factual_support_not_verified")
    if policy.get("requires_expected_observations") and not model_judgment.get("expected_observations"):
        failure_reasons.append("missing_expected_observations")
    if policy.get("requires_disconfirming_signals") and not model_judgment["disconfirming_signals"]:
        failure_reasons.append("missing_disconfirming_signals")
    if verdicts["contradiction"] == "contradiction":
        failure_reasons.append("contradiction_unresolved")
    if verdicts["deduplication"] == "same_as_existing":
        failure_reasons.append("duplicate_existing_belief")
    if verdicts["temporal_scope"] == "outdated":
        failure_reasons.append("temporal_scope_rejected")
    if required_domain and verdicts["domain_relevance"] != "relevant":
        failure_reasons.append("domain_relevance_not_verified")
    if (
        required_domain
        and verdicts["domain_relevance"] == "relevant"
        and not model_judgment["domain_relevance_rationale"]
    ):
        failure_reasons.append("missing_domain_relevance_rationale")
    return failure_reasons + _idea_policy_failures(policy, model_judgment)


def _recall_case_candidate_reason(failure_reasons: list[str]) -> str:
    for reason in ("duplicate_existing_belief", "contradiction_unresolved", "temporal_scope_rejected"):
        if reason in failure_reasons:
            return reason
    return ""


def _recall_case_candidate_for_decision(
    *,
    candidate_id: str,
    candidate: dict[str, Any] | None,
    failure_reasons: list[str],
    verdicts: dict[str, str],
    recall_context: dict[str, Any],
) -> dict[str, Any] | None:
    reason = _recall_case_candidate_reason(failure_reasons)
    if not reason or candidate is None:
        return None
    return build_recall_case_candidate(
        case_id=f"{candidate_id}_{reason}_recall",
        source_id=candidate_id,
        source_kind="claim_verification_decision",
        source_reason=reason,
        query=str(candidate.get("statement", "") or ""),
        candidate_belief_ids=candidate_belief_ids_from_recall_context(recall_context),
        derived_from=CLAIM_VERIFICATION_SCHEMA_VERSION,
        input_metadata={
            "claim_candidate_id": candidate_id,
            "claim_kind": str(candidate.get("claim_kind", "") or ""),
            "recall_candidate_count": recall_context.get("candidate_count", 0),
            "verifier_failure_reasons": failure_reasons,
            "verdicts": verdicts,
        },
        extra_fields={"source_candidate_id": candidate_id},
    )


def _verification_decision(
    item: dict[str, Any],
    *,
    candidates_by_id: dict[str, dict[str, Any]],
    recall_candidates_by_candidate_id: Mapping[str, Iterable[Any]],
    required_domain: str,
) -> dict[str, Any]:
    candidate_id = str(item.get("candidate_id", "") or "").strip()
    candidate = candidates_by_id.get(candidate_id)
    policy = _candidate_policy(candidate)
    verdicts = _verification_verdicts(item)
    model_judgment = _verification_model_judgment(item)
    edge_decisions, edge_decision_failures = _edge_decision_sets(
        item,
        current_candidate_id=candidate_id,
        candidates_by_id=candidates_by_id,
        edge_types=_EDGE_TYPES,
    )
    failure_reasons = _candidate_verification_failures(candidate_id, candidate)
    failure_reasons.extend(
        _policy_verification_failures(
            policy,
            verdicts,
            model_judgment,
            required_domain=required_domain,
        )
    )
    failure_reasons = sorted(set(failure_reasons))
    ready = bool(candidate is not None and not failure_reasons)
    recall_context = _recall.build_recall_context(recall_candidates_by_candidate_id.get(candidate_id, []))
    decision = {
        "candidate_id": candidate_id,
        "claim_kind": str((candidate or {}).get("claim_kind", item.get("claim_kind", "")) or ""),
        "state_policy": policy,
        "verdicts": verdicts,
        "model_judgment": model_judgment,
        "edge_decisions": edge_decisions,
        "edge_decision_failures": edge_decision_failures,
        "recall_context": recall_context,
        "readiness": {
            "ready_for_commit_envelope": ready,
            "failure_reasons": failure_reasons,
        },
        "commit_gate": {
            "status": "ready_for_commit_envelope" if ready else "blocked",
            "writes_graph": False,
            "requires_commit_envelope": True,
        },
    }
    recall_case_candidate = _recall_case_candidate_for_decision(
        candidate_id=candidate_id,
        candidate=candidate,
        failure_reasons=failure_reasons,
        verdicts=verdicts,
        recall_context=recall_context,
    )
    if recall_case_candidate is not None:
        decision["recall_case_candidate"] = recall_case_candidate
    return decision


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
    generation_readiness = source_pack.get("generation_readiness", {})
    if not isinstance(generation_readiness, dict):
        generation_readiness = {}
    generation_contract_ready = generation_readiness.get("ready") is not False
    missing_content_hash_count = sum(1 for source in sources if not source["has_content_hash"])
    valid_content_hash_count = sum(1 for source in sources if source["content_hash_valid"])
    invalid_content_hash_count = sum(
        1 for source in sources if source["has_content_hash"] and not source["content_hash_valid"]
    )
    ready_for_generation = bool(sources) and valid_content_hash_count == len(sources) and generation_contract_ready
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
            "answer_query": str(payload.get("answer_query", payload.get("query", "")) or ""),
            "retrieval_query": str(payload.get("retrieval_query", source_pack.get("query", "")) or ""),
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
            "generation_readiness": generation_readiness,
            "ready_for_generation": ready_for_generation,
            "ready_for_semantic_compile": ready_for_generation,
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
    generation_readiness = source_pack.get("generation_readiness", {})
    if not isinstance(generation_readiness, dict):
        generation_readiness = {}
    generation_contract_ready = generation_readiness.get("ready") is not False
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
    if not generation_contract_ready:
        failure_reasons.append("insufficient_content_addressed_sources")
    ready_for_generation = bool(notes) and ready_count == len(notes) and generation_contract_ready
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
            "answer_query": str(payload.get("answer_query", payload.get("query", "")) or ""),
            "retrieval_query": str(payload.get("retrieval_query", source_pack.get("query", "")) or ""),
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
            "generation_readiness": generation_readiness,
            "ready_for_generation": ready_for_generation,
            "ready_for_claim_extraction": ready_for_generation,
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


def build_semantic_claim_extraction(
    source_notes: dict[str, Any],
    model_output: dict[str, Any] | str,
    *,
    source_note_artifact: str = "",
    provider: str = "",
    model: str = "",
    capacity_source: str = "",
    cost_usd: float = 0.0,
    prompt_version: str = SEMANTIC_CLAIM_EXTRACTION_PROMPT_VERSION,
    prompt_ref: str = "",
    prompt_text: str = "",
    prompt_hash: str = "",
    generated_at: str = "",
    max_candidates: int | None = None,
) -> dict[str, Any]:
    """Compile model claim output into a verifier-gated candidate envelope.

    This stage records semantic model judgment, but it still writes no expert
    state. Deterministic code checks only shape, score bounds, source-note
    references, prompt/schema versions, and the graph-write gate. Grounding,
    contradiction, deduplication, novelty, and temporal interpretation remain
    downstream model-verifier work.
    """
    if max_candidates is not None and (
        isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or not 1 <= max_candidates <= 100
    ):
        raise ValueError("max_candidates must be an integer from 1 to 100")
    parsed, raw_response_hash, response_failure = _response_from_model_output(model_output)
    response_failure = response_failure or _claim_response_shape_failure(parsed)
    notes, windows_by_note = _note_index(source_notes)
    raw_claim_items = _raw_claim_items(parsed)
    retained_claim_items = raw_claim_items[:max_candidates] if max_candidates is not None else raw_claim_items
    candidates = [_claim_candidate(item, notes=notes, windows_by_note=windows_by_note) for item in retained_claim_items]
    ready_count = sum(1 for candidate in candidates if candidate["readiness"]["ready_for_verification"])
    invalid_ref_count = sum(candidate["readiness"]["invalid_source_ref_count"] for candidate in candidates)
    failure_reasons = sorted(
        {reason for candidate in candidates for reason in candidate["readiness"]["failure_reasons"]}
        | ({response_failure} if response_failure else set())
    )
    prompt_material = prompt_text if prompt_text else prompt_ref or prompt_version
    resolved_prompt_hash = prompt_hash or _sha256_text(prompt_material)
    status = (
        "ready_for_verification"
        if candidates and ready_count == len(candidates) and not response_failure
        else "blocked"
    )
    if not candidates and not response_failure:
        status = "empty"
    return {
        "schema_version": SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION,
        "kind": SEMANTIC_CLAIM_EXTRACTION_KIND,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "semantic_judgment": True,
            "model_calls": True,
            "cost_usd": round(max(cost_usd, 0.0), 6),
            "writes_graph": False,
            "breaking_changes_require_new_schema_version": True,
        },
        "input": {
            "source_note_artifact": source_note_artifact,
            "source_note_schema_version": str(source_notes.get("schema_version", "")),
            "source_note_kind": str(source_notes.get("kind", "")),
            "source_note_count": len(notes),
            "ready_note_count": _int_or_zero((source_notes.get("summary", {}) or {}).get("ready_note_count")),
            "source_pack": source_notes.get("source_pack", {}),
        },
        "prompt": {
            "prompt_version": prompt_version,
            "prompt_ref": prompt_ref,
            "prompt_hash": resolved_prompt_hash,
            "prompt_text_included": False,
            "response_schema_version": SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION,
            "response_schema_ref": "docs/schemas/semantic-claim-extraction-v1.json",
            "structured_output_mode": "json_schema_or_tool_schema",
            "app_side_schema_validation_required": True,
        },
        "model": {
            "provider": provider,
            "model": model,
            "capacity_source": capacity_source,
            "raw_response_hash": raw_response_hash,
            "response_failure": response_failure,
        },
        "summary": {
            "status": status,
            "raw_candidate_count": len(raw_claim_items),
            "parsed_candidate_count": len(candidates),
            "candidate_limit": max_candidates,
            "candidate_limit_applied": max_candidates is not None and len(raw_claim_items) > max_candidates,
            "dropped_candidate_count": len(raw_claim_items) - len(candidates),
            "ready_for_verification_count": ready_count,
            "blocked_candidate_count": len(candidates) - ready_count,
            "invalid_source_ref_count": invalid_ref_count,
            "failure_reasons": failure_reasons,
        },
        "candidates": candidates,
        "compiler": {
            "stage": "semantic_claim_extraction",
            "previous_stage": "source_notes",
            "next_stage": "claim_verification",
            "next_stage_requires_model_judgment": True,
            "graph_writes_require_commit_envelope": True,
        },
        "generated_at": generated_at or _artifact_generated_at({}, source_notes),
    }


def build_claim_verification(
    claim_extraction: dict[str, Any],
    model_output: dict[str, Any] | str,
    *,
    claim_extraction_artifact: str = "",
    provider: str = "",
    model: str = "",
    capacity_source: str = "",
    cost_usd: float = 0.0,
    prompt_version: str = CLAIM_VERIFICATION_PROMPT_VERSION,
    prompt_ref: str = "",
    prompt_text: str = "",
    prompt_hash: str = "",
    generated_at: str = "",
    recall_candidates_by_candidate_id: Mapping[str, Iterable[Any]] | None = None,
    recall_belief_store: Any | None = None,
    recall_domain: str | None = None,
    recall_top_k: int = 5,
    recall_min_score: float = 0.0,
    recall_query_embeddings_by_candidate_id: Mapping[str, Sequence[float]] | None = None,
    recall_embedding_model: str | None = None,
    recall_route_preference: Mapping[str, Any] | None = None,
    required_domain: str = "",
) -> dict[str, Any]:
    """Compile verifier output into graph-commit readiness decisions.

    This is still a no-write envelope. It records semantic verifier judgment and
    type-specific policy gates, but graph mutation waits for a later commit
    envelope that can atomically write beliefs and temporal edges.
    """
    parsed, raw_response_hash, response_failure = _response_from_model_output(model_output)
    response_failure = response_failure or _verification_response_shape_failure(parsed)
    candidates_by_id = _candidate_by_id(claim_extraction)
    recall_candidates_by_candidate_id = _recall.resolve_verification_recall_candidates(
        recall_candidates_by_candidate_id,
        claim_extraction,
        recall_belief_store,
        domain=recall_domain,
        top_k=recall_top_k,
        min_score=recall_min_score,
        query_embeddings_by_candidate_id=recall_query_embeddings_by_candidate_id,
        embedding_model=recall_embedding_model,
        route_preference=recall_route_preference,
    )
    decisions = [
        _verification_decision(
            item,
            candidates_by_id=candidates_by_id,
            recall_candidates_by_candidate_id=recall_candidates_by_candidate_id,
            required_domain=required_domain.strip(),
        )
        for item in _raw_verification_items(parsed)
    ]
    ready_count = sum(1 for decision in decisions if decision["readiness"]["ready_for_commit_envelope"])
    failure_reasons = sorted(
        {reason for decision in decisions for reason in decision["readiness"]["failure_reasons"]}
        | ({response_failure} if response_failure else set())
    )
    prompt_material = prompt_text if prompt_text else prompt_ref or prompt_version
    resolved_prompt_hash = prompt_hash or _sha256_text(prompt_material)
    if not decisions and not response_failure:
        status = "empty"
    elif decisions and ready_count == len(decisions) and not response_failure:
        status = "ready_for_commit_envelope"
    else:
        status = "blocked"

    return {
        "schema_version": CLAIM_VERIFICATION_SCHEMA_VERSION,
        "kind": CLAIM_VERIFICATION_KIND,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "semantic_judgment": True,
            "model_calls": True,
            "cost_usd": round(max(cost_usd, 0.0), 6),
            "writes_graph": False,
            "breaking_changes_require_new_schema_version": True,
        },
        "input": {
            "claim_extraction_artifact": claim_extraction_artifact,
            "claim_extraction_schema_version": str(claim_extraction.get("schema_version", "")),
            "claim_extraction_kind": str(claim_extraction.get("kind", "")),
            "candidate_count": len(candidates_by_id),
            "ready_candidate_count": _int_or_zero(
                (claim_extraction.get("summary", {}) or {}).get("ready_for_verification_count")
            ),
            "required_domain": required_domain.strip(),
            "domain_relevance_required": bool(required_domain.strip()),
        },
        "prompt": {
            "prompt_version": prompt_version,
            "prompt_ref": prompt_ref,
            "prompt_hash": resolved_prompt_hash,
            "prompt_text_included": False,
            "response_schema_version": CLAIM_VERIFICATION_SCHEMA_VERSION,
            "response_schema_ref": "docs/schemas/claim-verification-v1.json",
            "structured_output_mode": "json_schema_or_tool_schema",
            "app_side_schema_validation_required": True,
        },
        "model": {
            "provider": provider,
            "model": model,
            "capacity_source": capacity_source,
            "raw_response_hash": raw_response_hash,
            "response_failure": response_failure,
        },
        "summary": {
            "status": status,
            "parsed_decision_count": len(decisions),
            "ready_for_commit_envelope_count": ready_count,
            "blocked_decision_count": len(decisions) - ready_count,
            "recall_case_candidate_count": sum(1 for decision in decisions if "recall_case_candidate" in decision),
            "failure_reasons": failure_reasons,
        },
        "decisions": decisions,
        "compiler": {
            "stage": "claim_verification",
            "previous_stage": "semantic_claim_extraction",
            "next_stage": "graph_commit_envelope",
            "next_stage_requires_model_judgment": False,
            "graph_writes_require_commit_envelope": True,
        },
        "generated_at": generated_at or _artifact_generated_at({}, claim_extraction),
    }


__all__ = [
    "CLAIM_VERIFICATION_KIND",
    "CLAIM_VERIFICATION_PROMPT_VERSION",
    "CLAIM_VERIFICATION_SCHEMA_VERSION",
    "SEMANTIC_CLAIM_EXTRACTION_KIND",
    "SEMANTIC_CLAIM_EXTRACTION_PROMPT_VERSION",
    "SEMANTIC_CLAIM_EXTRACTION_SCHEMA_VERSION",
    "SOURCE_NOTE_KIND",
    "SOURCE_NOTE_SCHEMA_VERSION",
    "SOURCE_PACK_MANIFEST_KIND",
    "SOURCE_PACK_MANIFEST_SCHEMA_VERSION",
    "build_claim_verification",
    "build_semantic_claim_extraction",
    "build_source_notes",
    "build_source_pack_manifest",
]
