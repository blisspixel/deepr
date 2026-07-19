"""Socket.IO event handlers."""

import asyncio
import inspect
import logging
import os
import queue
import threading
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

from flask import request as flask_request
from flask_socketio import emit, join_room, leave_room

from deepr.experts.constants import ALL_TOOL_NAMES
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import (
    refund_research_cost,
    reserve_configured_cost_ceiling,
    settle_research_cost,
)
from deepr.security.http_auth import (
    SharedSecretDecision,
    check_shared_secret,
    env_flag,
    presented_http_secret,
)
from deepr.web.expert_chat_contract import (
    BrowserChatContractError,
    parse_browser_expert_chat_request,
    parse_browser_expert_name,
)

logger = logging.getLogger(__name__)

_Handler = TypeVar("_Handler", bound=Callable[..., Any])
_MAX_BROWSER_CHAT_WORKERS = 32


class _SocketIOEmitter(Protocol):
    def on(self, event: str) -> Callable[[_Handler], _Handler]: ...

    def emit(self, event: str, data: Any, *, room: str | None = None) -> Any: ...


@dataclass(frozen=True)
class _BrowserChatTask:
    task_id: int
    coro_fn: Callable[[], Coroutine[Any, Any, None]]
    on_error: Callable[[Exception], None]
    on_cancel: Callable[[str], Coroutine[Any, Any, None]] | None = None


@dataclass
class BrowserTurnAccounting:
    """Durable hold for one metered browser turn."""

    approved_budget: float
    reservation: Any | None = None
    session: Any | None = None
    starting_cost: float = 0.0
    dispatched: bool = False

    def begin(self, session: Any, selected_model: Any) -> None:
        require_dispatch = getattr(session, "require_provider_dispatch_allowed", None)
        if not callable(require_dispatch):
            raise RuntimeError("Browser expert-chat session has no capacity gate")
        require_dispatch("browser_expert_chat_turn")
        self.session = session
        self.starting_cost = float(getattr(session, "cost_accumulated", 0.0) or 0.0)
        remaining = self.approved_budget - self.starting_cost
        if remaining <= 0:
            raise RuntimeError("Browser expert-chat budget is exhausted")
        provider = str(getattr(selected_model, "provider", "") or "").strip().lower()
        model = str(getattr(selected_model, "model", "") or "").strip()
        configured_provider = str(getattr(session, "chat_provider", "") or "").strip().lower()
        if not provider or not model or model.casefold() == "unknown":
            raise RuntimeError("Browser expert-chat dispatch provider and model are unknown")
        if not configured_provider or provider != configured_provider:
            raise RuntimeError("Browser expert-chat dispatch provider does not match its API backend")
        self.reservation = reserve_configured_cost_ceiling(
            job_id=f"browser-chat-turn-{uuid.uuid4().hex}",
            provider=provider,
            model=model,
            max_cost_per_job=remaining,
        )

    def mark_dispatched(self) -> None:
        self.dispatched = True

    def release_success(self) -> None:
        if self.reservation is None:
            return
        refund_research_cost(self.reservation)
        self.reservation = None

    def close_ambiguous(self, *, source: str) -> str:
        if self.reservation is None:
            return "not_started"
        if not self.dispatched:
            refund_research_cost(self.reservation)
            self.reservation = None
            return "refunded_before_dispatch"
        current_cost = float(getattr(self.session, "cost_accumulated", self.starting_cost) or 0.0)
        known_cost = max(0.0, current_cost - self.starting_cost)
        unaccounted_ceiling = max(0.0, float(self.reservation.estimated_cost) - known_cost)
        settle_research_cost(
            self.reservation,
            actual_cost=unaccounted_ceiling,
            source=source,
            actual_cost_reported=False,
            settlement_metadata={
                "settlement_basis": "conservative_unaccounted_ceiling",
                "known_cost_usd": known_cost,
                "unaccounted_ceiling_usd": unaccounted_ceiling,
            },
        )
        self.reservation = None
        return "settled_conservative"


