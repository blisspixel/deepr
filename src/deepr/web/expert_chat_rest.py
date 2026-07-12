"""One-shot REST execution and saved-session helpers for browser expert chat."""

from __future__ import annotations

import inspect
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import experts_root
from deepr.experts.chat_capacity import MeteredExpertChatDisabledError
from deepr.web.expert_chat_contract import BrowserChatContractError, BrowserExpertChatRequest

logger = logging.getLogger(__name__)
_SESSION_ID_RE = re.compile(r"^[\w-]+$")
_TOOL_STEPS = {
    "search_knowledge_base",
    "standard_research",
    "deep_research",
    "skill_tool_call",
}
_UNCERTAINTY_PHRASES = (
    "i don't know",
    "i'm not sure",
    "i don't have",
    "no information",
    "not in my knowledge",
)


def restore_session_messages(
    session: Any,
    expert_name: str,
    session_id: str,
    *,
    experts_dir: Path | None = None,
) -> None:
    """Restore user and assistant messages from a path-safe saved session."""
    if _SESSION_ID_RE.fullmatch(session_id) is None:
        logger.warning("Invalid session_id rejected: %s", session_id)
        return

    from deepr.experts.profile import ExpertStore

    store = ExpertStore(str(experts_dir or experts_root()))
    conversation_file = store.get_conversations_dir(expert_name) / f"{session_id}.json"
    if not conversation_file.exists():
        return

    with open(conversation_file, encoding="utf-8") as file:
        data = json.load(file)
    for message in data.get("messages", []):
        if message.get("role") in ("user", "assistant"):
            session.messages.append({"role": message["role"], "content": message["content"]})


async def run_browser_expert_chat_once(
    *,
    expert_name: str,
    message: str,
    request_contract: BrowserExpertChatRequest,
    experts_dir: Path | None = None,
) -> tuple[Any, str]:
    """Run one REST chat turn with the same reservation contract as Socket.IO."""
    from deepr.api.websockets.events import BrowserTurnAccounting
    from deepr.experts.chat import start_chat_session

    session = await start_chat_session(
        expert_name,
        budget=request_contract.budget,
        agentic=True,
        quiet=True,
    )
    turn_accounting = BrowserTurnAccounting(request_contract.budget)
    try:
        session.chat_mode = request_contract.chat_mode
        if request_contract.session_id:
            restore_session_messages(
                session,
                expert_name,
                request_contract.session_id,
                experts_dir=experts_dir,
            )
        selected_model = session.select_model_for_turn(message)
        turn_accounting.begin(session, selected_model)
        turn_accounting.mark_dispatched()
        response = await session.send_message(message, selected_model=selected_model)
        if getattr(session, "last_turn_failed", False):
            raise RuntimeError("Expert chat session reported a terminal turn failure")
        turn_accounting.release_success()
        return session, response
    except Exception:
        try:
            turn_accounting.close_ambiguous(source="web.browser_chat.rest.failure")
        except Exception as accounting_exc:
            logger.error(
                "REST expert-chat failure left its durable reservation active: %s",
                type(accounting_exc).__name__,
            )
        raise
    finally:
        close = getattr(getattr(session, "client", None), "close", None)
        if callable(close):
            try:
                close_result = close()
                if inspect.isawaitable(close_result):
                    await close_result
            except Exception as exc:
                logger.warning("REST expert-chat client cleanup failed: %s", type(exc).__name__)
        close_cost_session = getattr(getattr(session, "cost_safety", None), "close_session", None)
        session_cost_id = getattr(session, "session_id", None)
        if callable(close_cost_session) and session_cost_id:
            try:
                close_cost_session(session_cost_id)
            except Exception as exc:
                logger.warning("REST expert-chat cost-session cleanup failed: %s", type(exc).__name__)


def build_browser_expert_chat_response(session: Any, response_text: str, session_id: str | None) -> dict[str, Any]:
    """Build the public response after persisting the completed conversation."""
    saved_session_id = session.save_conversation(session_id)
    tool_calls = [
        {"tool": item["step"], "query": item.get("query", "")[:200]}
        for item in session.reasoning_trace
        if item.get("step") in _TOOL_STEPS
    ]
    confidence = 0.9
    if response_text and any(phrase in response_text.lower() for phrase in _UNCERTAINTY_PHRASES):
        confidence = 0.3
    return {
        "response": {
            "id": uuid.uuid4().hex[:12],
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": saved_session_id,
            "cost": round(session.cost_accumulated, 4),
            "tool_calls": tool_calls,
            "confidence": confidence,
            "mode": session.chat_mode.value,
        }
    }


def handle_browser_expert_chat_request(
    *,
    name: str,
    data: Any,
    decode_expert_name: Any,
    max_budget: float,
    run_async_command: Any,
    parse_request: Any,
    run_chat_once: Any,
    build_response: Any,
    experts_dir: Path,
    jsonify_response: Any,
    route_logger: logging.Logger,
) -> Any:
    """Execute the Flask REST route while keeping app-level patch seams explicit."""
    try:
        if not isinstance(data, dict) or not isinstance(data.get("message"), str):
            return jsonify_response({"error": "Message required"}), 400
        if not data["message"].strip():
            return jsonify_response({"error": "Message required"}), 400

        decoded_name, err = decode_expert_name(name)
        if err:
            return err

        parsed = parse_request(data, max_budget=max_budget)
        session, response_text = run_async_command(
            run_chat_once(
                expert_name=decoded_name,
                message=data["message"].strip(),
                request_contract=parsed,
                experts_dir=experts_dir,
            )
        )
        return jsonify_response(build_response(session, response_text, parsed.session_id))
    except BrowserChatContractError as exc:
        return jsonify_response(exc.to_dict()), exc.status_code
    except MeteredExpertChatDisabledError as exc:
        return jsonify_response({"error": str(exc), "error_code": exc.code, **exc.to_dict()}), 409
    except ImportError:
        return jsonify_response({"error": "Expert system not available"}), 404
    except ValueError as exc:
        route_logger.warning("Chat error for expert %s: %s", name, exc)
        return jsonify_response({"error": "Expert not found"}), 404
    except Exception as exc:
        route_logger.error("Error chatting with expert %s: %s", name, exc)
        return jsonify_response({"error": "Internal server error"}), 500


__all__ = [
    "build_browser_expert_chat_response",
    "handle_browser_expert_chat_request",
    "restore_session_messages",
    "run_browser_expert_chat_once",
]
