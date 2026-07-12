"""Bounded auxiliary operations for a live expert-chat session."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import UTC, datetime
from typing import Any

from deepr.experts.chat_backends import ExpertChatRequest
from deepr.experts.chat_turns import chat_token_cost, chat_usage_tokens

logger = logging.getLogger(__name__)


async def generate_follow_ups(session: Any, user_message: str, response: str) -> list[str]:
    """Generate bounded suggestions while settling every possible dispatch."""
    model_name = session._provider_model_or("gpt-4o-mini")
    estimated_cost = max(0.01, session._estimate_chat_model_cost(model_name))
    try:
        allowed, _reason, needs_confirmation, reservation_id = session.cost_safety.check_and_reserve(
            session_id=session.session_id,
            operation_type="expert_chat_follow_ups",
            estimated_cost=estimated_cost,
            require_confirmation=False,
        )
    except Exception as exc:
        logger.warning("Follow-up cost reservation failed: %s", type(exc).__name__)
        return []
    if not allowed or needs_confirmation or not reservation_id:
        return []

    try:
        result = await session.chat_backend.complete(
            ExpertChatRequest(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Generate 2-3 short follow-up questions a user might ask after this exchange. "
                        "Return ONLY a JSON array of strings. No explanation.",
                    },
                    {
                        "role": "user",
                        "content": f"User asked: {user_message[:300]}\n\nExpert replied: {response[:500]}",
                    },
                ],
                extra={"temperature": 0.7, "max_tokens": 200},
            )
        )
    except asyncio.CancelledError:
        try:
            session.cost_safety.record_cost(
                session_id=session.session_id,
                operation_type="expert_chat_follow_ups",
                actual_cost=estimated_cost,
                provider=session.chat_provider,
                model=model_name,
                source="experts.chat.follow_ups.cancelled",
                metadata={"actual_cost_reported": False},
                reservation_id=reservation_id,
            )
            session.cost_accumulated += estimated_cost
        except Exception as exc:
            logger.error(
                "Follow-up cancellation left its cost reservation active: %s",
                type(exc).__name__,
            )
        raise
    except Exception:
        session.cost_safety.record_cost(
            session_id=session.session_id,
            operation_type="expert_chat_follow_ups",
            actual_cost=estimated_cost,
            provider=session.chat_provider,
            model=model_name,
            source="experts.chat.follow_ups.failed",
            metadata={"actual_cost_reported": False},
            reservation_id=reservation_id,
        )
        session.cost_accumulated += estimated_cost
        return []

    usage = result.usage
    actual_cost = chat_token_cost(usage, model_name) if usage is not None else estimated_cost
    tokens_input, tokens_output = chat_usage_tokens(usage)
    session.cost_safety.record_cost(
        session_id=session.session_id,
        operation_type="expert_chat_follow_ups",
        actual_cost=actual_cost,
        provider=session.chat_provider,
        model=model_name,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        request_id=result.provider_request_id,
        source="experts.chat.follow_ups",
        metadata={"actual_cost_reported": usage is not None},
        reservation_id=reservation_id,
    )
    session.cost_accumulated += actual_cost

    try:
        raw = result.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            return []
        return parsed[:3]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


async def cancel_inflight_provider_work(session: Any) -> dict[str, Any]:
    """Request cancellation for provider jobs accepted by this session."""
    responses = getattr(session.client, "responses", None)
    cancel = getattr(responses, "cancel", None)
    pending_ids = list(session.pending_research)
    if not pending_ids:
        return {"status": "transport_cancel_requested", "requested": 0, "failed": 0}
    if not callable(cancel):
        return {
            "status": "provider_cancel_unavailable",
            "requested": 0,
            "failed": len(pending_ids),
        }

    requested = 0
    failed = 0
    for job_id in pending_ids:
        try:
            result = cancel(job_id)
            if inspect.isawaitable(result):
                await result
            requested += 1
            session.pending_research.pop(job_id, None)
        except Exception as exc:
            failed += 1
            logger.warning(
                "Provider cancellation request failed for pending research %s: %s",
                job_id,
                type(exc).__name__,
            )

    if failed and requested:
        status = "provider_cancel_partial"
    elif failed:
        status = "provider_cancel_failed"
    else:
        status = "provider_cancel_requested"
    return {"status": status, "requested": requested, "failed": failed}


async def compact_conversation(session: Any) -> dict[str, Any]:
    """Replace older messages with one structured compact summary."""
    if len(session.messages) <= 6:
        return {"original_messages": len(session.messages), "summary_length": 0, "status": "too_short"}

    keep_count = 4
    to_summarise = session.messages[:-keep_count]
    kept = session.messages[-keep_count:]
    text_parts = []
    for msg in to_summarise:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        text_parts.append(f"{role}: {content[:500]}")
    conversation_text = "\n".join(text_parts)

    try:
        model_name = session._provider_model_or("gpt-4o-mini")
        result = await session.chat_backend.complete(
            ExpertChatRequest(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the following conversation into structured sections. "
                            "Use these exact headings:\n"
                            "KEY_FACTS: Important facts established\n"
                            "DECISIONS_MADE: Decisions or conclusions reached\n"
                            "OPEN_QUESTIONS: Unresolved questions\n"
                            "USER_PREFERENCES: Any user preferences noted\n"
                            "Keep each section to 2-3 bullet points max. Be concise."
                        ),
                    },
                    {"role": "user", "content": conversation_text[:8000]},
                ],
                extra={"temperature": 0.3, "max_tokens": 500},
            )
        )
        summary = result.text or "Summary unavailable."
    except Exception as exc:
        logger.warning("Compact summary failed: %s", exc)
        summary = f"[{len(to_summarise)} earlier messages - summary unavailable]"

    summary_msg = {
        "role": "system",
        "content": f"CONVERSATION SUMMARY (compacted from {len(to_summarise)} messages):\n\n{summary}",
    }
    session.messages = [summary_msg, *kept]
    session.reasoning_trace.append(
        {
            "step": "compact_conversation",
            "timestamp": datetime.now(UTC).isoformat(),
            "original_messages": len(to_summarise) + keep_count,
            "kept_messages": keep_count,
            "summary_length": len(summary),
        }
    )
    return {
        "original_messages": len(to_summarise) + keep_count,
        "summary_length": len(summary),
        "status": "compacted",
    }


__all__ = ["cancel_inflight_provider_work", "compact_conversation", "generate_follow_ups"]
