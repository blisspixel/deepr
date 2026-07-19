"""Research-function adapter for a verified plan-quota chat client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from deepr.backends.context_building import (
    ContextBuilder,
    build_context,
    context_evidence_fields,
    context_generation_readiness,
    context_not_ready_error,
)
from deepr.backends.local import _local_prompt
from deepr.backends.plan_quota.adapters import PlanQuotaAdapter
from deepr.backends.plan_quota.errors import PlanQuotaError, PlanQuotaExhausted
from deepr.backends.plan_quota.response import PlanQuotaResponse

ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]
CompletionCreate = Callable[..., Awaitable[PlanQuotaResponse]]


def make_plan_quota_research_fn(
    adapter: PlanQuotaAdapter,
    *,
    completion_create: CompletionCreate,
    model: str | None = None,
    context_builder: ContextBuilder | None = None,
) -> ResearchFn:
    """Build a research function that answers through verified plan capacity."""

    async def research_fn(
        query: str,
        budget: float,
        *,
        prior_source_pack: dict[str, Any] | None = None,
        retrieval_query: str | None = None,
    ) -> dict[str, Any]:
        del budget
        try:
            context = await build_context(
                context_builder,
                retrieval_query or query,
                prior_source_pack=prior_source_pack,
            )
            evidence_fields = context_evidence_fields(context)
            readiness = context_generation_readiness(context)
            if readiness is not None and not readiness.ready:
                return {
                    "answer": "",
                    "cost": 0.0,
                    "backend": f"plan_quota:{adapter.backend_id}",
                    "error": context_not_ready_error(readiness),
                    "error_code": "fresh_context_not_ready",
                    "retryable": readiness.retryable,
                    "no_metered_fallback": readiness.no_metered_fallback,
                    "context_preflight": readiness.to_dict(),
                    **evidence_fields,
                }
            prompt, metadata = _local_prompt(query, context)
            response = await completion_create(
                model=model or "",
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.choices[0].message.content or ""
            result: dict[str, Any] = {
                "answer": answer,
                "cost": 0.0,
                "backend": f"plan_quota:{adapter.backend_id}",
            }
            result.update(evidence_fields)
            if metadata is not None and "fresh_context" not in result:
                result["fresh_context"] = metadata
            return result
        except PlanQuotaError as error:
            return plan_quota_research_error_result(adapter, error)
        except Exception as error:  # seam contract: report, do not raise
            return {
                "answer": "",
                "cost": 0.0,
                "error": f"{adapter.backend_id} backend error: {error}",
                "error_code": "plan_quota_backend_error",
                "retryable": False,
                "no_metered_fallback": True,
            }

    return research_fn


def plan_quota_research_error_result(
    adapter: PlanQuotaAdapter,
    error: PlanQuotaError,
) -> dict[str, Any]:
    """Preserve typed no-fallback and accounting state across the seam."""
    outcome = str(getattr(error, "plan_quota_outcome", "plan_quota_error"))
    result: dict[str, Any] = {
        "answer": "",
        "cost": 0.0,
        "backend": f"plan_quota:{adapter.backend_id}",
        "error": str(error),
        "error_code": str(getattr(error, "error_code", outcome)),
        "outcome": outcome,
        "retryable": bool(getattr(error, "retryable", False)),
        "no_metered_fallback": bool(getattr(error, "no_metered_fallback", True)),
        "vendor_dispatched": bool(getattr(error, "vendor_dispatched", False)),
        "attempt_id": str(getattr(error, "plan_quota_attempt_id", "")),
        "quota_observation_recorded": bool(getattr(error, "quota_recorded", False)),
        "cost_event_recorded": bool(getattr(error, "cost_recorded", False)),
    }
    if isinstance(error, PlanQuotaExhausted):
        result["quota_exhausted"] = True
    attempt_outcome = error.__dict__.get("plan_quota_attempt_outcome")
    if attempt_outcome is not None:
        result["attempt_outcome"] = str(attempt_outcome)
    return result


__all__ = [
    "CompletionCreate",
    "ResearchFn",
    "make_plan_quota_research_fn",
    "plan_quota_research_error_result",
]
