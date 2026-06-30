"""Advisory hallucination-pattern risk reporting.

This report is a routing surface, not a truth verifier. It collects durable
review signals and structural trace metadata so operators can pick regression
cases, prompt variants, retrieval changes, and review queues without letting
deterministic code decide answer meaning.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import runtime_data_path
from deepr.experts.consult_quality import load_consult_quality_reviews
from deepr.experts.consult_traces import load_consult_traces
from deepr.experts.handoff import HANDOFF_KIND, HANDOFF_SCHEMA_VERSION
from deepr.experts.source_pack_compiler import SOURCE_PACK_MANIFEST_KIND, SOURCE_PACK_MANIFEST_SCHEMA_VERSION

HALLUCINATION_RISK_REPORT_SCHEMA_VERSION = "deepr-hallucination-risk-report-v1"
HALLUCINATION_RISK_REPORT_KIND = "deepr.eval.hallucination_risk_report"

_HIGH_STAKES_TERMS = {
    "attorney",
    "clinical",
    "compliance",
    "court",
    "diagnosis",
    "financial",
    "healthcare",
    "legal",
    "liability",
    "medical",
    "medicine",
    "policy",
    "regulatory",
    "statute",
}

_FAILURE_LABEL_RISKS = {
    "missing_current_context": ("citation_provenance_gap", "temporal_freshness_mismatch"),
    "unsupported_factual_claim": ("unsupported_factual_claim", "citation_provenance_gap"),
    "stale_claim_promoted_as_current": ("temporal_freshness_mismatch",),
    "false_premise_compliance": ("false_premise_compliance", "overconfident_uncertainty_failure"),
    "false_consensus": ("dissent_flattening",),
    "ignored_dissent": ("dissent_flattening",),
    "template_order_sensitivity": ("template_sensitivity",),
    "thin_or_generic_answer": ("thin_confabulation_risk",),
    "unlabeled_hypothesis": ("unlabeled_hypothesis", "overconfident_uncertainty_failure"),
    "not_actionable_for_host_agent": ("answer_quality_review_needed",),
}

_LOW_DIMENSION_RISKS = {
    "uses_expert_state": ("context_gap",),
    "surfaces_uncertainty": ("overconfident_uncertainty_failure",),
    "preserves_dissent": ("dissent_flattening",),
    "grounded_when_factual": ("unsupported_factual_claim", "citation_provenance_gap"),
    "original_thought": ("unlabeled_hypothesis",),
}

_PROMPT_REGRESSION_FOCUS = {
    "answer_quality_review_needed": "tighten reviewed-answer remediation instructions",
    "citation_provenance_gap": "require source-backed factual claims or explicit unverified labels",
    "context_gap": "require visible use of selected expert context before synthesis",
    "dissent_flattening": "preserve disagreements and unresolved tradeoffs in synthesis",
    "false_premise_compliance": "challenge or qualify unsupported premises before answering",
    "overconfident_uncertainty_failure": "surface uncertainty, stale context, and open questions",
    "template_sensitivity": "check answer stability across prompt-template and example-order variants",
    "temporal_freshness_mismatch": "force dated claims to carry freshness and cutoff language",
    "thin_confabulation_risk": "require concrete evidence, decision criteria, or next research action",
    "unlabeled_hypothesis": "label hypotheses and original synthesis separately from verified facts",
    "unsupported_factual_claim": "ground factual claims or route them to review before reuse",
}
_PROMPT_REGRESSION_SURFACES = {"consult_trace", "consult_quality_review"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "writes_state": False,
        "writes_beliefs": False,
        "semantic_verdict": False,
        "lexical_verdict_allowed": False,
        "blocks_answers": False,
        "risk_labels_are_advisory": True,
        "deterministic_labels_are_routing_only": True,
        "source_path_exposed": False,
    }


def _stable_id(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json_artifact(path: Path, *, schema_version: str, kind: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != schema_version:
        return None
    if payload.get("kind") != kind:
        return None
    return payload


def _sorted_json_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []

    def modified_at(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(root.glob("*.json"), key=modified_at, reverse=True)


def _dedupe_paths(paths: Sequence[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def load_handoff_artifacts(*, paths: Sequence[Path] | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Load explicit handoff artifacts without exposing local paths."""
    max_items = max(0, limit)
    if max_items == 0:
        return []

    loaded: list[dict[str, Any]] = []
    for path in _dedupe_paths(paths or ()):
        artifact = _load_json_artifact(path, schema_version=HANDOFF_SCHEMA_VERSION, kind=HANDOFF_KIND)
        if artifact is None:
            continue
        loaded.append(artifact)
        if len(loaded) >= max_items:
            break
    return loaded


