"""Which model read the corpus, recorded on every artifact it produced.

This is the highest-value quality signal available about an expert and the
cheapest to obtain, and until now it was thrown away.

The argument for weighting it heavily: a 14B local model and a frontier model
reading the *same* corpus with the *same* lenses produce genuinely different
experts. One returns four shallow restatements per chunk; the other finds the
disagreement between two sources and says which one the evidence favours. No
downstream statistic recovers that difference - a shallow finding is grounded,
traceable and cross-source just as easily as a deep one, so the corroboration
metrics score both alike.

It is also the signal least likely to be wrong. Everything else in
``expert_health`` is an inference about quality from structure, and two of
those inferences have already had to be withdrawn: effective source count
rewarded deleting evidence, and self-reported open-mindedness graded the
weakest channel available. Which model ran is not an inference. It is a fact
about a subprocess, and nothing an expert does can change it after the fact.

**Tier is coarse on purpose.** Three buckets, because the honest resolution is
low. Exact model identity is not always knowable: a plan CLI invoked without an
explicit model runs whatever it defaults to that week, and Deepr sees the
process, not the routing decision inside it. What *is* knowable is the family,
and the family is enough to separate "a frontier model read this" from "a 7B
model read this", which is the distinction that matters for ranking.

Recording an honest `unknown` is better than inferring a tier from a version
string that may not mean what it looks like.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

PROVENANCE_SCHEMA_VERSION = "deepr-model-provenance-v1"

TIER_FRONTIER = "frontier"
TIER_MID = "mid"
TIER_SMALL = "small"
TIER_UNKNOWN = "unknown"

_TIER_ORDER = {TIER_UNKNOWN: 0, TIER_SMALL: 1, TIER_MID: 2, TIER_FRONTIER: 3}

_FRONTIER_PLANS = frozenset({"claude", "codex", "grok", "antigravity", "copilot"})
"""Plan CLIs that front a frontier-class model.

The claim is about the family, not the exact checkpoint. Each of these is the
vendor's own agent CLI running the vendor's current flagship; none of them
defaults to a small model. If one starts routing to a cheap tier by default,
this set is where that gets corrected."""

_PARAM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)
"""Parameter count in a local model tag: qwen2.5:14b, llama-3.3-70b-instruct."""

_MID_PARAMS = 20.0
_FRONTIER_PARAMS = 65.0


@dataclass(frozen=True)
class ModelProvenance:
    """Who did the reading, on one artifact."""

    capacity_source: str = ""
    """`local:<model>` or `plan:<backend>`. What Deepr actually dispatched."""
    model: str = ""
    """The model string, where one was chosen. Empty when a plan CLI picked."""
    tier: str = TIER_UNKNOWN
    schema_version: str = PROVENANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> ModelProvenance:
        if not isinstance(data, dict):
            return cls()
        tier = str(data.get("tier") or TIER_UNKNOWN)
        return cls(
            capacity_source=str(data.get("capacity_source") or ""),
            model=str(data.get("model") or ""),
            tier=tier if tier in _TIER_ORDER else TIER_UNKNOWN,
            schema_version=str(data.get("schema_version") or PROVENANCE_SCHEMA_VERSION),
        )


def classify_tier(capacity_source: str, model: str = "") -> str:
    """Bucket the model behind one dispatch.

    Local models are classified by parameter count parsed from the tag, which
    is the one place the size is reliably stated. A tag with no parameter count
    is `unknown` rather than guessed: `mistral-small` and `mistral-large` are
    the same string to a heuristic that assumes.
    """
    source = (capacity_source or "").strip().lower()

    if source.startswith("plan:"):
        return TIER_FRONTIER if source.removeprefix("plan:") in _FRONTIER_PLANS else TIER_UNKNOWN

    if source.startswith("local:") or model:
        tag = source.removeprefix("local:") or model.lower()
        match = _PARAM_RE.search(tag)
        if not match:
            return TIER_UNKNOWN
        params = float(match.group(1))
        if params >= _FRONTIER_PARAMS:
            return TIER_FRONTIER
        return TIER_MID if params >= _MID_PARAMS else TIER_SMALL

    return TIER_UNKNOWN


def record(capacity_source: str, model: str = "") -> ModelProvenance:
    """Build the provenance stamp for an artifact about to be written."""
    return ModelProvenance(
        capacity_source=capacity_source or "",
        model=model or "",
        tier=classify_tier(capacity_source, model),
    )


def weakest(provenances: list[ModelProvenance]) -> ModelProvenance:
    """The weakest model that touched this expert.

    An expert is only as good as the worst reading in its chain. A brief
    written by a frontier model over findings a 7B model produced inherits the
    7B model's blind spots - the brief can only rank and reconcile what it was
    handed, so it cannot recover a comparison that was never found. Reporting
    the best of the chain would describe the artifact rather than the expert.
    """
    real = [p for p in provenances if p.capacity_source]
    if not real:
        return ModelProvenance()
    return min(real, key=lambda p: _TIER_ORDER.get(p.tier, 0))


def at_least(tier: str, floor: str) -> bool:
    """Whether ``tier`` reaches ``floor``. Unknown never does."""
    return _TIER_ORDER.get(tier, 0) >= _TIER_ORDER.get(floor, 0) > 0
