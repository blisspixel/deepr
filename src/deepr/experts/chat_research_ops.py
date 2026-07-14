"""Metered research helpers used by ExpertChatSession."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from deepr.experts.chat_backends import ExpertChatRequest
from deepr.experts.chat_capacity import require_expert_chat_dispatch
from deepr.experts.chat_metered import execute_metered_chat_provider_call
from deepr.experts.chat_turns import chat_token_cost, record_named_chat_cost
from deepr.experts.profile import ExpertStore

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
        session.cost_accumulated += cost

        session.cost_safety.record_cost(
            session_id=session.session_id,
            operation_type="standard_research",
            actual_cost=cost,
            provider="xai",
            model="grok-4.3",
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
                    "error": f"Grok search failed: {e!s}. GPT-5.5 fallback blocked: {reason}",
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
                            "content": "Answer based on your knowledge. Be honest if information might be outdated.",
                        },
                        {"role": "user", "content": query},
                    ],
                    reasoning_effort=session._provider_reasoning_effort_or_none("low"),
                )
            )

            answer = f"{result.text}\n\n[Note: Grok web search unavailable, using GPT-5.5 knowledge instead]"

            cost = record_named_chat_cost(
                cost_safety=session.cost_safety,
                session_id=session.session_id,
                usage=result.usage,
                model_name=model_name,
                operation_type="standard_research_fallback",
                fallback_cost=0.01,
                cost_calculator=chat_token_cost,
                provider=session.chat_provider,
                details=f"Fallback for: {query[:50]}...",
            )
            session.cost_accumulated += cost

            return {
                "answer": answer,
                "mode": "standard_research_fallback",
                "cost": cost,
                "budget_remaining": session.cost_session.get_remaining_budget(),
            }
        except Exception as fallback_error:
            return {"error": f"Grok search failed: {e!s}. GPT-5.5 fallback failed: {fallback_error!s}"}


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

        session.cost_session.record_operation(
            operation_type="deep_research", cost=estimated_cost, details=f"Query: {query[:50]}..."
        )

        session.cost_safety.record_cost(
            session_id=session.session_id,
            operation_type="deep_research",
            actual_cost=estimated_cost,
            details=f"Job {job_id}: {query[:50]}...",
        )

        session.cost_accumulated = session.cost_session.total_cost
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
