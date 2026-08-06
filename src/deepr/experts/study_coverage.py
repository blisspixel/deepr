"""Corpus coverage for a study pass (pure, $0, no model, no network).

Relevance-ranked retrieval reproduces a documented group-judgment failure for
free. Across 65 studies and 3,189 groups, groups surfaced commonly-held
information far more than uniquely-held information and were roughly eight times
less likely to reach the right answer when the decisive evidence sat with one
member. The mechanism needs no bias: widely-held information simply has more
chances to be raised. Retrieval is that sampling process.

Two findings drive this module:

1. **Coverage beat depth.** In that meta-analysis the stronger predictor of
   decision quality was the *breadth of distinct evidence touched*, not the
   depth of the top matches.
2. **Singletons are where the answer hides.** A hidden profile is precisely a
   fact held by one source that changes the conclusion.

So a study pass reports what it read, what it did not read, and which sources
contributed nothing to any finding. An untouched source is not an error, but it
must be visible: an expert that silently ignores a third of its corpus while
reporting confident findings is reproducing the failure this module exists to
surface.

Nothing here judges whether a finding is good. It counts what was consulted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from deepr.experts.corpus_store import CorpusEntry, CorpusStats
from deepr.experts.study_contracts import StudyFinding


@dataclass
class CoverageReport:
    """What a study pass actually touched. Structural counts only."""

    corpus_sources: int = 0
    studied_sources: int = 0
    cited_sources: int = 0
    """Sources at least one grounded finding anchored into."""
    corpus_origins: int = 0
    cited_origins: int = 0
    untouched_sources: list[str] = field(default_factory=list)
    """sha256 of studied sources no finding anchored into."""
    unstudied_sources: list[str] = field(default_factory=list)
    """sha256 of retained sources the pass never saw (budget or supersession)."""
    singleton_origin_sources: list[str] = field(default_factory=list)
    """Sources that are the only one from their origin. Hidden profiles live here."""
    uncited_singleton_origins: list[str] = field(default_factory=list)
    """Sole-source origins nothing cited. The highest-value review queue."""

    @property
    def source_coverage(self) -> float:
        """Share of studied sources that any finding anchored into."""
        if not self.studied_sources:
            return 0.0
        return round(self.cited_sources / self.studied_sources, 3)

    @property
    def origin_coverage(self) -> float:
        """Share of distinct origins represented in the findings.

        Reported separately from source coverage because one publisher with many
        pages can produce high source coverage while most independent origins go
        unread.
        """
        if not self.corpus_origins:
            return 0.0
        return round(self.cited_origins / self.corpus_origins, 3)

    def concerns(self) -> list[str]:
        """Coverage facts worth an operator's attention. Never a quality verdict."""
        notes: list[str] = []
        if self.unstudied_sources:
            notes.append(
                f"{len(self.unstudied_sources)} retained source(s) were not studied at all. "
                "Findings cannot reflect material that was never read."
            )
        if self.untouched_sources:
            notes.append(f"{len(self.untouched_sources)} studied source(s) produced no anchored finding.")
        if self.uncited_singleton_origins:
            notes.append(
                f"{len(self.uncited_singleton_origins)} sole-source origin(s) were not cited by any "
                "finding. Evidence held by a single source is exactly what relevance ranking buries, "
                "and is where a conclusion-changing fact is most likely to sit."
            )
        if self.corpus_origins and self.origin_coverage < 0.5:
            notes.append(
                f"origin_coverage={self.origin_coverage:.2f}: findings draw on under half the "
                "distinct origins in the corpus."
            )
        return notes

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_coverage"] = self.source_coverage
        data["origin_coverage"] = self.origin_coverage
        data["concerns"] = self.concerns()
        return data


def build_coverage_report(
    *,
    studied: list[tuple[CorpusEntry, str]],
    findings: list[StudyFinding],
    stats: CorpusStats,
    all_active: list[CorpusEntry],
) -> CoverageReport:
    """Compare what was read and cited against what the corpus holds."""
    studied_by_sha = {entry.sha256: entry for entry, _ in studied}
    active_by_sha = {entry.sha256: entry for entry in all_active}

    cited_shas: set[str] = set()
    for finding in findings:
        # Only grounded anchors count: an unverified quote is not evidence the
        # source was actually consulted.
        if finding.is_grounded:
            cited_shas.update(finding.corpus_shas)

    # An origin represented by exactly one source is where a conclusion-changing
    # fact can sit without frequency ever surfacing it.
    origin_counts: dict[str, int] = {}
    for entry in active_by_sha.values():
        origin_counts[entry.origin_key] = origin_counts.get(entry.origin_key, 0) + 1
    singleton_shas = [entry.sha256 for entry in active_by_sha.values() if origin_counts.get(entry.origin_key, 0) == 1]

    cited_origins = {studied_by_sha[sha].origin_key for sha in cited_shas if sha in studied_by_sha}

    return CoverageReport(
        corpus_sources=stats.active_count,
        studied_sources=len(studied),
        cited_sources=len(cited_shas & set(studied_by_sha)),
        corpus_origins=stats.distinct_origins,
        cited_origins=len(cited_origins),
        untouched_sources=sorted(set(studied_by_sha) - cited_shas),
        unstudied_sources=sorted(set(active_by_sha) - set(studied_by_sha)),
        singleton_origin_sources=sorted(singleton_shas),
        uncited_singleton_origins=sorted(sha for sha in singleton_shas if sha not in cited_shas),
    )
