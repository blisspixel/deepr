"""Integration test: A2A server endpoints.

Tests HTTP server lifecycle and endpoint responses.

Feature: mcp-client-agent-interop
Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5
"""

from __future__ import annotations

import asyncio
import json

import pytest

from deepr import __version__ as DEEPR_VERSION
from deepr.a2a.agent_card import AgentCardGenerator, ExpertInfo
from deepr.a2a.models import TaskState
from deepr.a2a.server import A2AServer
from deepr.a2a.task_manager import TaskManager


@pytest.fixture
def a2a_server() -> A2AServer:
    """Create an A2A server with test configuration."""
    gen = AgentCardGenerator(version=DEEPR_VERSION, url="http://localhost:9090")
    gen.register_expert(
        ExpertInfo(
            name="recon",
            description="DNS reconnaissance",
            domain="infrastructure",
        )
    )
    gen.register_expert(
        ExpertInfo(
            name="analyst",
            description="Market analysis",
            domain="strategic",
        )
    )
    mgr = TaskManager()
    return A2AServer(card_generator=gen, task_manager=mgr)


class TestServerLifecycle:
    """Test server start/stop."""

    def test_server_starts_and_stops(self, a2a_server: A2AServer) -> None:
        """Server can start and stop without errors."""

        async def _test() -> None:
            await a2a_server.start("localhost", 0)  # port 0 = OS picks
            assert a2a_server._running is True
            await a2a_server.stop()
            assert a2a_server._running is False

        asyncio.get_event_loop().run_until_complete(_test())


class TestAgentCardIntegration:
    """Test agent card endpoint integration."""

    def test_agent_card_returns_valid_json(self, a2a_server: A2AServer) -> None:
        """Agent card endpoint returns valid JSON with all skills."""
        status, body = asyncio.get_event_loop().run_until_complete(
            a2a_server.handle_request("GET", "/.well-known/agent.json")
        )

        assert status == 200
        # Verify it's valid JSON-serializable
        json_str = json.dumps(body)
        parsed = json.loads(json_str)

        assert parsed["name"] == "deepr"
        assert parsed["version"] == DEEPR_VERSION
        assert len(parsed["skills"]) == 2

        skill_names = {s["name"] for s in parsed["skills"]}
        assert "recon" in skill_names
        assert "analyst" in skill_names


class TestTaskLifecycleIntegration:
    """Test full task lifecycle: submit → working → completed."""

    def test_full_lifecycle(self, a2a_server: A2AServer) -> None:
        """Task goes through full lifecycle."""

        async def _test() -> None:
            # Create task
            payload = json.dumps(
                {
                    "skill": "recon",
                    "input": "example.com",
                    "budget": 5.0,
                }
            )
            status, body = await a2a_server.handle_request("POST", "/tasks", payload)
            assert status == 201
            task_id = body["id"]
            assert body["state"] == "submitted"

            # Transition to working
            a2a_server._task_manager.transition(task_id, TaskState.WORKING)

            # Get task - should be working
            status, body = await a2a_server.handle_request("GET", f"/tasks/{task_id}")
            assert status == 200
            assert body["state"] == "working"

            # Complete task
            a2a_server._task_manager.transition(
                task_id,
                TaskState.COMPLETED,
                result={"findings": ["dns data"]},
                cost=0.0,
                trace_id="trace-123",
            )

            # Get completed task
            status, body = await a2a_server.handle_request("GET", f"/tasks/{task_id}")
            assert status == 200
            assert body["state"] == "completed"
            assert body["cost"] == 0.0
            assert body["trace_id"] == "trace-123"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_cancellation_flow(self, a2a_server: A2AServer) -> None:
        """Task can be cancelled."""

        async def _test() -> None:
            payload = json.dumps({"skill": "analyst", "input": "test"})
            _, body = await a2a_server.handle_request("POST", "/tasks", payload)
            task_id = body["id"]

            status, body = await a2a_server.handle_request("POST", f"/tasks/{task_id}/cancel")
            assert status == 200
            assert body["state"] == "cancelled"

        asyncio.get_event_loop().run_until_complete(_test())


