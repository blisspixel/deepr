"""Socket.IO event handlers."""

import asyncio
import hmac
import logging
import os
import threading
import time
import uuid

from flask import request as flask_request
from flask_socketio import emit, join_room, leave_room

logger = logging.getLogger(__name__)

# Track active chat sessions for cancellation
_active_chats: dict[str, bool] = {}  # sid -> cancelled flag


def register_socketio_events(socketio):
    """Register Socket.IO event handlers."""

    @socketio.on("connect")
    def handle_connect(auth=None):
        """Handle client connection (with auth when DEEPR_API_KEY is set)."""
        api_key = os.getenv("DEEPR_API_KEY", "")
        if api_key:
            # Check socketio auth object (preferred), then headers as fallback
            token = ""
            if isinstance(auth, dict):
                token = auth.get("token", "")
            if not token:
                auth_header = flask_request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            if not token or not hmac.compare_digest(token, api_key):
                logger.warning("WebSocket auth rejected")
                return False  # reject connection
        logger.info("Client connected")
        emit("connected", {"message": "Connected to Deepr API"})

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info("Client disconnected")

    @socketio.on("subscribe_jobs")
    def handle_subscribe_jobs(data):
        """
        Subscribe to job updates.

        Client can subscribe to:
        - All jobs: {"scope": "all"}
        - Specific job: {"scope": "job", "job_id": "123"}
        """
        scope = data.get("scope", "all")

        if scope == "all":
            join_room("jobs")
            emit("subscribed", {"scope": "jobs", "message": "Subscribed to all jobs"})
            logger.info("Client subscribed to all jobs")

        elif scope == "job":
            job_id = data.get("job_id")
            if job_id:
                join_room(f"job_{job_id}")
                emit("subscribed", {"scope": "job", "job_id": job_id})
                logger.info(f"Client subscribed to job {job_id}")

    @socketio.on("unsubscribe_jobs")
    def handle_unsubscribe_jobs(data):
        """Unsubscribe from job updates."""
        scope = data.get("scope", "all")

        if scope == "all":
            leave_room("jobs")
            emit("unsubscribed", {"scope": "jobs"})

        elif scope == "job":
            job_id = data.get("job_id")
            if job_id:
                leave_room(f"job_{job_id}")
                emit("unsubscribed", {"scope": "job", "job_id": job_id})

    @socketio.on("chat_start")
    def handle_chat_start(data):
        """Start a streaming chat with an expert.

        Data: { expert_name: str, message: str, session_id?: str }
        Emits: chat_token, chat_status, chat_tool_start, chat_tool_end,
               chat_complete, chat_error
        """
        sid = flask_request.sid
        room = f"chat_{sid}"
        join_room(room)
        _active_chats[sid] = False  # not cancelled

        expert_name = data.get("expert_name", "")
        message = data.get("message", "")
        session_id = data.get("session_id")

        if not expert_name or not message:
            socketio.emit("chat_error", {"error": "expert_name and message required"}, room=room)
            return

        def _run_chat():
            """Run the chat session in a background thread with its own event loop."""
            try:
                from deepr.experts.chat import start_chat_session
                from deepr.web.app import _restore_session_messages

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                session = loop.run_until_complete(
                    start_chat_session(expert_name, budget=10.0, agentic=True, quiet=True)
                )

                if session_id:
                    _restore_session_messages(session, expert_name, session_id)

                tool_timers: dict[str, float] = {}

                def on_token(text):
                    if _active_chats.get(sid):
                        return  # cancelled
                    socketio.emit("chat_token", {"content": text}, room=room)

                def on_status(status):
                    if _active_chats.get(sid):
                        return
                    socketio.emit("chat_status", {"status": status}, room=room)

                    # Detect tool start/end from status text
                    tool_keywords = {
                        "Searching knowledge base": "search_knowledge_base",
                        "Searching web": "standard_research",
                        "Deep research": "deep_research",
                        "Submitting deep research": "deep_research",
                    }
                    for keyword, tool_name in tool_keywords.items():
                        if keyword.lower() in status.lower():
                            if tool_name not in tool_timers:
                                tool_timers[tool_name] = time.time()
                                socketio.emit(
                                    "chat_tool_start",
                                    {"tool": tool_name, "query": status},
                                    room=room,
                                )

                    if status.lower() == "thinking..." and tool_timers:
                        for tool_name, start in list(tool_timers.items()):
                            elapsed = int((time.time() - start) * 1000)
                            socketio.emit(
                                "chat_tool_end",
                                {"tool": tool_name, "elapsed_ms": elapsed},
                                room=room,
                            )
                        tool_timers.clear()

                response = loop.run_until_complete(
                    session.send_message_streaming(
                        message,
                        token_callback=on_token,
                        status_callback=on_status,
                    )
                )

                saved_session_id = session.save_conversation(session_id)

                tool_calls = [
                    {"tool": t["step"], "query": t.get("query", "")[:200]}
                    for t in session.reasoning_trace
                    if t.get("step") in (
                        "search_knowledge_base", "standard_research",
                        "deep_research", "skill_tool_call",
                    )
                ]

                socketio.emit(
                    "chat_complete",
                    {
                        "id": uuid.uuid4().hex[:12],
                        "content": response,
                        "session_id": saved_session_id,
                        "cost": round(session.cost_accumulated, 4),
                        "tool_calls": tool_calls,
                        "follow_ups": getattr(session, "_last_follow_ups", []),
                        "confidence": getattr(session, "_last_confidence", 0.9),
                    },
                    room=room,
                )

                loop.close()

            except Exception as e:
                logger.exception("Chat streaming error for %s", expert_name)
                socketio.emit("chat_error", {"error": str(e)}, room=room)
            finally:
                _active_chats.pop(sid, None)

        thread = threading.Thread(target=_run_chat, daemon=True)
        thread.start()

    @socketio.on("chat_stop")
    def handle_chat_stop(data=None):
        """Request cancellation of the current chat stream."""
        sid = flask_request.sid
        if sid in _active_chats:
            _active_chats[sid] = True
            logger.info("Chat cancelled for %s", sid)


