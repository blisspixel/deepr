"""Conflict resolution agent for expert beliefs.

Detects contradictions between beliefs using both heuristic and LLM-based
approaches, then resolves them via multi-provider adjudication.

Usage:
    resolver = ConflictResolver(consensus_engine=engine)
    contradictions = await resolver.detect_contradictions(beliefs)
    result = await resolver.resolve(belief_a, belief_b)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from deepr.core.contracts import DecisionRecord, DecisionType
from deepr.experts.beliefs import Belief

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ConflictResolutionResult:
    """Result of resolving a conflict between two beliefs."""

    belief_a_id: str
    belief_b_id: str
    outcome: str  # "a_wins", "b_wins", "merged", "needs_human_review"
    explanation: str
    merged_claim: Optional[str] = None
    merged_confidence: Optional[float] = None
    decision_record: Optional[DecisionRecord] = None
    resolved_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "belief_a_id": self.belief_a_id,
            "belief_b_id": self.belief_b_id,
            "outcome": self.outcome,
            "explanation": self.explanation,
            "merged_claim": self.merged_claim,
            "merged_confidence": self.merged_confidence,
            "decision_record": self.decision_record.to_dict() if self.decision_record else None,
            "resolved_at": self.resolved_at.isoformat(),
        }


class ConflictResolver:
    """Detects and resolves contradictions between beliefs.

    Attributes:
        consensus_engine: Optional ConsensusEngine for multi-provider adjudication
        client: OpenAI async client (lazily initialized)
    """

    def __init__(self, consensus_engine: Optional[Any] = None, client: Optional[Any] = None):
        self.consensus_engine = consensus_engine
        self.client = client

    async def _get_client(self):
        if self.client is None:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI()
        return self.client

    async def detect_contradictions(self, beliefs: list[Belief]) -> list[tuple[Belief, Belief]]:
        """Detect contradictions between beliefs.

        Stage 1: Heuristic check (negation + word overlap) — fast, free
        Stage 2: LLM check on remaining pairs — more accurate

        Args:
            beliefs: List of beliefs to check

        Returns:
            List of contradicting belief pairs
        """
        contradictions: list[tuple[Belief, Belief]] = []
        seen_pairs: set[tuple[str, str]] = set()

        # Stage 1: Heuristic detection (from beliefs.py pattern)
        negation_words = {"not", "no", "never", "false", "incorrect", "wrong", "isn't", "doesn't", "don't"}

        for i, a in enumerate(beliefs):
            a_words = set(a.claim.lower().split())
            a_negation = bool(a_words & negation_words)

            for b in beliefs[i + 1 :]:
                pair_key = tuple(sorted((a.id, b.id)))
                if pair_key in seen_pairs:
                    continue

                b_words = set(b.claim.lower().split())
                b_negation = bool(b_words & negation_words)

                # Same domain, opposite polarity, overlapping content
                content_overlap = len(a_words & b_words - negation_words)
                if content_overlap > 2 and a_negation != b_negation:
                    contradictions.append((a, b))
                    seen_pairs.add(pair_key)

        # Stage 2: LLM detection for remaining pairs (batch up to 20 pairs)
        unchecked_pairs = []
        for i, a in enumerate(beliefs):
            for b in beliefs[i + 1 :]:
                pair_key = tuple(sorted((a.id, b.id)))
                if pair_key not in seen_pairs and a.domain == b.domain:
                    unchecked_pairs.append((a, b))
                    seen_pairs.add(pair_key)

        if unchecked_pairs:
            llm_contradictions = await self._llm_detect_contradictions(unchecked_pairs[:20])
            contradictions.extend(llm_contradictions)

        return contradictions

    async def _llm_detect_contradictions(self, pairs: list[tuple[Belief, Belief]]) -> list[tuple[Belief, Belief]]:
        """Use LLM to detect contradictions in belief pairs.

        Args:
            pairs: Belief pairs to check

        Returns:
            Subset of pairs that are contradictory
        """
        if not pairs:
            return []

        prompt_parts = ["For each pair of beliefs, determine if they contradict each other.\n"]
        prompt_parts.append("Output a JSON array of indices (0-based) of contradicting pairs.\n")

        for i, (a, b) in enumerate(pairs):
            prompt_parts.append(f"Pair {i}: A='{a.claim}' vs B='{b.claim}'")

        prompt_parts.append("\nOutput ONLY a JSON array like [0, 3, 5] or [] if none contradict.")

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "Detect contradictions between belief pairs. Output only JSON."},
                    {"role": "user", "content": "\n".join(prompt_parts)},
                ],
                reasoning_effort="low",
            )
            text = (response.choices[0].message.content or "[]").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            indices = json.loads(text)
            return [pairs[i] for i in indices if 0 <= i < len(pairs)]
        except Exception as e:
            logger.warning("LLM contradiction detection failed: %s", e)
            return []

    async def resolve(
        self,
        belief_a: Belief,
        belief_b: Belief,
        context: str = "",
    ) -> ConflictResolutionResult:
        """Resolve a contradiction between two beliefs.

        If a consensus_engine is available, queries multiple providers.
        Otherwise, uses a single LLM call.

        Args:
            belief_a: First belief
            belief_b: Second belief
            context: Additional context for resolution

        Returns:
            ConflictResolutionResult with outcome and explanation
        """
        query = (
            f"Which claim is better supported and more accurate?\n"
            f"Claim A: {belief_a.claim} (confidence: {belief_a.confidence:.0%})\n"
            f"Claim B: {belief_b.claim} (confidence: {belief_b.confidence:.0%})"
        )
        if context:
            query += f"\nContext: {context}"

        if self.consensus_engine:
            # Multi-provider adjudication
            consensus = await self.consensus_engine.research_with_consensus(
                query=query, budget=0.50, expert_name="conflict_resolver"
            )
            return self._parse_resolution(
                belief_a,
                belief_b,
                consensus.consensus_answer,
                consensus.confidence,
                consensus.decision_record,
            )

        # Single-provider resolution
        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You resolve contradictions between beliefs. "
                            'Output JSON: {"winner": "a"|"b"|"merge"|"unclear", '
                            '"explanation": "...", "merged_claim": "..." (if merge)}'
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                reasoning_effort="low",
            )

            text = response.choices[0].message.content or "{}"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = json.loads(text)

            decision = DecisionRecord.create(
                decision_type=DecisionType.CONFLICT_RESOLUTION,
                title=f"Resolved: {belief_a.claim[:30]}... vs {belief_b.claim[:30]}...",
                rationale=parsed.get("explanation", ""),
                confidence=0.7,
                alternatives=[belief_a.claim, belief_b.claim],
            )

            winner = parsed.get("winner", "unclear")
            outcome_map = {"a": "a_wins", "b": "b_wins", "merge": "merged", "unclear": "needs_human_review"}

            return ConflictResolutionResult(
                belief_a_id=belief_a.id,
                belief_b_id=belief_b.id,
                outcome=outcome_map.get(winner, "needs_human_review"),
                explanation=parsed.get("explanation", ""),
                merged_claim=parsed.get("merged_claim"),
                merged_confidence=parsed.get("merged_confidence"),
                decision_record=decision,
            )
        except (json.JSONDecodeError, Exception) as e:
            return ConflictResolutionResult(
                belief_a_id=belief_a.id,
                belief_b_id=belief_b.id,
                outcome="needs_human_review",
                explanation=f"Resolution failed: {e}",
            )

    def _parse_resolution(
        self,
        belief_a: Belief,
        belief_b: Belief,
        answer: str,
        confidence: float,
        decision_record: Optional[DecisionRecord],
    ) -> ConflictResolutionResult:
        """Parse a consensus answer into a resolution result."""
        answer_lower = answer.lower()

        # Determine winner from consensus text
        if "claim a" in answer_lower and ("better" in answer_lower or "correct" in answer_lower):
            outcome = "a_wins"
        elif "claim b" in answer_lower and ("better" in answer_lower or "correct" in answer_lower):
            outcome = "b_wins"
        elif "both" in answer_lower or "merge" in answer_lower:
            outcome = "merged"
        else:
            outcome = "needs_human_review"

        return ConflictResolutionResult(
            belief_a_id=belief_a.id,
            belief_b_id=belief_b.id,
            outcome=outcome,
            explanation=answer[:500],
            decision_record=decision_record,
        )

    async def resolve_all(
        self,
        beliefs: list[Belief],
        budget: float = 5.0,
    ) -> list[ConflictResolutionResult]:
        """Detect and resolve all contradictions within budget.

        Args:
            beliefs: All beliefs to check
            budget: Total budget for all resolutions

        Returns:
            List of resolution results
        """
        contradictions = await self.detect_contradictions(beliefs)
        if not contradictions:
            return []

        cost_per_resolution = 0.50 if self.consensus_engine else 0.05
        max_resolutions = int(budget / cost_per_resolution)

        results = []
        for a, b in contradictions[:max_resolutions]:
            result = await self.resolve(a, b)
            results.append(result)

        return results
