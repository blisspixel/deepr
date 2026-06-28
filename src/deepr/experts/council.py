"""Expert Council - multi-expert consultation for cross-domain queries.

Selects relevant experts, queries them in parallel, and synthesises
their perspectives into a unified response with agreements/disagreements.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from deepr.experts.constants import MAX_COUNCIL_CONCURRENCY, SYNTHESIS_BUDGET_FRACTION, UTILITY_MODEL

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+\-.]*")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "this",
        "to",
        "we",
        "what",
        "when",
        "where",
        "why",
        "with",
    }
)
_MAX_STORED_BELIEFS = 8
_MAX_FALLBACK_BELIEFS = 5
_MAX_SOURCE_REFS = 3
_MAX_REF_CHARS = 140
_SYNTHESIS_FALLBACK_COST = 0.001


def _usage_count(usage: Any, *names: str) -> int:
    for name in names:
        value = getattr(usage, name, 0) or 0
        if value:
            return int(value)
    return 0


def _chat_completion_cost(usage: Any, model_name: str) -> tuple[float, int, int, bool]:
    """Compute a chat-completion cost from provider usage."""
    if usage is None:
        return _SYNTHESIS_FALLBACK_COST, 0, 0, True

    input_tokens = _usage_count(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_count(usage, "completion_tokens", "output_tokens")
    if input_tokens <= 0 and output_tokens <= 0:
        return _SYNTHESIS_FALLBACK_COST, 0, 0, True

    from deepr.providers.registry import get_token_pricing

    prices = get_token_pricing(model_name, input_tokens=input_tokens)
    cost = (input_tokens / 1_000_000) * prices["input"] + (output_tokens / 1_000_000) * prices["output"]
    return cost, input_tokens, output_tokens, False


def _synthesis_section(line: str) -> str | None:
    """Return the section marker for a synthesis heading, if present."""
    normalized = line.strip().lstrip("#").strip()
    normalized = re.sub(r"^\d+\.\s*", "", normalized).upper()
    if normalized.startswith("DISAGREEMENTS"):
        return "disagree"
    if normalized.startswith("AGREEMENTS"):
        return "agree"
    if normalized.startswith("SYNTHESIS"):
        return "synthesis"
    return None


def _clean_synthesis_bullet(item: str) -> str:
    """Normalize harmless Markdown emphasis in parsed synthesis bullets."""
    return re.sub(r"^(\*\*|__)(.+?)(\*\*|__)(:)", r"\2\4", item).strip()


def parse_synthesis_sections(text: str) -> tuple[list[str], list[str]]:
    """Parse agreement and disagreement bullets from a structured synthesis."""
    agreements: list[str] = []
    disagreements: list[str] = []
    section = None
    for line in text.split("\n"):
        stripped = line.strip()
        heading = _synthesis_section(stripped)
        if heading == "disagree":
            section = "disagree"
            continue
        if heading == "agree":
            section = "agree"
            continue
        if heading == "synthesis":
            section = None
            continue

        if stripped.startswith(("-", "*", "\u2022")) and len(stripped) > 3:
            item = _clean_synthesis_bullet(re.sub(r"^[-*\u2022]\s*", "", stripped).strip())
            if section == "agree":
                agreements.append(item)
            elif section == "disagree":
                disagreements.append(item)
    return agreements, disagreements


@dataclass
class ExpertPerspective:
    """One expert's response to a council query."""

    expert_name: str
    domain: str
    response: str
    confidence: float = 0.9
    cost: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)


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

    # Upper bound on auto-selected experts per consult. Parallel dispatch is
    # separately bounded by MAX_COUNCIL_CONCURRENCY, so a 10-expert fan-out runs
    # in concurrency-sized waves rather than 10 at once.
    MAX_EXPERTS = 10

    def __init__(
        self,
        *,
        synthesis_client: Any | None = None,
        synthesis_model: str = UTILITY_MODEL,
        synthesis_provider: str = "openai",
        allow_live_fallback: bool = True,
    ) -> None:
        self._synthesis_client = synthesis_client
        self._synthesis_model = synthesis_model
        self._synthesis_provider = synthesis_provider
        self._allow_live_fallback = allow_live_fallback

    @staticmethod
    def _terms(text: str) -> set[str]:
        """Tokenize text for retrieval only, never as a truth verdict."""
        terms: set[str] = set()
        for term in _TOKEN_RE.findall(text.lower()):
            if len(term) <= 2 or term in _STOPWORDS:
                continue
            terms.add(term)
            if term.endswith("s") and len(term) > 4:
                terms.add(term[:-1])
            if term == "agentic":
                terms.add("agent")
        return terms

    @staticmethod
    def _compact_refs(refs: Iterable[str]) -> list[str]:
        """Return compact source identifiers, skipping free-text excerpts."""
        compact: list[str] = []
        seen: set[str] = set()
        for ref in refs:
            token = str(ref).strip()
            if not token or any(ch.isspace() for ch in token):
                continue
            if len(token) > _MAX_REF_CHARS:
                token = token[: _MAX_REF_CHARS - 3] + "..."
            if token in seen:
                continue
            seen.add(token)
            compact.append(token)
            if len(compact) >= _MAX_SOURCE_REFS:
                break
        return compact

    def build_stored_perspective(
        self, query: str, name: str, domain: str, beliefs: Iterable[Any]
    ) -> ExpertPerspective | None:
        """Build a deterministic perspective from an expert's belief store.

        This is context selection, not adjudication: lexical overlap only decides
        which stored beliefs enter the council packet. The model synthesis step
        still receives confidence, source, and contradiction signals rather than
        a pre-baked verdict.
        """
        belief_list = list(beliefs)
        if not belief_list:
            return None

        query_terms = self._terms(query)

        def _score(belief: Any) -> tuple[int, float, str]:
            belief_terms = self._terms(f"{belief.domain} {belief.claim}")
            overlap = len(query_terms & belief_terms) if query_terms else 0
            return (overlap, belief.get_current_confidence(), belief.claim)

        scored = sorted(
            ((_score(belief), belief) for belief in belief_list),
            key=lambda item: (-item[0][0], -item[0][1], item[0][2]),
        )
        direct = any(score[0] > 0 for score, _belief in scored)
        selected_terms: set[str] = set()
        if direct:
            selected = [belief for score, belief in scored if score[0] > 0][:_MAX_STORED_BELIEFS]
            for belief in selected:
                selected_terms.update(query_terms & self._terms(f"{belief.domain} {belief.claim}"))
            selection = "query_overlap"
            selection_note = "Selected stored beliefs by query-token overlap, then confidence."
        else:
            selected = [belief for _score_tuple, belief in scored[:_MAX_FALLBACK_BELIEFS]]
            selection = "confidence_fallback"
            selection_note = (
                "No direct stored-belief overlap found; using highest-confidence beliefs as fallback context."
            )

        if not selected:
            return None

        lines = [
            f"Stored belief perspective for {name}.",
            selection_note,
            f"{len(selected)} of {len(belief_list)} active beliefs included.",
            "",
        ]
        for belief in selected:
            confidence = belief.get_current_confidence()
            contested = (
                f", contested with {len(belief.contradictions_with)} belief(s)" if belief.contradictions_with else ""
            )
            domain_label = belief.domain or domain or "general"
            lines.append(f"- ({confidence:.2f}, {domain_label}{contested}) {belief.claim}")
            refs = self._compact_refs(belief.evidence_refs)
            if refs:
                lines.append(f"  Sources: {'; '.join(refs)}")

        confidence = sum(b.get_current_confidence() for b in selected) / len(selected)
        return ExpertPerspective(
            expert_name=name,
            domain=domain,
            response="\n".join(lines),
            confidence=round(confidence, 3),
            cost=0.0,
            context={
                "source": "belief_store",
                "selection": selection,
                "selection_note": selection_note,
                "beliefs_available": len(belief_list),
                "beliefs_included": len(selected),
                "matched_terms": sorted(selected_terms)[:20],
            },
        )

    def _load_stored_perspective(self, query: str, name: str, domain: str) -> ExpertPerspective | None:
        """Load stored beliefs for an expert and build a council perspective."""
        from deepr.experts.beliefs import BeliefStore
        from deepr.experts.paths import canonical_expert_dir

        belief_file = canonical_expert_dir(name) / "beliefs" / "beliefs.json"
        if not belief_file.exists():
            return None

        store = BeliefStore(name)
        perspective = self.build_stored_perspective(query, name, domain, store.beliefs.values())
        if perspective is not None:
            self._attach_self_model_context(perspective.context, name)
        return perspective

    def _self_model_context(self, name: str) -> dict[str, Any]:
        """Return bounded self-model metadata for consult traces."""
        from deepr.experts.self_model import build_expert_self_model_context

        return build_expert_self_model_context(name, focus_limit=3)

    def _attach_self_model_context(self, context: dict[str, Any], name: str) -> None:
        self_model = self._self_model_context(name)
        if self_model:
            context["self_model"] = self_model

    async def select_experts(
        self,
        query: str,
        max_experts: int = 3,
        exclude: list[str] | None = None,
    ) -> list[dict]:
        """Score all experts against the query and return the top matches.

        Uses keyword overlap between the query and each expert's domain/description.
        Returns list of dicts with 'name' and 'domain' keys.
        """
        from deepr.experts.profile import ExpertStore

        store = ExpertStore()
        all_experts = store.list_all()
        exclude_set = set(exclude or [])

        query_words = self._terms(query)

        scored: list[tuple[float, dict]] = []
        for exp in all_experts:
            name = exp.name
            if name in exclude_set:
                continue
            domain = getattr(exp, "domain", "") or ""
            description = getattr(exp, "description", "") or ""
            domain_words = self._terms(f"{name} {domain} {description}")
            overlap = len(query_words & domain_words)
            scored.append((overlap, {"name": name, "domain": domain}))

        scored.sort(key=lambda x: x[0], reverse=True)
        limit = min(max_experts, self.MAX_EXPERTS)
        # Prefer only experts with at least some query overlap, so a wide
        # auto-fan-out (max_experts up to MAX_EXPERTS) does not pad the council
        # with irrelevant experts. Keyword overlap here only *routes* selection;
        # it never concludes meaning (AGENTIC_BALANCE). Fall back to the top
        # scorers when nothing overlaps, so consult is never starved of experts.
        relevant = [exp for score, exp in scored if score > 0]
        chosen = relevant if relevant else [exp for _, exp in scored]
        return chosen[:limit]

    @staticmethod
    def _notify(progress_callback: Any, name: str, status: str) -> None:
        if progress_callback:
            try:
                progress_callback(name, status)
            except Exception:
                logger.debug("Council progress callback failed for %s", name, exc_info=True)

    async def _query_expert(
        self,
        query: str,
        exp: dict,
        per_expert_budget: float,
        progress_callback: Any,
        agent_identity: Any,
    ) -> ExpertPerspective:
        name = exp["name"]
        domain = exp.get("domain", "")
        self._notify(progress_callback, name, "querying")
        try:
            stored = self._load_stored_perspective(query, name, domain)
            if stored is not None:
                self._notify(progress_callback, name, "done")
                return stored
            if not self._allow_live_fallback:
                self._notify(progress_callback, name, "done")
                context = {"source": "no_stored_context"}
                self._attach_self_model_context(context, name)
                return ExpertPerspective(
                    expert_name=name,
                    domain=domain,
                    response=(
                        "No stored belief context is available for this expert, and live metered "
                        "expert fallback is disabled for this consult mode."
                    ),
                    confidence=0.0,
                    cost=0.0,
                    context=context,
                )

            child_identity = None
            from deepr.experts.chat import start_chat_session

            if agent_identity is not None:
                from deepr.agents.contract import AgentRole

                child_identity = agent_identity.child(
                    role=AgentRole.WORKER,
                    name=f"council-{name}",
                )

            session = await start_chat_session(
                name,
                budget=per_expert_budget,
                agentic=True,
                quiet=True,
                agent_identity=child_identity,
            )
            response = await session.send_message(f"As a domain expert, please provide your perspective on: {query}")
            self._notify(progress_callback, name, "done")
            return ExpertPerspective(
                expert_name=name,
                domain=domain,
                response=response,
                cost=session.cost_accumulated,
                context=self._live_context(name),
            )
        except Exception as e:
            logger.warning("Council: expert %s failed: %s", name, e)
            self._notify(progress_callback, name, "failed")
            return ExpertPerspective(
                expert_name=name,
                domain=domain,
                response=f"Unable to respond: {e}",
                confidence=0.0,
                cost=0.0,
                context={"source": "failed", "error_type": type(e).__name__},
            )

    def _live_context(self, name: str) -> dict[str, Any]:
        context = {"source": "live_session"}
        self._attach_self_model_context(context, name)
        return context

    async def consult(
        self,
        query: str,
        experts: list[dict] | None = None,
        budget: float = 5.0,
        progress_callback: Any = None,
        agent_identity: Any = None,
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
        from deepr.experts.cost_safety import get_cost_safety_manager

        if not experts:
            experts = await self.select_experts(query)

        if not experts:
            return {
                "query": query,
                "perspectives": [],
                "synthesis": "No experts available for this query.",
                "agreements": [],
                "disagreements": [],
                "synthesis_status": "skipped_no_valid_perspectives",
                "synthesis_error_type": "",
                "requested_budget_usd": budget,
                "total_cost": 0.0,
            }

        import uuid as _uuid

        cost_safety = get_cost_safety_manager()
        owned_synthesis = self._synthesis_provider == "local" or self._synthesis_provider.startswith("plan_quota:")
        requires_cost_reservation = self._allow_live_fallback or not owned_synthesis
        council_session_id = f"council_{_uuid.uuid4().hex[:16]}"
        reservation_id = ""
        if requires_cost_reservation:
            # Reserve the full council budget against the global cost-safety
            # manager upfront. Without this, N=5 parallel experts each pass
            # their own session-budget check while the daily cap is observed
            # as if no other call is pending - classic fan-out over-commit.
            # Use a uuid so two near-simultaneous consult() calls on the same
            # ExpertCouncil instance can't collide on the cost-safety session map.
            allowed, deny_reason, _confirm, reservation_id = cost_safety.check_and_reserve(
                session_id=council_session_id,
                operation_type="council_consult",
                estimated_cost=min(budget, cost_safety.ABSOLUTE_MAX_PER_OPERATION),
                require_confirmation=False,
                reserve=True,
            )
            if not allowed:
                logger.warning("Council blocked by cost-safety: %s", deny_reason)
                return {
                    "query": query,
                    "perspectives": [],
                    "synthesis": f"Council blocked: {deny_reason}",
                    "agreements": [],
                    "disagreements": [],
                    "requested_budget_usd": budget,
                    "total_cost": 0.0,
                }

        num = len(experts)
        per_expert_budget = (budget * (1 - SYNTHESIS_BUDGET_FRACTION)) / max(num, 1)

        # Query all experts in parallel with bounded concurrency. The
        # reservation must always be refunded - even if dispatch or
        # synthesis raises - so we wrap the rest of the body in
        # try/finally. The previous code refunded only on the happy path,
        # leaking the daily-cap slot whenever ``_synthesise`` raised.
        from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

        dispatcher = AsyncTaskDispatcher(max_concurrent=MAX_COUNCIL_CONCURRENCY)
        dispatch_tasks = [
            {
                "id": exp["name"],
                "coro": self._query_expert(query, exp, per_expert_budget, progress_callback, agent_identity),
            }
            for exp in experts
        ]
        try:
            dispatch_result = await dispatcher.dispatch(dispatch_tasks)
            perspectives = [
                dispatch_result.tasks[exp["name"]].result
                for exp in experts
                if dispatch_result.tasks[exp["name"]].result is not None
            ]
            total_cost = sum(p.cost for p in perspectives)

            # Synthesise
            synthesis = await self._synthesise(query, perspectives, budget * SYNTHESIS_BUDGET_FRACTION)
            synthesis_cost = float(synthesis.get("cost", 0.0) or 0.0)
            if synthesis_cost > 0:
                cost_safety.record_cost(
                    session_id=council_session_id,
                    operation_type="council_synthesis",
                    actual_cost=synthesis_cost,
                    provider=self._synthesis_provider,
                    model=self._synthesis_model,
                    tokens_input=int(synthesis.get("tokens_input", 0) or 0),
                    tokens_output=int(synthesis.get("tokens_output", 0) or 0),
                    request_id=council_session_id,
                    idempotency_key=f"{council_session_id}:synthesis",
                    source="expert_council.synthesis",
                    metadata={
                        "expert_count": len(experts),
                        "perspective_count": len(perspectives),
                        "estimated": bool(synthesis.get("cost_estimated", False)),
                    },
                    reservation_id=reservation_id,
                )
                reservation_id = ""
            total_cost += synthesis_cost
        finally:
            # Always release the council-level reservation. Child sessions
            # already wrote their own ledger events via record_cost, so
            # we only release the in-flight pool slot here without
            # double-billing.
            if reservation_id:
                try:
                    cost_safety.refund_reservation(reservation_id)
                except Exception:  # never let cost-bookkeeping mask the result
                    logger.debug("Council reservation %s could not be refunded", reservation_id, exc_info=True)

        return {
            "query": query,
            "perspectives": [
                {
                    "expert_name": p.expert_name,
                    "domain": p.domain,
                    "response": p.response,
                    "confidence": p.confidence,
                    "cost": p.cost,
                    "context": dict(p.context),
                }
                for p in perspectives
            ],
            "synthesis": synthesis.get("text", ""),
            "agreements": synthesis.get("agreements", []),
            "disagreements": synthesis.get("disagreements", []),
            "synthesis_status": synthesis.get("synthesis_status", "completed"),
            "synthesis_error_type": synthesis.get("synthesis_error_type", ""),
            "requested_budget_usd": budget,
            "total_cost": round(total_cost, 4),
        }

    async def _synthesise(
        self,
        query: str,
        perspectives: list[ExpertPerspective],
        budget: float,
    ) -> dict:
        """Synthesise multiple expert perspectives into a unified view."""
        if not perspectives or all(p.confidence == 0 for p in perspectives):
            return {
                "text": "No valid perspectives to synthesise.",
                "agreements": [],
                "disagreements": [],
                "cost": 0.0,
                "synthesis_status": "skipped_no_valid_perspectives",
            }

        parts = []
        for p in perspectives:
            if p.confidence > 0:
                parts.append(f"**{p.expert_name}** ({p.domain}):\n{p.response[:1000]}")

        prompt = (
            f"Query: {query}\n\n"
            "Expert perspectives:\n\n" + "---\n".join(parts) + "\n\n"
            "Provide:\n"
            "1. SYNTHESIS: A unified answer combining the best insights.\n"
            "2. MATH AND STATISTICS: Model the relevant quantities, base rates, uncertainty, "
            "expected value, confidence intervals, sensitivity, or experiment design when applicable. "
            "State when the available evidence is not numeric enough to support the math.\n"
            "3. ASSUMPTIONS AND RISKS: Name assumptions, weak evidence, missing data, and what "
            "would change the council's view.\n"
            "4. EXECUTION PLAN: Give concrete next actions for the host agent, including what to "
            "measure, what to verify, and what not to do yet.\n"
            "5. AGREEMENTS: Points where experts agree (bullet list).\n"
            "6. DISAGREEMENTS: Points where they diverge (bullet list).\n"
        )

        try:
            client = self._synthesis_client or AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            result = await client.chat.completions.create(
                model=self._synthesis_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Synthesise expert perspectives for a host agent. Preserve dissent, avoid pretending "
                            "uncertain claims are facts, and make the result actionable."
                        ),
                    },
                    {"role": "user", "content": prompt[:6000]},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            text = result.choices[0].message.content or ""
            if self._synthesis_provider == "local" or self._synthesis_provider.startswith("plan_quota:"):
                cost = 0.0
                tokens_input = 0
                tokens_output = 0
                cost_estimated = False
            else:
                cost, tokens_input, tokens_output, cost_estimated = _chat_completion_cost(
                    getattr(result, "usage", None), self._synthesis_model
                )

            agreements, disagreements = parse_synthesis_sections(text)

            return {
                "text": text,
                "agreements": agreements,
                "disagreements": disagreements,
                "cost": cost,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "cost_estimated": cost_estimated,
                "synthesis_status": "completed",
            }
        except Exception as e:
            logger.warning("Council synthesis failed: %s", e)
            return {
                "text": "Synthesis unavailable.",
                "agreements": [],
                "disagreements": [],
                "cost": 0.0,
                "synthesis_status": "failed",
                "synthesis_error_type": type(e).__name__,
            }
