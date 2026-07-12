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
from deepr.experts.expert_routing import route_terms, score_experts_for_query, select_top_experts
from deepr.experts.maker_checker import assurance_short_label, is_verified_assurance
from deepr.experts.perspective_state import build_perspective_state_packet, render_original_ideas_for_council

logger = logging.getLogger(__name__)

_MAX_STORED_BELIEFS = 8
_MAX_FALLBACK_BELIEFS = 5
_MAX_SOURCE_REFS = 3
_MAX_REF_CHARS = 140

# The synthesis model receives stored-belief lines that may carry inline trust
# annotations (see build_stored_perspective): the grounding-assurance label and
# the pre-existing contested marker. This legend defines those terms so the model
# can actually read them. It is disclosure, not a rule: it frames corroboration
# and dissent as signals to weigh, never an instruction that a verified belief
# must win. The verified-label wording here must stay in step with
# assurance_short_label - test_synthesis_prompt_defines_verified_labels pins it,
# so a renamed or newly added label can never ship without a definition here
# (the test guards the label's presence; the surrounding prose is on us).
_SYNTHESIS_SYSTEM_PROMPT = (
    "Synthesise expert perspectives for a host agent. Preserve dissent, avoid pretending "
    "uncertain claims are facts, and make the result actionable. In a stored-belief line, "
    "'cross-vendor verified' means two independent model vendors corroborated that claim, "
    "'same-vendor verified' means one vendor re-checked it with fresh context, an unlabeled "
    "belief was not independently corroborated, and 'contested with N belief(s)' means it "
    "conflicts with other stored beliefs. Weigh corroboration and dissent alongside the stated "
    "confidence; none of these is a guarantee of truth."
)
_SYNTHESIS_FALLBACK_COST = 0.001
_SYNTHESIS_OUTPUT_TOKENS = 800
_LOCAL_SYNTHESIS_OUTPUT_TOKENS = 1200
_TRUNCATED_STOP_REASONS = frozenset({"length", "max_tokens"})
_EMPTY_SYNTHESIS_TEXT = "Synthesis unavailable: the model returned no visible answer."
_EMPTY_TRUNCATED_SYNTHESIS_TEXT = (
    "Synthesis incomplete: the model reached its output limit before emitting a visible answer."
)


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


def _anthropic_cache_rates(model_name: str, input_rate: float) -> dict[str, float]:
    from deepr.providers.anthropic_provider import ANTHROPIC_CACHE_PRICING

    for model, rates in ANTHROPIC_CACHE_PRICING.items():
        if model_name.startswith(model):
            return rates
    return {
        "cache_write": round(input_rate * 1.25, 6),
        "cache_read": round(input_rate * 0.10, 6),
    }


def _anthropic_completion_cost(usage: Any, model_name: str) -> dict[str, Any]:
    """Compute Anthropic Messages API cost across regular and cache buckets."""
    empty = {
        "cost": _SYNTHESIS_FALLBACK_COST,
        "tokens_input": 0,
        "tokens_output": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_estimated": True,
    }
    if usage is None:
        return dict(empty)

    from deepr.providers.base import coerce_usage_int
    from deepr.providers.registry import get_token_pricing

    input_tokens = coerce_usage_int(getattr(usage, "input_tokens", 0))
    output_tokens = coerce_usage_int(getattr(usage, "output_tokens", 0))
    cache_creation_tokens = coerce_usage_int(getattr(usage, "cache_creation_input_tokens", 0))
    cache_read_tokens = coerce_usage_int(getattr(usage, "cache_read_input_tokens", 0))
    if input_tokens <= 0 and output_tokens <= 0 and cache_creation_tokens <= 0 and cache_read_tokens <= 0:
        return dict(empty)

    prices = get_token_pricing(model_name, input_tokens=input_tokens)
    cache_rates = _anthropic_cache_rates(model_name, prices["input"])
    cost = (
        (input_tokens / 1_000_000) * prices["input"]
        + (output_tokens / 1_000_000) * prices["output"]
        + (cache_creation_tokens / 1_000_000) * cache_rates["cache_write"]
        + (cache_read_tokens / 1_000_000) * cache_rates["cache_read"]
    )
    return {
        "cost": round(cost, 6),
        "tokens_input": input_tokens + cache_creation_tokens + cache_read_tokens,
        "tokens_output": output_tokens,
        "cache_creation_input_tokens": cache_creation_tokens,
        "cache_read_input_tokens": cache_read_tokens,
        "cost_estimated": False,
    }


