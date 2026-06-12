"""Verification-gated absorption of a research report into expert beliefs.

``ReportAbsorber`` is the output-to-knowledge feedback loop (ROADMAP Phase 4):
it promotes a completed research report into an expert's permanent beliefs,
instead of treating the report as a terminal artifact. The compounding-knowledge
value is real, but so is the failure mode the roadmap names - "the model writes
something slightly wrong, you save it back, and the next answer builds on the
mistake." So absorption is gated, not blind:

1. Extraction: one LLM call turns the report into atomic, report-grounded
   candidate claims, each self-rated for how strongly the report supports it.
   (One call regardless of claim count, so cost stays predictable.)
2. Confidence gate: candidates below ``min_confidence`` are dropped.
3. Contradiction gate (cost-$0): a candidate that contradicts an existing
   belief - by the same free heuristic ``health-check`` uses - is never
   silently absorbed. By default it becomes a *flagged contradiction*: stored
   as a contested belief with contradiction edges both ways (contradiction-as-
   signal - the conflict is queryable and feeds ``expert resolve-conflicts``),
   while the existing belief is guaranteed untouched. The core safety property
   holds either way: a contradicting claim never overwrites a belief without
   adjudication or approval. Pass ``flag_contradictions=False`` for the legacy
   silent drop.
4. Dedup + integrate: survivors go through ``BeliefStore.add_belief``, which
   dedupes near-duplicates and integrates only the delta, with the report id
   recorded as provenance on every belief.

The service is deliberately decoupled from report loading and budget gating:
callers pass the report text in and own the cost-safety/approval flow. That
keeps the absorption logic pure and unit-testable without a live provider.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.conflict_resolver import ConflictResolver

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_MODEL = "gpt-5-mini"

# Cap claims extracted per report so a single absorb stays bounded.
_MAX_CLAIMS = 25

# Rough, conservative estimate for the single extraction call (gpt-5-mini class).
ESTIMATED_EXTRACTION_COST = 0.03

# Source tag recorded on every absorbed belief.
SOURCE_TYPE = "absorbed_report"


class ReportAbsorberError(Exception):
    """Raised when a report cannot be absorbed (empty text, bad model output)."""


@dataclass
class CandidateClaim:
    """A claim proposed by extraction, before gating."""

    statement: str
    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class AbsorbedClaim:
    """A claim that passed the gates (or would, in a dry run)."""

    statement: str
    confidence: float
    belief_id: str
    outcome: str  # "added" | "merged" | "would_add"

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "confidence": round(self.confidence, 3),
            "belief_id": self.belief_id,
            "outcome": self.outcome,
        }


# Below this extraction confidence a candidate is noise (rejected outright);
# between here and min_confidence the honest verdict is "the report does not
# support this strongly enough" - abstention, not falsity. The distinction is
# the DAVinCI/TRUST "Not Enough Info" pattern (docs/design/
# calibration-and-trust.md, literature grounding): collapsing both into
# "rejected" made weak support read as refutation.
INSUFFICIENT_GROUNDING_FLOOR = 0.4


@dataclass
class RejectedClaim:
    """A candidate the gates held back, with the reason it was held back."""

    statement: str
    reason: str  # "low_confidence" | "contradicts_existing"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "reason": self.reason, "detail": self.detail}


@dataclass
class InsufficientGroundingClaim:
    """A candidate the report did not support strongly enough to absorb.

    Distinct from rejected: this is abstention ("not enough evidence in THIS
    report"), not refutation. These are natural re-research targets - the
    claim may well be true, the report just is not the source that proves it.
    """

    statement: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "confidence": round(self.confidence, 3)}


@dataclass
class FlaggedContradiction:
    """A candidate that contradicts an existing belief, kept as a signal.

    Contradiction-as-signal (ROADMAP Phase 4): the conflict is the most
    informative thing absorption can surface, so instead of silently dropping
    the candidate we record it as a *contested* belief with contradiction
    edges both ways. The existing belief is never revised or overwritten -
    adjudication (``ConflictResolver.resolve`` / ``expert resolve-conflicts``)
    and human approval own any actual belief revision.
    """

    statement: str
    confidence: float
    belief_id: str  # candidate's belief id ("" until recorded in a live run)
    conflicts_with_id: str
    conflicts_with_claim: str
    conflicts_with_confidence: float
    outcome: str  # "flagged" | "would_flag"
    # The candidate is always the newer side; better_sourced compares
    # report-grounded confidence so reviewers see which way the scale tips.
    better_sourced: str = "tie"  # "candidate" | "existing" | "tie"
    resolution: str = ""  # adjudication outcome when requested: a_wins | b_wins | merged | needs_human_review
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
            "resolution": self.resolution,
            "resolution_explanation": self.resolution_explanation,
        }


@dataclass
class AbsorptionResult:
    """The outcome of one absorb run."""

    expert_name: str
    report_id: str
    dry_run: bool
    total_candidates: int
    absorbed: list[AbsorbedClaim] = field(default_factory=list)
    rejected: list[RejectedClaim] = field(default_factory=list)
    flagged: list[FlaggedContradiction] = field(default_factory=list)
    insufficient: list[InsufficientGroundingClaim] = field(default_factory=list)
    estimated_cost: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def added_count(self) -> int:
        return sum(1 for a in self.absorbed if a.outcome == "added")

    @property
    def merged_count(self) -> int:
        return sum(1 for a in self.absorbed if a.outcome == "merged")

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
            "absorbed": [a.to_dict() for a in self.absorbed],
            "rejected": [r.to_dict() for r in self.rejected],
            "flagged": [f.to_dict() for f in self.flagged],
            "insufficient": [i.to_dict() for i in self.insufficient],
            "estimated_cost": round(self.estimated_cost, 4),
            "generated_at": self.generated_at.isoformat(),
        }


class ReportAbsorber:
    """Promote a research report into an expert's beliefs, verification-gated."""

    def __init__(
        self,
        expert: ExpertProfile,
        *,
        client: Any | None = None,
        model: str = DEFAULT_EXTRACTION_MODEL,
        belief_store: BeliefStore | None = None,
    ) -> None:
        """Create an absorber for one expert.

        Args:
            expert: The loaded expert profile to absorb into.
            client: Optional pre-built AsyncOpenAI client (tests inject a mock).
                If omitted, one is built lazily from OPENAI_API_KEY at call time.
            model: Extraction model (default gpt-5-mini, cheap + structured).
            belief_store: Optional BeliefStore (tests inject one on a tmp dir);
                defaults to the expert's canonical store.
        """
        self.expert = expert
        self.model = model
        self._client = client
        self.belief_store = belief_store if belief_store is not None else BeliefStore(expert.name)

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ReportAbsorberError("OPENAI_API_KEY is not set. Pass a client explicitly or set the env var.")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def absorb(
        self,
        report_id: str,
        report_text: str,
        *,
        min_confidence: float = 0.6,
        dry_run: bool = False,
        max_claims: int = _MAX_CLAIMS,
        flag_contradictions: bool = True,
        adjudicate: bool = False,
    ) -> AbsorptionResult:
        """Extract, gate, and (unless dry_run) integrate report claims.

        Args:
            report_id: Identifier recorded as provenance on every belief.
            report_text: Full report text to absorb.
            min_confidence: Drop candidates the report supports more weakly.
            dry_run: Extract and gate but write nothing (preview).
            max_claims: Upper bound on candidates extracted.
            flag_contradictions: Record contradicting candidates as contested
                beliefs with contradiction edges (the signal) instead of
                silently dropping them. False restores the legacy drop.
            adjudicate: Additionally run ``ConflictResolver.resolve`` on each
                flagged pair (one paid LLM call per conflict) and record the
                verdict on the flag. Advisory only - never mutates beliefs.
                Ignored on dry runs (previews stay extraction-cost only).

        Returns:
            AbsorptionResult describing what was absorbed, held back, and flagged.
        """
        text = (report_text or "").strip()
        if not text:
            raise ReportAbsorberError("report text is empty")

        candidates = await self._extract_claims(text, max_claims)

        # Snapshot existing beliefs once for the contradiction gate; grow it as
        # we absorb so later candidates are checked against earlier ones too.
        existing: list[Belief] = list(self.belief_store.beliefs.values())

        absorbed: list[AbsorbedClaim] = []
        rejected: list[RejectedClaim] = []
        flagged: list[FlaggedContradiction] = []
        insufficient: list[InsufficientGroundingClaim] = []

        for cand in candidates:
            if cand.confidence < min_confidence:
                # Abstention vs refutation: a candidate the report supports
                # weakly (but above the noise floor) is "insufficient
                # grounding" - a re-research target, not a falsehood.
                if cand.confidence >= INSUFFICIENT_GROUNDING_FLOOR:
                    insufficient.append(InsufficientGroundingClaim(cand.statement, cand.confidence))
                else:
                    rejected.append(
                        RejectedClaim(cand.statement, "low_confidence", f"{cand.confidence:.2f} < {min_confidence:.2f}")
                    )
                continue

            belief = Belief(
                claim=cand.statement,
                confidence=cand.confidence,
                evidence_refs=[f"report:{report_id}", *cand.evidence],
                domain=self.expert.domain or "",
                source_type=SOURCE_TYPE,
                # Research-derived knowledge is tertiary: the source-trust
                # ceiling (0.6 single-source / 0.8 with independent
                # corroboration) applies at read time - the deterministic
                # ingestion-time prompt-injection backstop. A single
                # poisoned web result cannot mint a near-certain belief
                # regardless of extraction confidence.
                trust_class="tertiary",
            )

            conflict = self._contradicts_existing(belief, existing)
            if conflict is not None:
                if not flag_contradictions:
                    rejected.append(
                        RejectedClaim(
                            cand.statement,
                            "contradicts_existing",
                            f"conflicts with belief {conflict.id}: {conflict.claim}",
                        )
                    )
                    continue
                flagged.append(await self._flag_contradiction(belief, conflict, dry_run=dry_run, adjudicate=adjudicate))
                existing.append(belief)
                continue

            if dry_run:
                absorbed.append(AbsorbedClaim(cand.statement, cand.confidence, belief.id, "would_add"))
                existing.append(belief)
                continue

            pre_ids = set(self.belief_store.beliefs)
            stored, _change = self.belief_store.add_belief(belief, check_conflicts=True)
            outcome = "merged" if stored.id in pre_ids else "added"
            absorbed.append(AbsorbedClaim(stored.claim, stored.confidence, stored.id, outcome))
            existing.append(stored)

        return AbsorptionResult(
            expert_name=self.expert.name,
            report_id=report_id,
            dry_run=dry_run,
            total_candidates=len(candidates),
            absorbed=absorbed,
            rejected=rejected,
            flagged=flagged,
            insufficient=insufficient,
            estimated_cost=ESTIMATED_EXTRACTION_COST,
        )

    async def _flag_contradiction(
        self,
        belief: Belief,
        conflict: Belief,
        *,
        dry_run: bool,
        adjudicate: bool,
    ) -> FlaggedContradiction:
        """Record a contradicting candidate as a contested belief (the signal).

        Safety property: the existing belief is never revised or overwritten
        here. ``add_contested_belief`` bypasses similarity merging and
        conflict-resolution strategies entirely; it only stores the candidate
        with contradiction edges both ways so ``expert resolve-conflicts`` and
        health-check can adjudicate later. Optional adjudication is advisory -
        its verdict is recorded on the flag, never applied to the store.
        """
        if belief.confidence > conflict.confidence:
            better = "candidate"
        elif belief.confidence < conflict.confidence:
            better = "existing"
        else:
            better = "tie"

        flag = FlaggedContradiction(
            statement=belief.claim,
            confidence=belief.confidence,
            belief_id="" if dry_run else belief.id,
            conflicts_with_id=conflict.id,
            conflicts_with_claim=conflict.claim,
            conflicts_with_confidence=conflict.confidence,
            outcome="would_flag" if dry_run else "flagged",
            better_sourced=better,
        )

        if not dry_run:
            self.belief_store.add_contested_belief(belief, [conflict])
            if adjudicate:
                try:
                    resolver = ConflictResolver(client=self._client)
                    result = await resolver.resolve(belief, conflict)
                    flag.resolution = result.outcome
                    flag.resolution_explanation = result.explanation
                except Exception as exc:  # adjudication is best-effort advisory
                    logger.warning("Conflict adjudication failed for %s: %s", belief.id, exc)
                    flag.resolution = "adjudication_failed"
                    flag.resolution_explanation = str(exc)

        return flag

    @staticmethod
    def _contradicts_existing(belief: Belief, existing: list[Belief]) -> Belief | None:
        """Return the first existing belief the candidate contradicts, else None."""
        for other in existing:
            if ConflictResolver.beliefs_contradict(belief, other):
                return other
        return None

    async def _extract_claims(self, report_text: str, max_claims: int) -> list[CandidateClaim]:
        """One LLM call: report text -> atomic, report-grounded candidate claims."""
        client = self._get_client()
        system = (
            "You extract atomic, verifiable factual claims from a research report so they can "
            "be stored as an expert's beliefs. Return ONLY a JSON object. Each claim MUST be "
            "directly supported by the report text - do not infer beyond it, do not add outside "
            "knowledge. Set confidence to how strongly THIS REPORT supports the claim, not how "
            "plausible it sounds. Prefer fewer, well-grounded claims over many weak ones."
        )
        user = (
            f"Expert domain: {self.expert.domain or 'unspecified'}\n\n"
            f"REPORT:\n{report_text}\n\n"
            "Return JSON with exactly this shape:\n"
            '  {"claims": [{"statement": str, "confidence": number 0-1, '
            '"evidence": [short quote or section from the report]}]}\n'
            f"Extract at most {max_claims} claims. Each statement must be self-contained "
            "(resolve pronouns/acronyms) and stand alone without the report."
        )

        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ReportAbsorberError(f"Extraction model returned non-JSON output: {e}. Raw: {raw[:200]!r}") from e

        # Guard every shape the model might return: a non-dict object, a
        # missing "claims" key, an explicit null, or a non-list value all
        # degrade to "no candidates" rather than crashing.
        raw_claims = parsed.get("claims") if isinstance(parsed, dict) else None
        if not isinstance(raw_claims, list):
            raw_claims = []
        candidates: list[CandidateClaim] = []
        for item in raw_claims[:max_claims]:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement", "")).strip()
            if not statement:
                continue
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            evidence_raw = item.get("evidence", []) or []
            evidence = [str(e).strip() for e in evidence_raw if str(e).strip()][:5]
            candidates.append(CandidateClaim(statement=statement, confidence=confidence, evidence=evidence))

        return candidates
