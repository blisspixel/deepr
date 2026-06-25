"""Cross-vendor maker-checker for belief verification.

The absorb gate already routes the contradiction/dedup decision into a model
verdict - the *maker*. The 2026 evidence (docs/design/multi-backend-patterns.md)
is sharp: model errors are correlated across vendors, so averaging or voting adds
cost, not truth - but a *different*-vendor checker, in fresh context, prompted to
disconfirm, catches the independent error slice self-checking misses. This module
is that checker.

The split follows AGENTIC_BALANCE exactly:

- **Deterministic (form):** which vendor checks (vendor diversity is a routing
  requirement, not a preference), the prompt shape, and parsing the verdict.
- **Model judgment (meaning):** whether the evidence actually entails the claim.

The checker sees only ``{claim, evidence}`` - never the maker's reasoning - and is
asked to find what is *unsupported*, not to score quality (the dominant failure
mode is true-but-unsupported claims, so the test is entailment). When only one
vendor is available it degrades to a fresh-context same-model check (weaker, and
recorded as lower assurance) rather than silently skipping verification. A model
or parse failure yields "could not verify", never a false verdict.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CheckAssurance(str, Enum):
    """How hard a claim was checked - surfaced so consumers can weight it."""

    CROSS_VENDOR = "cross_vendor"  # checker is a different vendor than the maker
    SAME_VENDOR_FRESH_CONTEXT = "same_vendor_fresh_context"  # one vendor; fresh context still helps
    UNVERIFIED = "unverified"  # no checker available


@dataclass(frozen=True)
class CheckerChoice:
    """The deterministic vendor-diversity decision."""

    vendor: str | None
    assurance: CheckAssurance


def choose_checker_vendor(maker_vendor: str, available_vendors: list[str]) -> CheckerChoice:
    """Pick the checker vendor: a different one if possible (cross-vendor), else
    the maker's own (same-vendor fresh-context), else none (unverified).

    Deterministic - vendor diversity is a routing requirement, not a preference,
    so it belongs in code while the verdict stays model judgment. Order of
    ``available_vendors`` is the tie-break, so callers control preference.
    """
    for vendor in available_vendors:
        if vendor and vendor != maker_vendor:
            return CheckerChoice(vendor, CheckAssurance.CROSS_VENDOR)
    if maker_vendor and maker_vendor in available_vendors:
        return CheckerChoice(maker_vendor, CheckAssurance.SAME_VENDOR_FRESH_CONTEXT)
    return CheckerChoice(None, CheckAssurance.UNVERIFIED)


@dataclass(frozen=True)
class CheckVerdict:
    """The checker's verdict on one claim.

    ``supported`` is True (evidence entails the claim), False (unsupported by the
    evidence), or None (could not verify - a model/parse failure or no checker).
    None is never treated as a real "unsupported": the caller stays conservative.
    """

    supported: bool | None
    assurance: CheckAssurance
    checker_vendor: str | None
    reason: str = ""

    @property
    def refuted(self) -> bool:
        """True only on a positive UNSUPPORTED verdict (not on could-not-verify)."""
        return self.supported is False

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "assurance": self.assurance.value,
            "checker_vendor": self.checker_vendor,
            "reason": self.reason,
        }


GroundingChecker = Callable[[str, str], Awaitable[CheckVerdict]]


_SYSTEM_PROMPT = (
    "You are a skeptical fact-checker. You are given a CLAIM and the EVIDENCE that is "
    "supposed to support it, and nothing else. Decide only whether the evidence ENTAILS "
    "the claim - whether the claim follows from the evidence as written. A claim that is "
    "plausibly true but is not actually stated or entailed by the evidence is UNSUPPORTED. "
    "Judge only against the given evidence; do not rely on outside knowledge. Answer with "
    "one word on the first line - SUPPORTED, UNSUPPORTED, or UNVERIFIABLE - then one short "
    "sentence giving the reason."
)


def build_disconfirm_messages(claim: str, evidence: str) -> list[dict[str, str]]:
    """Fresh-context, disconfirm-focused prompt: claim + evidence only."""
    user = (
        f"CLAIM:\n{claim.strip()}\n\n"
        f"EVIDENCE:\n{evidence.strip() or '(no evidence provided)'}\n\n"
        "Does the evidence entail the claim?"
    )
    return [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse_verdict(text: str) -> tuple[bool | None, str]:
    """Parse the checker's reply into ``(supported, reason)``.

    Deterministic form parsing: the first word decides; anything that is not a
    clear SUPPORTED/UNSUPPORTED (including UNVERIFIABLE or an off-format reply)
    is ``None`` - could not verify - so an unclear answer never becomes a verdict.
    """
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None, ""
    first = lines[0].strip().lower()
    reason = " ".join(lines[1:]).strip()[:200]
    if first.startswith("unsupported"):
        return False, reason
    if first.startswith("supported"):
        return True, reason
    return None, reason


async def check_claim(
    claim: str,
    evidence: str,
    *,
    client: Any,
    checker_vendor: str | None,
    assurance: CheckAssurance,
    model: str,
) -> CheckVerdict:
    """Run a fresh-context, disconfirm-prompted entailment check on one claim.

    ``client`` is an OpenAI-shaped chat client for the chosen checker vendor (the
    caller selects it via :func:`choose_checker_vendor` and builds the matching
    client). A missing client or an UNVERIFIED assurance returns "could not
    verify"; so does any model/parse failure - the check never invents a verdict.
    """
    if client is None or assurance is CheckAssurance.UNVERIFIED:
        return CheckVerdict(None, CheckAssurance.UNVERIFIED, None)
    try:
        response = await client.chat.completions.create(
            model=model, messages=build_disconfirm_messages(claim, evidence)
        )
        text = response.choices[0].message.content or ""
    except Exception as exc:  # a verdict failure must never become a false refutation
        logger.warning("Cross-vendor check failed (vendor=%s): %s", checker_vendor, exc)
        return CheckVerdict(None, assurance, checker_vendor, "check failed")
    supported, reason = parse_verdict(text)
    return CheckVerdict(supported, assurance, checker_vendor, reason)


def make_grounding_checker(
    *,
    client: Any,
    checker_vendor: str | None,
    assurance: CheckAssurance,
    model: str,
) -> GroundingChecker:
    """Adapt an OpenAI-shaped client into ReportAbsorber's checker seam."""

    async def _grounding_checker(claim: str, evidence: str) -> CheckVerdict:
        return await check_claim(
            claim,
            evidence,
            client=client,
            checker_vendor=checker_vendor,
            assurance=assurance,
            model=model,
        )

    return _grounding_checker
