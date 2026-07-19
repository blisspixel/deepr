"""Unit tests for A2A server.

Feature: mcp-client-agent-interop
Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import asyncio
import json

import pytest

from deepr.a2a.agent_card import AgentCardGenerator, ExpertInfo
from deepr.a2a.constants import CONSULT_SKILL_NAME
from deepr.a2a.models import TaskState
from deepr.a2a.server import A2AServer
from deepr.a2a.task_manager import TaskManager
from deepr.mcp.consult_validation import build_offline_consult_fixture


@pytest.fixture
def server() -> A2AServer:
    """Create an A2A server with test experts."""
    gen = AgentCardGenerator(version="1.0.0", url="http://localhost:8080")
    gen.register_expert(ExpertInfo(name="recon", description="DNS recon", domain="infrastructure"))
    gen.register_expert(ExpertInfo(name="analyst", description="Analysis", domain="strategic"))
    mgr = TaskManager()
    return A2AServer(
        card_generator=gen,
        task_manager=mgr,
        allow_unauthenticated_loopback=True,
    )


class TestAgentCardEndpoint:
    """Test GET /.well-known/agent.json."""

    def test_returns_valid_json(self, server: A2AServer) -> None:
        """Agent card endpoint returns valid JSON with skills."""
        status, body = asyncio.run(server.handle_request("GET", "/.well-known/agent-card.json"))

        assert status == 200
        assert body["name"] == "deepr"
        assert body["version"] == "1.0.0"
        assert len(body["skills"]) == 3
        assert body["skills"][0]["name"] == "recon"
        assert body["skills"][1]["name"] == "analyst"
        assert body["skills"][2]["name"] == CONSULT_SKILL_NAME

    def test_legacy_agent_card_path_still_works(self, server: A2AServer) -> None:
        """Legacy Agent Card path remains compatible."""
        status, body = asyncio.run(server.handle_request("GET", "/.well-known/agent.json"))

        assert status == 200
        assert body["skills"][2]["name"] == CONSULT_SKILL_NAME

    def test_skills_have_required_fields(self, server: A2AServer) -> None:
        """Each skill has name, description, domain."""
        _status, body = asyncio.run(server.handle_request("GET", "/.well-known/agent.json"))

        for skill in body["skills"]:
            assert "name" in skill
            assert "description" in skill
            assert "domain" in skill


class TestTaskCreation:
    """Test POST /tasks."""

    def test_creates_task_in_submitted_state(self, server: A2AServer) -> None:
        """Task creation returns submitted state."""
        payload = json.dumps({"skill": "recon", "input": "example.com"})
        status, body = asyncio.run(server.handle_request("POST", "/tasks", payload))

        assert status == 201
        assert body["state"] == "submitted"
        assert body["skill"] == "recon"
        assert body["input"] == "example.com"
        assert body["schema_version"] == "deepr-a2a-task-v1"
        assert body["kind"] == "deepr.a2a.task"
        assert body["contract"]["cost_field"] == "cost"
        assert "id" in body

    def test_missing_skill_returns_400(self, server: A2AServer) -> None:
        """Missing skill field returns 400."""
        payload = json.dumps({"input": "test"})
        status, body = asyncio.run(server.handle_request("POST", "/tasks", payload))

        assert status == 400
        assert "skill" in body["error"]

    def test_invalid_json_returns_400(self, server: A2AServer) -> None:
        """Invalid JSON body returns 400."""
        status, _body = asyncio.run(server.handle_request("POST", "/tasks", "not json{"))

        assert status == 400

    def test_consult_task_completes_with_artifact(self, server: A2AServer, monkeypatch: pytest.MonkeyPatch) -> None:
        """Consult skill maps the consult contract into A2A task artifacts."""
        fixture = build_offline_consult_fixture(experts=("Contract Expert",))

        async def fake_consult_experts_tool(**kwargs):
            assert kwargs["question"] == "Map the math and plan."
            assert kwargs["experts"] == ["Contract Expert"]
            assert kwargs["synthesis_backend"] == "local"
            assert kwargs["budget"] == 0.0
            return fixture

        monkeypatch.setattr("deepr.a2a.consult_tasks.consult_experts_tool", fake_consult_experts_tool)
        payload = json.dumps(
            {
                "skill": CONSULT_SKILL_NAME,
                "input": "Map the math and plan.",
                "budget": 0,
                "metadata": {"experts": ["Contract Expert"], "synthesis_backend": "local"},
            }
        )
        status, body = asyncio.run(server.handle_request("POST", "/tasks", payload))

        assert status == 201
        assert body["state"] == "completed"
        assert body["result"]["consult_schema_version"] == "deepr-consult-v1"
        assert body["result"]["artifact_id"] == body["artifacts"][0]["artifact_id"]
        assert body["artifacts"][0]["name"] == "deepr-consult-v1"
        assert body["artifacts"][0]["content"]["collaboration"]["dissent_handling"]["dissent_preserved"] is True
        assert body["trace_id"] == fixture["trace"]["trace_id"]

    def test_consult_task_blocks_api_without_explicit_metered_approval(self, server: A2AServer) -> None:
        """A2A consult cannot fall into API synthesis unless explicitly approved."""
        payload = json.dumps(
            {
                "skill": CONSULT_SKILL_NAME,
                "input": "Use a paid model.",
                "budget": 1,
                "metadata": {"synthesis_backend": "api"},
            }
        )
        status, body = asyncio.run(server.handle_request("POST", "/tasks", payload))

        assert status == 201
        assert body["state"] == "failed"
        assert body["error"]["error_code"] == "METERED_API_NOT_APPROVED"
        assert body["cost"] == 0.0

    @pytest.mark.parametrize(
        ("synthesis_status", "error_code", "result_status"),
        [
            ("failed", "CONSULT_FAILED", "incomplete"),
            ("truncated", "CONSULT_INCOMPLETE", "incomplete"),
        ],
    )
    def test_consult_terminal_failure_preserves_artifact_trace_and_cost(
        self,
        server: A2AServer,
        monkeypatch: pytest.MonkeyPatch,
        synthesis_status: str,
        error_code: str,
        result_status: str,
    ) -> None:
        fixture = build_offline_consult_fixture(experts=("Contract Expert",))
        fixture["synthesis_status"] = synthesis_status
        fixture["synthesis_error_type"] = "OutputLimit" if synthesis_status == "truncated" else "ProviderFailure"
        fixture["synthesis_stop_reason"] = "length" if synthesis_status == "truncated" else "provider_error"
        fixture["cost_usd"] = 0.0000125

        async def fake_consult_experts_tool(**_kwargs):
            return fixture

        monkeypatch.setattr("deepr.a2a.consult_tasks.consult_experts_tool", fake_consult_experts_tool)
        payload = json.dumps(
            {
                "skill": CONSULT_SKILL_NAME,
                "input": "Preserve a failed consult artifact.",
                "budget": 1,
                "metadata": {
                    "experts": ["Contract Expert"],
                    "synthesis_backend": "api",
                    "allow_metered_api": True,
                    "confirm_metered_cost": True,
                },
            }
        )

        status, body = asyncio.run(server.handle_request("POST", "/tasks", payload))

        assert status == 201
        assert body["state"] == "failed"
        assert body["error"]["error_code"] == error_code
        assert body["error"]["synthesis_status"] == synthesis_status
        assert body["result"]["status"] == result_status
        assert body["result"]["synthesis_status"] == synthesis_status
        assert body["cost"] == 0.0000125
        assert body["result"]["cost_usd"] == 0.0000125
        assert body["trace_id"] == fixture["trace"]["trace_id"]
        assert body["artifacts"][0]["content"] == fixture


class TestTaskRetrieval:
    """Test GET /tasks/{id}."""

    def test_get_existing_task(self, server: A2AServer) -> None:
        """Can retrieve a created task."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.run(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        status, body = asyncio.run(server.handle_request("GET", f"/tasks/{task_id}"))

        assert status == 200
        assert body["id"] == task_id
        assert body["schema_version"] == "deepr-a2a-task-v1"

    def test_get_nonexistent_task_returns_404(self, server: A2AServer) -> None:
        """Nonexistent task returns 404."""
        status, _body = asyncio.run(server.handle_request("GET", "/tasks/nonexistent"))

        assert status == 404


