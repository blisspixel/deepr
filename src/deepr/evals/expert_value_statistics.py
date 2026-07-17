"""Deterministic paired uncertainty for longitudinal expert-value reviews.

The statistics operate only on human-supplied scores and labels from a complete
case-arm matrix. They report uncertainty without naming a winner or converting
an interval into a policy gate.
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

_SCORE_FIELDS = ("correctness", "source_relevance", "factual_support", "uncertainty_calibration")
_OPTIONAL_BOOLEAN_FIELDS = (
    "invalidated_belief_reused",
    "negative_transfer_observed",
    "retained_correctness",
    "forward_transfer_observed",
)


def _linear_percentile(values: np.ndarray, probability: float) -> float:
    ordered = np.sort(values)
    rank = (len(ordered) - 1) * probability
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return float(ordered[lower_index])
    weight = rank - lower_index
    return float(ordered[lower_index] * (1.0 - weight) + ordered[upper_index] * weight)


def _metric_interval(metric: str, deltas: Sequence[float]) -> dict[str, Any]:
    seed_payload = json.dumps({"metric": metric, "deltas": list(deltas)}, sort_keys=True, separators=(",", ":"))
    seed_bytes = hashlib.sha256(seed_payload.encode("utf-8")).digest()[:8]
    generator = np.random.Generator(np.random.PCG64(int.from_bytes(seed_bytes, "big")))
    delta_array = np.asarray(deltas, dtype=np.float64)
    resampled_means = np.empty(BOOTSTRAP_RESAMPLES, dtype=np.float64)
    case_count = len(delta_array)
    chunk_size = min(512, max(1, 250_000 // case_count))
    for start in range(0, BOOTSTRAP_RESAMPLES, chunk_size):
        stop = min(start + chunk_size, BOOTSTRAP_RESAMPLES)
        indices = generator.integers(0, case_count, size=(stop - start, case_count), dtype=np.int64)
        resampled_means[start:stop] = delta_array[indices].mean(axis=1)
    tail = (1.0 - BOOTSTRAP_CONFIDENCE_LEVEL) / 2.0
    return {
        "case_count": case_count,
        "mean_difference": round(float(delta_array.mean()), 6),
        "confidence_interval": {
            "lower": round(_linear_percentile(resampled_means, tail), 6),
            "upper": round(_linear_percentile(resampled_means, 1.0 - tail), 6),
        },
        "seed": seed_bytes.hex(),
    }


def paired_bootstrap_intervals(deltas_by_metric: Mapping[str, Sequence[float]]) -> dict[str, Any]:
    """Return reproducible percentile intervals for non-empty paired deltas."""
    nonempty = {metric: list(deltas) for metric, deltas in deltas_by_metric.items() if deltas}
    if not nonempty:
        raise ValueError("paired bootstrap requires at least one non-empty metric")
    if any(not math.isfinite(value) for deltas in nonempty.values() for value in deltas):
        raise ValueError("paired bootstrap deltas must be finite")
    return {
        "method": BOOTSTRAP_METHOD,
        "rng": BOOTSTRAP_RNG,
        "resamples": BOOTSTRAP_RESAMPLES,
        "confidence_level": BOOTSTRAP_CONFIDENCE_LEVEL,
        "metrics": {metric: _metric_interval(metric, deltas) for metric, deltas in nonempty.items()},
    }


def expert_value_paired_bootstrap(
    review: Any,
    *,
    target_arm: str,
    comparator_arm: str,
) -> dict[str, Any]:
    """Build paired target-minus-comparator intervals from a review matrix."""
    trials = {(trial.acceptance_case_id, trial.arm): trial for trial in review.trials}
    deltas: dict[str, list[float]] = {field: [] for field in _SCORE_FIELDS}
    deltas.update(
        {
            "false_support_observed": [],
            "invalidated_belief_reused": [],
            "negative_transfer_observed": [],
            "retained_correctness": [],
            "forward_transfer_observed": [],
            "update_completed": [],
        }
    )
    for case in review.cases:
        target = trials[(case.acceptance_case_id, target_arm)]
        comparator = trials[(case.acceptance_case_id, comparator_arm)]
        for field in _SCORE_FIELDS:
            deltas[field].append(
                float(getattr(target.semantic_attestation, field) - getattr(comparator.semantic_attestation, field))
            )
        deltas["false_support_observed"].append(
            float(target.semantic_attestation.false_support_observed)
            - float(comparator.semantic_attestation.false_support_observed)
        )
        for field in _OPTIONAL_BOOLEAN_FIELDS:
            target_value = getattr(target.semantic_attestation, field)
            comparator_value = getattr(comparator.semantic_attestation, field)
            if target_value is not None and comparator_value is not None:
                deltas[field].append(float(target_value) - float(comparator_value))
        target_update = target.measurements.update_completed
        comparator_update = comparator.measurements.update_completed
        if target_update is not None and comparator_update is not None:
            deltas["update_completed"].append(float(target_update) - float(comparator_update))
    return paired_bootstrap_intervals(deltas)


__all__ = [
    "BOOTSTRAP_CONFIDENCE_LEVEL",
    "BOOTSTRAP_METHOD",
    "BOOTSTRAP_RESAMPLES",
    "BOOTSTRAP_RNG",
    "expert_value_paired_bootstrap",
    "paired_bootstrap_intervals",
]
