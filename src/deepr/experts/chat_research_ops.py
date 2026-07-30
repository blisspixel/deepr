"""Fail-closed metered research helpers used by ExpertChatSession."""

from __future__ import annotations

from typing import Any

from deepr.experts.chat_capacity import MeteredExpertChatDisabledError


def _raise_unbounded_research(operation: str) -> None:
    raise MeteredExpertChatDisabledError(
        operation,
        message=(
            "Metered expert research is disabled because the provider does not expose "
            "one enforceable maximum charge covering tokens, tools, and background work. "
            "No provider request was sent. Use local or proven zero-dollar plan capacity."
        ),
    )


async def run_standard_research(session: Any, query: str) -> dict[str, Any]:
    """Refuse Grok web and X research before provider construction or dispatch."""
    del session, query
    _raise_unbounded_research("expert_chat_standard_research")


async def _standard_research_gpt_fallback(
    session: Any,
    query: str,
    *,
    primary_error: BaseException,
) -> dict[str, Any]:
    """Refuse the paid fallback independently of the primary research gate."""
    del session, query, primary_error
    _raise_unbounded_research("expert_chat_standard_research_fallback")


async def run_deep_research(session: Any, query: str) -> dict[str, Any]:
    """Refuse background deep research before provider construction or dispatch."""
    del session, query
    _raise_unbounded_research("expert_chat_deep_research")


async def reconcile_deep_research_job(session: Any, job_id: str) -> dict[str, Any]:
    """Refuse external job retrieval while the original charge is unbounded."""
    del session, job_id
    _raise_unbounded_research("expert_chat_deep_research_reconciliation")


__all__ = ["reconcile_deep_research_job", "run_deep_research", "run_standard_research"]
