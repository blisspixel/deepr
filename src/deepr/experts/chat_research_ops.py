"""Metered research helpers used by ExpertChatSession."""

from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from deepr.experts.chat_backends import ExpertChatRequest
from deepr.experts.chat_capacity import require_expert_chat_dispatch
from deepr.experts.chat_metered import execute_metered_chat_provider_call, mirror_chat_session_spend
from deepr.experts.chat_turns import chat_token_cost
from deepr.experts.profile import ExpertStore
from deepr.observability.cost_ledger import CostLedger

logger = logging.getLogger(__name__)


async def run_standard_research(session: Any, query: str) -> dict[str, Any]:
    """Run Grok standard research under durable metered admission when enabled."""
    require_expert_chat_dispatch(
        session.chat_backend,
        "expert_chat_standard_research",
        metered=True,
    )
    from deepr.providers.registry import get_cost_estimate as _get_cost_estimate

    try:
        estimated_cost = float(_get_cost_estimate("xai/grok-4-3"))
    except Exception:
        estimated_cost = 0.05

    allowed, reason, _ = session.cost_safety.check_operation(
        session_id=session.session_id,
        operation_type="standard_research",
        estimated_cost=estimated_cost,
        require_confirmation=False,
    )

    if not allowed:
        return {"error": f"Research blocked: {reason}", "mode": "standard_research", "status": "blocked"}

    try:
        from xai_sdk import Client
        from xai_sdk.chat import system, user
        from xai_sdk.tools import web_search, x_search

        xai_key = os.getenv("XAI_API_KEY")
        if not xai_key:
            raise Exception("XAI_API_KEY not set")

        xai_client = Client(api_key=xai_key, timeout=session.timeout if hasattr(session, "timeout") else 120)
        chat = xai_client.chat.create(
            model="grok-4.3",
            tools=[
                web_search(),
                x_search(),
            ],
        )

        chat.append(
            system(
                "You have real-time web search. Provide accurate current information with source citations. Be concise but thorough."
            )
        )
        chat.append(user(query))

        async def _sample_for_admission() -> SimpleNamespace:
            response = await asyncio.to_thread(chat.sample)
            return SimpleNamespace(
                content=getattr(response, "content", ""),
                citations=getattr(response, "citations", []),
                usage=None,
            )

        sample = await execute_metered_chat_provider_call(
            provider="xai",
            model="grok-4.3",
            source="expert_chat.standard_research",
            max_cost_per_job=estimated_cost,
            call=_sample_for_admission,
        )

        answer = str(sample.content or "")
        citations = sample.citations
        citations_list = list(citations) if citations else []

        if citations_list:
            answer += "\n\nSources:\n" + "\n".join(f"- {url}" for url in citations_list[:10])

        cost = estimated_cost
        # Durable admission already wrote the canonical ledger under the
        # research_* job id. Mirror into the chat session only.
        mirror_chat_session_spend(
            session,
            operation_type="standard_research",
            actual_cost=cost,
            details=f"Query: {query[:50]}...",
        )

        await session._add_research_to_knowledge_base(query, answer, "standard_research")

        return {
            "answer": answer,
            "mode": "standard_research_grok_agentic",
            "cost": cost,
            "citations": citations_list,
            "budget_remaining": session.cost_session.get_remaining_budget(),
        }

    except Exception as e:
        session.cost_safety.record_failure(session.session_id, "standard_research", str(e))
        return await _standard_research_gpt_fallback(session, query, primary_error=e)