class _BrowserChatState:
    """One persistent, serial event-loop worker for a browser socket."""

    def __init__(self, *, expert_name: str, approved_budget: float, conversation_id: str | None) -> None:
        self.expert_name = expert_name
        self.approved_budget = approved_budget
        self.conversation_id = conversation_id
        self.session: Any | None = None
        self._tasks: queue.Queue[_BrowserChatTask | None] = queue.Queue()
        self._state_lock = threading.Lock()
        self._busy = False
        self._busy_task_id: int | None = None
        self._busy_cancel_kind: str | None = None
        self._current_task_id: int | None = None
        self._current_async_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cancel_reason = "cancelled"
        self._cancel_requested = False
        self._session_closed = False
        self._next_task_id = 0
        self._closed = False
        self.closed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="browser-expert-chat")
        self._thread.start()

    def submit(
        self,
        coro_fn: Callable[[], Coroutine[Any, Any, None]],
        *,
        on_error: Callable[[Exception], None],
        on_cancel: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        cancel_kind: str | None = None,
    ) -> bool:
        """Submit one serialized operation, rejecting overlap and closed state."""
        with self._state_lock:
            if self._closed or self._busy:
                return False
            self._busy = True
            self._next_task_id += 1
            task_id = self._next_task_id
            self._busy_task_id = task_id
            self._busy_cancel_kind = cancel_kind
        self._tasks.put(
            _BrowserChatTask(
                task_id=task_id,
                coro_fn=coro_fn,
                on_error=on_error,
                on_cancel=on_cancel,
            )
        )
        return True

    def request_close(self, *, cancel_reason: str | None = None) -> None:
        """Stop accepting work and close resources after any active task."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            active_task = self._current_async_task
            loop = self._loop
            if cancel_reason is not None:
                self._cancel_reason = cancel_reason
                self._cancel_requested = True
        self._tasks.put(None)
        if active_task is not None and loop is not None and cancel_reason is not None:
            loop.call_soon_threadsafe(active_task.cancel)

    def cancel_current(self, reason: str, *, kind: str | None = None) -> bool:
        """Cancel the current coroutine on its owning event loop."""
        with self._state_lock:
            active_task = self._current_async_task
            loop = self._loop
            if self._closed or not self._busy or (kind is not None and self._busy_cancel_kind != kind):
                return False
            self._cancel_reason = reason
            self._cancel_requested = True
        if active_task is not None and loop is not None and not active_task.done():
            loop.call_soon_threadsafe(active_task.cancel)
        return True

    def mark_available(self) -> None:
        """Allow the next operation before publishing this task's terminal event."""
        with self._state_lock:
            if not self._closed and self._busy_task_id == self._current_task_id:
                self._busy = False
                self._busy_task_id = None
                self._busy_cancel_kind = None

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._state_lock:
            self._loop = loop
        try:
            while True:
                task = self._tasks.get()
                if task is None:
                    break
                if self._run_task(loop, task):
                    break
        finally:
            try:
                loop.run_until_complete(self._close_session())
            finally:
                with self._state_lock:
                    self._loop = None
                loop.close()
                self.closed.set()

    def _run_task(self, loop: asyncio.AbstractEventLoop, task: _BrowserChatTask) -> bool:
        """Run one queued coroutine and restore the worker state."""
        self._current_task_id = task.task_id
        async_task = loop.create_task(task.coro_fn())
        with self._state_lock:
            self._current_async_task = async_task
            cancel_requested = self._cancel_requested
        if cancel_requested:
            async_task.cancel()
        try:
            loop.run_until_complete(async_task)
        except asyncio.CancelledError:
            if task.on_cancel is not None:
                try:
                    loop.run_until_complete(task.on_cancel(self._cancel_reason))
                except Exception as exc:
                    logger.error(
                        "Browser expert-chat cancellation handler failed: %s",
                        type(exc).__name__,
                    )
        except Exception as exc:
            try:
                task.on_error(exc)
            except Exception:
                logger.exception("Browser expert-chat failure handler failed")
        finally:
            with self._state_lock:
                if self._busy_task_id == task.task_id:
                    self._busy = False
                    self._busy_task_id = None
                    self._busy_cancel_kind = None
                self._current_task_id = None
                self._current_async_task = None
                should_close = self._closed
        return should_close

    async def _close_session(self) -> None:
        if self.session is None or self._session_closed:
            return
        self._session_closed = True
        client = getattr(self.session, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning("Browser expert-chat client cleanup failed: %s", type(exc).__name__)
        cost_safety = getattr(self.session, "cost_safety", None)
        close_cost_session = getattr(cost_safety, "close_session", None)
        session_id = getattr(self.session, "session_id", None)
        if callable(close_cost_session) and session_id:
            try:
                close_cost_session(session_id)
            except Exception as exc:
                logger.warning("Browser expert-chat cost-session cleanup failed: %s", type(exc).__name__)


# Track active chat sessions for cancellation
_active_chats: dict[str, bool] = {}  # sid -> cancelled flag

# Track persistent per-socket workers for command and follow-up dispatch.
_active_sessions: dict[str, _BrowserChatState] = {}
_active_sessions_lock = threading.Lock()


def _get_browser_chat_state(sid: str) -> _BrowserChatState | None:
    with _active_sessions_lock:
        return _active_sessions.get(sid)


def _valid_subscription_job_id(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 128 and all(char.isalnum() or char in "-_.:" for char in value)


def _get_or_create_browser_chat_state(
    *,
    sid: str,
    expert_name: str,
    approved_budget: float,
    conversation_id: str | None,
    max_workers: int,
) -> _BrowserChatState | None:
    """Atomically enforce the process-wide browser worker ceiling."""
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
        raise ValueError("max browser chat workers must be a positive integer")
    with _active_sessions_lock:
        state = _active_sessions.get(sid)
        if state is not None:
            return state
        if len(_active_sessions) >= max_workers:
            return None
        state = _BrowserChatState(
            expert_name=expert_name,
            approved_budget=approved_budget,
            conversation_id=conversation_id,
        )
        _active_sessions[sid] = state
        return state


def _drop_browser_chat_state(
    sid: str,
    state: _BrowserChatState | None = None,
    *,
    cancel_reason: str | None = None,
) -> None:
    with _active_sessions_lock:
        current = _active_sessions.get(sid)
        if current is None or (state is not None and current is not state):
            return
        _active_sessions.pop(sid, None)
    _active_chats.pop(sid, None)
    current.request_close(cancel_reason=cancel_reason)


def _shutdown_browser_chat_states_for_tests() -> None:
    """Close all browser chat workers so unit tests do not leak daemon state."""
    with _active_sessions_lock:
        states = list(_active_sessions.values())
        _active_sessions.clear()
    _active_chats.clear()
    for state in states:
        state.request_close(cancel_reason="test_shutdown")
    for state in states:
        state.closed.wait(2.0)


def _chat_error_payload(message: str, *, code: str, retryable: bool) -> dict[str, Any]:
    return {"error": message, "error_code": code, "retryable": retryable}


def _socket_sid() -> str:
    return cast(str, cast(Any, flask_request).sid)


def register_socketio_events(
    socketio: _SocketIOEmitter,
    *,
    max_chat_budget: Callable[[], float] | None = None,
    api_key: Callable[[], str] | None = None,
    allow_unauthenticated_loopback: Callable[[], bool] | None = None,
    max_chat_workers: Callable[[], int] | None = None,
) -> None:
    """Register Socket.IO event handlers."""

    chat_budget_ceiling = max_chat_budget or (lambda: CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION)
    configured_api_key = api_key or (lambda: os.getenv("DEEPR_API_KEY", "").strip())
    unsafe_loopback_allowed = allow_unauthenticated_loopback or (
        lambda: env_flag("DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK")
    )
    worker_ceiling = max_chat_workers or (lambda: _MAX_BROWSER_CHAT_WORKERS)

    @socketio.on("connect")
    def handle_connect(auth: Any = None) -> bool | None:
        """Handle a client connection under the dashboard auth contract."""
        token = str(auth.get("token", "")) if isinstance(auth, dict) else ""
        if not token:
            token = presented_http_secret(flask_request.headers.get("Authorization", ""))
        decision = check_shared_secret(
            configured_secret=configured_api_key(),
            presented_secret=token,
            allow_unauthenticated_loopback=unsafe_loopback_allowed(),
            remote_addr=flask_request.remote_addr,
        )
        if decision is not SharedSecretDecision.ALLOW:
            logger.warning("WebSocket auth rejected: %s", decision.value)
            return False
        logger.info("Client connected")
        emit("connected", {"message": "Connected to Deepr API"})
        return None

    @socketio.on("disconnect")
    def handle_disconnect() -> None:
        """Handle client disconnection."""
        sid = _socket_sid()
        _drop_browser_chat_state(sid, cancel_reason="disconnect")
        logger.info("Client disconnected")

    @socketio.on("subscribe_jobs")
    def handle_subscribe_jobs(data: Any) -> None:
        """
        Subscribe to job updates.

        Client can subscribe to:
        - All jobs: {"scope": "all"}
        - Specific job: {"scope": "job", "job_id": "123"}
        """
        if not isinstance(data, dict):
            emit("subscription_error", {"error": "subscription must be an object"})
            return
        scope = data.get("scope", "all")

        if scope == "all":
            join_room("jobs")
            emit("subscribed", {"scope": "jobs", "message": "Subscribed to all jobs"})
            logger.info("Client subscribed to all jobs")

        elif scope == "job":
            job_id = data.get("job_id")
            if _valid_subscription_job_id(job_id):
                join_room(f"job_{job_id}")
                emit("subscribed", {"scope": "job", "job_id": job_id})
                logger.info(f"Client subscribed to job {job_id}")
            else:
                emit("subscription_error", {"error": "invalid job_id"})

    @socketio.on("unsubscribe_jobs")
    def handle_unsubscribe_jobs(data: Any) -> None:
        """Unsubscribe from job updates."""
        if not isinstance(data, dict):
            emit("subscription_error", {"error": "subscription must be an object"})
            return
        scope = data.get("scope", "all")

        if scope == "all":
            leave_room("jobs")
            emit("unsubscribed", {"scope": "jobs"})

        elif scope == "job":
            job_id = data.get("job_id")
            if _valid_subscription_job_id(job_id):
                leave_room(f"job_{job_id}")
                emit("unsubscribed", {"scope": "job", "job_id": job_id})
            else:
                emit("subscription_error", {"error": "invalid job_id"})

    @socketio.on("chat_start")
    def handle_chat_start(data: Any) -> None:
        """Start a streaming chat with an expert.

        The browser contract is API-only and requires a positive bounded
        budget plus two explicit metered-cost acknowledgements.

        Emits: chat_token, chat_status, chat_tool_start, chat_tool_end,
               chat_complete, chat_error
        """
        sid = _socket_sid()
        room = f"chat_{sid}"
        join_room(room)

        if not isinstance(data, dict):
            socketio.emit(
                "chat_error",
                _chat_error_payload(
                    "Browser expert chat requires a JSON object.",
                    code="invalid_chat_request",
                    retryable=False,
                ),
                room=room,
            )
            return

        try:
            expert_name = parse_browser_expert_name(data.get("expert_name"))
        except BrowserChatContractError as exc:
            socketio.emit("chat_error", exc.to_dict(), room=room)
            return
        message = data.get("message")
        if not isinstance(message, str) or not message.strip():
            socketio.emit(
                "chat_error",
                _chat_error_payload("message is required.", code="invalid_chat_request", retryable=False),
                room=room,
            )
            return

        try:
            parsed = parse_browser_expert_chat_request(data, max_budget=chat_budget_ceiling())
        except BrowserChatContractError as exc:
            socketio.emit("chat_error", exc.to_dict(), room=room)
            return

        state = _get_or_create_browser_chat_state(
            sid=sid,
            expert_name=expert_name,
            approved_budget=parsed.budget,
            conversation_id=parsed.session_id,
            max_workers=worker_ceiling(),
        )
        if state is None:
            socketio.emit(
                "chat_error",
                _chat_error_payload(
                    "Browser chat worker capacity is full.",
                    code="chat_worker_capacity",
                    retryable=True,
                ),
                room=room,
            )
            return

        if (
            state.expert_name != expert_name
            or state.approved_budget != parsed.budget
            or (
                parsed.session_id is not None
                and state.conversation_id is not None
                and parsed.session_id != state.conversation_id
            )
        ):
            socketio.emit(
                "chat_error",
                _chat_error_payload(
                    "Active chat settings cannot change. End the session and start a new one.",
                    code="chat_session_contract_mismatch",
                    retryable=False,
                ),
                room=room,
            )
            return

        turn_accounting = BrowserTurnAccounting(state.approved_budget)

        async def _run_turn() -> None:
            from deepr.experts.chat import start_chat_session
            from deepr.web.expert_chat_rest import restore_session_messages

            _active_chats[sid] = False
            if state.session is None:
                state.session = await start_chat_session(
                    expert_name,
                    budget=parsed.budget,
                    agentic=True,
                    quiet=True,
                )
                if state.conversation_id:
                    restore_session_messages(state.session, expert_name, state.conversation_id)

                def on_thought(thought: Any) -> None:
                    if _active_chats.get(sid) is not False:
                        return
                    socketio.emit(
                        "chat_thought",
                        {
                            "type": thought.thought_type.value,
                            "text": thought.public_text,
                            "confidence": thought.confidence,
                            "phase": thought.metadata.get("phase"),
                            "timestamp": thought.timestamp.isoformat(),
                        },
                        room=room,
                    )

                state.session.thought_stream.add_callback(on_thought)

                def on_compact_suggest(msg_count: int, token_count: int) -> None:
                    if _active_chats.get(sid) is not False:
                        return
                    socketio.emit(
                        "chat_compact_suggest",
                        {"message_count": msg_count, "token_estimate": token_count},
                        room=room,
                    )

                state.session._compact_callback = on_compact_suggest

            session = state.session
            session.chat_mode = parsed.chat_mode
            selected_model = session.select_model_for_turn(message.strip())
            turn_accounting.begin(session, selected_model)
            tool_timers: dict[str, float] = {}

            def on_token(text: str) -> None:
                if _active_chats.get(sid) is False:
                    socketio.emit("chat_token", {"content": text}, room=room)

            def on_status(status: str) -> None:
                if _active_chats.get(sid) is not False:
                    return
                socketio.emit("chat_status", {"status": status}, room=room)
                tool_keywords = {
                    "Searching knowledge base": "search_knowledge_base",
                    "Searching web": "standard_research",
                    "Deep research": "deep_research",
                    "Submitting deep research": "deep_research",
                }
                for keyword, tool_name in tool_keywords.items():
                    if keyword.lower() in status.lower() and tool_name not in tool_timers:
                        tool_timers[tool_name] = time.time()
                        socketio.emit(
                            "chat_tool_start",
                            {"tool": tool_name, "query": status},
                            room=room,
                        )

                if status.lower() == "thinking..." and tool_timers:
                    for tool_name, started_at in list(tool_timers.items()):
                        elapsed = int((time.time() - started_at) * 1000)
                        socketio.emit(
                            "chat_tool_end",
                            {"tool": tool_name, "elapsed_ms": elapsed},
                            room=room,
                        )
                    tool_timers.clear()

            turn_accounting.mark_dispatched()
            response = await session.send_message_streaming(
                message.strip(),
                token_callback=on_token,
                status_callback=on_status,
                selected_model=selected_model,
            )
            if getattr(session, "last_turn_failed", False):
                raise RuntimeError("Expert chat session reported a terminal turn failure")
            turn_accounting.release_success()
            state.conversation_id = session.save_conversation(state.conversation_id)
            tool_calls = [
                {"tool": item["step"], "query": item.get("query", "")[:200]}
                for item in session.reasoning_trace
                if item.get("step") in ALL_TOOL_NAMES
            ]
            state.mark_available()
            socketio.emit(
                "chat_complete",
                {
                    "id": uuid.uuid4().hex[:12],
                    "content": response,
                    "session_id": state.conversation_id,
                    "cost": round(session.cost_accumulated, 4),
                    "tool_calls": tool_calls,
                    "follow_ups": getattr(session, "_last_follow_ups", []),
                    "confidence": getattr(session, "_last_confidence", 0.9),
                    "mode": session.chat_mode.value,
                },
                room=room,
            )
            _active_chats.pop(sid, None)

        def on_turn_error(exc: Exception) -> None:
            logger.exception(
                "Browser expert-chat turn failed for %s: %s",
                expert_name,
                type(exc).__name__,
                exc_info=exc,
            )
            try:
                try:
                    turn_accounting.close_ambiguous(source="web.browser_chat.failure")
                except Exception as accounting_exc:
                    logger.error(
                        "Browser expert-chat failure left its durable reservation active: %s",
                        type(accounting_exc).__name__,
                    )
                from deepr.experts.chat_capacity import MeteredExpertChatDisabledError

                if isinstance(exc, MeteredExpertChatDisabledError):
                    payload = {
                        **_chat_error_payload(str(exc), code=exc.code, retryable=False),
                        **exc.to_dict(),
                    }
                else:
                    payload = _chat_error_payload(
                        "Expert chat failed. Start a new session and retry.",
                        code="chat_turn_failed",
                        retryable=True,
                    )
                socketio.emit("chat_error", payload, room=room)
            finally:
                _drop_browser_chat_state(sid, state)

        async def on_turn_cancel(reason: str) -> None:
            provider_status = "not_started"
            session = state.session
            if session is not None:
                provider_status = "transport_cancel_requested"
                cancel_provider_work = getattr(session, "cancel_inflight_provider_work", None)
                if callable(cancel_provider_work):
                    try:
                        result = cancel_provider_work()
                        if inspect.isawaitable(result):
                            result = await result
                        if isinstance(result, dict) and isinstance(result.get("status"), str):
                            provider_status = result["status"]
                    except Exception as cancel_exc:
                        provider_status = "provider_cancel_failed"
                        logger.warning(
                            "Browser expert-chat provider cancellation failed: %s",
                            type(cancel_exc).__name__,
                        )

            await state._close_session()
            try:
                cost_status = turn_accounting.close_ambiguous(source="web.browser_chat.cancelled")
            except Exception as accounting_exc:
                cost_status = "reservation_active"
                logger.error(
                    "Browser expert-chat cancellation left its durable reservation active: %s",
                    type(accounting_exc).__name__,
                )

            _drop_browser_chat_state(sid, state)
            if reason == "stop":
                socketio.emit(
                    "chat_cancelled",
                    {
                        "status": "cancelled",
                        "provider_cancel_status": provider_status,
                        "cost_status": cost_status,
                    },
                    room=room,
                )

        if not state.submit(
            _run_turn,
            on_error=on_turn_error,
            on_cancel=on_turn_cancel,
            cancel_kind="chat",
        ):
            socketio.emit(
                "chat_error",
                _chat_error_payload(
                    "A chat operation is already in progress.",
                    code="chat_turn_in_progress",
                    retryable=True,
                ),
                room=room,
            )

    @socketio.on("chat_stop")
    def handle_chat_stop(data: Any = None) -> None:
        """Request cancellation of the current chat stream."""
        sid = _socket_sid()
        state = _get_browser_chat_state(sid)
        if state is not None and state.cancel_current("stop", kind="chat"):
            _active_chats[sid] = True
            socketio.emit("chat_status", {"status": "Stopping..."}, room=f"chat_{sid}")
            logger.info("Chat cancellation requested for %s", sid)
            return
        emit(
            "chat_error",
            _chat_error_payload(
                "No chat turn is currently running.",
                code="chat_not_running",
                retryable=False,
            ),
        )

    @socketio.on("chat_end")
    def handle_chat_end(data: Any = None) -> None:
        """Explicitly end the persistent browser chat session."""
        sid = _socket_sid()
        _drop_browser_chat_state(sid, cancel_reason="end")
        socketio.emit("chat_ended", {"ended": True}, room=f"chat_{sid}")

    @socketio.on("chat_command")
    def handle_chat_command(data: Any) -> None:
        """Execute a slash command on the active session.

        Data: { command: str }  (e.g. "/status", "/ask", "/compact")
        Emits: chat_command_result
        """
        sid = _socket_sid()
        room = f"chat_{sid}"
        raw = data.get("command", "")

        state = _get_browser_chat_state(sid)
        if state is None or state.session is None:
            socketio.emit(
                "chat_command_result",
                {"success": False, "output": "No active chat session. Send a message first."},
                room=room,
            )
            return

        async def _dispatch() -> None:
            from deepr.experts.command_handlers import dispatch_command

            result = await dispatch_command(
                state.session,
                raw,
                {"web": True, "approved_budget": state.approved_budget},
            )

            if result is None:
                state.mark_available()
                socketio.emit(
                    "chat_command_result",
                    {"success": False, "output": f"Unknown command: {raw}"},
                    room=room,
                )
                return

            payload = {
                "success": result.success,
                "output": result.output,
                "clear_chat": result.clear_chat,
                "end_session": result.end_session,
                "data": result.data,
            }
            if result.mode_changed:
                payload["mode"] = result.mode_changed.value
            if result.export_content:
                payload["export_content"] = result.export_content

            if result.end_session:
                _drop_browser_chat_state(sid, state)
            else:
                state.mark_available()
            socketio.emit("chat_command_result", payload, room=room)

        def on_command_error(exc: Exception) -> None:
            logger.exception("Browser expert-chat command failed: %s", type(exc).__name__, exc_info=exc)
            try:
                socketio.emit(
                    "chat_command_result",
                    {"success": False, "output": "Command failed. Start a new chat session."},
                    room=room,
                )
            finally:
                _drop_browser_chat_state(sid, state)

        if not state.submit(_dispatch, on_error=on_command_error):
            socketio.emit(
                "chat_command_result",
                {"success": False, "output": "A chat operation is already in progress."},
                room=room,
            )

    @socketio.on("chat_compact")
    def handle_chat_compact(data: Any = None) -> None:
        """Run conversation compaction on the active session."""
        sid = _socket_sid()
        room = f"chat_{sid}"
        state = _get_browser_chat_state(sid)
        session = state.session if state is not None else None

        if state is None or session is None:
            socketio.emit("chat_compact_done", {"error": "No active session"}, room=room)
            return

        async def _compact() -> None:
            result = await session.compact_conversation()
            state.mark_available()
            socketio.emit("chat_compact_done", result, room=room)

        def on_compact_error(exc: Exception) -> None:
            logger.exception("Browser expert-chat compaction failed: %s", type(exc).__name__, exc_info=exc)
            try:
                socketio.emit(
                    "chat_compact_done",
                    {"error": "Compaction failed. Start a new chat session."},
                    room=room,
                )
            finally:
                _drop_browser_chat_state(sid, state)

        if not state.submit(_compact, on_error=on_compact_error):
            socketio.emit(
                "chat_compact_done",
                {"error": "A chat operation is already in progress."},
                room=room,
            )

    @socketio.on("chat_confirm_response")
    def handle_chat_confirm_response(data: Any) -> None:
        """User's response to an approval request.

        Data: { request_id: str, approved: bool }
        """
        sid = _socket_sid()
        state = _get_browser_chat_state(sid)
        if state is None or state.session is None:
            return

        request_id = data.get("request_id", "")
        approved = data.get("approved", False)

        session = state.session
        if hasattr(session, "_approval_manager") and session._approval_manager:
            session._approval_manager.respond(request_id, approved)


def emit_job_created(socketio: Any, job: Any) -> None:
    """Emit job created event."""
    try:
        socketio.emit("job_created", job.to_dict(), room="jobs")
        logger.info("Emitted job_created for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_created for %s", job.id)
        # Intent: best-effort event emission; one websocket delivery failure must not break job state tracking or the calling code path.


def emit_job_updated(socketio: Any, job: Any) -> None:
    """Emit job updated event."""
    try:
        data = job.to_dict()
        socketio.emit("job_updated", data, room="jobs")
        socketio.emit("job_updated", data, room=f"job_{job.id}")
        logger.info("Emitted job_updated for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_updated for %s", job.id)
        # Intent: best-effort event emission; one websocket delivery failure must not break job state tracking or the calling code path.


def emit_job_completed(socketio: Any, job: Any) -> None:
    """Emit job completed event."""
    try:
        data = job.to_dict()
        socketio.emit("job_completed", data, room="jobs")
        socketio.emit("job_completed", data, room=f"job_{job.id}")
        logger.info("Emitted job_completed for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_completed for %s", job.id)
        # Intent: best-effort event emission; one websocket delivery failure must not break job state tracking or the calling code path.


def emit_job_failed(socketio: Any, job: Any, error: Any) -> None:
    """Emit job failed event."""
    try:
        data = job.to_dict()
        data["error"] = error
        socketio.emit("job_failed", data, room="jobs")
        socketio.emit("job_failed", data, room=f"job_{job.id}")
        logger.info("Emitted job_failed for %s", job.id)
    except Exception:
        logger.exception("Failed to emit job_failed for %s", job.id)
        # Intent: best-effort event emission; one websocket delivery failure must not break job state tracking or the calling code path.


def emit_cost_warning(socketio: Any, warning: Any) -> None:
    """Emit cost warning event."""
    try:
        socketio.emit("cost_warning", warning, room="jobs")
        logger.warning("Emitted cost_warning: %s", warning)
    except Exception:
        logger.exception("Failed to emit cost_warning")
        # Intent: best-effort event emission; one websocket delivery failure must not break cost alerting for the user.


def emit_cost_exceeded(socketio: Any, exceeded: Any) -> None:
    """Emit cost exceeded event."""
    try:
        socketio.emit("cost_exceeded", exceeded, room="jobs")
        logger.error("Emitted cost_exceeded: %s", exceeded)
    except Exception:
        logger.exception("Failed to emit cost_exceeded")
        # Intent: best-effort event emission; one websocket delivery failure must not break cost alerting for the user.
