"""Fail-closed browser expert-chat contract and session lifecycle regressions."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from flask_socketio import SocketIOTestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

from deepr.api.websockets import events
from deepr.experts.commands import ChatMode
from deepr.experts.profile import ExpertStore
from deepr.experts.router import ModelConfig
from deepr.web import app as web_app
from deepr.web.expert_chat_contract import (
    BrowserChatContractError,
    parse_browser_expert_chat_request,
    parse_browser_expert_name,
)
from deepr.web.expert_chat_rest import restore_session_messages


def _request(**overrides):
    payload = {
        "expert_name": "Budget Expert",
        "message": "What changed?",
        "backend": "api",
        "chat_mode": "research",
        "budget": 0.5,
        "allow_metered_api": True,
        "confirm_metered_cost": True,
    }
    payload.update(overrides)
    return payload


def _wait_for_event(client, name: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for packet in client.get_received():
            if packet["name"] == name:
                args = packet.get("args") or [{}]
                return args[0]
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for Socket.IO event: {name}")


class _FakeThoughtStream:
    def add_callback(self, callback) -> None:
        self.callback = callback


class _FakeSession:
    def __init__(self, *, fail_turn: bool = False, reported_failure: bool = False) -> None:
        self.chat_mode = ChatMode.RESEARCH
        self.thought_stream = _FakeThoughtStream()
        self.reasoning_trace = []
        self.cost_accumulated = 0.125
        self._last_follow_ups = []
        self._last_confidence = 0.8
        self._compact_callback = None
        self.messages = []
        self.turns: list[tuple[str, ChatMode]] = []
        self.fail_turn = fail_turn
        self.reported_failure = reported_failure
        self.last_turn_failed = False
        self.closed = threading.Event()
        self.client = SimpleNamespace(close=AsyncMock(side_effect=self.closed.set))
        self.chat_provider = "openai"
        self.chat_model = "test-model"
        self.selected_model = ModelConfig(provider="openai", model="test-model", cost_estimate=0.1)
        self.dispatched_models: list[ModelConfig] = []
        self.session_id = "chat_budget_expert_test"
        self.cost_safety = SimpleNamespace(close_session=MagicMock())
        self.cancel_inflight_provider_work = AsyncMock(
            return_value={"status": "transport_cancel_requested", "requested": 0, "failed": 0}
        )
        self.budget = 0.5
        self.cost_session = SimpleNamespace(budget_limit=0.5)

    def select_model_for_turn(self, message):
        return self.selected_model

    async def send_message_streaming(self, message, *, token_callback, status_callback, selected_model):
        self.dispatched_models.append(selected_model)
        self.turns.append((message, self.chat_mode))
        if self.fail_turn:
            raise RuntimeError("provider detail must not escape")
        self.last_turn_failed = self.reported_failure
        status_callback("Thinking...")
        token_callback("answer")
        if self.reported_failure:
            return "Error communicating with expert: provider detail must not escape"
        return f"answer: {message}"

    async def send_message(self, message, *, selected_model):
        self.dispatched_models.append(selected_model)
        self.turns.append((message, self.chat_mode))
        self.last_turn_failed = self.reported_failure
        if self.reported_failure:
            return "Error communicating with expert: provider detail must not escape"
        return f"answer: {message}"

    def save_conversation(self, session_id=None):
        return session_id or "conversation-test"

    async def compact_conversation(self):
        return {"original_messages": len(self.messages)}

    def get_session_summary(self):
        return {
            "expert_name": "Budget Expert",
            "messages_exchanged": len(self.turns),
            "cost_accumulated": self.cost_accumulated,
            "model": "test-model",
            "research_jobs_triggered": 0,
            "reasoning_steps": 0,
        }


class _BlockingSession(_FakeSession):
    def __init__(self) -> None:
        super().__init__()
        self.turn_started = threading.Event()
        self.turn_cancelled = threading.Event()
        self.token_callback = None
        self.save_conversation = MagicMock(side_effect=AssertionError("cancelled turns must not be saved"))

    async def send_message_streaming(self, message, *, token_callback, status_callback, selected_model):
        self.dispatched_models.append(selected_model)
        self.turns.append((message, self.chat_mode))
        self.token_callback = token_callback
        self.turn_started.set()
        token_callback("partial")
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.turn_cancelled.set()
            raise


@pytest.fixture
def chat_accounting(monkeypatch):
    reserve = MagicMock(
        side_effect=lambda **kwargs: SimpleNamespace(
            estimated_cost=kwargs["max_cost_per_job"],
            reservation_id=f"reservation-{reserve.call_count}",
        )
    )
    refund = MagicMock()
    settle = MagicMock()
    monkeypatch.setattr(events, "reserve_configured_cost_ceiling", reserve)
    monkeypatch.setattr(events, "refund_research_cost", refund)
    monkeypatch.setattr(events, "settle_research_cost", settle)
    return SimpleNamespace(reserve=reserve, refund=refund, settle=settle)


@pytest.fixture(autouse=True)
def _clean_browser_chat_states(monkeypatch, chat_accounting):
    monkeypatch.delenv("DEEPR_API_KEY", raising=False)
    monkeypatch.setattr(web_app, "_API_KEY", "")
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    events._shutdown_browser_chat_states_for_tests()
    yield
    events._shutdown_browser_chat_states_for_tests()


@pytest.fixture
def socket_client():
    client = web_app.socketio.test_client(web_app.app)
    assert isinstance(client, SocketIOTestClient)
    client.get_received()
    yield client
    if client.is_connected():
        client.disconnect()


def test_contract_rejects_non_api_backends_and_invalid_modes() -> None:
    with pytest.raises(BrowserChatContractError, match="Browser expert chat supports only backend=api"):
        parse_browser_expert_chat_request(_request(backend="local"), max_budget=1.0)

    with pytest.raises(BrowserChatContractError, match="chat_mode must be one of"):
        parse_browser_expert_chat_request(_request(chat_mode="turbo"), max_budget=1.0)


def test_saved_session_restore_keeps_only_chat_roles_and_rejects_unsafe_ids(tmp_path) -> None:
    store = ExpertStore(str(tmp_path))
    conversations = store.get_conversations_dir("Budget Expert")
    conversations.mkdir(parents=True)
    (conversations / "safe-session.json").write_text(
        '{"messages": ['
        '{"role": "system", "content": "hidden"},'
        '{"role": "user", "content": "question"},'
        '{"role": "assistant", "content": "answer"}'
        "]}",
        encoding="utf-8",
    )
    session = SimpleNamespace(messages=[])

    restore_session_messages(session, "Budget Expert", "safe-session", experts_dir=tmp_path)
    restore_session_messages(session, "Budget Expert", "../unsafe", experts_dir=tmp_path)

    assert session.messages == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]


def test_contract_rejects_unsafe_expert_names_and_oversized_session_ids() -> None:
    with pytest.raises(BrowserChatContractError, match="unsupported characters"):
        parse_browser_expert_name("../other-expert")

    with pytest.raises(BrowserChatContractError, match="session_id"):
        parse_browser_expert_chat_request(_request(session_id="a" * 129), max_budget=1.0)


@pytest.mark.parametrize("budget", [None, True, 0, -1, float("nan"), 1.01])
def test_contract_rejects_missing_nonfinite_or_out_of_bounds_budget(budget) -> None:
    with pytest.raises(BrowserChatContractError, match="budget"):
        parse_browser_expert_chat_request(_request(budget=budget), max_budget=1.0)


def test_socket_rejects_unacknowledged_metered_chat_before_session(socket_client, monkeypatch) -> None:
    start = AsyncMock(side_effect=AssertionError("provider session must not be constructed"))
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", start)

    socket_client.emit(
        "chat_start",
        _request(allow_metered_api=False, confirm_metered_cost=False),
    )

    error = _wait_for_event(socket_client, "chat_error")
    assert error["error_code"] == "metered_chat_not_confirmed"
    assert error["retryable"] is False
    start.assert_not_awaited()
    assert not events._active_sessions


def test_socket_rejects_unsafe_expert_identity_before_session(socket_client, monkeypatch) -> None:
    start = AsyncMock(side_effect=AssertionError("provider session must not be constructed"))
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", start)

    socket_client.emit("chat_start", _request(expert_name="../other-expert"))

    error = _wait_for_event(socket_client, "chat_error")
    assert error["error_code"] == "invalid_chat_expert_name"
    start.assert_not_awaited()


def test_socket_reuses_session_honors_modes_and_runs_commands(
    socket_client,
    monkeypatch,
    chat_accounting,
) -> None:
    session = _FakeSession()
    start = AsyncMock(return_value=session)
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", start)

    socket_client.emit("chat_start", _request(message="first", chat_mode="research"))
    first = _wait_for_event(socket_client, "chat_complete")
    assert first["mode"] == "research"
    assert len(events._active_sessions) == 1

    socket_client.emit("chat_command", {"command": "/ask"})
    command = _wait_for_event(socket_client, "chat_command_result")
    assert command["success"] is True
    assert command["mode"] == "ask"

    socket_client.emit("chat_start", _request(message="second", chat_mode="ask"))
    second = _wait_for_event(socket_client, "chat_complete")

    assert second["mode"] == "ask"
    assert session.turns == [("first", ChatMode.RESEARCH), ("second", ChatMode.ASK)]
    start.assert_awaited_once_with("Budget Expert", budget=0.5, agentic=True, quiet=True)
    assert len(events._active_sessions) == 1
    assert chat_accounting.reserve.call_count == 2
    assert chat_accounting.refund.call_count == 2
    chat_accounting.settle.assert_not_called()


def test_socket_rejects_budget_change_during_active_session(socket_client, monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request(message="first"))
    _wait_for_event(socket_client, "chat_complete")
    socket_client.emit("chat_start", _request(message="second", budget=0.75))

    error = _wait_for_event(socket_client, "chat_error")
    assert error["error_code"] == "chat_session_contract_mismatch"
    assert session.turns == [("first", ChatMode.RESEARCH)]


def test_socket_quit_closes_persistent_session(socket_client, monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())
    _wait_for_event(socket_client, "chat_complete")
    socket_client.emit("chat_command", {"command": "/quit"})

    result = _wait_for_event(socket_client, "chat_command_result")
    assert result["end_session"] is True
    assert session.closed.wait(2.0)
    assert not events._active_sessions


def test_socket_explicit_end_closes_persistent_session(socket_client, monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())
    _wait_for_event(socket_client, "chat_complete")
    socket_client.emit("chat_end", {})

    assert _wait_for_event(socket_client, "chat_ended") == {"ended": True}
    assert session.closed.wait(2.0)
    assert not events._active_sessions


def test_socket_stop_cancels_provider_turn_and_settles_before_ack(
    socket_client,
    monkeypatch,
    chat_accounting,
) -> None:
    session = _BlockingSession()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())
    assert session.turn_started.wait(2.0)
    socket_client.emit("chat_stop", {})

    cancelled = _wait_for_event(socket_client, "chat_cancelled")
    assert cancelled == {
        "status": "cancelled",
        "provider_cancel_status": "transport_cancel_requested",
        "cost_status": "settled_conservative",
    }
    assert session.turn_cancelled.wait(2.0)
    session.cancel_inflight_provider_work.assert_awaited_once_with()
    assert session.closed.is_set()
    session.cost_safety.close_session.assert_called_once_with(session.session_id)
    chat_accounting.settle.assert_called_once()
    assert chat_accounting.settle.call_args.kwargs == {
        "actual_cost": pytest.approx(0.375),
        "source": "web.browser_chat.cancelled",
        "actual_cost_reported": False,
        "settlement_metadata": {
            "settlement_basis": "conservative_unaccounted_ceiling",
            "known_cost_usd": 0.0,
            "unaccounted_ceiling_usd": pytest.approx(0.375),
        },
    }
    assert not events._active_sessions
    time.sleep(0.05)
    assert session.token_callback is not None
    session.token_callback("late-provider-token")
    assert not {"chat_complete", "chat_token"}.intersection(packet["name"] for packet in socket_client.get_received())
    session.save_conversation.assert_not_called()


def test_socket_stop_without_running_turn_is_explicit(socket_client) -> None:
    socket_client.emit("chat_stop", {})

    error = _wait_for_event(socket_client, "chat_error")
    assert error == {
        "error": "No chat turn is currently running.",
        "error_code": "chat_not_running",
        "retryable": False,
    }


def test_socket_disconnect_closes_persistent_session(socket_client, monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())
    _wait_for_event(socket_client, "chat_complete")
    socket_client.disconnect()

    assert session.closed.wait(2.0)
    assert not events._active_sessions


def test_socket_budget_command_cannot_exceed_browser_approval(socket_client, monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())
    _wait_for_event(socket_client, "chat_complete")

    socket_client.emit("chat_command", {"command": "/budget 0.75"})
    rejected = _wait_for_event(socket_client, "chat_command_result")
    assert rejected["success"] is False
    assert "browser-approved ceiling" in rejected["output"]
    assert session.budget == 0.5
    assert session.cost_session.budget_limit == 0.5

    socket_client.emit("chat_command", {"command": "/budget 0.25"})
    accepted = _wait_for_event(socket_client, "chat_command_result")
    assert accepted["success"] is True
    assert session.budget == 0.25
    assert session.cost_session.budget_limit == 0.25


def test_socket_terminal_turn_failure_drops_session_and_hides_provider_detail(socket_client, monkeypatch) -> None:
    session = _FakeSession(fail_turn=True)
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())

    error = _wait_for_event(socket_client, "chat_error")
    assert error == {
        "error": "Expert chat failed. Start a new session and retry.",
        "error_code": "chat_turn_failed",
        "retryable": True,
    }
    assert session.closed.wait(2.0)
    assert not events._active_sessions


def test_socket_reservation_uses_the_exact_routed_provider_and_model(
    socket_client,
    monkeypatch,
    chat_accounting,
) -> None:
    session = _FakeSession()
    session.chat_model = "qwen2.5-coder:32b"
    session.selected_model = ModelConfig(provider="openai", model="gpt-5.2", cost_estimate=0.1)
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request(message="Which model handles this?"))

    _wait_for_event(socket_client, "chat_complete")
    assert chat_accounting.reserve.call_args.kwargs["provider"] == "openai"
    assert chat_accounting.reserve.call_args.kwargs["model"] == "gpt-5.2"
    assert session.dispatched_models == [session.selected_model]


def test_socket_fails_closed_when_routed_dispatch_identity_is_unknown(
    socket_client,
    monkeypatch,
    chat_accounting,
) -> None:
    session = _FakeSession()
    session.selected_model = ModelConfig(provider="openai", model="unknown", cost_estimate=0.1)
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())

    error = _wait_for_event(socket_client, "chat_error")
    assert error["error_code"] == "chat_turn_failed"
    chat_accounting.reserve.assert_not_called()
    assert session.turns == []


def test_socket_reported_provider_failure_settles_hold_instead_of_completing(
    socket_client,
    monkeypatch,
    chat_accounting,
) -> None:
    session = _FakeSession(reported_failure=True)
    session.save_conversation = MagicMock()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))

    socket_client.emit("chat_start", _request())

    error = _wait_for_event(socket_client, "chat_error")
    assert error["error_code"] == "chat_turn_failed"
    assert "provider detail" not in error["error"]
    assert session.closed.wait(2.0)
    session.save_conversation.assert_not_called()
    chat_accounting.refund.assert_not_called()
    chat_accounting.settle.assert_called_once()
    assert chat_accounting.settle.call_args.kwargs["source"] == "web.browser_chat.failure"
    assert all(packet["name"] != "chat_complete" for packet in socket_client.get_received())


def test_rest_reported_provider_failure_settles_hold_without_saving(monkeypatch, chat_accounting) -> None:
    session = _FakeSession(reported_failure=True)
    session.save_conversation = MagicMock()
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", AsyncMock(return_value=session))
    flask_client = web_app.app.test_client()

    response = flask_client.post(
        "/api/experts/Budget%20Expert/chat",
        json=_request(message="REST question"),
    )

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}
    assert b"provider detail" not in response.data
    session.save_conversation.assert_not_called()
    chat_accounting.refund.assert_not_called()
    chat_accounting.settle.assert_called_once()
    assert chat_accounting.settle.call_args.kwargs["source"] == "web.browser_chat.rest.failure"


def test_rest_chat_requires_same_metered_contract_before_provider(monkeypatch):
    start = AsyncMock(side_effect=AssertionError("provider session must not be constructed"))
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", start)
    flask_client = web_app.app.test_client()

    response = flask_client.post(
        "/api/experts/Budget%20Expert/chat",
        json={"message": "hello", "backend": "api", "chat_mode": "ask", "budget": 0.5},
    )

    assert response.status_code == 402
    assert response.get_json()["error_code"] == "metered_chat_not_confirmed"
    start.assert_not_awaited()


def test_rest_chat_honors_explicit_budget_and_mode(monkeypatch) -> None:
    session = _FakeSession()
    start = AsyncMock(return_value=session)
    monkeypatch.setattr("deepr.experts.chat.start_chat_session", start)
    flask_client = web_app.app.test_client()

    response = flask_client.post(
        "/api/experts/Budget%20Expert/chat",
        json=_request(message="REST question", budget=0.25, chat_mode="advise"),
    )

    assert response.status_code == 200
    payload = response.get_json()["response"]
    assert payload["mode"] == "advise"
    assert session.turns == [("REST question", ChatMode.ADVISE)]
    assert session.closed.is_set()
    start.assert_awaited_once_with("Budget Expert", budget=0.25, agentic=True, quiet=True)
