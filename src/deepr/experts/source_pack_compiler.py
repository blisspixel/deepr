"""Deterministic source-pack compiler primitives."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from deepr.experts.beliefs import EDGE_TYPES

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
_FACTUAL_KINDS = {"factual_claim", "fact", "external_fact", "current_fact"}
_IDEA_KINDS = {"concept", "hypothesis", "stance", "proposal", "original_idea", "original_synthesis"}
_GAP_KINDS = {"gap", "knowledge_gap", "research_gap"}
_SUPPORT_VERDICTS = {"supported", "refuted", "insufficient", "not_applicable", "unverified"}
_CONTRADICTION_VERDICTS = {"none", "possible", "contradiction", "unverified"}
_DEDUP_VERDICTS = {"new", "same_as_existing", "uncertain", "unverified"}
_TEMPORAL_VERDICTS = {"valid", "unclear", "outdated", "not_applicable"}
_EDGE_TYPES = set(EDGE_TYPES)


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


def _float_0_1(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _float_nonnegative(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, parsed)


def _int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _normalized_key(value: Any, *, default: str = "") -> str:
    text = str(value if value is not None else default).strip().lower()
    return text.replace("-", "_").replace(" ", "_") or default


def _enum_value(value: Any, allowed: set[str], *, default: str) -> str:
    normalized = _normalized_key(value, default=default)
    return normalized if normalized in allowed else default


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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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
    if claim_kind in _GAP_KINDS:
        candidate["gap"] = _gap_candidate(item, statement)
    return candidate


def _claim_kind_policy(claim_kind: str) -> dict[str, Any]:
    kind = _normalized_key(claim_kind, default="factual_claim")
    if kind in _GAP_KINDS:
        return {
            "state_type": "knowledge_gap",
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": False,
            "must_not_present_as_verified_fact": True,
            "writes_gap_backlog": True,
        }
    if kind in _IDEA_KINDS:
        return {
            "state_type": kind,
            "requires_external_support": False,
            "requires_origin_and_rationale": True,
            "requires_disconfirming_signals": True,
            "must_not_present_as_verified_fact": True,
        }
    if kind not in _FACTUAL_KINDS:
        kind = "factual_claim"
    return {
        "state_type": kind,
        "requires_external_support": True,
        "requires_origin_and_rationale": False,
        "requires_disconfirming_signals": False,
        "must_not_present_as_verified_fact": False,
    }


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


def _string_field(item: dict[str, Any], key: str) -> str:
    return str(item.get(key, "") or "").strip()


def _string_list_field(item: dict[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


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
    }


def _verification_model_judgment(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": _float_0_1(item.get("confidence")),
        "rationale": _string_field(item, "rationale"),
        "support_summary": _string_field(item, "support_summary"),
        "origin": _string_field(item, "origin"),
        "uncertainty": _string_field(item, "uncertainty"),
        "disconfirming_signals": _string_list_field(item, "disconfirming_signals"),
    }


def _edge_decision_values(
    raw_edge: dict[str, Any],
    *,
    current_candidate_id: str,
) -> dict[str, Any]:
    source_candidate_id = str(raw_edge.get("source_candidate_id", current_candidate_id) or "").strip()
    target_candidate_id = str(raw_edge.get("target_candidate_id", raw_edge.get("dst_candidate_id", "")) or "").strip()
    return {
        "source_candidate_id": source_candidate_id,
        "target_candidate_id": target_candidate_id,
        "edge_type": _enum_value(raw_edge.get("edge_type"), _EDGE_TYPES, default=""),
        "confidence": _float_0_1(raw_edge.get("confidence")),
        "rationale": _string_field(raw_edge, "rationale"),
    }


def _edge_decision_failures(edge: dict[str, Any], candidates_by_id: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    source_candidate_id = str(edge.get("source_candidate_id", "") or "")
    target_candidate_id = str(edge.get("target_candidate_id", "") or "")
    if not source_candidate_id:
        failures.append("missing_source_candidate_id")
    elif source_candidate_id not in candidates_by_id:
        failures.append("unknown_source_candidate_id")
    if not target_candidate_id:
        failures.append("missing_target_candidate_id")
    elif target_candidate_id not in candidates_by_id:
        failures.append("unknown_target_candidate_id")
    if not str(edge.get("edge_type", "") or ""):
        failures.append("invalid_edge_type")
    if source_candidate_id and target_candidate_id and source_candidate_id == target_candidate_id:
        failures.append("self_edge")
    return failures


def _edge_decision_sets(
    item: dict[str, Any],
    *,
    current_candidate_id: str,
    candidates_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edge_decisions: list[dict[str, Any]] = []
    edge_failures: list[dict[str, Any]] = []
    raw_edges = item.get("edge_decisions", [])
    if "edge_decisions" in item and not isinstance(raw_edges, list):
        return [], [{"index": 0, "failure_reasons": ["invalid_edge_decisions_field"]}]
    if not isinstance(raw_edges, list):
        raw_edges = []
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, dict):
            edge_failures.append({"index": index, "failure_reasons": ["invalid_edge_decision"]})
            continue
        edge = _edge_decision_values(raw_edge, current_candidate_id=current_candidate_id)
        failures = _edge_decision_failures(edge, candidates_by_id)
        if failures:
            edge_failures.append({"index": index, "failure_reasons": sorted(set(failures))})
            continue
        edge_decision = {
            "source_candidate_id": edge["source_candidate_id"],
            "target_candidate_id": edge["target_candidate_id"],
            "edge_type": edge["edge_type"],
        }
        if "confidence" in raw_edge:
            edge_decision["confidence"] = edge["confidence"]
        if edge["rationale"]:
            edge_decision["rationale"] = edge["rationale"]
        edge_decisions.append(edge_decision)
    return edge_decisions, edge_failures


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
) -> list[str]:
    failure_reasons: list[str] = []
    if policy.get("requires_external_support") and verdicts["support"] != "supported":
        failure_reasons.append("factual_support_not_verified")
    if policy.get("requires_disconfirming_signals") and not model_judgment["disconfirming_signals"]:
        failure_reasons.append("missing_disconfirming_signals")
    if verdicts["contradiction"] == "contradiction":
        failure_reasons.append("contradiction_unresolved")
    if verdicts["deduplication"] == "same_as_existing":
        failure_reasons.append("duplicate_existing_belief")
    if verdicts["temporal_scope"] == "outdated":
        failure_reasons.append("temporal_scope_rejected")
    return failure_reasons + _idea_policy_failures(policy, model_judgment)


def _verification_decision(
    item: dict[str, Any],
    *,
    candidates_by_id: dict[str, dict[str, Any]],
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
    )
    failure_reasons = _candidate_verification_failures(candidate_id, candidate)
    failure_reasons.extend(_policy_verification_failures(policy, verdicts, model_judgment))
    failure_reasons = sorted(set(failure_reasons))
    ready = bool(candidate is not None and not failure_reasons)
    return {
        "candidate_id": candidate_id,
        "claim_kind": str((candidate or {}).get("claim_kind", item.get("claim_kind", "")) or ""),
        "state_policy": policy,
        "verdicts": verdicts,
        "model_judgment": model_judgment,
        "edge_decisions": edge_decisions,
        "edge_decision_failures": edge_decision_failures,
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
) -> dict[str, Any]:
    """Compile model claim output into a verifier-gated candidate envelope.

    This stage records semantic model judgment, but it still writes no expert
    state. Deterministic code checks only shape, score bounds, source-note
    references, prompt/schema versions, and the graph-write gate. Grounding,
    contradiction, deduplication, novelty, and temporal interpretation remain
    downstream model-verifier work.
    """
    parsed, raw_response_hash, response_failure = _response_from_model_output(model_output)
    response_failure = response_failure or _claim_response_shape_failure(parsed)
    notes, windows_by_note = _note_index(source_notes)
    candidates = [
        _claim_candidate(item, notes=notes, windows_by_note=windows_by_note) for item in _raw_claim_items(parsed)
    ]
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
            "parsed_candidate_count": len(candidates),
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
) -> dict[str, Any]:
    """Compile verifier output into graph-commit readiness decisions.

    This is still a no-write envelope. It records semantic verifier judgment and
    type-specific policy gates, but graph mutation waits for a later commit
    envelope that can atomically write beliefs and temporal edges.
    """
    parsed, raw_response_hash, response_failure = _response_from_model_output(model_output)
    response_failure = response_failure or _verification_response_shape_failure(parsed)
    candidates_by_id = _candidate_by_id(claim_extraction)
    decisions = [
        _verification_decision(item, candidates_by_id=candidates_by_id) for item in _raw_verification_items(parsed)
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
