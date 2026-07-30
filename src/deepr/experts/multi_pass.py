"""Multi-pass gap-filling pipeline for expert knowledge.

Implements a 3-pass research pipeline:
  Pass 1 - Extract: Research the gap (optionally with consensus)
  Pass 2 - Cross-Reference: Compare findings against existing claims
  Pass 3 - Synthesize: Integrate into beliefs with closure rationale

Usage:
    pipeline = MultiPassPipeline()
    result = await pipeline.fill_gap(gap, existing_claims, expert_name, domain, budget)
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.services.context_chainer import ContextChainer, StructuredPhaseOutput

logger = logging.getLogger(__name__)

_MODEL = "gpt-5.2"
_EXTRACT_CALL_CEILING_USD = 0.10
_EXTRACT_OUTPUT_TOKENS = 1_600
_CROSS_REFERENCE_CALL_CEILING_USD = 0.04
_CROSS_REFERENCE_OUTPUT_TOKENS = 1_000
_SYNTHESIS_CALL_CEILING_USD = 0.05
_SYNTHESIS_OUTPUT_TOKENS = 1_400


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class CrossReferenceResult:
    """Result of cross-referencing findings against existing claims."""

    confirmations: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    novel_facts: list[str] = field(default_factory=list)
    confidence_adjustment: float = 0.0


@dataclass
class MultiPassResult:
    """Result of the multi-pass gap-filling pipeline."""

    gap_topic: str
    beliefs: list[dict] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    filled: bool = False
    extraction_output: StructuredPhaseOutput | None = None
    cross_reference: CrossReferenceResult | None = None
    total_cost: float = 0.0
    passes_completed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_topic": self.gap_topic,
            "beliefs": self.beliefs,
            "changes": self.changes,
            "filled": self.filled,
            "extraction_output": self.extraction_output.to_dict() if self.extraction_output else None,
            "cross_reference": {
                "confirmations": self.cross_reference.confirmations,
                "contradictions": self.cross_reference.contradictions,
                "novel_facts": self.cross_reference.novel_facts,
                "confidence_adjustment": self.cross_reference.confidence_adjustment,
            }
            if self.cross_reference
            else None,
            "total_cost": self.total_cost,
            "passes_completed": self.passes_completed,
        }


class MultiPassPipeline:
    """3-pass gap-filling pipeline: Extract -> Cross-Reference -> Synthesize.

    Attributes:
        client: OpenAI async client (lazily initialized)
        consensus_engine: Optional ConsensusEngine for multi-provider research
        chainer: ContextChainer for structured phase handoffs
    """

    def __init__(self, client: Any | None = None, consensus_engine: Any | None = None):
        self.client = client
        self.consensus_engine = consensus_engine
        self.chainer = ContextChainer()

    async def _get_client(self):
        if self.client is None:
            from openai import AsyncOpenAI

            from deepr.providers.dispatch_authority import default_paid_endpoint

            self.client = AsyncOpenAI(base_url=default_paid_endpoint("openai"), max_retries=0)
        return self.client

    async def _complete_bounded(
        self,
        *,
        operation: str,
        source: str,
        messages: list[dict[str, str]],
        budget: float,
        hard_ceiling: float,
        output_tokens: int,
    ) -> Any:
        """Execute one pass without exceeding its caller allocation."""
        from deepr.experts.report_absorber_costs import bounded_metered_completion_kwargs
        from deepr.providers.dispatch_authority import require_official_paid_client
        from deepr.services.metered_call import execute_reserved_async_call

        if not math.isfinite(float(budget)) or float(budget) <= 0:
            raise ValueError("multi-pass call budget must be finite and positive")
        call_ceiling = min(float(budget), hard_ceiling)
        kwargs, worst_case_cost = bounded_metered_completion_kwargs(
            operation=operation,
            model=_MODEL,
            call_ceiling=call_ceiling,
            kwargs={
                "model": _MODEL,
                "messages": messages,
                "reasoning_effort": "low",
                "max_completion_tokens": output_tokens,
            },
        )

        client = await self._get_client()
        require_official_paid_client(client, "openai")

        async def dispatch() -> Any:
            return await client.chat.completions.create(**kwargs)

        return await execute_reserved_async_call(
            operation_prefix=f"multi-pass-{operation}",
            provider="openai",
            model=_MODEL,
            source=source,
            max_cost_per_job=worst_case_cost,
            call=dispatch,
            request_envelope=kwargs,
        )

    async def fill_gap(
        self,
        gap: Any,
        existing_claims: list[dict],
        expert_name: str,
        domain: str,
        budget: float,
        use_consensus: bool = False,
    ) -> MultiPassResult:
        """Execute the 3-pass gap-filling pipeline.

        Args:
            gap: KnowledgeGap or similar object with topic/questions
            existing_claims: List of existing claim dicts for cross-referencing
            expert_name: Name of the expert
            domain: Expert's domain
            budget: Total budget for all passes
            use_consensus: Whether to use multi-provider consensus in extraction

        Returns:
            MultiPassResult with beliefs, changes, and metadata
        """
        gap_topic = gap.topic if hasattr(gap, "topic") else str(gap)
        gap_questions = gap.questions if hasattr(gap, "questions") else []

        result = MultiPassResult(gap_topic=gap_topic)

        # Budget allocation: 50% extract, 25% cross-ref, 25% synthesize
        extract_budget = budget * 0.5
        cross_ref_budget = budget * 0.25
        synth_budget = budget * 0.25

        # Pass 1: Extract
        try:
            extraction = await self._pass_extract(gap_topic, gap_questions, extract_budget, use_consensus)
            result.extraction_output = extraction
            result.passes_completed = 1
        except Exception as e:
            logger.warning("Pass 1 (Extract) failed for %s: %s", gap_topic, e)
            return result

        # Pass 2: Cross-Reference
        try:
            cross_ref = await self._pass_cross_reference(extraction, existing_claims, cross_ref_budget)
            result.cross_reference = cross_ref
            result.passes_completed = 2
        except Exception as e:
            logger.warning("Pass 2 (Cross-Reference) failed for %s: %s", gap_topic, e)
            # Continue with synthesis anyway using extraction alone

        # Pass 3: Synthesize
        try:
            beliefs, changes, filled = await self._pass_synthesize(
                extraction, result.cross_reference, gap_topic, domain, synth_budget
            )
            result.beliefs = beliefs
            result.changes = changes
            result.filled = filled
            result.passes_completed = 3
        except Exception as e:
            logger.warning("Pass 3 (Synthesize) failed for %s: %s", gap_topic, e)

        return result

    async def _pass_extract(
        self,
        gap_topic: str,
        gap_questions: list[str],
        budget: float,
        use_consensus: bool,
    ) -> StructuredPhaseOutput:
        """Pass 1: Research the gap.

        Args:
            gap_topic: Topic of the knowledge gap
            gap_questions: Questions to answer
            budget: Budget for this pass
            use_consensus: Whether to use multi-provider consensus

        Returns:
            StructuredPhaseOutput with extracted findings
        """
        query = gap_topic
        if gap_questions:
            query = gap_questions[0]
            if len(gap_questions) > 1:
                query += f" Also: {'; '.join(gap_questions[1:3])}"

        if use_consensus and self.consensus_engine:
            consensus_result = await self.consensus_engine.research_with_consensus(
                query=query, budget=budget, expert_name="multi_pass"
            )
            raw_output = consensus_result.consensus_answer
        else:
            # Server-side search is intentionally excluded here because this
            # legacy chat endpoint cannot prove a provider-enforced tool-call
            # count. Fresh web research must use the bounded research service.
            response = await self._complete_bounded(
                operation="extract",
                source="experts.multi_pass.pass_extract",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a research assistant. Provide thorough, evidence-based answers.",
                    },
                    {"role": "user", "content": f"Research thoroughly: {query}"},
                ],
                budget=budget,
                hard_ceiling=_EXTRACT_CALL_CEILING_USD,
                output_tokens=_EXTRACT_OUTPUT_TOKENS,
            )
            raw_output = response.choices[0].message.content or ""

        # Structure the output
        return self.chainer.structure_phase_output(raw_output=raw_output, phase=1)

    async def _pass_cross_reference(
        self,
        extraction: StructuredPhaseOutput,
        existing_claims: list[dict],
        budget: float,
    ) -> CrossReferenceResult:
        """Pass 2: Cross-reference findings against existing claims.

        Args:
            extraction: Structured output from Pass 1
            existing_claims: Existing claim dicts
            budget: Budget for this pass

        Returns:
            CrossReferenceResult with confirmations, contradictions, novel facts
        """
        # Build context from extraction
        findings_text = "\n".join(f"- {f.text[:200]}" for f in extraction.key_findings[:10])

        claims_text = ""
        for claim in existing_claims[:20]:
            statement = claim.get("statement", claim.get("claim", ""))
            confidence = claim.get("confidence", 0.0)
            claims_text += f"- {statement} (confidence: {confidence:.0%})\n"

        prompt = (
            "Compare these new research findings against the existing claims.\n\n"
            f"**New Findings:**\n{findings_text}\n\n"
            f"**Existing Claims:**\n{claims_text}\n\n"
            "Output JSON:\n"
            '{"confirmations": ["findings that support existing claims"],\n'
            ' "contradictions": ["findings that contradict existing claims"],\n'
            ' "novel_facts": ["entirely new information not in existing claims"]}\n\n'
            "Output ONLY the JSON."
        )

        response = await self._complete_bounded(
            operation="cross-reference",
            source="experts.multi_pass.pass_cross_reference",
            messages=[
                {"role": "system", "content": "You cross-reference research findings. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            budget=budget,
            hard_ceiling=_CROSS_REFERENCE_CALL_CEILING_USD,
            output_tokens=_CROSS_REFERENCE_OUTPUT_TOKENS,
        )

        try:
            text = response.choices[0].message.content or "{}"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = json.loads(text)

            confirmations = parsed.get("confirmations", [])
            contradictions = parsed.get("contradictions", [])
            novel_facts = parsed.get("novel_facts", [])

            # Confidence adjustment based on cross-reference
            adjustment = 0.0
            if confirmations:
                adjustment += 0.1 * min(len(confirmations), 3) / 3
            if contradictions:
                adjustment -= 0.2 * min(len(contradictions), 3) / 3

            return CrossReferenceResult(
                confirmations=confirmations,
                contradictions=contradictions,
                novel_facts=novel_facts,
                confidence_adjustment=adjustment,
            )
        except json.JSONDecodeError:
            return CrossReferenceResult()

    async def _pass_synthesize(
        self,
        extraction: StructuredPhaseOutput,
        cross_ref: CrossReferenceResult | None,
        gap_topic: str,
        domain: str,
        budget: float,
    ) -> tuple[list[dict], list[dict], bool]:
        """Pass 3: Synthesize findings into beliefs.

        Args:
            extraction: Pass 1 output
            cross_ref: Pass 2 output (may be None)
            gap_topic: Topic of the gap
            domain: Expert's domain
            budget: Budget for this pass

        Returns:
            Tuple of (beliefs, changes, gap_filled)
        """
        findings_text = "\n".join(f"- {f.text[:200]}" for f in extraction.key_findings[:10])

        cross_ref_text = ""
        if cross_ref:
            if cross_ref.confirmations:
                cross_ref_text += "\nConfirmed: " + "; ".join(cross_ref.confirmations[:3])
            if cross_ref.contradictions:
                cross_ref_text += "\nContradicted: " + "; ".join(cross_ref.contradictions[:3])
            if cross_ref.novel_facts:
                cross_ref_text += "\nNovel: " + "; ".join(cross_ref.novel_facts[:3])

        prompt = (
            f"Synthesize these findings about '{gap_topic}' in domain '{domain}' into structured beliefs.\n\n"
            f"**Research Findings:**\n{findings_text}\n"
            f"{cross_ref_text}\n\n"
            "Output JSON:\n"
            '{"beliefs": [{"statement": "...", "confidence": 0.85, "evidence": ["..."]}],\n'
            ' "changes": [{"type": "created|revised", "description": "..."}],\n'
            ' "gap_filled": true/false}\n\n'
            "Output ONLY the JSON."
        )

        response = await self._complete_bounded(
            operation="synthesize",
            source="experts.multi_pass.pass_synthesize",
            messages=[
                {
                    "role": "system",
                    "content": "You synthesize research into structured beliefs. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            budget=budget,
            hard_ceiling=_SYNTHESIS_CALL_CEILING_USD,
            output_tokens=_SYNTHESIS_OUTPUT_TOKENS,
        )

        try:
            text = response.choices[0].message.content or "{}"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = json.loads(text)

            beliefs = parsed.get("beliefs", [])
            changes = parsed.get("changes", [])
            filled = parsed.get("gap_filled", bool(beliefs))

            # Apply confidence adjustment from cross-referencing
            if cross_ref:
                for belief in beliefs:
                    base_conf = belief.get("confidence", 0.5)
                    adjusted = max(0.0, min(1.0, base_conf + cross_ref.confidence_adjustment))
                    belief["confidence"] = adjusted

            return beliefs, changes, filled

        except json.JSONDecodeError:
            return [], [], False
