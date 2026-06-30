"""MCP implementation for ``deepr_query_expert``."""

from __future__ import annotations

import hashlib
from collections.abc import MutableMapping
from logging import Logger
from typing import Any, Protocol

from deepr.core.errors import DeeprError
from deepr.mcp.consult_tool import consult_experts_tool

QUERY_EXPERT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "expert_name": {"type": "string", "description": "Name of the expert (from deepr_list_experts)"},
        "question": {"type": "string", "description": "Question to ask the expert"},
        "backend": {
            "type": "string",
            "enum": ["api", "local", "plan"],
            "default": "api",
            "description": (
                "api uses the legacy expert chat path; local and plan use the one-expert "
                "consult path with live metered fallback disabled."
            ),
        },
        "agentic": {
            "type": "boolean",
            "default": False,
            "description": "Enable autonomous research for backend='api' only.",
        },
        "budget": {
            "type": "number",
            "description": (
                "USD ceiling for this metered-capable chat session. Omit to use the server default; "
                "0 is accepted for backend='local' and backend='plan'."
            ),
        },
        "local_model": {"type": "string", "description": "Optional Ollama model when backend='local'."},
        "plan": {
            "type": "string",
            "description": "Plan-quota backend id when backend='plan' (for example codex).",
        },
        "plan_model": {"type": "string", "description": "Optional model hint for the plan-quota CLI."},
    },
    "required": ["expert_name", "question"],
}


class ExpertStoreLike(Protocol):
    """Store surface used by the MCP query tool."""

    def load(self, name: str) -> Any:
        """Return an expert profile or None."""


class ExpertChatSessionFactory(Protocol):
    """Factory for the legacy API-backed expert chat session."""

    def __call__(self, expert: Any, *, budget: float | None, agentic: bool) -> Any:
        """Build a chat session for one loaded expert."""


def _make_error(code: str, message: str, *, category: str = "internal") -> dict[str, Any]:
    return {
        "error_code": code,
        "message": message,
        "category": category,
        "retryable": False,
    }


async def query_expert_tool(
    *,
    store: ExpertStoreLike,
    sessions: MutableMapping[str, Any],
    session_factory: ExpertChatSessionFactory,
    logger: Logger,
    expert_name: str,
    question: str,
    budget: float | None = None,
    agentic: bool = False,
    backend: str = "api",
    local_model: str | None = None,
    plan: str | None = None,
    plan_model: str | None = None,
) -> dict[str, Any]:
    """Query one expert through legacy chat or the no-metered consult bridge."""
    try:
        expert = store.load(expert_name)
        if not expert:
            return _make_error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

        backend_mode = (backend or "api").strip().lower()
        if backend_mode in {"local", "plan"}:
            return await _query_expert_via_consult(
                expert_name=expert_name,
                question=question,
                budget=budget,
                agentic=agentic,
                backend=backend_mode,
                local_model=local_model,
                plan=plan,
                plan_model=plan_model,
            )
        if backend_mode != "api":
            return _make_error("INVALID_BACKEND", "backend must be one of: api, local, plan", category="validation")

        return await _query_legacy_expert_chat(
            expert=expert,
            expert_name=expert_name,
            question=question,
            budget=budget,
            agentic=agentic,
            sessions=sessions,
            session_factory=session_factory,
            logger=logger,
        )
    except (OSError, KeyError, ValueError, DeeprError) as exc:
        return _make_error("EXPERT_QUERY_FAILED", str(exc))


async def _query_expert_via_consult(
    *,
    expert_name: str,
    question: str,
    budget: float | None,
    agentic: bool,
    backend: str,
    local_model: str | None,
    plan: str | None,
    plan_model: str | None,
) -> dict[str, Any]:
    if agentic:
        return _make_error(
            "UNSUPPORTED_AGENTIC_BACKEND",
            "agentic=true is only supported by backend='api' expert chat for now",
            category="validation",
        )
    payload = await consult_experts_tool(
        question=question,
        experts=[expert_name],
        max_experts=1,
        budget=budget if budget is not None else 0.0,
        synthesis_backend=backend,
        local_model=local_model,
        plan=plan if backend == "plan" else None,
        plan_model=plan_model if backend == "plan" else None,
    )
    if "error_code" in payload:
        return payload
    return {
        "answer": payload.get("answer", ""),
        "expert": expert_name,
        "cost": payload.get("cost_usd", 0.0),
        "budget_remaining": None,
        "research_triggered": 0,
        "backend": backend,
        "capacity": payload.get("capacity", {}),
        "consult_artifact": payload,
    }


async def _query_legacy_expert_chat(
    *,
    expert: Any,
    expert_name: str,
    question: str,
    budget: float | None,
    agentic: bool,
    sessions: MutableMapping[str, Any],
    session_factory: ExpertChatSessionFactory,
    logger: Logger,
) -> dict[str, Any]:
    digest = hashlib.md5(question.encode(), usedforsecurity=False).hexdigest()[:12]
    session_key = f"{expert_name}_{digest}"
    if session_key not in sessions:
        sessions[session_key] = session_factory(expert, budget=budget, agentic=agentic)

    session = sessions[session_key]
    try:
        response_text = await session.send_message(question)
        summary = session.get_session_summary()
    finally:
        sessions.pop(session_key, None)
        try:
            session.cost_safety.close_session(session.session_id)
        except Exception:
            logger.debug("Cost session cleanup skipped for %s", session_key, exc_info=False)

    return {
        "answer": response_text,
        "expert": expert_name,
        "cost": summary["cost_accumulated"],
        "budget_remaining": summary.get("budget_remaining"),
        "research_triggered": summary["research_jobs_triggered"],
    }
