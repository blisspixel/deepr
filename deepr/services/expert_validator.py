"""Expert-as-guardrail: validate claims against an expert's knowledge.

Phase 4 capability. Lets downstream agents (or humans) ask an expert
whether a specific claim/statement is consistent with what that expert
has already learned, and get back a structured PASS / WARN / FAIL with
citations and confidence.

This is the second-class twin of `deepr expert chat`: chat is open-ended
research, validate is bounded, single-turn, JSON-shaped assessment that
downstream agents can branch on without parsing prose.

Design notes
============
- Pure read-side: never mutates the expert's belief store, gap list, or
  worldview. Validation observes; learning is a separate path.
- No web search, no research, no autonomous re-research. The whole point
  is a fast verdict (sub-second target with a small reasoning model)
  bounded to the knowledge the expert already has. If the expert's
  knowledge is thin, that surfaces as WARN with explicit caveats.
- LLM call uses JSON-object response format so the verdict is machine-
  parseable. The model is asked to be conservative — WARN over PASS when
  evidence is thin.
- Claim IDs returned by the LLM are resolved back to canonical Claim
  objects, so callers get full citation provenance, not just statements.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from deepr.core.contracts import Claim
from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)


Verdict = Literal["pass", "warn", "fail"]
_ALLOWED_VERDICTS: frozenset[str] = frozenset({"pass", "warn", "fail"})

# Default model for validation. Cheap + fast reasoning model is the right
# fit: the task is bounded to JSON-shaped assessment over <=2 KB of evidence
# context, so a flagship is wasteful. Callers can override.
DEFAULT_VALIDATION_MODEL = "gpt-5-mini"


@dataclass
class ValidationResult:
    """Structured verdict from validating a claim against an expert.

    Attributes:
        expert_name: Name of the expert that performed the validation.
        claim: The exact claim text that was assessed.
        verdict: One of "pass", "warn", "fail".
        confidence: 0.0-1.0 confidence in the verdict itself.
        reasoning: 1-3 sentence justification, suitable for surfacing to
            humans or downstream agents.
        supporting: Claims from the expert's knowledge that support the
            assessment. May be empty for a fail verdict.
        contradicting: Claims that conflict with the input claim. Empty
            for a clean pass.
        caveats: Specific things the expert is unsure about or knows it
            does not know (gaps that bear on this claim).
        model: The model used for validation (for audit).
    """

    expert_name: str
    claim: str
    verdict: Verdict
    confidence: float
    reasoning: str
    supporting: list[Claim] = field(default_factory=list)
    contradicting: list[Claim] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    model: str = DEFAULT_VALIDATION_MODEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "claim": self.claim,
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "supporting": [c.to_dict() for c in self.supporting],
            "contradicting": [c.to_dict() for c in self.contradicting],
            "caveats": list(self.caveats),
            "model": self.model,
        }


class ExpertValidatorError(Exception):
    """Raised when validation cannot run (e.g. expert has no knowledge yet)."""


class ExpertValidator:
    """Assess a claim against an expert's accumulated knowledge.

    Stateless and side-effect free: validation does not modify the
    expert. Multiple validations can run in parallel against the same
    expert profile safely.
    """

    def __init__(
        self,
        client: Any | None = None,
        model: str = DEFAULT_VALIDATION_MODEL,
        max_evidence: int = 8,
    ) -> None:
        """Create a validator.

        Args:
            client: Optional pre-built AsyncOpenAI client. If omitted, one
                is constructed from the OPENAI_API_KEY environment
                variable. Tests pass a mock here.
            model: Model name to use for the assessment call.
            max_evidence: Maximum number of expert beliefs to include in
                the prompt. Higher = better grounding but more tokens.
        """
        if client is None:
            # Imported lazily so tests that inject their own client do not
            # require the openai package or an API key to be present.
            from openai import AsyncOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ExpertValidatorError("OPENAI_API_KEY is not set. Pass a client explicitly or set the env var.")
            client = AsyncOpenAI(api_key=api_key)
        self.client = client
        self.model = model
        self.max_evidence = max_evidence

    async def validate(self, expert: ExpertProfile, claim: str) -> ValidationResult:
        """Run a single validation against an expert.

        Args:
            expert: The expert profile to consult. Must be loaded; this
                method does not look up by name.
            claim: The statement to assess. Free text.

        Returns:
            ValidationResult with verdict + reasoning + evidence.

        Raises:
            ExpertValidatorError: If the claim is empty, or if the LLM
                returns an unparseable / invalid response shape.
        """
        if not claim or not claim.strip():
            raise ExpertValidatorError("claim must be a non-empty string")

        manifest = expert.get_manifest()

        # Sort by confidence so the highest-signal beliefs land in the
        # prompt first, then cap to max_evidence.
        ranked_claims = sorted(manifest.claims, key=lambda c: c.confidence, reverse=True)[: self.max_evidence]
        top_gaps = list(manifest.gaps)[:5]

        evidence_block = self._format_evidence(ranked_claims)
        gaps_block = self._format_gaps(top_gaps)

        system = (
            "You assess a single claim against an expert's accumulated knowledge. "
            "Return ONLY a JSON object matching the requested schema. "
            "Be conservative: when evidence is thin or absent, choose WARN with "
            "explicit caveats rather than PASS. Reserve FAIL for clear contradiction "
            "with the expert's known beliefs."
        )
        user = (
            f"Expert: {expert.name} (domain: {expert.domain or 'unspecified'})\n\n"
            f"CLAIM TO ASSESS:\n{claim.strip()}\n\n"
            f"EXPERT'S KNOWN BELIEFS (id -> statement, with confidence):\n{evidence_block}\n\n"
            f"EXPERT'S KNOWN GAPS (areas where the expert is explicitly under-informed):\n{gaps_block}\n\n"
            "Return JSON with exactly these fields:\n"
            '  verdict: one of "pass", "warn", "fail"\n'
            "  confidence: number between 0 and 1 (how sure you are in the verdict)\n"
            "  reasoning: 1-3 sentence justification\n"
            "  supporting_claim_ids: list of belief ids that support your verdict (subset of those shown above)\n"
            "  contradicting_claim_ids: list of belief ids that contradict the claim (subset of those shown above)\n"
            "  caveats: list of strings calling out gaps, uncertainties, or scope limits relevant to this claim\n"
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ExpertValidatorError(f"Validator model returned non-JSON output: {e}. Raw: {raw[:200]!r}") from e

        verdict = str(parsed.get("verdict", "")).strip().lower()
        if verdict not in _ALLOWED_VERDICTS:
            raise ExpertValidatorError(
                f"Validator returned invalid verdict {verdict!r}; expected one of {sorted(_ALLOWED_VERDICTS)}"
            )

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reasoning = str(parsed.get("reasoning", "")).strip() or "(no reasoning provided)"

        supporting_ids = {str(i) for i in parsed.get("supporting_claim_ids", []) if i}
        contradicting_ids = {str(i) for i in parsed.get("contradicting_claim_ids", []) if i}
        by_id: dict[str, Claim] = {c.id: c for c in ranked_claims}
        supporting = [by_id[i] for i in supporting_ids if i in by_id]
        contradicting = [by_id[i] for i in contradicting_ids if i in by_id]

        caveats_raw = parsed.get("caveats", []) or []
        caveats = [str(c).strip() for c in caveats_raw if str(c).strip()]

        return ValidationResult(
            expert_name=expert.name,
            claim=claim.strip(),
            verdict=verdict,  # type: ignore[arg-type]
            confidence=confidence,
            reasoning=reasoning,
            supporting=supporting,
            contradicting=contradicting,
            caveats=caveats,
            model=self.model,
        )

    @staticmethod
    def _format_evidence(claims: list[Claim]) -> str:
        if not claims:
            return (
                "(none — this expert has no recorded beliefs yet; you should likely choose WARN with that as a caveat)"
            )
        lines = []
        for c in claims:
            stmt = (c.statement or "").strip().replace("\n", " ")
            if len(stmt) > 220:
                stmt = stmt[:217] + "..."
            lines.append(f"  - {c.id}: {stmt} (conf {c.confidence:.2f})")
        return "\n".join(lines)

    @staticmethod
    def _format_gaps(gaps: list) -> str:
        if not gaps:
            return "(none recorded)"
        lines = []
        for g in gaps:
            topic = getattr(g, "topic", None) or getattr(g, "description", None) or str(g)
            topic = str(topic).strip().replace("\n", " ")
            if len(topic) > 180:
                topic = topic[:177] + "..."
            lines.append(f"  - {topic}")
        return "\n".join(lines)
