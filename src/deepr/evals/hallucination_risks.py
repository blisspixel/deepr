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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import runtime_data_path
from deepr.experts.consult_quality import load_consult_quality_reviews
from deepr.experts.consult_traces import load_consult_traces

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
    "false_consensus": ("dissent_flattening",),
    "ignored_dissent": ("dissent_flattening",),
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


def _coverage_gaps(observed_labels: set[str]) -> list[dict[str, str]]:
    required = {
        "false_premise_compliance": "needs false-premise eval cases and calibrated semantic review",
        "long_context_middle_loss": "needs context-position metadata before detection can be measured",
        "template_sensitivity": "needs prompt-template variant evals before example-order risk can be measured",
    }
    return [
        {
            "risk_label": label,
            "status": "not_measured",
            "reason": reason,
        }
        for label, reason in sorted(required.items())
        if label not in observed_labels
    ]


def build_hallucination_risk_report(
    *,
    trace_path: Path | None = None,
    review_dir: Path | None = None,
    trace_limit: int = 50,
    review_limit: int = 200,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a no-write hallucination-pattern advisory report."""
    traces = load_consult_traces(path=trace_path, limit=max(0, trace_limit))
    reviews = load_consult_quality_reviews(output_dir=review_dir, limit=max(0, review_limit))
    signals: list[dict[str, Any]] = []
    for trace in traces:
        signal = _trace_signal(trace)
        if signal is not None:
            signals.append(signal)
    for review in reviews:
        signal = _review_signal(review)
        if signal is not None:
            signals.append(signal)
    label_counts = Counter(label for signal in signals for label in signal.get("risk_labels", []) or [])
    observed_labels = set(label_counts)
    return {
        "schema_version": HALLUCINATION_RISK_REPORT_SCHEMA_VERSION,
        "kind": HALLUCINATION_RISK_REPORT_KIND,
        "contract": _contract(),
        "trace_count": len(traces),
        "review_count": len(reviews),
        "signal_count": len(signals),
        "risk_label_counts": dict(sorted(label_counts.items())),
        "signals": signals,
        "coverage_gaps": _coverage_gaps(observed_labels),
        "mitigation_policy": {
            "signals_inform_only": True,
            "never_blocks_answers": True,
            "never_writes_beliefs": True,
            "semantic_judgment_requires_human_or_calibrated_model": True,
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