async def _standard_research_gpt_fallback(
    session: Any,
    query: str,
    *,
    primary_error: BaseException,
) -> dict[str, Any]:
    """GPT fallback after Grok failure; mirror session spend only after durable complete."""
    try:
        fallback_estimate = 0.05
        allowed, reason, _ = session.cost_safety.check_operation(
            session_id=session.session_id,
            operation_type="standard_research_fallback",
            estimated_cost=fallback_estimate,
            require_confirmation=False,
        )
        if not allowed:
            return {
                "error": f"Grok search failed: {primary_error!s}. GPT-5.5 fallback blocked: {reason}",
                "mode": "standard_research_fallback",
                "status": "blocked",
            }
        model_name = session._provider_model_or("gpt-5.5")
        result = await session.chat_backend.complete(
            ExpertChatRequest(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer based on your knowledge. Be honest if information might be outdated."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                reasoning_effort=session._provider_reasoning_effort_or_none("low"),
            )
        )

        answer = f"{result.text}\n\n[Note: Grok web search unavailable, using GPT-5.5 knowledge instead]"

        # Backend complete already settled the canonical ledger under durable
        # admission. Mirror into the chat session only - never record_cost again.
        try:
            cost = float(chat_token_cost(result.usage, model_name)) if result.usage else 0.01
        except Exception:
            cost = 0.01
        if not math.isfinite(cost) or cost < 0:
            cost = 0.01
        mirror_chat_session_spend(
            session,
            operation_type="standard_research_fallback",
            actual_cost=cost,
            details=f"Fallback for: {query[:50]}...",
        )

        return {
            "answer": answer,
            "mode": "standard_research_fallback",
            "cost": cost,
            "budget_remaining": session.cost_session.get_remaining_budget(),
        }
    except Exception as fallback_error:
        return {
            "error": f"Grok search failed: {primary_error!s}. GPT-5.5 fallback failed: {fallback_error!s}"
        }


async def run_deep_research(session: Any, query: str) -> dict[str, Any]:
    """Submit deep research under durable metered admission when enabled."""
    require_expert_chat_dispatch(
        session.chat_backend,
        "expert_chat_deep_research",
        metered=True,
    )
    from deepr.providers.registry import get_cost_estimate as _get_cost_estimate

    try:
        estimated_cost = float(_get_cost_estimate("o4-mini-deep-research"))
    except Exception:
        estimated_cost = 2.00

    allowed, reason, _needs_confirm = session.cost_safety.check_operation(
        session_id=session.session_id,
        operation_type="deep_research",
        estimated_cost=estimated_cost,
        require_confirmation=True,
    )

    if not allowed:
        is_budget_denial = reason.startswith("Insufficient budget:")
        session_denial = is_budget_denial or reason.startswith("Session circuit breaker open:")
        error_prefix = "Session budget exceeded" if is_budget_denial else "Deep research blocked"
        return {
            "error": f"{error_prefix}: {reason}",
            "mode": "deep_research",
            "status": "blocked",
            **(
                {"session_spent": session.cost_session.total_cost, "session_budget": session.budget}
                if session_denial
                else {"daily_spent": session.cost_safety.daily_cost, "daily_limit": session.cost_safety.max_daily}
            ),
            **(
                {"session_circuit_breaker_open": session.cost_session.is_circuit_open}
                if reason.startswith("Session circuit breaker open:")
                else {}
            ),
        }

    try:
        response = await execute_metered_chat_provider_call(
            provider="openai",
            model="o4-mini-deep-research",
            source="expert_chat.deep_research",
            max_cost_per_job=estimated_cost,
            call=lambda: session.client.responses.create(
                model="o4-mini-deep-research",
                messages=[{"role": "user", "content": query}],
            ),
        )

        job_id = response.id

        session.research_jobs.append(job_id)
        session.pending_research[job_id] = {
            "query": query,
            "started_at": datetime.now(UTC),
            "estimated_cost": estimated_cost,
        }

        if job_id not in session.expert.research_jobs:
            session.expert.research_jobs.append(job_id)
            store = ExpertStore()
            session.expert._sync_budget_from_manager()
            store.save(session.expert)

        mirror_chat_session_spend(
            session,
            operation_type="deep_research",
            actual_cost=estimated_cost,
            details=f"Job {job_id}: {query[:50]}...",
        )
        spending = session.cost_safety.get_spending_summary()

        return {
            "job_id": job_id,
            "mode": "deep_research",
            "status": "submitted",
            "estimated_cost": estimated_cost,
            "estimated_time_minutes": 10,
            "message": "Deep research job submitted. Results will be available in 5-20 minutes and automatically integrated into knowledge base.",
            "budget_remaining": session.cost_session.get_remaining_budget(),
            "daily_spent": spending["daily"]["spent"],
            "daily_limit": spending["daily"]["limit"],
            "daily_remaining": spending["daily"]["remaining"],
        }
    except Exception as e:
        session.cost_session.record_failure("deep_research", str(e))
        session.cost_safety.record_failure(session.session_id, "deep_research", str(e))
        return {"error": str(e)}


