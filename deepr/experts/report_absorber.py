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
   belief - by the same free heuristic ``health-check`` uses - is rejected, not
   silently absorbed. This is the core safety property.
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


@dataclass
class RejectedClaim:
    """A candidate the gates held back, with the reason it was held back."""

    statement: str
    reason: str  # "low_confidence" | "contradicts_existing"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "reason": self.reason, "detail": self.detail}


@dataclass
class AbsorptionResult:
    """The outcome of one absorb run."""

    expert_name: str
    report_id: str
    dry_run: bool
    total_candidates: int
    absorbed: list[AbsorbedClaim] = field(default_factory=list)
    rejected: list[RejectedClaim] = field(default_factory=list)
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
            "absorbed": [a.to_dict() for a in self.absorbed],
            "rejected": [r.to_dict() for r in self.rejected],
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
    ) -> AbsorptionResult:
        """Extract, gate, and (unless dry_run) integrate report claims.

        Args:
            report_id: Identifier recorded as provenance on every belief.
            report_text: Full report text to absorb.
            min_confidence: Drop candidates the report supports more weakly.
            dry_run: Extract and gate but write nothing (preview).
            max_claims: Upper bound on candidates extracted.

        Returns:
            AbsorptionResult describing what was absorbed and what was held back.
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

        for cand in candidates:
            if cand.confidence < min_confidence:
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
            )

            conflict = self._contradicts_existing(belief, existing)
            if conflict is not None:
                rejected.append(
                    RejectedClaim(
                        cand.statement,
                        "contradicts_existing",
                        f"conflicts with belief {conflict.id}: {conflict.claim}",
                    )
                )
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
            estimated_cost=ESTIMATED_EXTRACTION_COST,
        )

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

        raw_claims = parsed.get("claims", []) if isinstance(parsed, dict) else []
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
