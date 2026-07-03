"""$0 judge-calibration eval over consult-quality reviews (ROADMAP items 5, 9).

Before a calibrated-model judge's scores can be trusted as a product metric,
you have to know how well that judge agrees with a human anchor on the same
work. This eval measures exactly that: it pairs a human review and a
calibrated-model review of the *same* consult trace and reports their
per-dimension agreement - mean absolute error, directional bias, exact- and
within-tolerance-agreement rates - plus decision agreement.

Every number here is a deterministic statistic over scores humans and judges
already recorded; this module computes no scores and judges no answer meaning.
Agreement is not correctness: a judge that matches a biased human matches a
biased human. The report is measured visibility to gate trust, not a claim
that either score is right.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from deepr.experts.consult_quality import review_score_map

JUDGE_CALIBRATION_REPORT_SCHEMA_VERSION = "deepr-judge-calibration-report-v1"
JUDGE_CALIBRATION_REPORT_KIND = "deepr.eval.judge_calibration"

HUMAN_JUDGE = "human"
MODEL_JUDGE = "calibrated_model"

DEFAULT_AGREEMENT_TOLERANCE = 1.0
# Fewer than this many independently paired traces and an agreement number is
# noise, not signal. Counted in traces (independent samples), not in
# trace x dimension deltas, so multiple rubric dimensions of one trace do not
# inflate the apparent evidence.
MIN_PAIRED_TRACES_FOR_SIGNAL = 5


def _judge_type(review: dict[str, Any]) -> str:
    judge = review.get("judge")
    return str(judge.get("type", "")) if isinstance(judge, dict) else ""


def _trace_id(review: dict[str, Any]) -> str:
    source = review.get("source")
    return str(source.get("source_trace_id", "")) if isinstance(source, dict) else ""


def _generated_at(review: dict[str, Any]) -> str:
    return str(review.get("generated_at", "") or "")


def _decision(review: dict[str, Any]) -> str:
    decision = review.get("decision")
    if isinstance(decision, dict):
        return str(decision.get("decision", "") or "").strip()
    return str(decision or "").strip()


@dataclass(frozen=True)
class PairedTrace:
    """The latest human review and latest model review of one shared trace."""

    trace_id: str
    human: dict[str, Any]
    model: dict[str, Any]


def pair_reviews_by_trace(reviews: Sequence[dict[str, Any]]) -> list[PairedTrace]:
    """Pair the latest human and latest model review for each shared trace.

    A trace with reviews from only one judge type is not a pair (it carries no
    agreement signal) and is excluded. When a judge type has several reviews of
    a trace, the newest by ``generated_at`` is the anchor, so re-review updates
    rather than double-counts. Traces sort by id for a stable report order.
    """
    latest: dict[str, dict[str, dict[str, Any]]] = {}
    for review in reviews:
        trace_id = _trace_id(review)
        judge_type = _judge_type(review)
        if not trace_id or judge_type not in (HUMAN_JUDGE, MODEL_JUDGE):
            continue
        by_type = latest.setdefault(trace_id, {})
        current = by_type.get(judge_type)
        if current is None or _generated_at(review) >= _generated_at(current):
            by_type[judge_type] = review

    pairs: list[PairedTrace] = []
    for trace_id in sorted(latest):
        by_type = latest[trace_id]
        if HUMAN_JUDGE in by_type and MODEL_JUDGE in by_type:
            pairs.append(PairedTrace(trace_id, by_type[HUMAN_JUDGE], by_type[MODEL_JUDGE]))
    return pairs


def _agreement_metrics(deltas: list[float], *, tolerance: float) -> dict[str, Any]:
    count = len(deltas)
    if count == 0:
        return {
            "pair_count": 0,
            "mean_absolute_error": 0.0,
            "mean_signed_error": 0.0,
            "exact_agreement_rate": 0.0,
            "within_tolerance_rate": 0.0,
        }
    return {
        "pair_count": count,
        "mean_absolute_error": round(sum(abs(d) for d in deltas) / count, 4),
        # Positive means the model judge scores higher than the human anchor.
        "mean_signed_error": round(sum(deltas) / count, 4),
        "exact_agreement_rate": round(sum(1 for d in deltas if d == 0) / count, 4),
        "within_tolerance_rate": round(sum(1 for d in deltas if abs(d) <= tolerance) / count, 4),
    }


def build_judge_calibration_report(
    reviews: Sequence[dict[str, Any]],
    *,
    expert_name: str = "",
    agreement_tolerance: float = DEFAULT_AGREEMENT_TOLERANCE,
) -> dict[str, Any]:
    """Build a read-only judge-vs-human agreement report from paired reviews."""
    tolerance = max(0.0, float(agreement_tolerance))
    pairs = pair_reviews_by_trace(reviews)

    deltas_by_dimension: dict[str, list[float]] = {}
    all_deltas: list[float] = []
    decision_matches = 0
    decision_comparable = 0
    for pair in pairs:
        human_scores = review_score_map(pair.human)
        model_scores = review_score_map(pair.model)
        for dimension in sorted(set(human_scores) & set(model_scores)):
            delta = model_scores[dimension] - human_scores[dimension]
            deltas_by_dimension.setdefault(dimension, []).append(delta)
            all_deltas.append(delta)
        human_decision = _decision(pair.human)
        model_decision = _decision(pair.model)
        if human_decision and model_decision:
            decision_comparable += 1
            decision_matches += int(human_decision == model_decision)

    per_dimension = {
        dimension: _agreement_metrics(deltas, tolerance=tolerance)
        for dimension, deltas in sorted(deltas_by_dimension.items())
    }
    overall = _agreement_metrics(all_deltas, tolerance=tolerance)
    decision_agreement = {
        "comparable_trace_count": decision_comparable,
        "agreement_rate": round(decision_matches / decision_comparable, 4) if decision_comparable else 0.0,
    }

    return {
        "schema_version": JUDGE_CALIBRATION_REPORT_SCHEMA_VERSION,
        "kind": JUDGE_CALIBRATION_REPORT_KIND,
        "expert": {"name": expert_name},
        "contract": {
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_beliefs": False,
            "semantic_judgment": False,
            "measurement_only": True,
            "note": "agreement between recorded scores; not a verdict that either judge is correct",
        },
        "request": {
            "review_count": len(reviews),
            "paired_trace_count": len(pairs),
            "agreement_tolerance": tolerance,
        },
        "summary": {
            "paired_trace_count": len(pairs),
            "scored_pair_count": overall["pair_count"],
            "sufficient_data": len(pairs) >= MIN_PAIRED_TRACES_FOR_SIGNAL,
            "min_paired_traces_for_signal": MIN_PAIRED_TRACES_FOR_SIGNAL,
        },
        "overall_agreement": overall,
        "per_dimension_agreement": per_dimension,
        "decision_agreement": decision_agreement,
        "generated_at": datetime.now(UTC).isoformat(),
    }


__all__ = [
    "JUDGE_CALIBRATION_REPORT_KIND",
    "JUDGE_CALIBRATION_REPORT_SCHEMA_VERSION",
    "MIN_PAIRED_TRACES_FOR_SIGNAL",
    "PairedTrace",
    "build_judge_calibration_report",
    "pair_reviews_by_trace",
]
