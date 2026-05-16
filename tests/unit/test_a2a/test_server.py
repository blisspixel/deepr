"""Unit tests for A2A server.

Feature: mcp-client-agent-interop
Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import asyncio
import json

import pytest

from deepr.a2a.agent_card import AgentCardGenerator, ExpertInfo
from deepr.a2a.models import TaskState
from deepr.a2a.server import A2AServer
from deepr.a2a.task_manager import TaskManager


@pytest.fixture
def server() -> A2AServer:
    """Create an A2A server with test experts."""
    gen = AgentCardGenerator(version="1.0.0", url="http://localhost:8080")
    gen.register_expert(ExpertInfo(name="recon", description="DNS recon", domain="infrastructure"))
    gen.register_expert(ExpertInfo(name="analyst", description="Analysis", domain="strategic"))
    mgr = TaskManager()
    return A2AServer(card_generator=gen, task_manager=mgr)


class TestAgentCardEndpoint:
    """Test GET /.well-known/agent.json."""

    def test_returns_valid_json(self, server: A2AServer) -> None:
        """Agent card endpoint returns valid JSON with skills."""
        status, body = asyncio.get_event_loop().run_until_complete(
            server.handle_request("GET", "/.well-known/agent.json")
        )

        assert status == 200
        assert body["name"] == "deepr"
        assert body["version"] == "1.0.0"
        assert len(body["skills"]) == 2
        assert body["skills"][0]["name"] == "recon"
        assert body["skills"][1]["name"] == "analyst"

    def test_skills_have_required_fields(self, server: A2AServer) -> None:
        """Each skill has name, description, domain."""
        status, body = asyncio.get_event_loop().run_until_complete(
            server.handle_request("GET", "/.well-known/agent.json")
        )

        for skill in body["skills"]:
            assert "name" in skill
            assert "description" in skill
            assert "domain" in skill


class TestTaskCreation:
    """Test POST /tasks."""

    def test_creates_task_in_submitted_state(self, server: A2AServer) -> None:
        """Task creation returns submitted state."""
        payload = json.dumps({"skill": "recon", "input": "example.com"})
        status, body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", payload))

        assert status == 201
        assert body["state"] == "submitted"
        assert body["skill"] == "recon"
        assert body["input"] == "example.com"
        assert "id" in body

    def test_missing_skill_returns_400(self, server: A2AServer) -> None:
        """Missing skill field returns 400."""
        payload = json.dumps({"input": "test"})
        status, body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", payload))

        assert status == 400
        assert "skill" in body["error"]

    def test_invalid_json_returns_400(self, server: A2AServer) -> None:
        """Invalid JSON body returns 400."""
        status, body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", "not json{"))

        assert status == 400


class TestTaskRetrieval:
    """Test GET /tasks/{id}."""

    def test_get_existing_task(self, server: A2AServer) -> None:
        """Can retrieve a created task."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        status, body = asyncio.get_event_loop().run_until_complete(server.handle_request("GET", f"/tasks/{task_id}"))

        assert status == 200
        assert body["id"] == task_id

    def test_get_nonexistent_task_returns_404(self, server: A2AServer) -> None:
        """Nonexistent task returns 404."""
        status, body = asyncio.get_event_loop().run_until_complete(server.handle_request("GET", "/tasks/nonexistent"))

        assert status == 404


class TestTaskCancellation:
    """Test POST /tasks/{id}/cancel."""

    def test_cancel_submitted_task(self, server: A2AServer) -> None:
        """Can cancel a submitted task."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        status, body = asyncio.get_event_loop().run_until_complete(
            server.handle_request("POST", f"/tasks/{task_id}/cancel")
        )

        assert status == 200
        assert body["state"] == "cancelled"

    def test_cancel_completed_task_returns_409(self, server: A2AServer) -> None:
        """Cannot cancel a completed task."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        # Transition to working then completed
        server._task_manager.transition(task_id, TaskState.WORKING)
        server._task_manager.transition(task_id, TaskState.COMPLETED, result="done")

        status, body = asyncio.get_event_loop().run_until_complete(
            server.handle_request("POST", f"/tasks/{task_id}/cancel")
        )

        assert status == 409


class TestSSEStream:
    """Test GET /tasks/{id}/stream."""

    def test_stream_info_for_existing_task(self, server: A2AServer) -> None:
        """Stream endpoint returns stream metadata."""
        payload = json.dumps({"skill": "recon", "input": "test.com"})
        _, create_body = asyncio.get_event_loop().run_until_complete(server.handle_request("POST", "/tasks", payload))
        task_id = create_body["id"]

        status, body = asyncio.get_event_loop().run_until_complete(
            server.handle_request("GET", f"/tasks/{task_id}/stream")
        )

        assert status == 200
        assert body["task_id"] == task_id
        assert body["stream"] == "text/event-stream"

    def test_progress_emission(self, server: A2AServer) -> None:
        """Progress events can be emitted."""
        # Just verify emit doesn't crash
        server.emit_progress("test-id", {"progress": 50})
