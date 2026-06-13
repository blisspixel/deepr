"""Calibration measurement for absorb extraction confidence (eval methodology v2).

The absorb pipeline records a self-rated extraction confidence per claim
("how strongly does THIS REPORT support this claim"). Nobody has measured
whether 0.7 means ~70% grounded - so today the honest framing is
"report-grounded candidates with confidence-as-signal", never "verified
facts" (docs/design/calibration-and-trust.md, panel-review finding).

This module is the measurement engine for that harness: given
(predicted_confidence, is_grounded) pairs - the predictions plus human gold
labels - it computes a reliability (calibration) curve, the expected
calibration error, a Platt-scaled post-hoc calibrator, the confidence
threshold at which true grounding crosses a target rate (so absorb's
``min_confidence`` is *derived*, not hand-picked), and extraction
precision/recall.

It is pure and $0: no model calls, no network. The keyed parts - running the
extraction model over a held-out corpus and the operator's gold grading -
live in the (later) ``deepr eval calibrate`` command and feed pairs in here.
Platt scaling follows VERDI (the calibration corpus); a logistic fit over
the raw scores is the cheap post-hoc calibrator the literature recommends
over reading the raw curve directly.
"""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

# Bump when a metric's computation changes, so stored runs stay comparable.
CALIBRATION_METHODOLOGY_VERSION = "1.0"

# Pair = (predicted_confidence in [0, 1], is_grounded). Gold labels come from
# human grading of held-out reports.
Pair = tuple[float, bool]

# Grading-pipeline seams (injectable so the orchestrator is tested at $0):
# extract a report into (claim, self-rated confidence) pairs, and grade whether
# a claim is grounded in its report. The CLI wires the extraction model and a
# strong-model pre-grader here; tests pass fakes.
ExtractFn = Callable[[str], Awaitable[list[tuple[str, float]]]]
GradeFn = Callable[[str, str], Awaitable[bool]]


@dataclass
class CalibrationBin:
    """One reliability-curve bucket: predicted vs observed grounding."""

    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower": round(self.lower, 3),
            "upper": round(self.upper, 3),
            "count": self.count,
            "mean_predicted": round(self.mean_predicted, 3),
            "observed_rate": round(self.observed_rate, 3),
        }


@dataclass
class CalibrationReport:
    """Measured calibration of extraction confidence against gold grounding."""

    sample_size: int
    grounded_rate: float
    ece: float  # expected calibration error (lower is better; 0 = perfect)
    ece_platt: float  # ECE after applying the Platt-scaled calibrator
    bins: list[CalibrationBin]
    platt_a: float  # P(grounded) = sigmoid(platt_a * conf + platt_b)
    platt_b: float
    derived_threshold: float | None  # raw confidence where true grounding crosses target
    target_grounding: float
    precision: float
    recall: float
    f1: float
    decision_threshold: float
    methodology_version: str = CALIBRATION_METHODOLOGY_VERSION
    notes: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "methodology_version": self.methodology_version,
            "sample_size": self.sample_size,
            "grounded_rate": round(self.grounded_rate, 3),
            "ece": round(self.ece, 4),
            "ece_platt": round(self.ece_platt, 4),
            "platt": {"a": round(self.platt_a, 4), "b": round(self.platt_b, 4)},
            "derived_threshold": (round(self.derived_threshold, 3) if self.derived_threshold is not None else None),
            "target_grounding": self.target_grounding,
            "extraction": {
                "precision": round(self.precision, 3),
                "recall": round(self.recall, 3),
                "f1": round(self.f1, 3),
                "decision_threshold": self.decision_threshold,
            },
            "bins": [b.to_dict() for b in self.bins],
            "notes": self.notes,
        }


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


