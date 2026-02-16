"""Expert Council — multi-expert consultation for cross-domain queries.

Selects relevant experts, queries them in parallel, and synthesises
their perspectives into a unified response with agreements/disagreements.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExpertPerspective:
    """One expert's response to a council query."""

    expert_name: str
    domain: str
    response: str
    confidence: float = 0.9
    cost: float = 0.0


@dataclass
class CouncilResult:
    """Result of a council consultation."""

    query: str
    perspectives: list[ExpertPerspective] = field(default_factory=list)
    synthesis: str = ""
    agreements: list[str] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    total_cost: float = 0.0


class ExpertCouncil:
    """Consult multiple domain experts and synthesise their views."""

    MAX_EXPERTS = 5

    async def select_experts(
        self,
        query: str,
        max_experts: int = 3,
        exclude: list[str] | None = None,
    ) -> list[dict]:
        """Score all experts against the query and return the top matches.

        Uses keyword overlap between the query and each expert's domain/description.
        """
        from deepr.experts.profile import ExpertStore

        store = ExpertStore()
        all_experts = store.list_all()
        exclude_set = set(exclude or [])

        query_words = set(query.lower().split())

        scored: list[tuple[float, dict]] = []
        for exp in all_experts:
            if exp["name"] in exclude_set:
                continue
            domain_words = set((exp.get("domain", "") + " " + exp.get("description", "")).lower().split())
            overlap = len(query_words & domain_words)
            scored.append((overlap, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in scored[: min(max_experts, self.MAX_EXPERTS)]]

    async def consult(
        self,
        query: str,
        experts: list[dict] | None = None,
        budget: float = 5.0,
        progress_callback: Any = None,
    ) -> dict:
        """Run a multi-expert consultation.

        Args:
            query: The question to ask all experts
            experts: Optional list of expert dicts (auto-selects if None)
            budget: Total budget for the consultation
            progress_callback: Optional callback(expert_name, status) for progress

        Returns:
            Dict with perspectives, synthesis, agreements, disagreements, total_cost
        """
        from deepr.experts.chat import start_chat_session

        if not experts:
            experts = await self.select_experts(query)

        if not experts:
            return {
                "query": query,
                "perspectives": [],
                "synthesis": "No experts available for this query.",
                "agreements": [],
                "disagreements": [],
                "total_cost": 0.0,
            }

        num = len(experts)
        # 10% reserve for synthesis, rest split among experts
        per_expert_budget = (budget * 0.9) / max(num, 1)

        async def _query_expert(exp: dict) -> ExpertPerspective:
            name = exp["name"]
            if progress_callback:
                try:
                    progress_callback(name, "querying")
                except Exception:
                    pass
            try:
                session = await start_chat_session(name, budget=per_expert_budget, agentic=True, quiet=True)
                response = await session.send_message(
                    f"As a domain expert, please provide your perspective on: {query}"
                )
                cost = session.cost_accumulated
                if progress_callback:
                    try:
                        progress_callback(name, "done")
                    except Exception:
                        pass
                return ExpertPerspective(
                    expert_name=name,
                    domain=exp.get("domain", ""),
                    response=response,
                    cost=cost,
                )
            except Exception as e:
                logger.warning("Council: expert %s failed: %s", name, e)
                if progress_callback:
                    try:
                        progress_callback(name, "failed")
                    except Exception:
                        pass
                return ExpertPerspective(
                    expert_name=name,
                    domain=exp.get("domain", ""),
                    response=f"Unable to respond: {e}",
                    confidence=0.0,
                    cost=0.0,
                )

        # Query all experts in parallel
        perspectives = await asyncio.gather(*[_query_expert(e) for e in experts])
        total_cost = sum(p.cost for p in perspectives)

        # Synthesise
        synthesis = await self._synthesise(query, perspectives, budget * 0.1)
        total_cost += synthesis.get("cost", 0.0)

        return {
            "query": query,
            "perspectives": [
                {
                    "expert_name": p.expert_name,
                    "domain": p.domain,
                    "response": p.response,
                    "confidence": p.confidence,
                    "cost": p.cost,
                }
                for p in perspectives
            ],
            "synthesis": synthesis.get("text", ""),
            "agreements": synthesis.get("agreements", []),
            "disagreements": synthesis.get("disagreements", []),
            "total_cost": round(total_cost, 4),
        }

    async def _synthesise(
        self,
        query: str,
        perspectives: list[ExpertPerspective],
        budget: float,
    ) -> dict:
        """Synthesise multiple expert perspectives into a unified view."""
        import os

        from openai import AsyncOpenAI

        if not perspectives or all(p.confidence == 0 for p in perspectives):
            return {"text": "No valid perspectives to synthesise.", "agreements": [], "disagreements": [], "cost": 0.0}

        parts = []
        for p in perspectives:
            if p.confidence > 0:
                parts.append(f"**{p.expert_name}** ({p.domain}):\n{p.response[:1000]}")

        prompt = (
            f"Query: {query}\n\n"
            f"Expert perspectives:\n\n{'---'.join(parts)}\n\n"
            "Provide:\n"
            "1. SYNTHESIS: A unified answer combining the best insights\n"
            "2. AGREEMENTS: Points where experts agree (bullet list)\n"
            "3. DISAGREEMENTS: Points where they diverge (bullet list)\n"
        )

        try:
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            result = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Synthesise expert perspectives. Be concise and structured."},
                    {"role": "user", "content": prompt[:6000]},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            text = result.choices[0].message.content or ""

            # Simple parsing of agreements/disagreements
            agreements = []
            disagreements = []
            section = None
            for line in text.split("\n"):
                stripped = line.strip()
                upper = stripped.upper()
                if "AGREEMENT" in upper:
                    section = "agree"
                    continue
                elif "DISAGREEMENT" in upper:
                    section = "disagree"
                    continue
                elif "SYNTHESIS" in upper:
                    section = None
                    continue

                if stripped.startswith(("-", "*", "•")) and len(stripped) > 3:
                    item = stripped.lstrip("-*• ").strip()
                    if section == "agree":
                        agreements.append(item)
                    elif section == "disagree":
                        disagreements.append(item)

            return {
                "text": text,
                "agreements": agreements,
                "disagreements": disagreements,
                "cost": 0.001,  # gpt-4o-mini is very cheap
            }
        except Exception as e:
            logger.warning("Council synthesis failed: %s", e)
            return {"text": "Synthesis unavailable.", "agreements": [], "disagreements": [], "cost": 0.0}
