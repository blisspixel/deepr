"""Multi-provider consensus engine for expert gap-filling.

Queries 2-3 providers for the same gap question, compares outputs,
and calibrates confidence by inter-provider agreement.

Usage:
    engine = ConsensusEngine()
    result = await engine.research_with_consensus(
        query="What are the latest advances in quantum error correction?",
        budget=3.0,
        expert_name="Quantum Expert"
    )
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from deepr.core.contracts import ConsensusResult, DecisionRecord, DecisionType

logger = logging.getLogger(__name__)

# Provider → env var mapping (mirrors routing/auto_mode.py)
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

# Provider → preferred model for web research
_PROVIDER_MODELS = {
    "xai": "grok-4-fast",
    "openai": "gpt-5.2",
    "gemini": "gemini-3.1-pro-preview",
    "anthropic": "claude-sonnet-4-5-20250929",
}

# Rough cost per query by provider (used for budget planning)
_ESTIMATED_COST = {
    "xai": 0.15,
    "openai": 0.10,
    "gemini": 0.08,
    "anthropic": 0.12,
}


def _has_api_key(provider: str) -> bool:
    """Check if an API key is configured for the given provider."""
    env_var = _PROVIDER_KEY_ENV.get(provider)
    if not env_var:
        return False
    return bool(os.environ.get(env_var))


@dataclass
class ProviderResponse:
    """Response from a single provider query."""

    provider: str
    model: str
    answer: str
    citations: list[str]
    cost: float
    latency: float


class ConsensusEngine:
    """Queries multiple providers and synthesizes consensus answers.

    Attributes:
        min_providers: Minimum providers to query (default 2)
        max_providers: Maximum providers to query (default 3)
        agreement_threshold: Threshold for high-agreement shortcut (default 0.7)
    """

    def __init__(
        self,
        min_providers: int = 2,
        max_providers: int = 3,
        agreement_threshold: float = 0.7,
    ):
        self.min_providers = min_providers
        self.max_providers = max_providers
        self.agreement_threshold = agreement_threshold

    async def research_with_consensus(
        self,
        query: str,
        budget: float,
        expert_name: str,
    ) -> ConsensusResult:
        """Research a query with multi-provider consensus.

        Args:
            query: The research question
            budget: Budget in USD for this query
            expert_name: Name of the expert (for decision records)

        Returns:
            ConsensusResult with calibrated confidence
        """
        providers = self._select_providers(budget)

        if len(providers) < 2:
            # Fall back to single provider
            if providers:
                resp = await self._query_provider(providers[0][0], providers[0][1], query)
                return ConsensusResult(
                    query=query,
                    provider_responses=[
                        {"provider": resp.provider, "model": resp.model, "answer": resp.answer, "cost": resp.cost}
                    ],
                    agreement_score=0.5,
                    consensus_answer=resp.answer,
                    confidence=0.5,
                    total_cost=resp.cost,
                )
            return ConsensusResult(query=query, consensus_answer="No providers available.")

        # Query all providers concurrently
        tasks = [self._query_provider(prov, model, query) for prov, model in providers]
        responses: list[ProviderResponse] = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failed responses
        valid_responses = [r for r in responses if isinstance(r, ProviderResponse)]
        if not valid_responses:
            return ConsensusResult(query=query, consensus_answer="All providers failed.")

        # Compute agreement
        agreement = await self._compute_agreement(valid_responses, query)

        # Merge answers based on agreement level
        merged = self._merge_answers(valid_responses, agreement)

        total_cost = sum(r.cost for r in valid_responses)
        confidence = min(1.0, agreement * 0.8 + 0.2)  # Scale: 0.2 base + 0.8 * agreement

        # Emit decision record
        provider_names = [r.provider for r in valid_responses]
        decision = DecisionRecord.create(
            decision_type=DecisionType.GAP_FILL,
            title=f"Consensus research: {query[:60]}",
            rationale=f"Queried {len(valid_responses)} providers ({', '.join(provider_names)}). "
            f"Agreement: {agreement:.0%}. Confidence: {confidence:.0%}.",
            confidence=confidence,
            alternatives=[f"{r.provider}: {r.answer[:80]}..." for r in valid_responses],
            cost_impact=total_cost,
            context={"expert_name": expert_name, "agreement_score": agreement},
        )

        return ConsensusResult(
            query=query,
            provider_responses=[
                {"provider": r.provider, "model": r.model, "answer": r.answer, "cost": r.cost} for r in valid_responses
            ],
            agreement_score=agreement,
            consensus_answer=merged,
            confidence=confidence,
            total_cost=total_cost,
            decision_record=decision,
        )

    def _select_providers(self, budget: float) -> list[tuple[str, str]]:
        """Select available providers within budget.

        Args:
            budget: Total budget for this query

        Returns:
            List of (provider, model) tuples
        """
        available = []
        for provider, model in _PROVIDER_MODELS.items():
            if _has_api_key(provider):
                available.append((provider, model))

        if not available:
            return []

        # Budget too small for multi-provider: use cheapest single provider
        if budget < 0.10:
            cheapest = min(available, key=lambda p: _ESTIMATED_COST.get(p[0], 1.0))
            return [cheapest]

        # Prefer diverse providers, up to max_providers
        # Sort by estimated cost ascending to maximize count within budget
        available.sort(key=lambda p: _ESTIMATED_COST.get(p[0], 1.0))

        selected = []
        remaining_budget = budget
        for provider, model in available:
            est_cost = _ESTIMATED_COST.get(provider, 0.20)
            if remaining_budget >= est_cost and len(selected) < self.max_providers:
                selected.append((provider, model))
                remaining_budget -= est_cost

        return selected

    async def _query_provider(self, provider: str, model: str, query: str) -> ProviderResponse:
        """Query a single provider for research.

        Args:
            provider: Provider name (openai, xai, gemini, anthropic)
            model: Model identifier
            query: Research query

        Returns:
            ProviderResponse with answer and metadata
        """
        start = time.monotonic()
        answer = ""
        citations: list[str] = []
        cost = 0.0

        try:
            if provider == "xai":
                answer, citations, cost = await self._query_xai(model, query)
            elif provider == "openai":
                answer, citations, cost = await self._query_openai(model, query)
            elif provider == "gemini":
                answer, citations, cost = await self._query_gemini(model, query)
            elif provider == "anthropic":
                answer, citations, cost = await self._query_anthropic(model, query)
            else:
                answer = f"Unsupported provider: {provider}"
        except Exception as e:
            logger.warning("Provider %s failed: %s", provider, e)
            raise

        latency = time.monotonic() - start
        return ProviderResponse(
            provider=provider,
            model=model,
            answer=answer,
            citations=citations,
            cost=cost,
            latency=latency,
        )

    async def _query_xai(self, model: str, query: str) -> tuple[str, list[str], float]:
        """Query xAI (Grok) with web search."""
        import xai_sdk

        client = xai_sdk.Client()
        response = await asyncio.to_thread(
            lambda: client.chat.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a research assistant. Provide thorough, well-sourced answers.",
                    },
                    {"role": "user", "content": query},
                ],
                tools=[{"type": "web_search"}],
            )
        )
        answer = response.choices[0].message.content or ""
        citations = []
        if hasattr(response, "citations") and response.citations:
            citations = [c.get("url", "") for c in response.citations if isinstance(c, dict)]
        cost = getattr(response, "usage", None)
        cost_val = (cost.prompt_tokens * 0.000005 + cost.completion_tokens * 0.000025) if cost else 0.05
        return answer, citations, cost_val

    async def _query_openai(self, model: str, query: str) -> tuple[str, list[str], float]:
        """Query OpenAI with web search preview."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a research assistant. Provide thorough, well-sourced answers."},
                {"role": "user", "content": query},
            ],
            tools=[{"type": "web_search_preview"}],
            reasoning_effort="low",
        )
        answer = response.choices[0].message.content or ""
        citations = []
        # Extract citations from annotations if available
        msg = response.choices[0].message
        if hasattr(msg, "annotations") and msg.annotations:
            for ann in msg.annotations:
                if hasattr(ann, "url"):
                    citations.append(ann.url)
        cost = 0.0
        if response.usage:
            cost = response.usage.prompt_tokens * 0.000002 + response.usage.completion_tokens * 0.000008
        return answer, citations, cost

    async def _query_gemini(self, model: str, query: str) -> tuple[str, list[str], float]:
        """Query Google Gemini with search grounding."""
        from google import genai

        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        response = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model=model,
                contents=query,
                config={"tools": [{"google_search": {}}]},
            )
        )
        answer = response.text or ""
        citations = []
        if hasattr(response, "candidates") and response.candidates:
            cand = response.candidates[0]
            if hasattr(cand, "grounding_metadata") and cand.grounding_metadata:
                for chunk in getattr(cand.grounding_metadata, "grounding_chunks", []):
                    if hasattr(chunk, "web") and hasattr(chunk.web, "uri"):
                        citations.append(chunk.web.uri)
        cost = 0.05  # Estimated
        return answer, citations, cost

    async def _query_anthropic(self, model: str, query: str) -> tuple[str, list[str], float]:
        """Query Anthropic Claude with web search."""
        import anthropic

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": query}],
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        )
        answer = ""
        citations = []
        for block in response.content:
            if hasattr(block, "text"):
                answer += block.text
            if hasattr(block, "citations"):
                for cite in block.citations:
                    if hasattr(cite, "url"):
                        citations.append(cite.url)
        cost = 0.0
        if response.usage:
            cost = response.usage.input_tokens * 0.000003 + response.usage.output_tokens * 0.000015
        return answer, citations, cost

    async def _compute_agreement(self, responses: list[ProviderResponse], query: str) -> float:
        """Compute inter-provider agreement score.

        Uses a lightweight LLM call to compare answers.

        Args:
            responses: Provider responses to compare
            query: Original query for context

        Returns:
            Agreement score 0.0-1.0
        """
        if len(responses) < 2:
            return 0.5

        # Build comparison prompt
        answers_text = ""
        for i, resp in enumerate(responses, 1):
            answers_text += f"\n--- Answer {i} (from {resp.provider}) ---\n{resp.answer[:500]}\n"

        prompt = (
            f"Rate the agreement between these {len(responses)} answers to the question: {query}\n"
            f"{answers_text}\n\n"
            "Output ONLY a single number between 0.0 and 1.0 representing agreement level.\n"
            "1.0 = perfectly agree, 0.0 = completely contradict each other."
        )

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "Output only a single decimal number between 0.0 and 1.0."},
                    {"role": "user", "content": prompt},
                ],
                reasoning_effort="low",
                max_completion_tokens=10,
            )
            text = (response.choices[0].message.content or "0.5").strip()
            return max(0.0, min(1.0, float(text)))
        except Exception:
            # Fallback: simple word overlap heuristic
            return self._heuristic_agreement(responses)

    def _heuristic_agreement(self, responses: list[ProviderResponse]) -> float:
        """Compute agreement via word overlap (fallback when LLM unavailable)."""
        if len(responses) < 2:
            return 0.5

        word_sets = [set(r.answer.lower().split()) for r in responses]
        total_overlap = 0.0
        pairs = 0
        for i in range(len(word_sets)):
            for j in range(i + 1, len(word_sets)):
                intersection = len(word_sets[i] & word_sets[j])
                union = len(word_sets[i] | word_sets[j])
                if union > 0:
                    total_overlap += intersection / union
                pairs += 1

        return total_overlap / max(pairs, 1)

    def _merge_answers(self, responses: list[ProviderResponse], agreement_score: float) -> str:
        """Merge provider answers based on agreement level.

        Args:
            responses: Provider responses
            agreement_score: Inter-provider agreement

        Returns:
            Merged consensus answer
        """
        if not responses:
            return ""

        if agreement_score >= 0.8:
            # High agreement: pick most detailed answer
            return max(responses, key=lambda r: len(r.answer)).answer

        if agreement_score >= 0.5:
            # Moderate agreement: combine unique insights
            primary = max(responses, key=lambda r: len(r.answer))
            others = [r for r in responses if r is not primary]

            merged = primary.answer
            if others:
                merged += "\n\n**Additional perspectives:**\n"
                for r in others:
                    # Add only if substantively different (< 50% word overlap)
                    primary_words = set(primary.answer.lower().split())
                    other_words = set(r.answer.lower().split())
                    overlap = len(primary_words & other_words) / max(len(primary_words | other_words), 1)
                    if overlap < 0.5:
                        merged += f"\n[{r.provider}]: {r.answer[:300]}\n"
            return merged

        # Low agreement: present all perspectives
        parts = []
        for r in responses:
            parts.append(f"**[{r.provider}]**: {r.answer}")
        return "**Note: Providers disagree on this topic. Multiple perspectives follow:**\n\n" + "\n\n---\n\n".join(
            parts
        )
