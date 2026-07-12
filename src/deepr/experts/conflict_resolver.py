"""Conflict resolution agent for expert beliefs.

Routes candidate belief pairs with a lexical heuristic, confirms
contradictions with model judgment, then resolves them via multi-provider
adjudication.

Usage:
    resolver = ConflictResolver(consensus_engine=engine)
    contradictions = await resolver.detect_contradictions(beliefs)
    result = await resolver.resolve(belief_a, belief_b)
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.core.contracts import DecisionRecord, DecisionType
from deepr.experts.beliefs import Belief

logger = logging.getLogger(__name__)

CompletionCall = Callable[..., Awaitable[Any]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _pair_key(a_id: str, b_id: str) -> tuple[str, str]:
    """Order-independent key for a belief pair (for dedup across stages)."""
    return (a_id, b_id) if a_id <= b_id else (b_id, a_id)


@dataclass
class ConflictResolutionResult:
    """Result of resolving a conflict between two beliefs."""

    belief_a_id: str
    belief_b_id: str
    outcome: str  # "a_wins", "b_wins", "merged", "needs_human_review"
    explanation: str
    merged_claim: str | None = None
    merged_confidence: float | None = None
    decision_record: DecisionRecord | None = None
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
        completion_call: Accounted metered completion seam. Without it, direct
            model calls require the explicit owned/prepaid declaration
            ``estimated_cost=0.0``; the default is fail-closed.
    """

    def __init__(
        self,
        consensus_engine: Any | None = None,
        client: Any | None = None,
        completion_call: CompletionCall | None = None,
        estimated_cost: float | None = None,
    ):
        self.consensus_engine = consensus_engine
        self.client = client
        self._completion_call = completion_call
        # None is fail-closed. Zero is an explicit local/prepaid declaration;
        # metered callers must inject a reservation/settlement completion seam.
        self._estimated_cost = estimated_cost

    async def _get_client(self) -> Any:
        if self.client is None:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI()
        return self.client

    _NEGATION_WORDS = {"not", "no", "never", "false", "incorrect", "wrong", "isn't", "doesn't", "don't"}
    _ROUTER_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "because",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "when",
        "with",
    }
    _WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")

    @staticmethod
    def _router_words(claim: str) -> tuple[set[str], bool]:
        """Return meaningful routing tokens plus surface negation presence."""
        words = set(ConflictResolver._WORD_RE.findall(claim.lower()))
        negated = bool(words & ConflictResolver._NEGATION_WORDS)
        meaningful = words - ConflictResolver._NEGATION_WORDS - ConflictResolver._ROUTER_STOPWORDS
        return meaningful, negated

    @staticmethod
    def beliefs_contradict(a: Belief, b: Belief) -> bool:
        """True if two beliefs should be routed for contradiction review.

        The heuristic: opposite polarity (exactly one is negated) plus
        meaningful content overlap (>2 shared non-negation words). No LLM call.
        This is the single-pair predicate behind both
        :meth:`detect_contradictions_heuristic` and the cost-$0 absorption gate.
        It is never a semantic verdict.
        """
        if a.domain != b.domain:
            return False
        a_words, a_negation = ConflictResolver._router_words(a.claim)
        b_words, b_negation = ConflictResolver._router_words(b.claim)
        content_overlap = len(a_words & b_words)
        return content_overlap > 2 and a_negation != b_negation

    @staticmethod
    def detect_contradictions_heuristic(beliefs: list[Belief]) -> list[tuple[Belief, Belief]]:
        """Route contradiction candidates using the free heuristic.

        Flags same-domain belief pairs with opposite polarity (one negated,
        the other not) and meaningful content overlap. This is Stage 1 of
        :meth:`detect_contradictions`, exposed standalone so cost-$0 callers
        (e.g. ``expert health-check``) can run it without an event loop or any
        provider spend.

        Args:
            beliefs: List of beliefs to check

        Returns:
            List of lexical candidate pairs, not confirmed contradictions
        """
        contradictions: list[tuple[Belief, Belief]] = []
        for i, a in enumerate(beliefs):
            for b in beliefs[i + 1 :]:
                if ConflictResolver.beliefs_contradict(a, b):
                    contradictions.append((a, b))
        return contradictions

    async def detect_contradictions(
        self, beliefs: list[Belief], heuristic_only: bool = False
    ) -> list[tuple[Belief, Belief]]:
        """Return model-confirmed contradictions between beliefs.

        Stage 1 prioritizes candidate pairs with a fast lexical router. Stage 2
        asks the model about those candidates and the remaining same-domain
        pairs. Only Stage-2 verdicts are returned. ``heuristic_only`` exposes
        the advisory Stage-1 candidates for cost-$0 health routing and never
        represents them as confirmed meaning.

        Args:
            beliefs: List of beliefs to check
            heuristic_only: When True, run only the free Stage 1 heuristic and
                skip the paid LLM pass.

        Returns:
            Model-confirmed pairs, or lexical candidates when
            ``heuristic_only=True``
        """
        routed_candidates = self.detect_contradictions_heuristic(beliefs)

        if heuristic_only:
            return routed_candidates

        # Model judgment owns meaning. Prioritize lexical candidates to keep the
        # bounded batch useful, then include other same-domain pairs. A router
        # hit is deliberately not copied into the return value.
        candidate_pairs: list[tuple[Belief, Belief]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for a, b in routed_candidates:
            if a.domain != b.domain:
                continue
            candidate_pairs.append((a, b))
            seen_pairs.add(_pair_key(a.id, b.id))

        for i, a in enumerate(beliefs):
            for b in beliefs[i + 1 :]:
                pair_key = _pair_key(a.id, b.id)
                if pair_key not in seen_pairs and a.domain == b.domain:
                    candidate_pairs.append((a, b))
                    seen_pairs.add(pair_key)

        if not candidate_pairs:
            return []
        return await self._llm_detect_contradictions(candidate_pairs[:20])

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

        completion_kwargs = {
            "model": "gpt-5.2",
            "messages": [
                {"role": "system", "content": "Detect contradictions between belief pairs. Output only JSON."},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            "reasoning_effort": "low",
        }
        if self._completion_call is None and self._estimated_cost != 0.0:
            logger.warning("LLM contradiction detection blocked: no accounted or explicit $0 completion path")
            return []

        try:
            if self._completion_call is not None:
                response = await self._completion_call(**completion_kwargs)
            else:
                client = await self._get_client()
                response = await client.chat.completions.create(**completion_kwargs)
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
            if self._estimated_cost != 0.0:
                return ConflictResolutionResult(
                    belief_a_id=belief_a.id,
                    belief_b_id=belief_b.id,
                    outcome="needs_human_review",
                    explanation="Consensus resolution blocked: no explicit $0 capacity contract",
                )
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

        # Single-provider resolution. ReportAbsorber injects completion_call so
        # this optional adjudication shares its caller-supplied run ceiling and
        # canonical settlement path. Keep that dispatch outside the parsing
        # try/except: a cost-admission or settlement failure must fail closed,
        # not be converted into a best-effort semantic result.
        completion_kwargs = {
            "model": "gpt-5.2",
            "messages": [
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
            "reasoning_effort": "low",
        }
        if self._completion_call is not None:
            response = await self._completion_call(**completion_kwargs)
        elif self._estimated_cost != 0.0:
            return ConflictResolutionResult(
                belief_a_id=belief_a.id,
                belief_b_id=belief_b.id,
                outcome="needs_human_review",
                explanation="Resolution blocked: no accounted or explicit $0 completion path",
            )
        else:
            try:
                client = await self._get_client()
                response = await client.chat.completions.create(**completion_kwargs)
            except Exception as e:
                return ConflictResolutionResult(
                    belief_a_id=belief_a.id,
                    belief_b_id=belief_b.id,
                    outcome="needs_human_review",
                    explanation=f"Resolution failed: {e}",
                )

        try:
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
        decision_record: DecisionRecord | None,
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
