"""Pure contracts and form helpers for report absorption."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class ReportAbsorberError(Exception):
    """Raised when a report cannot be absorbed."""


class ReportAbsorberCostError(ReportAbsorberError):
    """Raised when metered absorb admission or settlement fails."""

    def __init__(self, message: str, *, actual_cost: float = 0.0) -> None:
        super().__init__(message)
        self.actual_cost = nonnegative_cost(actual_cost)


def nonnegative_cost(value: Any) -> float:
    try:
        cost = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(cost, 0.0) if math.isfinite(cost) else 0.0


def _loads_json_candidate(candidate: str, *, strict: bool) -> Any:
    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"Non-finite JSON number is not allowed: {value}")

    return json.loads(candidate, strict=strict, parse_constant=reject_nonfinite)


def absorber_estimated_cost(absorber: Any) -> float:
    """Return the caller-accounting estimate for an absorber-like object."""
    return nonnegative_cost(getattr(absorber, "estimated_cost", getattr(absorber, "_estimated_cost", 0.0)))


def absorption_result_cost(absorption: Any) -> float:
    """Return settled aggregate cost from an absorption result-like object."""
    actual = getattr(absorption, "actual_cost", None)
    if actual is not None:
        return nonnegative_cost(actual)
    return nonnegative_cost(getattr(absorption, "estimated_cost", 0.0))


@dataclass
class AbsorbRunBudget:
    """In-process view of one caller ceiling over all absorber model calls."""

    ceiling: float
    settled: float = 0.0

    @property
    def remaining(self) -> float:
        return max(self.ceiling - self.settled, 0.0)

    def record(self, cost: float) -> None:
        self.settled += nonnegative_cost(cost)


def loads_model_json(raw: str) -> Any:
    """Parse provider JSON output without rejecting raw control characters."""
    text = raw.strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        sliced = text[start : end + 1]
        if sliced != text:
            candidates.append(sliced)

    first_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            return _loads_json_candidate(candidate, strict=True)
        except ValueError as exc:
            if first_error is None:
                first_error = (
                    exc if isinstance(exc, json.JSONDecodeError) else json.JSONDecodeError(str(exc), candidate, 0)
                )
        try:
            return _loads_json_candidate(candidate, strict=False)
        except ValueError as exc:
            if first_error is None:
                first_error = (
                    exc if isinstance(exc, json.JSONDecodeError) else json.JSONDecodeError(str(exc), candidate, 0)
                )
    if first_error is not None:
        raise first_error
    raise json.JSONDecodeError("No JSON object found", raw, 0)


@dataclass
class CandidateClaim:
    """A claim proposed by extraction, before gating."""

    statement: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)


@dataclass
class AbsorbedClaim:
    statement: str
    confidence: float
    belief_id: str
    outcome: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "confidence": round(self.confidence, 3),
            "belief_id": self.belief_id,
            "outcome": self.outcome,
        }


INSUFFICIENT_GROUNDING_FLOOR = 0.4
_NON_BELIEF_META_STATEMENTS = {"no significant changes", "there were no significant changes"}


def is_non_belief_meta_statement(statement: str) -> bool:
    """Reject exact sync/report status markers that are not domain beliefs."""
    normalized = statement.lower().replace("*", "").replace("_", "").replace("`", "").replace("~", "")
    normalized = " ".join(normalized.strip(" .!:;").split())
    return normalized in _NON_BELIEF_META_STATEMENTS


def normalize_evidence_items(evidence: Any) -> list[str]:
    """Normalize model evidence into at most five short string excerpts."""
    if evidence is None:
        return []
    if isinstance(evidence, str):
        raw_items: list[Any] = [evidence]
    elif isinstance(evidence, (list, tuple)):
        raw_items = list(evidence)
    else:
        raw_items = [evidence]
    return [item for raw in raw_items if (item := str(raw).strip())][:5]


def normalize_source_ref_catalog(source_ref_catalog: Mapping[str, str] | None) -> dict[str, str] | None:
    """Validate candidate-selectable replay pointers without judging support."""
    if source_ref_catalog is None:
        return None
    normalized: dict[str, str] = {}
    for raw_label, raw_ref in source_ref_catalog.items():
        label = str(raw_label).strip()
        source_ref = str(raw_ref).strip()
        if not label or not source_ref or any(character.isspace() for character in source_ref):
            raise ReportAbsorberError("source_ref_catalog requires non-empty labels and compact replay refs")
        normalized[label] = source_ref
    if not normalized:
        raise ReportAbsorberError("source_ref_catalog must contain at least one replayable source")
    return normalized


def normalize_selected_source_label(value: Any) -> str:
    """Remove at most one citation-style bracket pair from a source label."""
    label = str(value).strip()
    if len(label) >= 3 and label.startswith("[") and label.endswith("]"):
        inner = label[1:-1].strip()
        if inner and "[" not in inner and "]" not in inner:
            return inner
    return label


@dataclass
class RejectedClaim:
    statement: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "reason": self.reason, "detail": self.detail}


@dataclass
class InsufficientGroundingClaim:
    statement: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "confidence": round(self.confidence, 3)}


@dataclass
class FlaggedContradiction:
    statement: str
    confidence: float
    belief_id: str
    conflicts_with_id: str
    conflicts_with_claim: str
    conflicts_with_confidence: float
    outcome: str
    better_sourced: str = "tie"
    verification: str = "lexical_unverified"
    resolution: str = ""
    resolution_explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "confidence": round(self.confidence, 3),
            "belief_id": self.belief_id,
            "conflicts_with_id": self.conflicts_with_id,
            "conflicts_with_claim": self.conflicts_with_claim,
            "conflicts_with_confidence": round(self.conflicts_with_confidence, 3),
            "outcome": self.outcome,
            "newer": "candidate",
            "better_sourced": self.better_sourced,
            "verification": self.verification,
            "resolution": self.resolution,
            "resolution_explanation": self.resolution_explanation,
        }


@dataclass
class GroundingFlag:
    statement: str
    checker_vendor: str | None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "checker_vendor": self.checker_vendor, "reason": self.reason}


@dataclass
class AbsorptionResult:
    expert_name: str
    report_id: str
    dry_run: bool
    total_candidates: int
    absorbed: list[AbsorbedClaim] = field(default_factory=list)
    rejected: list[RejectedClaim] = field(default_factory=list)
    flagged: list[FlaggedContradiction] = field(default_factory=list)
    insufficient: list[InsufficientGroundingClaim] = field(default_factory=list)
    grounding_flagged: list[GroundingFlag] = field(default_factory=list)
    estimated_cost: float = 0.0
    actual_cost: float | None = None
    budget: float = 0.0
    contradictions_refuted: int = 0
    merges_blocked: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def added_count(self) -> int:
        return sum(1 for absorbed in self.absorbed if absorbed.outcome == "added")

    @property
    def merged_count(self) -> int:
        return sum(1 for absorbed in self.absorbed if absorbed.outcome == "merged")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "report_id": self.report_id,
            "dry_run": self.dry_run,
            "total_candidates": self.total_candidates,
            "absorbed_count": len(self.absorbed),
            "added_count": self.added_count,
            "merged_count": self.merged_count,
            "rejected_count": len(self.rejected),
            "flagged_count": len(self.flagged),
            "insufficient_count": len(self.insufficient),
            "grounding_flagged_count": len(self.grounding_flagged),
            "contradictions_refuted": self.contradictions_refuted,
            "merges_blocked": self.merges_blocked,
            "absorbed": [absorbed.to_dict() for absorbed in self.absorbed],
            "rejected": [rejected.to_dict() for rejected in self.rejected],
            "flagged": [flag.to_dict() for flag in self.flagged],
            "insufficient": [claim.to_dict() for claim in self.insufficient],
            "grounding_flagged": [flag.to_dict() for flag in self.grounding_flagged],
            "estimated_cost": round(self.estimated_cost, 4),
            "actual_cost": round(absorption_result_cost(self), 6),
            "budget": round(self.budget, 4),
            "generated_at": self.generated_at.isoformat(),
        }