class TestSSEStreamIntegration:
    """Test SSE streaming for progress updates."""

    def test_stream_endpoint_returns_metadata(self, a2a_server: A2AServer) -> None:
        """Stream endpoint returns stream info."""

        async def _test() -> None:
            payload = json.dumps({"skill": "recon", "input": "test.com"})
            _, body = await a2a_server.handle_request("POST", "/tasks", payload)
            task_id = body["id"]

            status, body = await a2a_server.handle_request("GET", f"/tasks/{task_id}/stream")
            assert status == 200
            assert body["stream"] == "text/event-stream"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_progress_emission_no_crash(self, a2a_server: A2AServer) -> None:
        """Progress emission doesn't crash even without subscribers."""
        a2a_server.emit_progress("task-123", {"progress": 75, "phase": "analyzing"})


class TestErrorPaths:
    """Test error handling in A2A server endpoints."""

    def test_not_found_route(self, a2a_server: A2AServer) -> None:
        """Unknown routes return 404."""

        async def _test() -> None:
            status, body = await a2a_server.handle_request("GET", "/unknown")
            assert status == 404
            assert "error" in body

        asyncio.get_event_loop().run_until_complete(_test())

    def test_create_task_invalid_json(self, a2a_server: A2AServer) -> None:
        """Invalid JSON body returns 400."""

        async def _test() -> None:
            status, body = await a2a_server.handle_request("POST", "/tasks", "not json{")
            assert status == 400
            assert "Invalid JSON" in body["error"]

        asyncio.get_event_loop().run_until_complete(_test())

    def test_create_task_missing_skill(self, a2a_server: A2AServer) -> None:
        """Missing skill field returns 400."""

        async def _test() -> None:
            payload = json.dumps({"input": "test"})
            status, body = await a2a_server.handle_request("POST", "/tasks", payload)
            assert status == 400
            assert "skill" in body["error"]

        asyncio.get_event_loop().run_until_complete(_test())

    def test_create_task_missing_input(self, a2a_server: A2AServer) -> None:
        """Missing input field returns 400."""

        async def _test() -> None:
            payload = json.dumps({"skill": "recon"})
            status, body = await a2a_server.handle_request("POST", "/tasks", payload)
            assert status == 400
            assert "input" in body["error"]

        asyncio.get_event_loop().run_until_complete(_test())

    def test_get_nonexistent_task(self, a2a_server: A2AServer) -> None:
        """Getting a non-existent task returns 404."""

        async def _test() -> None:
            status, body = await a2a_server.handle_request("GET", "/tasks/nonexistent")
            assert status == 404
            assert "not found" in body["error"].lower()

        asyncio.get_event_loop().run_until_complete(_test())

    def test_cancel_nonexistent_task(self, a2a_server: A2AServer) -> None:
        """Cancelling a non-existent task returns 404."""

        async def _test() -> None:
            status, _body = await a2a_server.handle_request("POST", "/tasks/nonexistent/cancel")
            assert status == 404

        asyncio.get_event_loop().run_until_complete(_test())

    def test_cancel_completed_task_returns_409(self, a2a_server: A2AServer) -> None:
        """Cancelling a completed task returns 409 conflict."""

        async def _test() -> None:
            payload = json.dumps({"skill": "recon", "input": "test.com"})
            _, body = await a2a_server.handle_request("POST", "/tasks", payload)
            task_id = body["id"]

            # Transition to working then completed
            a2a_server._task_manager.transition(task_id, TaskState.WORKING)
            a2a_server._task_manager.transition(task_id, TaskState.COMPLETED, result={"data": "done"})

            # Try to cancel completed task
            status, body = await a2a_server.handle_request("POST", f"/tasks/{task_id}/cancel")
            assert status == 409

        asyncio.get_event_loop().run_until_complete(_test())

    def test_stream_nonexistent_task(self, a2a_server: A2AServer) -> None:
        """Stream endpoint for non-existent task returns 404."""

        async def _test() -> None:
            status, _body = await a2a_server.handle_request("GET", "/tasks/nonexistent/stream")
            assert status == 404

        asyncio.get_event_loop().run_until_complete(_test())

    def test_get_agent_card_directly(self, a2a_server: A2AServer) -> None:
        """get_agent_card() returns dict with expected fields."""
        card = a2a_server.get_agent_card()
        assert card["name"] == "deepr"
        assert "skills" in card
        assert len(card["skills"]) == 2