def calibration_curve(pairs: list[Pair], n_bins: int = 10) -> list[CalibrationBin]:
    """Bucket predictions into equal-width confidence bins (empty bins dropped)."""
    bins: list[CalibrationBin] = []
    if not pairs:
        return bins
    conf = np.array([p for p, _ in pairs], dtype=float)
    grounded = np.array([1.0 if g else 0.0 for _, g in pairs], dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        # Last bin is closed on the right so confidence == 1.0 is included.
        in_bin = (conf >= lo) & (conf < hi) if i < n_bins - 1 else (conf >= lo) & (conf <= hi)
        count = int(in_bin.sum())
        if count == 0:
            continue
        bins.append(
            CalibrationBin(
                lower=float(lo),
                upper=float(hi),
                count=count,
                mean_predicted=float(conf[in_bin].mean()),
                observed_rate=float(grounded[in_bin].mean()),
            )
        )
    return bins


def expected_calibration_error(pairs: list[Pair], n_bins: int = 10) -> float:
    """Sample-weighted mean gap between predicted confidence and observed rate."""
    if not pairs:
        return 0.0
    total = len(pairs)
    return sum((b.count / total) * abs(b.mean_predicted - b.observed_rate) for b in calibration_curve(pairs, n_bins))


def fit_platt(pairs: list[Pair], *, iterations: int = 100, ridge: float = 1e-6) -> tuple[float, float]:
    """Fit P(grounded) = sigmoid(a*conf + b) by Newton-Raphson (numpy only).

    A 1-D logistic regression over the raw confidence. Ridge-regularized so a
    perfectly separable sample does not blow up the Hessian. Returns (a, b);
    falls back to (0, logit(base_rate)) when the fit is degenerate.
    """
    if len(pairs) < 2:
        return 0.0, 0.0
    x = np.array([p for p, _ in pairs], dtype=float)
    y = np.array([1.0 if g else 0.0 for _, g in pairs], dtype=float)
    design = np.column_stack([x, np.ones_like(x)])  # columns: [conf, 1]
    w = np.zeros(2, dtype=float)
    reg = ridge * np.eye(2)
    for _ in range(iterations):
        p = _sigmoid(design @ w)
        grad = design.T @ (p - y) + ridge * w
        weights = p * (1.0 - p)
        hessian = design.T @ (design * weights[:, None]) + reg
        try:
            step = np.linalg.solve(hessian, grad)
        except np.linalg.LinAlgError:
            break
        w = w - step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return float(w[0]), float(w[1])


def derive_threshold(platt_a: float, platt_b: float, target: float = 0.8) -> float | None:
    """Raw confidence at which the calibrated grounding probability hits ``target``.

    Solves sigmoid(a*x + b) = target for x. Returns None when the calibrator
    has no positive discrimination (a <= 0) - there is no confidence above
    which grounding reliably crosses the target. Clamped to [0, 1].
    """
    if platt_a <= 0 or not (0.0 < target < 1.0):
        return None
    logit = math.log(target / (1.0 - target))
    x = (logit - platt_b) / platt_a
    return float(min(1.0, max(0.0, x)))


def precision_recall_f1(pairs: list[Pair], decision_threshold: float = 0.6) -> tuple[float, float, float]:
    """Treat confidence >= threshold as 'predict grounded'; score vs gold."""
    tp = fp = fn = 0
    for conf, grounded in pairs:
        predicted = conf >= decision_threshold
        if predicted and grounded:
            tp += 1
        elif predicted and not grounded:
            fp += 1
        elif not predicted and grounded:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def parse_graded_pairs(text: str) -> list[Pair]:
    """Parse a graded-pairs JSONL: one ``{"confidence": float, "grounded": bool}``
    object per line (extra keys like claim/report_id are ignored). Blank lines
    and ``#`` comments are skipped; confidence is clamped to [0, 1]."""
    pairs: list[Pair] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        conf = max(0.0, min(1.0, float(obj["confidence"])))
        pairs.append((conf, bool(obj["grounded"])))
    return pairs


async def grade_corpus(
    reports: dict[str, str],
    *,
    extract_fn: ExtractFn,
    grade_fn: GradeFn,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[Pair], list[dict[str, Any]]]:
    """Extract claims from each report and grade their grounding.

    The FActScore/SAFE-shaped pipeline (decompose -> verify), but as pure
    orchestration over injectable seams: ``extract_fn`` turns a report into
    (claim, self-rated confidence) pairs, ``grade_fn`` judges whether a claim is
    grounded in its report. Returns the (confidence, grounded) pairs for
    ``measure_calibration`` plus per-claim records (report_id, claim,
    confidence, grounded) - the latter is the file the operator spot-corrects
    before publishing, since a strong-model pre-grade is a starting point, not
    ground truth (the grading-as-evidence discipline of ADR-adjacent design).

    A report whose extraction fails, or a claim whose grade fails, is skipped
    (recorded via on_progress) rather than aborting the whole run - calibration
    over a large corpus should be resumable, not all-or-nothing. No model calls
    here; cost lives entirely in the injected fns.
    """
    pairs: list[Pair] = []
    records: list[dict[str, Any]] = []
    for report_id, text in reports.items():
        try:
            claims = await extract_fn(text)
        except Exception as e:  # one bad report must not sink the corpus
            if on_progress:
                on_progress(f"skip {report_id}: extraction failed ({e})")
            continue
        for claim, confidence in claims:
            conf = max(0.0, min(1.0, float(confidence)))
            try:
                grounded = await grade_fn(claim, text)
            except Exception as e:
                if on_progress:
                    on_progress(f"skip claim in {report_id}: grading failed ({e})")
                continue
            pairs.append((conf, bool(grounded)))
            records.append({"report_id": report_id, "claim": claim, "confidence": conf, "grounded": bool(grounded)})
        if on_progress:
            on_progress(f"graded {report_id}: {len(claims)} claim(s)")
    return pairs, records


def render_calibration_markdown(report: CalibrationReport, *, model: str) -> str:
    """Render a CalibrationReport as the published ``docs/CALIBRATION.md`` body."""
    threshold = "n/a" if report.derived_threshold is None else f"{report.derived_threshold:.3f}"
    lines = [
        "# Calibration",
        "",
        f"Extraction model: `{model}`  ",
        f"Methodology: v{report.methodology_version}  ",
        f"Measured: {report.generated_at.date().isoformat()}",
        "",
        "Does the absorb extraction confidence mean what it says? This report is",
        "measured from graded (confidence, grounded) pairs, not asserted.",
        "",
        "## Summary",
        "",
        f"- Samples: {report.sample_size}",
        f"- Grounded rate: {report.grounded_rate:.1%}",
        f"- Expected calibration error (ECE): {report.ece:.3f} (lower is better; 0 = perfect)",
        f"- ECE after Platt scaling: {report.ece_platt:.3f}",
        f"- Derived absorb threshold (>= {report.target_grounding:.0%} grounded): {threshold}",
        f"- Extraction precision / recall / F1 @ {report.decision_threshold}: "
        f"{report.precision:.2f} / {report.recall:.2f} / {report.f1:.2f}",
        "",
        "## Reliability curve",
        "",
        "| Confidence bin | n | Mean predicted | Observed grounded |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {b.lower:.2f}-{b.upper:.2f} | {b.count} | {b.mean_predicted:.2f} | {b.observed_rate:.2f} |"
        for b in report.bins
    ]
    if report.notes:
        lines += ["", "## Notes", "", *[f"- {n}" for n in report.notes]]
    lines += [
        "",
        "_Derived view: regenerate with `deepr eval calibrate`. If gold labels were",
        "seeded by a strong-model pre-grade and spot-corrected, that bias is noted above._",
        "",
    ]
    return "\n".join(lines)


def measure_calibration(
    pairs: list[Pair],
    *,
    n_bins: int = 10,
    target_grounding: float = 0.8,
    decision_threshold: float = 0.6,
) -> CalibrationReport:
    """Measure how well extraction confidence tracks true grounding ($0).

    Args:
        pairs: (predicted_confidence, is_grounded) from gold-graded reports.
        n_bins: Reliability-curve resolution.
        target_grounding: Grounding rate absorb's threshold should guarantee.
        decision_threshold: Confidence at/above which a claim is treated as a
            grounded prediction for precision/recall.

    Returns:
        A methodology-versioned CalibrationReport. With too few samples the
        Platt fit and derived threshold degrade gracefully (recorded in notes).
    """
    notes: list[str] = []
    n = len(pairs)
    if n == 0:
        return CalibrationReport(
            sample_size=0,
            grounded_rate=0.0,
            ece=0.0,
            ece_platt=0.0,
            bins=[],
            platt_a=0.0,
            platt_b=0.0,
            derived_threshold=None,
            target_grounding=target_grounding,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            decision_threshold=decision_threshold,
            notes=["no samples"],
        )

    grounded_rate = sum(1 for _, g in pairs if g) / n
    bins = calibration_curve(pairs, n_bins)
    ece = expected_calibration_error(pairs, n_bins)

    platt_a, platt_b = fit_platt(pairs)
    calibrated = [(float(_sigmoid(np.array([platt_a * c + platt_b]))[0]), g) for c, g in pairs]
    ece_platt = expected_calibration_error(calibrated, n_bins)
    derived = derive_threshold(platt_a, platt_b, target_grounding)

    precision, recall, f1 = precision_recall_f1(pairs, decision_threshold)

    if n < 30:
        notes.append(f"small sample (n={n}); calibration estimates are noisy")
    if derived is None:
        notes.append("no derived threshold: confidence does not positively track grounding in this sample")

    return CalibrationReport(
        sample_size=n,
        grounded_rate=grounded_rate,
        ece=ece,
        ece_platt=ece_platt,
        bins=bins,
        platt_a=platt_a,
        platt_b=platt_b,
        derived_threshold=derived,
        target_grounding=target_grounding,
        precision=precision,
        recall=recall,
        f1=f1,
        decision_threshold=decision_threshold,
        notes=notes,
    )