_TERMINAL_DEEP_RESEARCH_STATUSES = frozenset({"completed", "failed", "cancelled", "incomplete"})


def _usage_cost_from_response(response: Any, model: str, fallback: float) -> tuple[float, int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return float(fallback), 0, 0
    try:
        from deepr.core.costs import CostEstimator

        input_tokens = int(getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0)
        if input_tokens <= 0 and output_tokens <= 0:
            return float(fallback), 0, 0
        actual = float(CostEstimator.calculate_actual_cost(model, input_tokens, output_tokens))
        if not math.isfinite(actual) or actual < 0:
            return float(fallback), input_tokens, output_tokens
        return actual, input_tokens, output_tokens
    except Exception:
        return float(fallback), 0, 0


async def reconcile_deep_research_job(session: Any, job_id: str) -> dict[str, Any]:
    """Retrieve a submitted deep-research job and record final usage honestly.

    Submission already settled the registry estimate under durable admission.
    This step appends an idempotent final-usage observation so operators can
    compare estimate vs provider-reported cost without double-charging the
    session when actual is at or below the estimate. When actual exceeds the
    estimate, only the positive delta is mirrored into the chat session.
    """
    pending = session.pending_research.get(job_id)
    if pending is None:
        return {"status": "not_pending", "job_id": job_id}

    responses = getattr(session.client, "responses", None)
    retrieve = getattr(responses, "retrieve", None)
    if not callable(retrieve):
        return {"status": "provider_retrieve_unavailable", "job_id": job_id}

    response = await retrieve(job_id)
    provider_status = str(getattr(response, "status", "") or "")
    if provider_status and provider_status not in _TERMINAL_DEEP_RESEARCH_STATUSES:
        return {
            "status": "pending",
            "job_id": job_id,
            "provider_status": provider_status,
        }

    model = "o4-mini-deep-research"
    estimated = float(pending.get("estimated_cost") or 0.0)
    actual, tokens_in, tokens_out = _usage_cost_from_response(response, model, estimated)
    # Submission already settled the registry estimate on the ledger. This
    # observation may only append unaccounted overrun (delta), never the full
    # actual again, or ledger totals double-count deep research spend.
    delta = max(0.0, actual - estimated)
    ledger = CostLedger()
    event, written = ledger.record_event(
        operation="deep_research_final_usage",
        provider="openai",
        cost_usd=delta,
        model=model,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        task_id=f"research_{job_id}",
        session_id=str(getattr(session, "session_id", "") or ""),
        source="expert_chat.deep_research.final_usage",
        idempotency_key=f"job:{job_id}:final_usage",
        metadata={
            "estimated_cost_usd": f"{estimated:.6f}",
            "actual_cost_usd": f"{actual:.6f}",
            "delta_usd": f"{(actual - estimated):.6f}",
            "provider_status": provider_status or "unknown",
            "charged_session_delta_usd": f"{delta:.6f}",
            "ledger_cost_is_overrun_only": "true",
        },
        require_fsync=True,
    )
    if written and delta > 0:
        mirror_chat_session_spend(
            session,
            operation_type="deep_research_final_delta",
            actual_cost=delta,
            details=f"Job {job_id} final usage exceeded estimate",
        )
    session.pending_research.pop(job_id, None)
    return {
        "status": "reconciled",
        "job_id": job_id,
        "provider_status": provider_status or "unknown",
        "estimated_cost": estimated,
        "actual_cost": actual,
        "delta_cost": actual - estimated,
        "ledger_written": written,
        "event_id": getattr(event, "idempotency_key", f"job:{job_id}:final_usage"),
    }
