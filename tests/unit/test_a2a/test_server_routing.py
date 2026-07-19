"""Tests for deepr.a2a.server.A2AServer request routing + auth gate.

handle_request is exercised directly (no socket), covering the public agent
card, task create/get/cancel/stream, the 404/400/409 error paths, and the
Bearer-token auth gate added for the unauthenticated-A2A finding.
"""

from __future__ import annotations

import json

import pytest

from deepr.a2a.agent_card import AgentCardGenerator
from deepr.a2a.server import A2AServer
from deepr.a2a.task_manager import TaskManager


def _server(auth_token: str | None = None) -> A2AServer:
    return A2AServer(
        AgentCardGenerator(name="deepr-test"),
        TaskManager(),
        auth_token=auth_token,
        allow_unauthenticated_loopback=auth_token is None,
    )


def _create_body(skill: str = "Tech Expert", text: str = "analyze") -> str:
    return json.dumps({"skill": skill, "input": text})


class TestAgentCard:
    @pytest.mark.asyncio
    async def test_agent_card_public(self):
        status, body = await _server().handle_request("GET", "/.well-known/agent.json")
        assert status == 200
        assert body["name"] == "deepr-test"

    def test_get_agent_card_dict(self):
        card = _server().get_agent_card()
        assert "name" in card and "skills" in card


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_returns_201_submitted(self):
        status, body = await _server().handle_request("POST", "/tasks", _create_body())
        assert status == 201
        assert body["state"] == "submitted"
        assert body["skill"] == "Tech Expert"

    @pytest.mark.asyncio
    async def test_missing_skill_400(self):
        status, body = await _server().handle_request("POST", "/tasks", json.dumps({"input": "x"}))
        assert status == 400
        assert "skill" in body["error"]

    @pytest.mark.asyncio
    async def test_missing_input_400(self):
        status, _ = await _server().handle_request("POST", "/tasks", json.dumps({"skill": "x"}))
        assert status == 400

    @pytest.mark.asyncio
    async def test_invalid_json_400(self):
        status, body = await _server().handle_request("POST", "/tasks", "{ not json")
        assert status == 400
        assert body["error"] == "Invalid JSON"


class TestGetCancelStream:
    @pytest.mark.asyncio
    async def test_get_task_roundtrip(self):
        srv = _server()
        _, created = await srv.handle_request("POST", "/tasks", _create_body())
        tid = created["id"]
        status, body = await srv.handle_request("GET", f"/tasks/{tid}")
        assert status == 200
        assert body["id"] == tid
        assert body["schema_version"] == "deepr-a2a-task-v1"

    @pytest.mark.asyncio
    async def test_malformed_task_payload_fails_closed(self):
        srv = _server()
        _, created = await srv.handle_request("POST", "/tasks", _create_body())
        task = srv._task_manager.get_task(created["id"])
        assert task is not None
        task.to_dict = lambda: {"schema_version": "deepr-a2a-task-v1"}

        status, body = await srv.handle_request("GET", f"/tasks/{created['id']}")

        assert status == 500
        assert body["error_code"] == "SCHEMA_VALIDATION_FAILED"
        assert body["schema_version"] == "deepr-a2a-task-v1"
        assert any("kind" in error for error in body["schema_errors"])

    @pytest.mark.asyncio
    async def test_get_unknown_task_404(self):
        status, _ = await _server().handle_request("GET", "/tasks/nope")
        assert status == 404

    @pytest.mark.asyncio
    async def test_cancel_submitted_task(self):
        srv = _server()
        _, created = await srv.handle_request("POST", "/tasks", _create_body())
        status, body = await srv.handle_request("POST", f"/tasks/{created['id']}/cancel")
        assert status == 200
        assert body["state"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_unknown_404(self):
        status, _ = await _server().handle_request("POST", "/tasks/ghost/cancel")
        assert status == 404

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_409(self):
        srv = _server()
        _, created = await srv.handle_request("POST", "/tasks", _create_body())
        tid = created["id"]
        await srv.handle_request("POST", f"/tasks/{tid}/cancel")
        status, _ = await srv.handle_request("POST", f"/tasks/{tid}/cancel")
        assert status == 409

    @pytest.mark.asyncio
    async def test_stream_info_and_unknown(self):
        srv = _server()
        _, created = await srv.handle_request("POST", "/tasks", _create_body())
        status, body = await srv.handle_request("GET", f"/tasks/{created['id']}/stream")
        assert status == 200
        assert body["stream"] == "text/event-stream"
        status2, _ = await srv.handle_request("GET", "/tasks/ghost/stream")
        assert status2 == 404

    @pytest.mark.asyncio
    async def test_unknown_route_404(self):
        status, _ = await _server().handle_request("GET", "/random")
        assert status == 404


class TestAuthGate:
    @pytest.mark.asyncio
    async def test_card_public_even_with_token(self):
        status, _ = await _server(auth_token="secret").handle_request("GET", "/.well-known/agent.json")
        assert status == 200

    @pytest.mark.asyncio
    async def test_create_requires_token(self):
        srv = _server(auth_token="secret")
        status, _ = await srv.handle_request("POST", "/tasks", _create_body())
        assert status == 401

    @pytest.mark.asyncio
    async def test_create_bad_token_401(self):
        srv = _server(auth_token="secret")
        status, _ = await srv.handle_request("POST", "/tasks", _create_body(), auth_header="Bearer wrong")
        assert status == 401

    @pytest.mark.asyncio
    async def test_create_good_token_201(self):
        srv = _server(auth_token="secret")
        status, _ = await srv.handle_request("POST", "/tasks", _create_body(), auth_header="Bearer secret")
        assert status == 201


class TestStartGuard:
    @pytest.mark.asyncio
    async def test_refuses_public_bind_without_token(self, monkeypatch):
        monkeypatch.delenv("DEEPR_A2A_ALLOW_PUBLIC", raising=False)
        with pytest.raises(RuntimeError):
            await _server().start(host="0.0.0.0", port=0)

    @pytest.mark.asyncio
    async def test_empty_host_treated_as_public(self, monkeypatch):
        monkeypatch.delenv("DEEPR_A2A_ALLOW_PUBLIC", raising=False)
        with pytest.raises(RuntimeError):
            await _server().start(host="", port=0)


class TestProgress:
    def test_emit_progress_no_subscribers_is_noop(self):
        _server().emit_progress("any", {"phase": "x"})  # must not raise