def _anthropic_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(str(block.get("text", "") or ""))
            continue
        if getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "text", "") or ""))
    return "\n".join(part for part in parts if part).strip()


def _owned_synthesis_provider(provider: str) -> bool:
    return provider == "local" or provider.startswith("plan_quota:")


def _synthesis_ledger_metadata(
    synthesis: dict[str, Any],
    *,
    expert_count: int,
    perspective_count: int,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "expert_count": expert_count,
        "perspective_count": perspective_count,
        "estimated": bool(synthesis.get("cost_estimated", False)),
    }
    for field_name in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        field_value = int(synthesis.get(field_name, 0) or 0)
        if field_value > 0:
            metadata[field_name] = field_value
    for field_name in ("provider_request_id", "stop_reason"):
        field_value = str(synthesis.get(field_name, "") or "")
        if field_value:
            metadata[field_name] = field_value
    return metadata


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


def _render_synthesis_perspectives(perspectives: list[ExpertPerspective]) -> list[str]:
    return [
        f"**{perspective.expert_name}** ({perspective.domain}):\n{perspective.response[:1000]}"
        for perspective in perspectives
        if perspective.confidence > 0
    ]


@dataclass(frozen=True)
class StoredBeliefSelection:
    """Stored beliefs selected for a consult packet."""

    beliefs: list[Any]
    selection: str
    selection_note: str
    matched_terms: set[str]


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
        """Tokenize text for retrieval routing only (delegates to expert_routing)."""
        return route_terms(text)

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

    def _select_stored_beliefs(self, query: str, beliefs: list[Any]) -> StoredBeliefSelection:
        """Select stored beliefs for routing context, not semantic judgment."""
        if not beliefs:
            return StoredBeliefSelection(
                beliefs=[],
                selection="original_ideas_only",
                selection_note="No stored beliefs available; using active original ideas as labeled perspective state.",
                matched_terms=set(),
            )

        query_terms = self._terms(query)

        def _score(belief: Any) -> tuple[int, float, str]:
            belief_terms = self._terms(f"{belief.domain} {belief.claim}")
            overlap = len(query_terms & belief_terms) if query_terms else 0
            return (overlap, belief.get_current_confidence(), belief.claim)

        scored = sorted(
            ((_score(belief), belief) for belief in beliefs),
            key=lambda item: (-item[0][0], -item[0][1], item[0][2]),
        )
        direct = any(score[0] > 0 for score, _belief in scored)
        if not direct:
            return StoredBeliefSelection(
                beliefs=[belief for _score_tuple, belief in scored[:_MAX_FALLBACK_BELIEFS]],
                selection="confidence_fallback",
                selection_note="No direct stored-belief overlap found; using highest-confidence beliefs as fallback context.",
                matched_terms=set(),
            )

        selected = [belief for score, belief in scored if score[0] > 0][:_MAX_STORED_BELIEFS]
        matched_terms: set[str] = set()
        for belief in selected:
            matched_terms.update(query_terms & self._terms(f"{belief.domain} {belief.claim}"))
        return StoredBeliefSelection(
            beliefs=selected,
            selection="query_overlap",
            selection_note="Selected stored beliefs by query-token overlap, then confidence.",
            matched_terms=matched_terms,
        )

    def build_stored_perspective(
        self,
        query: str,
        name: str,
        domain: str,
        beliefs: Iterable[Any],
        *,
        perspective_state: dict[str, Any] | None = None,
    ) -> ExpertPerspective | None:
        """Build a deterministic perspective from an expert's belief store.

        This is context selection, not adjudication: lexical overlap only decides
        which stored beliefs enter the council packet. The model synthesis step
        still receives confidence, source, contradiction, and grounding-assurance
        signals rather than a pre-baked verdict. The grounding stamp is disclosed
        so the synthesis model can weigh how corroborated each belief is; per
        AGENTIC_BALANCE it never gates or reorders selection here, and an
        unverified belief is neither dropped nor penalized for lacking the stamp.
        """
        perspective_state = perspective_state or build_perspective_state_packet(name, limit=3)
        original_ideas = list(perspective_state["original_ideas"])
        belief_list = list(beliefs)
        if not belief_list and not original_ideas:
            return None

        selected_context = self._select_stored_beliefs(query, belief_list)
        selected = selected_context.beliefs

        if not selected and not original_ideas:
            return None

        header = "Stored belief perspective" if selected else "Stored perspective state"
        lines = [
            f"{header} for {name}.",
            selected_context.selection_note,
            f"{len(selected)} of {len(belief_list)} active beliefs included.",
            "",
        ]
        for belief in selected:
            confidence = belief.get_current_confidence()
            contested = (
                f", contested with {len(belief.contradictions_with)} belief(s)" if belief.contradictions_with else ""
            )
            verified_label = assurance_short_label(getattr(belief, "grounding_assurance", ""))
            verified = f", {verified_label}" if verified_label else ""
            domain_label = belief.domain or domain or "general"
            lines.append(f"- ({confidence:.2f}, {domain_label}{verified}{contested}) {belief.claim}")
            refs = self._compact_refs(belief.evidence_refs)
            if refs:
                lines.append(f"  Sources: {'; '.join(refs)}")

        lines.extend(render_original_ideas_for_council(original_ideas))
        if selected:
            confidence = sum(b.get_current_confidence() for b in selected) / len(selected)
        else:
            confidence = sum(float(idea["confidence"]) for idea in original_ideas) / len(original_ideas)
        source = "belief_store" if selected else "perspective_state"
        context = {
            "source": source,
            "selection": selected_context.selection,
            "selection_note": selected_context.selection_note,
            "beliefs_available": len(belief_list),
            "beliefs_included": len(selected),
            "belief_ids": [belief.id for belief in selected],
            "beliefs_verified": sum(
                1 for belief in selected if is_verified_assurance(getattr(belief, "grounding_assurance", ""))
            ),
            "matched_terms": sorted(selected_context.matched_terms)[:20],
        }
        if original_ideas:
            context.update(
                {
                    "perspective_state": perspective_state,
                    "original_ideas_available": int(perspective_state["counts"]["original_ideas"]),
                    "original_ideas_included": len(original_ideas),
                }
            )

        return ExpertPerspective(
            expert_name=name,
            domain=domain,
            response="\n".join(lines),
            confidence=round(confidence, 3),
            cost=0.0,
            context=context,
        )

    def _load_stored_perspective(self, query: str, name: str, domain: str) -> ExpertPerspective | None:
        """Load stored beliefs for an expert and build a council perspective."""
        from deepr.experts.beliefs import BeliefStore
        from deepr.experts.paths import canonical_expert_dir

        perspective_state = build_perspective_state_packet(name, limit=3)
        original_ideas = list(perspective_state["original_ideas"])
        belief_file = canonical_expert_dir(name) / "beliefs" / "beliefs.json"
        if not belief_file.exists() and not original_ideas:
            return None

        store = BeliefStore(name)
        perspective = self.build_stored_perspective(
            query,
            name,
            domain,
            store.beliefs.values(),
            perspective_state=perspective_state,
        )
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
        perspective_state = build_perspective_state_packet(name, limit=3)
        if perspective_state["counts"]["original_ideas"]:
            context["perspective_state"] = perspective_state
            context["original_ideas_available"] = int(perspective_state["counts"]["original_ideas"])

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

        # Keyword overlap here only *routes* selection; it never concludes meaning
        # (AGENTIC_BALANCE). The shared router prefers experts with any overlap and
        # falls back to the top scorers when nothing overlaps, so consult is never
        # starved. `deepr route explain` renders the same signal.
        scored = score_experts_for_query(query, ExpertStore().list_all(), exclude=set(exclude or []))
        return select_top_experts(scored, max_experts=max_experts)

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
        owned_synthesis = _owned_synthesis_provider(self._synthesis_provider)
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
                    metadata=_synthesis_ledger_metadata(
                        synthesis,
                        expert_count=len(experts),
                        perspective_count=len(perspectives),
                    ),
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
            "synthesis_stop_reason": synthesis.get("stop_reason", ""),
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

        parts = _render_synthesis_perspectives(perspectives)

        prompt = (
            f"Query: {query}\n\n"
            "Expert perspectives:\n\n" + "---\n".join(parts) + "\n\n"
            "Return these sections in order and keep the complete response under 700 words:\n"
            "1. AGREEMENTS: Points where experts agree (bullet list).\n"
            "2. DISAGREEMENTS: Points where they diverge (bullet list). Preserve meaningful dissent.\n"
            "3. SYNTHESIS: A unified answer combining the best insights without forcing consensus.\n"
            "4. ASSUMPTIONS AND RISKS: Name weak evidence, missing data, and disconfirming evidence.\n"
            "5. EXECUTION PLAN: Give concrete next actions, measures, verification, and stop rules.\n"
            "Include quantitative analysis only when the supplied evidence supports it.\n"
        )

        system_prompt = _SYNTHESIS_SYSTEM_PROMPT
        user_prompt = prompt[:6000]

        output_tokens = (
            _LOCAL_SYNTHESIS_OUTPUT_TOKENS if self._synthesis_provider == "local" else _SYNTHESIS_OUTPUT_TOKENS
        )
        try:
            if self._synthesis_provider == "anthropic":
                client = self._synthesis_client
                if client is None:
                    from deepr.experts.consult import AnthropicConsultSynthesisClient

                    client = AnthropicConsultSynthesisClient()
                result = await client.messages.create(
                    model=self._synthesis_model,
                    max_tokens=output_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                if getattr(result, "stop_reason", None) == "refusal":
                    details = getattr(result, "stop_details", None)
                    category = getattr(details, "category", None) if details else None
                    raise RuntimeError(
                        "Anthropic safety classifiers declined council synthesis"
                        f"{f' (category: {category})' if category else ''}"
                    )
                text = _anthropic_text(result)
                usage = _anthropic_completion_cost(getattr(result, "usage", None), self._synthesis_model)
                cost = float(usage["cost"])
                tokens_input = int(usage["tokens_input"])
                tokens_output = int(usage["tokens_output"])
                cache_creation_input_tokens = int(usage["cache_creation_input_tokens"])
                cache_read_input_tokens = int(usage["cache_read_input_tokens"])
                cost_estimated = bool(usage["cost_estimated"])
                provider_request_id = str(getattr(result, "id", "") or "")
                stop_reason = str(getattr(result, "stop_reason", "") or "")
            else:
                client = self._synthesis_client or AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                completion_params: dict[str, Any] = {
                    "model": self._synthesis_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": output_tokens,
                }
                if self._synthesis_provider == "local":
                    # Ollama enables thinking by default for supported models. Its
                    # OpenAI-compatible endpoint maps this supported value to a
                    # no-thinking request, preserving the bounded output allowance
                    # for the visible council answer. This must never leak into a
                    # metered or plan-quota provider request.
                    # The installed OpenAI SDK's typed enum does not yet include
                    # Ollama's documented "none" value, so use its supported
                    # extra-body escape hatch to serialize the top-level field.
                    completion_params["extra_body"] = {"reasoning_effort": "none"}
                result = await client.chat.completions.create(
                    **completion_params,
                )
                choice = result.choices[0]
                text = choice.message.content or ""
                if _owned_synthesis_provider(self._synthesis_provider):
                    cost = 0.0
                    tokens_input = 0
                    tokens_output = 0
                    cost_estimated = False
                else:
                    cost, tokens_input, tokens_output, cost_estimated = _chat_completion_cost(
                        getattr(result, "usage", None), self._synthesis_model
                    )
                cache_creation_input_tokens = 0
                cache_read_input_tokens = 0
                provider_request_id = str(getattr(result, "id", "") or "")
                stop_reason = str(getattr(choice, "finish_reason", "") or "")

            if _owned_synthesis_provider(self._synthesis_provider):
                cost = 0.0
                tokens_input = 0
                tokens_output = 0
                cost_estimated = False
            truncated = stop_reason in _TRUNCATED_STOP_REASONS
            empty_visible_answer = not text.strip()
            if empty_visible_answer:
                text = _EMPTY_TRUNCATED_SYNTHESIS_TEXT if truncated else _EMPTY_SYNTHESIS_TEXT
            agreements, disagreements = parse_synthesis_sections(text)

            return {
                "text": text,
                "agreements": agreements,
                "disagreements": disagreements,
                "cost": cost,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "provider_request_id": provider_request_id,
                "stop_reason": stop_reason,
                "cost_estimated": cost_estimated,
                "synthesis_status": "truncated" if truncated else "failed" if empty_visible_answer else "completed",
                "synthesis_error_type": "OutputLimit"
                if truncated
                else "EmptySynthesis"
                if empty_visible_answer
                else "",
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
