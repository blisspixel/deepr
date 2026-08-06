"""How many independent sources a corpus actually holds.

A count of documents is not a count of evidence. Three pages from one
publisher share an editorial policy, a house style, and usually an author
pool; they are one source wearing three hats. Every downstream number that
reads as corroboration - agreement between findings, positions resting on
several citations, trust ceilings lifted by a second reference - inherits
that error and amplifies it.

The measurement is old and cheap. Effective source count is the Hill number
of order 1, ``exp(H)`` over the publisher share vector: the number of equally
weighted publishers that would produce the observed concentration. Three
pages from one publisher score 1.0 against a nominal 3. One number, computed
with no model and no network, that fails the corpus before a study spends
anything on it.

Deliberately a report, not a refusal. Refusing to study a thin corpus would
leave the operator with nothing; studying it while saying it is thin leaves
them with findings and an accurate read on what those findings are worth.

Duplicate publication is the documented cost of getting this wrong: in the
clearest measurement, including duplicated reports of the same underlying
study overstated efficacy by roughly a quarter, and the reports that got
duplicated were the ones showing larger effects. Counting agreement without
collapsing to origin is directionally wrong, not merely noisy.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from deepr.experts.corpus_store import CorpusEntry

_TIER_WEIGHTS: dict[str, float] = {"primary": 1.0, "secondary": 0.5, "tertiary": 0.25}
"""How much a source class is worth as evidence.

Graded rather than binary because the alternative is treating an operator
attested spec and an encyclopedia summary as interchangeable. Weights are a
convention, not a measurement, and are reported alongside the raw counts so
a reader can disagree with them.
"""

_THIN_EFFECTIVE_SOURCES = 2.0
"""Below this, agreement in the corpus carries no independent weight."""

_DOMINANT_SHARE = 0.6
"""One publisher above this share sets what the corpus can conclude."""


@dataclass
class IndependenceReport:
    """What the corpus holds, counted by origin rather than by document."""

    source_count: int = 0
    origin_count: int = 0
    effective_source_count: float = 0.0
    """exp(Shannon entropy) over origin shares. The number that means something."""
    concentration: float = 0.0
    """Herfindahl index over origin shares. 1.0 is a single publisher."""
    dominant_origin: str = ""
    dominant_share: float = 0.0
    tier_counts: dict[str, int] = field(default_factory=dict)
    mean_tier_weight: float = 0.0

    @property
    def is_thin(self) -> bool:
        """True when agreement between these sources is not corroboration."""
        return self.effective_source_count < _THIN_EFFECTIVE_SOURCES

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_thin"] = self.is_thin
        return data

    def concerns(self) -> list[str]:
        """What a reader must know before trusting anything derived from this."""
        notes: list[str] = []
        if not self.source_count:
            return ["Corpus is empty."]

        if self.is_thin:
            notes.append(
                f"{self.source_count} source(s) collapse to {self.effective_source_count:.1f} "
                "independent origin(s). Agreement between them is one publisher agreeing with "
                "itself, and any finding that reads as corroborated here is not."
            )
        if self.dominant_share >= _DOMINANT_SHARE and self.origin_count > 1:
            notes.append(
                f"{self.dominant_origin} supplies {self.dominant_share:.0%} of this corpus, so it "
                "sets what can be concluded. A contention lens will mostly find that publisher "
                "disagreeing with itself."
            )
        if self.mean_tier_weight and self.mean_tier_weight <= _TIER_WEIGHTS["tertiary"]:
            notes.append(
                "This corpus is almost entirely tertiary material, which summarizes primary work "
                "rather than reporting it. Findings inherit whatever the summary got wrong."
            )
        return notes


def _shares(entries: list[CorpusEntry]) -> dict[str, float]:
    counts = Counter(entry.origin_key for entry in entries if entry.origin_key)
    total = sum(counts.values())
    return {origin: n / total for origin, n in counts.items()} if total else {}


def measure_independence(entries: list[CorpusEntry]) -> IndependenceReport:
    """Count the corpus by origin, not by document.

    Only active entries should be passed: a superseded revision is the same
    source at an earlier moment, and counting it again would manufacture the
    corroboration this exists to detect.
    """
    active = [entry for entry in entries if entry.is_active]
    if not active:
        return IndependenceReport()

    shares = _shares(active)
    entropy = -sum(share * math.log(share) for share in shares.values() if share > 0)
    dominant = max(shares.items(), key=lambda item: (item[1], item[0]), default=("", 0.0))
    tiers = Counter(entry.trust_class or "secondary" for entry in active)

    return IndependenceReport(
        source_count=len(active),
        origin_count=len(shares),
        effective_source_count=round(math.exp(entropy), 2) if shares else 0.0,
        concentration=round(sum(share**2 for share in shares.values()), 3),
        dominant_origin=dominant[0],
        dominant_share=round(dominant[1], 3),
        tier_counts=dict(sorted(tiers.items())),
        mean_tier_weight=round(sum(_TIER_WEIGHTS.get(entry.trust_class, 0.5) for entry in active) / len(active), 3),
    )
