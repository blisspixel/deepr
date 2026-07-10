"""Deterministic ranked-retrieval metrics and paired uncertainty.

This module measures rankings against supplied binary relevance labels. It does
not create labels, judge meaning, call providers, or write application state.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

BOOTSTRAP_RESAMPLES = 9_999
BOOTSTRAP_CONFIDENCE_LEVEL = 0.95
BOOTSTRAP_METHOD = "paired_percentile_bootstrap"
BOOTSTRAP_RNG = "numpy.PCG64"
RETRIEVAL_METRIC_CASE_FIELDS = {
    "hit_at_k": "hit_at_k",
    "mean_reciprocal_rank": "reciprocal_rank",
    "mean_precision_at_k": "precision_at_k",
    "mean_recall_at_k": "recall_at_k",
    "mean_average_precision_at_k": "average_precision_at_k",
    "mean_ndcg_at_k": "ndcg_at_k",
    "mean_relevant_retrieved": "relevant_retrieved",
}
RETRIEVAL_ROUTE_METRICS = tuple(RETRIEVAL_METRIC_CASE_FIELDS)


def ranked_binary_retrieval_metrics(
    candidate_ids: Sequence[str],
    relevant_ids: Sequence[str],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Measure one ranked result list against non-empty binary labels."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("relevant_ids must not be empty")
    ranked_candidates = list(candidate_ids[:top_k])
    credited_relevant: set[str] = set()
    relevant_ranks: list[int] = []
    for rank, candidate_id in enumerate(ranked_candidates, start=1):
        if candidate_id in relevant and candidate_id not in credited_relevant:
            credited_relevant.add(candidate_id)
            relevant_ranks.append(rank)

    first_relevant_rank = relevant_ranks[0] if relevant_ranks else None
    retrieved_relevant = len(relevant_ranks)
    precision_at_k = retrieved_relevant / top_k
    recall_at_k = retrieved_relevant / len(relevant)
    average_precision_numerator = sum(index / rank for index, rank in enumerate(relevant_ranks, start=1))
    average_precision_at_k = average_precision_numerator / min(len(relevant), top_k)
    discounted_gain = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
    ideal_discounted_gain = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(relevant), top_k) + 1))
    ndcg_at_k = discounted_gain / ideal_discounted_gain
    return {
        "candidate_ids": ranked_candidates,
        "hit_at_k": first_relevant_rank is not None,
        "reciprocal_rank": 0.0 if first_relevant_rank is None else round(1.0 / first_relevant_rank, 6),
        "precision_at_k": round(precision_at_k, 6),
        "recall_at_k": round(recall_at_k, 6),
        "average_precision_at_k": round(average_precision_at_k, 6),
        "ndcg_at_k": round(ndcg_at_k, 6),
        "relevant_retrieved": retrieved_relevant,
        "relevant_total": len(relevant),
    }


def summarize_retrieval_route(case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return macro means for one route's case-level results."""
    if not case_results:
        return {"case_count": 0}
    count = len(case_results)
    return {
        "case_count": count,
        **{
            summary_field: round(sum(float(case[case_field]) for case in case_results) / count, 6)
            for summary_field, case_field in RETRIEVAL_METRIC_CASE_FIELDS.items()
        },
    }


def compare_retrieval_routes(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    baseline_label: str,
    candidate_label: str,
) -> dict[str, str]:
    """Name the point-estimate winner for every retrieval metric."""
    comparison: dict[str, str] = {}
    for metric in RETRIEVAL_ROUTE_METRICS:
        baseline_score = float(baseline.get(metric, 0.0))
        candidate_score = float(candidate.get(metric, 0.0))
        if candidate_score > baseline_score:
            comparison[metric] = candidate_label
        elif baseline_score > candidate_score:
            comparison[metric] = baseline_label
        else:
            comparison[metric] = "tie"
    return comparison


def _linear_percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * probability
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = rank - lower_index
    return ordered[lower_index] * (1.0 - weight) + ordered[upper_index] * weight


def paired_vector_bootstrap_comparison(
    baseline_cases: Sequence[Mapping[str, Any]],
    candidate_cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Estimate paired vector-minus-baseline uncertainty reproducibly."""
    if not baseline_cases or len(baseline_cases) != len(candidate_cases):
        raise ValueError("paired bootstrap requires equal non-empty route results")

    case_count = len(baseline_cases)
    deltas_by_metric = {
        summary_field: [
            float(candidate[case_field]) - float(baseline[case_field])
            for baseline, candidate in zip(baseline_cases, candidate_cases, strict=True)
        ]
        for summary_field, case_field in RETRIEVAL_METRIC_CASE_FIELDS.items()
    }
    seed_payload = json.dumps(deltas_by_metric, sort_keys=True, separators=(",", ":"))
    seed_bytes = hashlib.sha256(seed_payload.encode("utf-8")).digest()[:8]
    seed_hex = seed_bytes.hex()
    generator = np.random.Generator(np.random.PCG64(int.from_bytes(seed_bytes, "big")))
    delta_matrix = np.column_stack([deltas_by_metric[metric] for metric in RETRIEVAL_ROUTE_METRICS])
    resampled_means = np.empty((BOOTSTRAP_RESAMPLES, len(RETRIEVAL_ROUTE_METRICS)), dtype=np.float64)
    chunk_size = min(256, max(1, 250_000 // case_count))
    for start in range(0, BOOTSTRAP_RESAMPLES, chunk_size):
        stop = min(start + chunk_size, BOOTSTRAP_RESAMPLES)
        indices = generator.integers(0, case_count, size=(stop - start, case_count), dtype=np.int64)
        resampled_means[start:stop] = delta_matrix[indices].mean(axis=1)

    tail_probability = (1.0 - BOOTSTRAP_CONFIDENCE_LEVEL) / 2.0
    evidence: dict[str, dict[str, Any]] = {}
    for metric_index, (metric, deltas) in enumerate(deltas_by_metric.items()):
        metric_means = resampled_means[:, metric_index].tolist()
        lower = _linear_percentile(metric_means, tail_probability)
        upper = _linear_percentile(metric_means, 1.0 - tail_probability)
        rounded_lower = round(lower, 6)
        rounded_upper = round(upper, 6)
        evidence[metric] = {
            "mean_difference": round(sum(deltas) / case_count, 6),
            "confidence_interval": {"lower": rounded_lower, "upper": rounded_upper},
            "vector_superiority_supported": rounded_lower > 0.0,
        }

    return {
        "method": BOOTSTRAP_METHOD,
        "rng": BOOTSTRAP_RNG,
        "case_count": case_count,
        "resamples": BOOTSTRAP_RESAMPLES,
        "confidence_level": BOOTSTRAP_CONFIDENCE_LEVEL,
        "seed": seed_hex,
        "metrics": evidence,
    }


__all__ = [
    "BOOTSTRAP_CONFIDENCE_LEVEL",
    "BOOTSTRAP_METHOD",
    "BOOTSTRAP_RESAMPLES",
    "BOOTSTRAP_RNG",
    "RETRIEVAL_METRIC_CASE_FIELDS",
    "RETRIEVAL_ROUTE_METRICS",
    "compare_retrieval_routes",
    "paired_vector_bootstrap_comparison",
    "ranked_binary_retrieval_metrics",
    "summarize_retrieval_route",
]
