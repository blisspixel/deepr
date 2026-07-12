"""Expert Council - multi-expert consultation for cross-domain queries.

Selects relevant experts, queries them in parallel, and synthesises
their perspectives into a unified response with agreements/disagreements.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from deepr.experts.constants import MAX_COUNCIL_CONCURRENCY, SYNTHESIS_BUDGET_FRACTION, UTILITY_MODEL
from deepr.experts.consult_lifecycle import ConsultLifecycleError
from deepr.experts.council_synthesis_costs import (
    CouncilSynthesisCostError,
    SynthesisCostBound,
    attach_synthesis_settlement,
    failed_synthesis,
    metered_synthesis_cost_bound,
    settle_cancelled_synthesis,
    settle_synthesis_cost,
    synthesis_accounting_envelope,
)
from deepr.experts.council_synthesis_runtime import SynthesisProviderResponse, dispatch_synthesis
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
_SYNTHESIS_OUTPUT_TOKENS = 800
_LOCAL_SYNTHESIS_OUTPUT_TOKENS = 1200
_TRUNCATED_STOP_REASONS = frozenset({"length", "max_tokens"})
_EMPTY_SYNTHESIS_TEXT = "Synthesis unavailable: the model returned no visible answer."
_EMPTY_TRUNCATED_SYNTHESIS_TEXT = (
    "Synthesis incomplete: the model reached its output limit before emitting a visible answer."
)


def _owned_synthesis_provider(provider: str) -> bool:
    return provider == "local" or provider.startswith("plan_quota:")


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


def _shape_synthesis_response(response: SynthesisProviderResponse) -> dict[str, Any]:
    text = response.text
    truncated = response.stop_reason in _TRUNCATED_STOP_REASONS
    empty_visible_answer = not text.strip()
    if empty_visible_answer:
        text = _EMPTY_TRUNCATED_SYNTHESIS_TEXT if truncated else _EMPTY_SYNTHESIS_TEXT
    agreements, disagreements = parse_synthesis_sections(text)
    bound_exceeded = bool(response.usage.get("cost_bound_exceeded", False))
    if bound_exceeded:
        synthesis_status = "failed"
        error_type = "SynthesisCostBoundViolation"
    elif truncated:
        synthesis_status = "truncated"
        error_type = "OutputLimit"
    elif empty_visible_answer:
        synthesis_status = "failed"
        error_type = "EmptySynthesis"
    else:
        synthesis_status = "completed"
        error_type = ""
    return {
        "text": text,
        "agreements": agreements,
        "disagreements": disagreements,
        **response.usage,
        "provider_request_id": response.provider_request_id,
        "stop_reason": response.stop_reason,
        "synthesis_status": synthesis_status,
        "synthesis_error_type": error_type,
    }


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
    """Consult multiple domain experts and synthesise their views.

    Injected synthesis clients are caller-owned. Deepr disables retries only on
    the metered SDK clients it constructs itself.
    """

    def __init__(
        self,
        *,
        synthesis_client: Any | None = None,
        synthesis_model: str = UTILITY_MODEL,
        synthesis_provider: str = "openai",
        allow_live_fallback: bool = False,
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

        store = BeliefStore(name, read_only=True, read_path=belief_file)
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
    ) -> list[dict[str, Any]]:
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
    async def _notify(progress_callback: Any, name: str, status: str) -> None:
        if not progress_callback:
            return
        try:
            if inspect.iscoroutinefunction(progress_callback):
                result = progress_callback(name, status)
            else:
                result = await asyncio.to_thread(progress_callback, name, status)
            if inspect.isawaitable(result):
                await result
        except ConsultLifecycleError:
            raise
        except Exception:
            logger.debug("Council progress callback failed for %s", name, exc_info=True)

    async def _query_expert(
        self,
        query: str,
        exp: dict[str, Any],
        per_expert_budget: float,
        progress_callback: Any,
        agent_identity: Any,
    ) -> ExpertPerspective:
        del per_expert_budget
        from deepr.agents.contract import AgentRole

        name = exp["name"]
        domain = exp.get("domain", "")
        child_identity = (
            agent_identity.child(role=AgentRole.WORKER, name=f"council-{name}") if agent_identity is not None else None
        )
        await self._notify(progress_callback, name, "querying")
        try:
            stored = self._load_stored_perspective(query, name, domain)
            if stored is not None:
                if child_identity is not None:
                    stored.context["agent_identity"] = child_identity.to_dict()
                await self._notify(progress_callback, name, "done")
                return stored
            await self._notify(progress_callback, name, "done")
            fallback_requested = self._allow_live_fallback
            context = {
                "source": "live_metered_fallback_gated" if fallback_requested else "no_stored_context",
                "live_metered_fallback": False,
            }
            if child_identity is not None:
                context["agent_identity"] = child_identity.to_dict()
            self._attach_self_model_context(context, name)
            return ExpertPerspective(
                expert_name=name,
                domain=domain,
                response=(
                    "No stored belief context is available. Live metered perspective fallback is gated "
                    "until every chat turn has deterministic reserve and required settlement."
                    if fallback_requested
                    else "No stored belief context is available, and live metered perspective fallback is disabled."
                ),
                confidence=0.0,
                cost=0.0,
                context=context,
            )
        except ConsultLifecycleError:
            raise
        except Exception as e:
            logger.warning("Council: expert %s failed: %s", name, e)
            await self._notify(progress_callback, name, "failed")
            return ExpertPerspective(
                expert_name=name,
                domain=domain,
                response=f"Unable to respond: {e}",
                confidence=0.0,
                cost=0.0,
                context={"source": "failed", "error_type": type(e).__name__},
            )

    async def consult(
        self,
        query: str,
        experts: list[dict[str, Any]] | None = None,
        budget: float = 5.0,
        progress_callback: Any = None,
        agent_identity: Any = None,
    ) -> dict[str, Any]:
        """Run one stored-context council and bounded synthesis."""
        from deepr.experts.consult import validate_consult_roster
        from deepr.experts.cost_safety import get_cost_safety_manager
        from deepr.experts.paths import expert_slug

        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
            raise ValueError("budget must be finite and non-negative")
        selected = experts or await self.select_experts(query)
        if not selected:
            return self._empty_consult_result(query, budget)
        validate_consult_roster(selected)
        task_ids = [expert_slug(exp["name"]) for exp in selected]
        per_expert_budget = (budget * (1 - SYNTHESIS_BUDGET_FRACTION)) / max(len(selected), 1)

        import uuid as _uuid

        cost_safety = await asyncio.to_thread(get_cost_safety_manager)
        council_session_id = f"council_{_uuid.uuid4().hex[:16]}"
        reservation_id = ""
        if not _owned_synthesis_provider(self._synthesis_provider):
            allowed, deny_reason, _confirm, reservation_id = await self._reserve_council_budget(
                cost_safety,
                council_session_id,
                budget,
            )
            if not allowed:
                return self._blocked_consult_result(query, budget, deny_reason)
        operation_error: BaseException | None = None
        try:
            perspectives = await self._dispatch_perspectives(
                query,
                selected,
                task_ids,
                per_expert_budget,
                progress_callback,
                agent_identity,
            )
            synthesis, synthesis_cost = await self._run_synthesis_and_settle(
                query,
                perspectives,
                budget,
                progress_callback,
                cost_safety,
                council_session_id,
                reservation_id,
                len(selected),
            )
        except BaseException as error:
            operation_error = error
            raise
        finally:
            if reservation_id:
                try:
                    await self._refund_to_completion(cost_safety, reservation_id)
                except BaseException as cleanup_error:
                    if operation_error is None:
                        raise
                    operation_error.__dict__["council_reservation_cleanup_error"] = cleanup_error
                    operation_error.add_note("Council reservation cleanup failed after the operation error.")
        return self._consult_result(query, budget, perspectives, synthesis, synthesis_cost)

    async def _reserve_council_budget(
        self,
        cost_safety: Any,
        council_session_id: str,
        budget: float,
    ) -> tuple[bool, str, bool, str]:
        task = asyncio.create_task(
            asyncio.to_thread(
                cost_safety.check_and_reserve,
                session_id=council_session_id,
                operation_type="council_consult",
                estimated_cost=budget,
                require_confirmation=False,
                reserve=True,
                durable_reservation=True,
                reservation_job_id=council_session_id,
            ),
            name=f"council-reserve-{council_session_id}",
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError as cancellation_error:
            result = await self._finish_thread_task(task, cancellation_error)
            reservation_id = result[3]
            if reservation_id:
                await self._refund_after_cancellation(cost_safety, reservation_id, cancellation_error)
            cancellation_error.__dict__["council_predispatch_reservation_cleaned"] = True
            raise

    async def _dispatch_perspectives(
        self,
        query: str,
        experts: list[dict[str, Any]],
        task_ids: list[str],
        per_expert_budget: float,
        progress_callback: Any,
        agent_identity: Any,
    ) -> list[ExpertPerspective]:
        from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

        tasks = [
            {
                "id": task_id,
                "coro": self._query_expert(
                    query,
                    expert,
                    per_expert_budget,
                    progress_callback,
                    agent_identity,
                ),
            }
            for task_id, expert in zip(task_ids, experts, strict=True)
        ]
        result = await AsyncTaskDispatcher(max_concurrent=MAX_COUNCIL_CONCURRENCY).dispatch(
            tasks,
            fatal_exception_types=(ConsultLifecycleError,),
        )
        return [result.tasks[task_id].result for task_id in task_ids if result.tasks[task_id].result is not None]

    async def _run_synthesis_and_settle(
        self,
        query: str,
        perspectives: list[ExpertPerspective],
        budget: float,
        progress_callback: Any,
        cost_safety: Any,
        council_session_id: str,
        reservation_id: str,
        expert_count: int,
    ) -> tuple[dict[str, Any], float]:
        await self._notify(progress_callback, "__synthesis__", "querying")
        pre_dispatch = None
        if reservation_id:

            async def pre_dispatch() -> None:
                await self._mark_provider_dispatch(cost_safety, reservation_id)

        try:
            synthesis = await self._synthesise(
                query,
                perspectives,
                budget * SYNTHESIS_BUDGET_FRACTION,
                pre_dispatch_callback=pre_dispatch,
            )
        except asyncio.CancelledError as cancellation_error:
            await settle_cancelled_synthesis(
                cancellation_error,
                cost_safety,
                council_session_id=council_session_id,
                reservation_id=reservation_id,
                provider=self._synthesis_provider,
                model=self._synthesis_model,
                expert_count=expert_count,
                perspective_count=len(perspectives),
            )
            raise
        settlement_reservation = reservation_id
        if reservation_id and self._synthesis_not_dispatched(synthesis):
            await asyncio.to_thread(
                cost_safety.refund_reservation,
                reservation_id,
                provider_work_did_not_run=True,
            )
            settlement_reservation = ""
        await settle_synthesis_cost(
            cost_safety,
            council_session_id=council_session_id,
            reservation_id=settlement_reservation,
            synthesis=synthesis,
            provider=self._synthesis_provider,
            model=self._synthesis_model,
            expert_count=expert_count,
            perspective_count=len(perspectives),
        )
        synthesis_cost = float(synthesis.get("cost", 0.0) or 0.0)
        await self._notify_synthesis_completion(
            progress_callback,
            synthesis,
            synthesis_cost,
            council_session_id,
        )
        return synthesis, synthesis_cost

    async def _notify_synthesis_completion(
        self,
        progress_callback: Any,
        synthesis: dict[str, Any],
        synthesis_cost: float,
        council_session_id: str,
    ) -> None:
        status = str(synthesis.get("synthesis_status", "completed"))
        progress_status = "done" if status in {"completed", "skipped_no_valid_perspectives"} else "failed"
        try:
            await self._notify(progress_callback, "__synthesis__", progress_status)
        except (asyncio.CancelledError, ConsultLifecycleError) as error:
            if synthesis_cost > 0:
                attach_synthesis_settlement(error, synthesis, council_session_id=council_session_id, settled=True)
            raise

    @staticmethod
    def _synthesis_not_dispatched(synthesis: dict[str, Any]) -> bool:
        return (
            synthesis.get("dispatch_status") == "not_dispatched"
            or synthesis.get("synthesis_status") == "skipped_no_valid_perspectives"
        )

    async def _mark_provider_dispatch(self, cost_safety: Any, reservation_id: str) -> None:
        task = asyncio.create_task(
            asyncio.to_thread(cost_safety.mark_provider_work_may_have_run, reservation_id),
            name=f"council-dispatch-mark-{reservation_id}",
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as cancellation_error:
            await self._finish_thread_task(task, cancellation_error)
            await self._refund_after_cancellation(cost_safety, reservation_id, cancellation_error)
            cancellation_error.__dict__["council_predispatch_reservation_cleaned"] = True
            raise

    async def _refund_to_completion(self, cost_safety: Any, reservation_id: str) -> None:
        task = asyncio.create_task(
            asyncio.to_thread(cost_safety.refund_reservation, reservation_id),
            name=f"council-refund-{reservation_id}",
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as cancellation_error:
            await self._finish_thread_task(task, cancellation_error)
            cancellation_error.__dict__["council_reservation_cleanup_completed"] = True
            raise

    async def _refund_after_cancellation(
        self,
        cost_safety: Any,
        reservation_id: str,
        cancellation_error: BaseException,
    ) -> None:
        task = asyncio.create_task(
            asyncio.to_thread(
                cost_safety.refund_reservation,
                reservation_id,
                provider_work_did_not_run=True,
            ),
            name=f"council-predispatch-refund-{reservation_id}",
        )
        try:
            await self._finish_thread_task(task, cancellation_error)
        except Exception as cleanup_error:
            cancellation_error.__dict__["council_reservation_cleanup_error"] = cleanup_error
            cancellation_error.add_note("Council predispatch reservation cleanup failed.")

    @staticmethod
    async def _finish_thread_task(task: asyncio.Task[Any], cancellation_error: BaseException) -> Any:
        repeated_cancellations = 0
        while True:
            try:
                result = await asyncio.shield(task)
                if repeated_cancellations:
                    cancellation_error.__dict__["council_repeated_cancellations"] = repeated_cancellations
                return result
            except asyncio.CancelledError:
                repeated_cancellations += 1

    @staticmethod
    def _empty_consult_result(query: str, budget: float) -> dict[str, Any]:
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

    @staticmethod
    def _blocked_consult_result(query: str, budget: float, reason: str) -> dict[str, Any]:
        logger.warning("Council blocked by cost-safety: %s", reason)
        return {
            "query": query,
            "perspectives": [],
            "synthesis": f"Council blocked: {reason}",
            "agreements": [],
            "disagreements": [],
            "synthesis_status": "failed",
            "synthesis_error_type": "CostSafetyDenied",
            "requested_budget_usd": budget,
            "total_cost": 0.0,
        }

    @staticmethod
    def _consult_result(
        query: str,
        budget: float,
        perspectives: list[ExpertPerspective],
        synthesis: dict[str, Any],
        synthesis_cost: float,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "perspectives": [
                {
                    "expert_name": perspective.expert_name,
                    "domain": perspective.domain,
                    "response": perspective.response,
                    "confidence": perspective.confidence,
                    "cost": perspective.cost,
                    "context": dict(perspective.context),
                }
                for perspective in perspectives
            ],
            "synthesis": synthesis.get("text", ""),
            "agreements": synthesis.get("agreements", []),
            "disagreements": synthesis.get("disagreements", []),
            "synthesis_status": synthesis.get("synthesis_status", "completed"),
            "synthesis_error_type": synthesis.get("synthesis_error_type", ""),
            "synthesis_stop_reason": synthesis.get("stop_reason", ""),
            "requested_budget_usd": budget,
            "total_cost": sum(perspective.cost for perspective in perspectives) + synthesis_cost,
        }

    async def _synthesise(
        self,
        query: str,
        perspectives: list[ExpertPerspective],
        budget: float,
        *,
        pre_dispatch_callback: Any = None,
    ) -> dict[str, Any]:
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
        cost_bound: SynthesisCostBound | None = None
        if not _owned_synthesis_provider(self._synthesis_provider):
            try:
                cost_bound = metered_synthesis_cost_bound(
                    provider=self._synthesis_provider,
                    model=self._synthesis_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    output_token_ceiling=output_tokens,
                    budget=budget,
                )
            except CouncilSynthesisCostError as error:
                logger.warning("Council synthesis rejected before dispatch: %s", error)
                return failed_synthesis(error, cost_bound=None, dispatched=False)

        dispatched = False
        try:

            async def mark_dispatch_started() -> None:
                nonlocal dispatched
                if pre_dispatch_callback is not None:
                    await pre_dispatch_callback()
                dispatched = True

            response = await dispatch_synthesis(
                provider=self._synthesis_provider,
                model=self._synthesis_model,
                client=self._synthesis_client,
                openai_client_factory=AsyncOpenAI,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_tokens=output_tokens,
                cost_bound=cost_bound,
                pre_dispatch_callback=mark_dispatch_started,
            )
            return _shape_synthesis_response(response)
        except asyncio.CancelledError as error:
            if dispatched and cost_bound is not None:
                settlement = failed_synthesis(error, cost_bound=cost_bound, dispatched=True)
                settlement["cost_estimate_reason"] = "cancelled_after_dispatch"
                error.__dict__["council_synthesis_settlement"] = synthesis_accounting_envelope(settlement)
                error.add_note(
                    f"Metered council synthesis may have dispatched; conservative settlement "
                    f"ceiling is ${float(settlement['cost']):.6f}."
                )
            raise
        except Exception as error:
            logger.warning("Council synthesis failed: %s", error)
            return failed_synthesis(error, cost_bound=cost_bound, dispatched=dispatched)