def emit_job_created(socketio, job):
    """Emit job created event."""
    try:
        socketio.emit("job_created", job.to_dict(), room="jobs")
        logger.info("Emitted job_created for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_created for %s", job.id)


def emit_job_updated(socketio, job):
    """Emit job updated event."""
    try:
        data = job.to_dict()
        socketio.emit("job_updated", data, room="jobs")
        socketio.emit("job_updated", data, room=f"job_{job.id}")
        logger.info("Emitted job_updated for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_updated for %s", job.id)


def emit_job_completed(socketio, job):
    """Emit job completed event."""
    try:
        data = job.to_dict()
        socketio.emit("job_completed", data, room="jobs")
        socketio.emit("job_completed", data, room=f"job_{job.id}")
        logger.info("Emitted job_completed for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_completed for %s", job.id)


def emit_job_failed(socketio, job, error):
    """Emit job failed event."""
    try:
        data = job.to_dict()
        data["error"] = error
        socketio.emit("job_failed", data, room="jobs")
        socketio.emit("job_failed", data, room=f"job_{job.id}")
        logger.info("Emitted job_failed for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_failed for %s", job.id)


def emit_cost_warning(socketio, warning):
    """Emit cost warning event."""
    try:
        socketio.emit("cost_warning", warning, room="jobs")
        logger.warning("Emitted cost_warning: %s", warning)
    except Exception:
        logger.exception("Failed to emit cost_warning")


def emit_cost_exceeded(socketio, exceeded):
    """Emit cost exceeded event."""
    try:
        socketio.emit("cost_exceeded", exceeded, room="jobs")
        logger.error("Emitted cost_exceeded: %s", exceeded)
    except Exception:
        logger.exception("Failed to emit cost_exceeded")
