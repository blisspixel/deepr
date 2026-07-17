"""Tests for deterministic paired expert-value uncertainty intervals."""

from __future__ import annotations

import pytest

from deepr.evals.expert_value_statistics import paired_bootstrap_intervals


def test_paired_bootstrap_is_deterministic_and_reports_no_winner() -> None:
    deltas = {"correctness": [1.0, -1.0, 2.0, 0.0]}

    first = paired_bootstrap_intervals(deltas)
    second = paired_bootstrap_intervals(deltas)
    metric = first["metrics"]["correctness"]

    assert first == second
    assert first["method"] == "paired_percentile_bootstrap"
    assert first["rng"] == "numpy.PCG64"
    assert first["resamples"] == 9999
    assert first["confidence_level"] == 0.95
    assert metric["case_count"] == 4
    assert metric["mean_difference"] == 0.5
    assert metric["confidence_interval"]["lower"] <= metric["mean_difference"]
    assert metric["confidence_interval"]["upper"] >= metric["mean_difference"]
    assert "winner" not in metric
    assert "superiority_supported" not in metric


def test_paired_bootstrap_omits_empty_optional_metrics() -> None:
    result = paired_bootstrap_intervals({"correctness": [1.0], "retained_correctness": []})

    assert set(result["metrics"]) == {"correctness"}
    assert result["metrics"]["correctness"]["confidence_interval"] == {"lower": 1.0, "upper": 1.0}


def test_paired_bootstrap_requires_a_nonempty_metric() -> None:
    with pytest.raises(ValueError, match="non-empty metric"):
        paired_bootstrap_intervals({"retained_correctness": []})


def test_paired_bootstrap_rejects_nonfinite_deltas() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        paired_bootstrap_intervals({"correctness": [float("inf")]})
