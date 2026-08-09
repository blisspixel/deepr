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
from dataclasses import fields as dataclass_fields
from typing import Any

STUDY_SCHEMA_VERSION = "deepr-expert-study-v1"


def _provenance(capacity_source: str, model: str) -> Any:
    """Stamp which model did the reading, imported lazily to avoid a cycle."""
    from deepr.experts.model_provenance import record

    return record(capacity_source, model)


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
    finding_id: str = ""
    """Stable handle a brief cites, so citations do not go through the title.

    Titles collide: several lenses fall back to a constant when the model names
    nothing, and descriptive lenses emit sentence-length titles that get
    truncated. Matching citations by title meant one citation could claim every
    finding sharing that string, inflating evidential depth, while a title
    holding a newline could never be matched at all and the brief blamed the
    model for citing nothing.
    """

    @property
    def is_grounded(self) -> bool:
        """At least one anchor verifiably appears in the retained corpus."""
        return self.grounded_anchor_count > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_grounded"] = self.is_grounded
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StudyFinding:
        return cls(
            lens=data.get("lens", ""),
            axis=data.get("axis", ""),
            kind=data.get("kind", ""),
            title=data.get("title", ""),
            payload=data.get("payload") or {},
            anchors=data.get("anchors") or [],
            grounded_anchor_count=int(data.get("grounded_anchor_count", 0) or 0),
            ungrounded_anchor_count=int(data.get("ungrounded_anchor_count", 0) or 0),
            corpus_shas=data.get("corpus_shas") or [],
            finding_id=data.get("finding_id", ""),
        )