def load_source_pack_manifests(
    *,
    paths: Sequence[Path] | None = None,
    directory: Path | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Load explicit source-pack manifest artifacts without exposing local paths."""
    max_items = max(0, limit)
    if max_items == 0:
        return []

    candidate_paths = list(paths or ())
    if directory is not None:
        candidate_paths.extend(_sorted_json_paths(directory))

    loaded: list[dict[str, Any]] = []
    for path in _dedupe_paths(candidate_paths):
        artifact = _load_json_artifact(
            path,
            schema_version=SOURCE_PACK_MANIFEST_SCHEMA_VERSION,
            kind=SOURCE_PACK_MANIFEST_KIND,
        )
        if artifact is None:
            continue
        loaded.append(artifact)
        if len(loaded) >= max_items:
            break
    return loaded


def _score_map(review: dict[str, Any]) -> dict[str, float]:
    scores = {}
    for item in review.get("scores", []) or []:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension", "")).strip()
        if not dimension:
            continue
        try:
            scores[dimension] = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            continue
    return scores


def _source_ref_from_review(review: dict[str, Any]) -> dict[str, str]:
    source = review.get("source") if isinstance(review.get("source"), dict) else {}
    return {
        "review_id": str(review.get("review_id", "")),
        "source_trace_id": str(source.get("source_trace_id", "")),
        "case_id": str(source.get("case_id", "")),
        "question_hash": str(source.get("question_hash", "")),
        "question_preview": str(source.get("question_preview", "")),
    }


def _review_signal(review: dict[str, Any]) -> dict[str, Any] | None:
    labels: set[str] = set()
    basis: list[str] = []

    for failure_label in review.get("failure_labels", []) or []:
        mapped = _FAILURE_LABEL_RISKS.get(str(failure_label), ("answer_quality_review_needed",))
        labels.update(mapped)
        basis.append(f"reviewed_failure_label:{failure_label}")

    scores = _score_map(review)
    for dimension, mapped in _LOW_DIMENSION_RISKS.items():
        score = scores.get(dimension)
        if score is not None and score < 4.0:
            labels.update(mapped)
            basis.append(f"review_score_below_policy:{dimension}")

    status = str(review.get("review_status", ""))
    if status and status != "accepted":
        labels.add("answer_quality_review_needed")
        basis.append(f"review_status:{status}")

    if not labels:
        return None

    source_ref = _source_ref_from_review(review)
    signal_id = "hallucination_signal_" + _stable_id(
        [
            "review",
            source_ref["review_id"],
            source_ref["source_trace_id"],
            ",".join(sorted(labels)),
        ]
    )
    return {
        "signal_id": signal_id,
        "surface": "consult_quality_review",
        "source_ref": source_ref,
        "risk_labels": sorted(labels),
        "basis": basis,
        "review_status": "reviewed",
        "judgment_source": "human_or_calibrated_model_review",
        "semantic_verdict": False,
        "recommended_action": "add_to_consult_quality_regression_pool",
    }


def _trace_selected_context_count(trace: dict[str, Any]) -> int:
    packet = trace.get("context_packet") if isinstance(trace.get("context_packet"), dict) else {}
    selected = packet.get("selected", []) if isinstance(packet, dict) else []
    if not isinstance(selected, list):
        return 0
    return sum(1 for item in selected if isinstance(item, dict) and bool(item.get("context")))


def _trace_selected_context_items(trace: dict[str, Any]) -> list[dict[str, Any]]:
    packet = trace.get("context_packet") if isinstance(trace.get("context_packet"), dict) else {}
    selected = packet.get("selected", []) if isinstance(packet, dict) else []
    if not isinstance(selected, list):
        return []
    return [item for item in selected if isinstance(item, dict) and bool(item.get("context"))]


def _context_position_metadata(traces: list[dict[str, Any]]) -> dict[str, Any]:
    selected_context_slot_count = 0
    position_metadata_slot_count = 0
    middle_context_slot_count = 0
    trace_count_with_position_metadata = 0
    trace_count_with_middle_context = 0

    for trace in traces:
        trace_has_position_metadata = False
        trace_has_middle_context = False
        for item in _trace_selected_context_items(trace):
            selected_context_slot_count += 1
            position = item.get("context_position") if isinstance(item.get("context_position"), dict) else {}
            if not position:
                continue
            position_metadata_slot_count += 1
            trace_has_position_metadata = True
            if str(position.get("selected_order_zone", "")) == "middle":
                middle_context_slot_count += 1
                trace_has_middle_context = True
        if trace_has_position_metadata:
            trace_count_with_position_metadata += 1
        if trace_has_middle_context:
            trace_count_with_middle_context += 1

    return {
        "source": "consult_trace_selected_order",
        "trace_count": len(traces),
        "trace_count_with_position_metadata": trace_count_with_position_metadata,
        "trace_count_with_middle_context": trace_count_with_middle_context,
        "selected_context_slot_count": selected_context_slot_count,
        "position_metadata_slot_count": position_metadata_slot_count,
        "middle_context_slot_count": middle_context_slot_count,
        "token_offsets_available": False,
        "semantic_verdict": False,
        "writes_state": False,
        "measures_long_context_middle_loss": False,
    }


def _trace_question(trace: dict[str, Any]) -> str:
    input_block = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    return str(input_block.get("question", ""))


def _trace_structural_labels(trace: dict[str, Any]) -> tuple[list[str], list[str]]:
    labels: set[str] = set()
    basis: list[str] = []
    question = _trace_question(trace).lower()
    if any(term in question for term in _HIGH_STAKES_TERMS):
        labels.add("high_stakes_review_needed")
        basis.append("high_stakes_keyword_router")

    if _trace_selected_context_count(trace) == 0:
        labels.add("context_gap")
        basis.append("selected_context_count:0")

    for check in trace.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name", ""))
        status = str(check.get("status", ""))
        if status in {"failed", "warning"} and name == "perspective_context_packet":
            labels.add("context_gap")
            basis.append(f"trace_check:{name}:{status}")

    return sorted(labels), basis


def _trace_signal(trace: dict[str, Any]) -> dict[str, Any] | None:
    labels, basis = _trace_structural_labels(trace)
    if not labels:
        return None
    input_block = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    trace_id = str(trace.get("trace_id", ""))
    signal_id = "hallucination_signal_" + _stable_id(["trace", trace_id, ",".join(labels)])
    return {
        "signal_id": signal_id,
        "surface": "consult_trace",
        "source_ref": {
            "trace_id": trace_id,
            "question_hash": str(input_block.get("question_hash", "")),
            "question_preview": " ".join(_trace_question(trace).split())[:160],
        },
        "risk_labels": labels,
        "basis": basis,
        "review_status": "needs_review",
        "judgment_source": "deterministic_router",
        "semantic_verdict": False,
        "recommended_action": "route_to_human_or_calibrated_model_review",
    }


def _has_high_stakes_text(values: Sequence[str]) -> bool:
    joined = " ".join(values).lower()
    return any(term in joined for term in _HIGH_STAKES_TERMS)


def _handoff_signal(handoff: dict[str, Any]) -> dict[str, Any] | None:
    labels: set[str] = set()
    basis: list[str] = []
    expert = handoff.get("expert") if isinstance(handoff.get("expert"), dict) else {}
    summary = handoff.get("summary") if isinstance(handoff.get("summary"), dict) else {}
    limits = handoff.get("limits") if isinstance(handoff.get("limits"), dict) else {}
    grounding = summary.get("grounding_assurance") if isinstance(summary.get("grounding_assurance"), dict) else {}

    claim_count = _int_value(summary.get("claim_count"))
    unverified_count = _int_value(grounding.get("unverified"))
    if unverified_count > 0:
        labels.add("grounding_assurance_gap")
        basis.append(f"handoff_unverified_claim_count:{unverified_count}")

    contested_count = _int_value(summary.get("contested_open_count"))
    if contested_count > 0:
        labels.add("dissent_review_needed")
        basis.append(f"handoff_contested_open_count:{contested_count}")

    max_claims = _int_value(limits.get("max_claims"), default=claim_count)
    if claim_count > max_claims:
        labels.add("handoff_truncation_review_needed")
        basis.append(f"handoff_claim_limit:{max_claims}/{claim_count}")

    expert_name = str(expert.get("name", "") or "")
    domain = str(expert.get("domain", "") or "")
    description = str(expert.get("description", "") or "")
    if _has_high_stakes_text([expert_name, domain, description]):
        labels.add("high_stakes_review_needed")
        basis.append("handoff_high_stakes_metadata_router")

    if not labels:
        return None

    generated_at = str(handoff.get("generated_at", "") or "")
    handoff_id = _stable_id(["handoff", expert_name, domain, generated_at, ",".join(sorted(labels))])
    return {
        "signal_id": f"hallucination_signal_{handoff_id}",
        "surface": "expert_handoff",
        "source_ref": {
            "handoff_id": handoff_id,
            "expert_name": expert_name,
            "domain": domain,
            "generated_at": generated_at,
            "claim_count": str(claim_count),
        },
        "risk_labels": sorted(labels),
        "basis": basis,
        "review_status": "needs_review",
        "judgment_source": "deterministic_router",
        "semantic_verdict": False,
        "recommended_action": "review_handoff_grounding_and_contested_claims",
    }


def _source_pack_manifest_signal(manifest: dict[str, Any]) -> dict[str, Any] | None:
    labels: set[str] = set()
    basis: list[str] = []
    source_pack = manifest.get("source_pack") if isinstance(manifest.get("source_pack"), dict) else {}
    summary = manifest.get("manifest") if isinstance(manifest.get("manifest"), dict) else {}

    source_count = _int_value(summary.get("source_entry_count"))
    if source_count == 0:
        labels.add("context_gap")
        basis.append("source_pack_source_entry_count:0")

    missing_hash_count = _int_value(summary.get("missing_content_hash_count"))
    invalid_hash_count = _int_value(summary.get("invalid_content_hash_count"))
    if missing_hash_count > 0 or invalid_hash_count > 0:
        labels.add("citation_provenance_gap")
        basis.append(f"source_pack_content_hash_gaps:{missing_hash_count + invalid_hash_count}")

    if source_count > 0 and not bool(summary.get("ready_for_semantic_compile", False)):
        labels.add("source_pack_compile_blocked")
        basis.append("source_pack_ready_for_semantic_compile:false")

    retrieved_count = _int_value(source_pack.get("retrieved_source_count"), default=source_count)
    declared_count = _int_value(source_pack.get("source_count"), default=source_count)
    if declared_count > retrieved_count:
        labels.add("context_gap")
        basis.append(f"source_pack_retrieved_source_count:{retrieved_count}/{declared_count}")

    generated_at = str(source_pack.get("generated_at", "") or "")
    if not generated_at:
        labels.add("temporal_freshness_mismatch")
        basis.append("source_pack_generated_at:missing")

    query = str(source_pack.get("query", "") or "")
    topic = str(source_pack.get("topic", "") or "")
    if _has_high_stakes_text([query, topic]):
        labels.add("high_stakes_review_needed")
        basis.append("source_pack_high_stakes_query_router")

    if not labels:
        return None

    manifest_id = _stable_id(
        [
            "source_pack_manifest",
            _stable_hash(query),
            _stable_hash(topic),
            str(manifest.get("generated_at", "") or ""),
            ",".join(sorted(labels)),
        ]
    )
    return {
        "signal_id": f"hallucination_signal_{manifest_id}",
        "surface": "source_pack_manifest",
        "source_ref": {
            "manifest_id": manifest_id,
            "query_hash": _stable_hash(query),
            "topic_hash": _stable_hash(topic),
            "generated_at": str(manifest.get("generated_at", "") or ""),
            "source_count": str(source_count),
        },
        "risk_labels": sorted(labels),
        "basis": basis,
        "review_status": "needs_review",
        "judgment_source": "deterministic_router",
        "semantic_verdict": False,
        "recommended_action": "repair_source_pack_provenance_or_route_to_review",
    }


def _coverage_gaps(
    observed_labels: set[str],
    *,
    context_position_metadata: dict[str, Any],
) -> list[dict[str, str]]:
    required = {
        "false_premise_compliance": "needs false-premise eval cases and calibrated semantic review",
        "long_context_middle_loss": "needs context-position metadata before detection can be measured",
        "template_sensitivity": "needs prompt-template variant evals before example-order risk can be measured",
    }
    if _int_value(context_position_metadata.get("position_metadata_slot_count")) > 0:
        required["long_context_middle_loss"] = (
            "selected-order context-position metadata is present; calibrated long-context eval cases are still needed "
            "before detection can be measured"
        )
    return [
        {
            "risk_label": label,
            "status": "not_measured",
            "reason": reason,
        }
        for label, reason in sorted(required.items())
        if label not in observed_labels
    ]


def _prompt_regression_candidates(signals: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    max_candidates = max(0, limit)
    if max_candidates == 0:
        return []

    candidates: list[dict[str, Any]] = []
    for signal in signals:
        surface = str(signal.get("surface", ""))
        if surface not in _PROMPT_REGRESSION_SURFACES:
            continue

        labels = sorted(
            {str(label) for label in signal.get("risk_labels", []) or [] if str(label) in _PROMPT_REGRESSION_FOCUS}
        )
        if not labels:
            continue

        source_ref = signal.get("source_ref") if isinstance(signal.get("source_ref"), dict) else {}
        candidates.append(
            {
                "candidate_id": "prompt_regression_" + _stable_id([str(signal.get("signal_id", "")), ",".join(labels)]),
                "source_signal_id": str(signal.get("signal_id", "")),
                "surface": surface,
                "source_ref": {str(key): str(value) for key, value in source_ref.items() if isinstance(key, str)},
                "risk_labels": labels,
                "selection_reason": "advisory_risk_label",
                "prompt_focus": [_PROMPT_REGRESSION_FOCUS[label] for label in labels],
                "review_status": str(signal.get("review_status", "")),
                "judgment_source": str(signal.get("judgment_source", "")),
                "semantic_verdict": False,
                "writes_state": False,
                "recommended_action": "add_to_consult_prompt_regression_selection",
            }
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def build_hallucination_risk_report(
    *,
    trace_path: Path | None = None,
    review_dir: Path | None = None,
    handoff_paths: Sequence[Path] | None = None,
    source_pack_manifest_paths: Sequence[Path] | None = None,
    source_pack_manifest_dir: Path | None = None,
    trace_limit: int = 50,
    review_limit: int = 200,
    handoff_limit: int = 50,
    source_pack_limit: int = 100,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a no-write hallucination-pattern advisory report."""
    traces = load_consult_traces(path=trace_path, limit=max(0, trace_limit))
    reviews = load_consult_quality_reviews(output_dir=review_dir, limit=max(0, review_limit))
    handoffs = load_handoff_artifacts(paths=handoff_paths, limit=max(0, handoff_limit))
    source_pack_manifests = load_source_pack_manifests(
        paths=source_pack_manifest_paths,
        directory=source_pack_manifest_dir,
        limit=max(0, source_pack_limit),
    )
    signals: list[dict[str, Any]] = []
    for trace in traces:
        signal = _trace_signal(trace)
        if signal is not None:
            signals.append(signal)
    for review in reviews:
        signal = _review_signal(review)
        if signal is not None:
            signals.append(signal)
    for handoff in handoffs:
        signal = _handoff_signal(handoff)
        if signal is not None:
            signals.append(signal)
    for manifest in source_pack_manifests:
        signal = _source_pack_manifest_signal(manifest)
        if signal is not None:
            signals.append(signal)
    label_counts = Counter(label for signal in signals for label in signal.get("risk_labels", []) or [])
    observed_labels = set(label_counts)
    prompt_regression_candidates = _prompt_regression_candidates(signals)
    context_position_metadata = _context_position_metadata(traces)
    return {
        "schema_version": HALLUCINATION_RISK_REPORT_SCHEMA_VERSION,
        "kind": HALLUCINATION_RISK_REPORT_KIND,
        "contract": _contract(),
        "trace_count": len(traces),
        "review_count": len(reviews),
        "handoff_count": len(handoffs),
        "source_pack_manifest_count": len(source_pack_manifests),
        "signal_count": len(signals),
        "risk_label_counts": dict(sorted(label_counts.items())),
        "signals": signals,
        "prompt_regression_candidate_count": len(prompt_regression_candidates),
        "prompt_regression_candidates": prompt_regression_candidates,
        "context_position_metadata": context_position_metadata,
        "coverage_gaps": _coverage_gaps(
            observed_labels,
            context_position_metadata=context_position_metadata,
        ),
        "mitigation_policy": {
            "signals_inform_only": True,
            "never_blocks_answers": True,
            "never_writes_beliefs": True,
            "semantic_judgment_requires_human_or_calibrated_model": True,
            "prompt_regression_selection_uses_advisory_labels_only": True,
            "recommended_uses": [
                "prompt_variant_selection",
                "retrieval_strategy_review",
                "consult_quality_regression_selection",
                "human_review_queue",
            ],
        },
        "generated_at": (generated_at or _utc_now()).isoformat(),
    }


def write_hallucination_risk_report(report: dict[str, Any], *, output_dir: Path | None = None) -> Path:
    """Write a hallucination risk report under the configured benchmarks directory."""
    root = output_dir or runtime_data_path("benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"hallucination_risks_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path
