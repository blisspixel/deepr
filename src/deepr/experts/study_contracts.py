"""Typed results of a study pass.

Each lens returns a different shape because each asks a different question. A
failure mode is a conditional structure (trigger, symptom, mechanism,
correction, detection); a tension needs two quoted sides; an absence needs what
was expected and why. Flattening these into one generic "finding" record loses
exactly the structure that makes them usable, which is the v1 mistake repeated
one level up.

Every record carries ``anchors``: exact phrases quoted from the corpus. An
anchor that does not appear in the retained source text is a form failure and is
marked, not silently dropped - deciding a finding is wrong is meaning, and
meaning is not this module's job.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

STUDY_SCHEMA_VERSION = "deepr-expert-study-v1"


@dataclass
class StudyFinding:
    """One item produced by one lens.

    ``payload`` holds the lens-specific fields verbatim so a new lens does not
    require a schema migration. ``anchors`` and grounding are common because
    they are what admission is checked against.
    """

    lens: str
    axis: str
    kind: str
    """The lens's output field, e.g. fail_patterns, tensions, observations."""
    title: str
    payload: dict[str, Any] = field(default_factory=dict)
    anchors: list[str] = field(default_factory=list)
    grounded_anchor_count: int = 0
    ungrounded_anchor_count: int = 0
    corpus_shas: list[str] = field(default_factory=list)
    """Retained sources an anchor was actually found in."""

    @property
    def is_grounded(self) -> bool:
        """At least one anchor verifiably appears in the retained corpus."""
        return self.grounded_anchor_count > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_grounded"] = self.is_grounded
        return data


@dataclass
class LensOutcome:
    """What one lens produced, including honest failure."""

    lens: str
    axis: str
    status: str
    """ok | parse_failed | model_error | skipped"""
    findings: list[StudyFinding] = field(default_factory=list)
    detail: str = ""
    elapsed_s: float = 0.0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens": self.lens,
            "axis": self.axis,
            "status": self.status,
            "detail": self.detail,
            "elapsed_s": round(self.elapsed_s, 2),
            "cost_usd": self.cost_usd,
            "finding_count": len(self.findings),
            "grounded_count": sum(1 for f in self.findings if f.is_grounded),
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class StudyResult:
    """The whole pass. Structural counts only; no verdict on quality."""

    expert_name: str
    schema_version: str = STUDY_SCHEMA_VERSION
    outcomes: list[LensOutcome] = field(default_factory=list)
    corpus_sources: int = 0
    corpus_origins: int = 0
    corpus_chars: int = 0
    capacity_source: str = ""
    started_at: str = ""
    elapsed_s: float = 0.0
    cost_usd: float = 0.0
    limitations: list[str] = field(default_factory=list)
    coverage: Any = None
    """CoverageReport: what the pass read and cited versus what the corpus holds."""

    @property
    def findings(self) -> list[StudyFinding]:
        return [f for outcome in self.outcomes for f in outcome.findings]

    @property
    def grounded_findings(self) -> list[StudyFinding]:
        return [f for f in self.findings if f.is_grounded]

    @property
    def failed_lenses(self) -> list[str]:
        return [o.lens for o in self.outcomes if o.status != "ok"]

    @property
    def exit_code(self) -> int:
        """0 all lenses ok, 1 partial, 2 nothing worked."""
        if not self.outcomes:
            return 2
        failed = len(self.failed_lenses)
        if failed == 0:
            return 0
        return 2 if failed == len(self.outcomes) else 1

    def axis_coverage(self) -> dict[str, int]:
        counts = {"interrogation": 0, "perspective": 0}
        for outcome in self.outcomes:
            if outcome.status == "ok" and outcome.axis in counts:
                counts[outcome.axis] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "corpus": {
                "sources": self.corpus_sources,
                "distinct_origins": self.corpus_origins,
                "chars": self.corpus_chars,
            },
            "capacity_source": self.capacity_source,
            "started_at": self.started_at,
            "elapsed_s": round(self.elapsed_s, 2),
            "cost_usd": self.cost_usd,
            "totals": {
                "lenses_run": len(self.outcomes),
                "lenses_failed": len(self.failed_lenses),
                "findings": len(self.findings),
                "grounded_findings": len(self.grounded_findings),
                "axis_coverage": self.axis_coverage(),
            },
            "coverage": self.coverage.to_dict() if self.coverage is not None else None,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "limitations": self.limitations,
        }