@dataclass
class LensOutcome:
    """What one lens produced, including honest failure."""

    lens: str
    axis: str
    status: str
    """ok | partial | parse_failed | model_error | skipped"""
    findings: list[StudyFinding] = field(default_factory=list)
    detail: str = ""
    elapsed_s: float = 0.0
    cost_usd: float = 0.0
    chunks_total: int = 0
    chunks_failed: int = 0
    corpus_fingerprint: str = ""
    """Which sources this lens read, so a stale reuse is detectable.

    An expert accumulates sources. Resuming on lens name alone reuses findings
    that never saw the new material, which is an expert that silently stops
    learning from what it retained."""
    """How much of the corpus this lens actually got through.

    Carried as counts rather than only in a prose ``detail`` string, so a run
    that read a tenth of its corpus is legible to a scheduler and not just to
    an attentive reader.
    """

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens": self.lens,
            "axis": self.axis,
            "status": self.status,
            "detail": self.detail,
            "elapsed_s": round(self.elapsed_s, 2),
            "cost_usd": self.cost_usd,
            "chunks_total": self.chunks_total,
            "chunks_failed": self.chunks_failed,
            "corpus_fingerprint": self.corpus_fingerprint,
            "finding_count": len(self.findings),
            "grounded_count": sum(1 for f in self.findings if f.is_grounded),
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LensOutcome:
        return cls(
            lens=data.get("lens", ""),
            axis=data.get("axis", ""),
            status=data.get("status", "ok"),
            findings=[StudyFinding.from_dict(f) for f in (data.get("findings") or [])],
            detail=data.get("detail", ""),
            elapsed_s=float(data.get("elapsed_s", 0.0) or 0.0),
            chunks_total=int(data.get("chunks_total", 0) or 0),
            chunks_failed=int(data.get("chunks_failed", 0) or 0),
            corpus_fingerprint=data.get("corpus_fingerprint", ""),
        )


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
    model: str = ""
    """The model behind ``capacity_source``, where one was chosen explicitly.

    ``capacity_source`` names the dispatch (``plan:grok``); this names what ran
    inside it. Empty when a plan CLI picked for itself, which is honest rather
    than absent - Deepr sees the process, not the routing decision inside it."""
    started_at: str = ""
    elapsed_s: float = 0.0
    cost_usd: float = 0.0
    limitations: list[str] = field(default_factory=list)
    coverage: Any = None
    """CoverageReport: what the pass read and cited versus what the corpus holds."""
    independence: Any = None
    """IndependenceReport: how many independent origins the corpus really holds."""

    @property
    def findings(self) -> list[StudyFinding]:
        return [f for outcome in self.outcomes for f in outcome.findings]

    @property
    def grounded_findings(self) -> list[StudyFinding]:
        return [f for f in self.findings if f.is_grounded]

    @property
    def cross_source_findings(self) -> list[StudyFinding]:
        """Findings anchored in more than one retained source.

        The headline number for whether this pass compared sources at all.
        When every lens call sees a slice of a single document, this is zero by
        construction, and a contention lens reporting forty findings is really
        reporting forty documents disagreeing with themselves. Kept as a first
        class metric so that regression is visible rather than plausible.
        """
        return [f for f in self.findings if len(set(f.corpus_shas)) > 1]

    @property
    def failed_lenses(self) -> list[str]:
        return [o.lens for o in self.outcomes if o.status != "ok"]

    @property
    def exit_code(self) -> int:
        """0 clean, 1 degraded but usable, 2 nothing usable came back.

        A lens that got through one chunk of ten used to report ``ok``, and a
        pass whose every finding was unverifiable used to exit 0. Both are
        indistinguishable from a clean run to the scheduler or maintenance loop
        that reads this, which is the only consumer that cannot notice a
        warning printed alongside it.
        """
        if not self.outcomes:
            return 2
        if not self.findings or not self.grounded_findings:
            return 2
        degraded = [o for o in self.outcomes if o.status != "ok"]
        if not degraded:
            return 0
        return 2 if len(degraded) == len(self.outcomes) and not self.findings else 1

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
            "model": self.model,
            "model_provenance": _provenance(self.capacity_source, self.model).to_dict(),
            "started_at": self.started_at,
            "elapsed_s": round(self.elapsed_s, 2),
            "cost_usd": self.cost_usd,
            "totals": {
                "lenses_run": len(self.outcomes),
                "lenses_failed": len(self.failed_lenses),
                "findings": len(self.findings),
                "grounded_findings": len(self.grounded_findings),
                "cross_source_findings": len(self.cross_source_findings),
                "axis_coverage": self.axis_coverage(),
            },
            "coverage": self.coverage.to_dict() if self.coverage is not None else None,
            "independence": self.independence.to_dict() if self.independence is not None else None,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "limitations": self.limitations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, expert_name: str = "") -> StudyResult:
        """Rebuild a whole pass from study.json.

        One rehydration, because there were two and they had already drifted:
        both dropped coverage, so regenerating a notebook from the canonical
        record produced a document missing the section that reports what the
        pass never read.
        """
        from deepr.experts.corpus_independence import IndependenceReport
        from deepr.experts.study_coverage import CoverageReport

        _INDEPENDENCE_FIELDS = {f.name for f in dataclass_fields(IndependenceReport)}

        corpus = data.get("corpus") or {}
        result = cls(
            expert_name=data.get("expert") or expert_name,
            corpus_sources=int(corpus.get("sources", 0) or 0),
            corpus_origins=int(corpus.get("distinct_origins", 0) or 0),
            corpus_chars=int(corpus.get("chars", 0) or 0),
            capacity_source=data.get("capacity_source", ""),
            model=data.get("model", ""),
            started_at=data.get("started_at", ""),
            elapsed_s=float(data.get("elapsed_s", 0.0) or 0.0),
            limitations=list(data.get("limitations") or []),
        )
        result.outcomes = [LensOutcome.from_dict(o) for o in (data.get("outcomes") or [])]
        result.coverage = CoverageReport.from_dict(data.get("coverage"))
        independence = data.get("independence")
        if independence:
            result.independence = IndependenceReport(
                **{k: v for k, v in independence.items() if k in _INDEPENDENCE_FIELDS}
            )
        return result
