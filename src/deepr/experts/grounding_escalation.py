"""Bounded second-checker escalation for weak grounding verdicts (ROADMAP item 8).

The cross-vendor maker-checker (``maker_checker.py``) gives a claim one
independent opinion. This module adds a *second* independent opinion, but only
where it earns its cost: a claim the first checker positively refuted, could
not verify, or that a caller flags high-risk. A clean SUPPORTED verdict is
never escalated, so healthy claims pay for one check, not two - that is the
cost bound that keeps this from becoming a spend storm.

The split follows AGENTIC_BALANCE exactly:

- **Deterministic (form / side-effects):** which claims escalate, which vendor
  gives a genuinely independent third opinion (different from both the maker
  and the first checker, because correlated model error is the failure mode
  this guards against), how two verdicts combine into a hold/clear/contest
  disposition, and whether a metered second checker is even constructed.
- **Model judgment (meaning):** whether the evidence entails the claim - that
  stays entirely inside the injected checkers.

This module never constructs a provider client. The caller injects a
``second_checker_factory`` (vendor -> checker or ``None``) so the spend-policy
gate lives at the orchestration boundary and a metered second checker is built
only when the escalation policy actually fires.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from deepr.experts.maker_checker import CheckAssurance, CheckVerdict, GroundingChecker

# vendor -> a checker for that vendor, or None when unavailable / gated off.
SecondCheckerFactory = Callable[[str], GroundingChecker | None]


class GroundingDisposition(str, Enum):
    """How a claim's grounding resolved after the escalation policy ran."""

    NOT_ESCALATED = "not_escalated"  # first check was clean (or unverifiable with no checker)
    NO_INDEPENDENT_VENDOR = "no_independent_vendor"  # weak, but no genuine third vendor / gated off
    ESCALATED_CLEARED = "escalated_cleared"  # both independent checks positively support
    ESCALATED_HELD = "escalated_held"  # both independent checks positively refute
    ESCALATED_CONTESTED = "escalated_contested"  # checks disagree or the second could not verify


def is_weak_verdict(verdict: CheckVerdict, *, high_risk: bool = False) -> bool:
    """Whether a first-checker verdict warrants a second independent opinion.

    Weak means a positive refutation, or a could-not-verify from a checker that
    actually ran (assurance is not ``UNVERIFIED``), or an explicitly high-risk
    claim. A clean SUPPORTED verdict is never weak unless ``high_risk`` forces
    a second look. ``high_risk`` is a caller-supplied signal, not a meaning
    verdict computed here - deterministic code does not classify claim risk.
    """
    if high_risk:
        return True
    if verdict.refuted:
        return True
    return verdict.supported is None and verdict.assurance is not CheckAssurance.UNVERIFIED


def choose_independent_vendor(
    maker_vendor: str,
    first_checker_vendor: str | None,
    available_vendors: Sequence[str],
) -> str | None:
    """A vendor different from BOTH the maker and the first checker.

    A genuine third opinion needs a third vendor: repeating the maker or the
    first checker re-samples correlated error and adds cost without truth.
    Order of ``available_vendors`` is the tie-break, so callers control
    preference. Returns ``None`` when no independent vendor exists.
    """
    for vendor in available_vendors:
        if vendor and vendor != maker_vendor and vendor != first_checker_vendor:
            return vendor
    return None


def _held_verdict(first: CheckVerdict, second: CheckVerdict) -> CheckVerdict:
    reason = f"held: refuted independently by {first.checker_vendor} and {second.checker_vendor}"
    return CheckVerdict(False, CheckAssurance.CROSS_VENDOR, second.checker_vendor, reason[:200])


def _contested_verdict(second: CheckVerdict) -> CheckVerdict:
    # Conservative: could-not-verify, so the belief is neither trusted nor
    # hard-refuted; the contest is surfaced through the disposition and flag.
    # Covers both genuine disagreement and an unresolved second check.
    return CheckVerdict(None, second.assurance, second.checker_vendor, "contested: independent checks did not agree")


def combine_grounding_verdicts(
    first: CheckVerdict,
    second: CheckVerdict,
) -> tuple[GroundingDisposition, CheckVerdict]:
    """Deterministic disposition over two independent verdicts.

    - both positively support -> CLEARED, carry the supporting second verdict.
    - both positively refute -> HELD, carry a refuted verdict naming both.
    - anything else (disagreement, or the second could not verify) ->
      CONTESTED, carry a conservative could-not-verify verdict.

    CLEARED and HELD each require two *positive* independent agreements, so a
    single lucky or unlucky checker can never alone clear or hold a claim.
    """
    if second.supported is True and first.supported is True:
        return GroundingDisposition.ESCALATED_CLEARED, second
    if second.supported is False and first.supported is False:
        return GroundingDisposition.ESCALATED_HELD, _held_verdict(first, second)
    return GroundingDisposition.ESCALATED_CONTESTED, _contested_verdict(second)


@dataclass(frozen=True)
class EscalatedGrounding:
    """Result of the bounded escalation policy for one claim."""

    disposition: GroundingDisposition
    verdict: CheckVerdict
    first: CheckVerdict
    second: CheckVerdict | None = None
    second_checker_vendor: str | None = None

    @property
    def held(self) -> bool:
        return self.disposition is GroundingDisposition.ESCALATED_HELD


@dataclass(frozen=True)
class GroundingEscalator:
    """Runs bounded second-checker escalation behind an injected checker factory.

    ``second_checker_factory`` is the spend-policy gate seam: it returns a
    checker for a vendor, or ``None`` when that vendor is unavailable or the
    gate declines. It is called only after the policy decides a claim is weak
    *and* an independent vendor exists, so no metered second checker is ever
    constructed for a healthy claim.
    """

    maker_vendor: str
    available_vendors: tuple[str, ...]
    second_checker_factory: SecondCheckerFactory

    def __post_init__(self) -> None:
        # Coerce any sequence to a tuple so the frozen instance is genuinely
        # immutable and hashable regardless of what the caller passes.
        if not isinstance(self.available_vendors, tuple):
            object.__setattr__(self, "available_vendors", tuple(self.available_vendors))

    async def escalate(
        self,
        claim: str,
        evidence: str,
        first_verdict: CheckVerdict,
        *,
        high_risk: bool = False,
    ) -> EscalatedGrounding:
        if not is_weak_verdict(first_verdict, high_risk=high_risk):
            return EscalatedGrounding(GroundingDisposition.NOT_ESCALATED, first_verdict, first_verdict)

        vendor = choose_independent_vendor(self.maker_vendor, first_verdict.checker_vendor, self.available_vendors)
        checker = self.second_checker_factory(vendor) if vendor else None
        if vendor is None or checker is None:
            return EscalatedGrounding(GroundingDisposition.NO_INDEPENDENT_VENDOR, first_verdict, first_verdict)

        second = await checker(claim, evidence)
        disposition, verdict = combine_grounding_verdicts(first_verdict, second)
        return EscalatedGrounding(disposition, verdict, first_verdict, second, vendor)


__all__ = [
    "EscalatedGrounding",
    "GroundingDisposition",
    "GroundingEscalator",
    "SecondCheckerFactory",
    "choose_independent_vendor",
    "combine_grounding_verdicts",
    "is_weak_verdict",
]
