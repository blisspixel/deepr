"""Atomicity monitor for extracted claims (telemetry, never a gate).

Atomic claim decomposition is the LLM extractor's job, not a rule's: the
FActScore/SAFE pipelines split text into atomic facts with a model, and no
credible source recommends a regex/deterministic decomposer
(docs/design/checks-deterministic-vs-agentic.md, finding 3). This module does
NOT decompose or gate anything. It measures the decomposer's *output* with a
cheap lexical proxy - a DecompScore-style atomicity rate - so the system can
observe whether the extraction prompt is actually producing single-assertion
claims.

Two hard contracts, both enforced by tests:

1. **Non-gating.** The rate is telemetry and a router signal only. It never
   drops, holds, splits, or reorders a claim. Absorb outcomes are identical
   whether or not this runs. A lexical signal is never a semantic verdict
   (the explicit invariant of the checks doc); at most it routes attention.
2. **Proxy until calibrated.** Lexical overlap correlates poorly with meaning,
   so a high "compound" count here is a *flag to look*, not a truth. The
   calibration harness (v2.15) owns validating whether this cheap signal
   tracks true atomicity before any paid split pass is ever considered.

The point is honesty about the decomposer, achieved without adding a brittle
rule to the decision path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Conservative clause-joining markers: each tends to join two assertions into
# one claim. Deliberately small and surrounded by word boundaries to limit the
# obvious lexical false positives (e.g. "research and development"). This is a
# proxy, so residual noise is acceptable - it only ever inflates a telemetry
# count, never a verdict, and calibration measures the noise rather than
# assuming it away.
_COMPOUND_MARKERS: tuple[str, ...] = (
    r"\band\b",
    r"\bbut\b",
    r"\bwhereas\b",
    r"\bwhile\b",
    r"\bas well as\b",
    r";",
)
_COMPOUND_RE = re.compile("|".join(_COMPOUND_MARKERS), re.IGNORECASE)


def looks_compound(claim: str) -> bool:
    """Proxy: True if a claim *looks* like it joins more than one assertion.

    A high-recall lexical flag, NOT a verdict that the claim is non-atomic.
    Used only to compute a telemetry rate and to route reviewer attention.
    """
    return bool(_COMPOUND_RE.search(claim or ""))


@dataclass(frozen=True)
class AtomicityReport:
    """DecompScore-style telemetry over a batch of extracted claims.

    Frozen and derived: a pure measurement of the extractor's output, never an
    input to any storage or gating decision.
    """

    total: int
    atomic: int
    compound: int
    rate: float  # atomic / total, in [0, 1]; 1.0 for an empty batch (vacuously)
    compound_examples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "atomic": self.atomic,
            "compound": self.compound,
            "rate": round(self.rate, 3),
            "compound_examples": list(self.compound_examples),
            # Stamp the contract into the payload so a downstream consumer
            # cannot mistake this proxy for a semantic verdict.
            "signal": "lexical_proxy",
            "gating": False,
        }


def atomicity_report(statements: list[str], *, max_examples: int = 5) -> AtomicityReport:
    """Measure the atomicity rate of extracted claim statements (telemetry).

    Args:
        statements: The raw extracted claim strings (measure the decomposer's
            output, before any confidence/contradiction gating).
        max_examples: Cap on compound examples surfaced for review.

    Returns:
        An AtomicityReport. Pure: callers attach it as telemetry; nothing in
        the absorb/sync path branches on it.
    """
    total = len(statements)
    compound_examples = [s for s in statements if looks_compound(s)]
    compound = len(compound_examples)
    atomic = total - compound
    rate = 1.0 if total == 0 else atomic / total
    return AtomicityReport(
        total=total,
        atomic=atomic,
        compound=compound,
        rate=rate,
        compound_examples=tuple(compound_examples[:max_examples]),
    )