class TestTaskCancellation:
    """Test POST /tasks/{id}/cancel."""

    def test_cancel_submitted_task(self, server: A2AServer) -> None:
        """Can cancel a submitted task."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.run(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        status, body = asyncio.run(server.handle_request("POST", f"/tasks/{task_id}/cancel"))

        assert status == 200
        assert body["state"] == "cancelled"
        assert body["kind"] == "deepr.a2a.task"

    def test_cancel_completed_task_returns_409(self, server: A2AServer) -> None:
        """Cannot cancel a completed task."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.run(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        # Transition to working then completed
        server._task_manager.transition(task_id, TaskState.WORKING)
        server._task_manager.transition(task_id, TaskState.COMPLETED, result="done")

        status, _body = asyncio.run(server.handle_request("POST", f"/tasks/{task_id}/cancel"))

        assert status == 409

    @pytest.mark.asyncio
    async def test_cancel_active_consult_cancels_underlying_coroutine(
        self,
        server: A2AServer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocking_consult(**_kwargs):
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        monkeypatch.setattr(
            "deepr.a2a.consult_tasks.consult_experts_tool",
            blocking_consult,
        )
        payload = json.dumps(
            {
                "skill": CONSULT_SKILL_NAME,
                "input": "Wait for cancellation.",
                "budget": 0,
                "metadata": {"synthesis_backend": "local"},
            }
        )
        create_call = asyncio.create_task(
            server.handle_request("POST", "/tasks", payload)
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        active = server._task_manager.list_tasks(TaskState.WORKING)
        assert len(active) == 1

        status, body = await server.handle_request(
            "POST",
            f"/tasks/{active[0].id}/cancel",
        )
        create_status, create_body = await asyncio.wait_for(create_call, timeout=1)

        assert status == 200
        assert body["state"] == "cancelled"
        assert create_status == 200
        assert create_body["state"] == "cancelled"
        assert cancelled.is_set()
        assert not server._active_runs


class TestTaskCapacity:
    @pytest.mark.asyncio
    async def test_active_task_and_input_limits_fail_closed(self) -> None:
        manager = TaskManager(
            max_active_tasks=1,
            max_active_input_bytes=16,
            max_task_input_bytes=8,
        )
        server = A2AServer(
            AgentCardGenerator(name="bounded"),
            manager,
            allow_unauthenticated_loopback=True,
        )

        first_status, _ = await server.handle_request(
            "POST",
            "/tasks",
            json.dumps({"skill": "recon", "input": "12345678"}),
        )
        active_status, active_body = await server.handle_request(
            "POST",
            "/tasks",
            json.dumps({"skill": "recon", "input": "x"}),
        )

        assert first_status == 201
        assert active_status == 429
        assert active_body["error_code"] == "TASK_CAPACITY_EXCEEDED"

        separate = A2AServer(
            AgentCardGenerator(name="bounded"),
            TaskManager(max_task_input_bytes=8),
            allow_unauthenticated_loopback=True,
        )
        large_status, large_body = await separate.handle_request(
            "POST",
            "/tasks",
            json.dumps({"skill": "recon", "input": "123456789"}),
        )
        assert large_status == 413
        assert large_body["error_code"] == "TASK_CAPACITY_EXCEEDED"


class TestSSEStream:
    """Test GET /tasks/{id}/stream."""

    def test_stream_info_for_existing_task(self, server: A2AServer) -> None:
        """Stream endpoint returns stream metadata."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.run(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        status, body = asyncio.run(server.handle_request("GET", f"/tasks/{task_id}/stream"))

        assert status == 200
        assert body["task_id"] == task_id
        assert body["stream"] == "text/event-stream"

    def test_progress_emission(self, server: A2AServer) -> None:
        """Progress events can be emitted."""
        # Just verify emit doesn't crash
        server.emit_progress("test-id", {"progress": 50})
