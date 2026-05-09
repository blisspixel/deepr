"""Lightweight A2A HTTP server with agent discovery and task endpoints.

Uses Python's built-in asyncio and a minimal ASGI-like handler pattern.
No heavy framework dependency — just async request/response handling.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from deepr.a2a.agent_card import AgentCardGenerator
from deepr.a2a.models import TaskRequest, TaskState
from deepr.a2a.task_manager import (
    InvalidTransitionError,
    TaskManager,
    TaskNotFoundError,
)

logger = logging.getLogger(__name__)


class A2AServer:
    """Lightweight A2A HTTP server.

    Endpoints:
    - GET  /.well-known/agent.json  — Agent card
    - POST /tasks                   — Create task
    - GET  /tasks/{id}              — Get task status
    - POST /tasks/{id}/cancel       — Cancel task
    - GET  /tasks/{id}/stream       — SSE progress stream

    Usage::

        server = A2AServer(card_generator=gen, task_manager=mgr)
        await server.start("localhost", 8080)
        # ... serve requests ...
        await server.stop()
    """

    def __init__(
        self,
        card_generator: AgentCardGenerator,
        task_manager: TaskManager,
    ) -> None:
        self._card_generator = card_generator
        self._task_manager = task_manager
        self._server: asyncio.Server | None = None
        self._running = False
        self._progress_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    async def start(self, host: str = "localhost", port: int = 8080) -> None:
        """Start the A2A HTTP server."""
        self._running = True
        self._server = await asyncio.start_server(self._handle_connection, host, port)
        logger.info("A2A server started on %s:%d", host, port)

    async def stop(self) -> None:
        """Gracefully stop the server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("A2A server stopped")

    def get_agent_card(self) -> dict[str, Any]:
        """Generate the agent card as a dict."""
        return self._card_generator.to_dict()

    async def handle_request(
        self,
        method: str,
        path: str,
        body: str = "",
    ) -> tuple[int, dict[str, Any]]:
        """Route and handle an HTTP request.

        Returns (status_code, response_body_dict).
        """
        if method == "GET" and path == "/.well-known/agent.json":
            return self._handle_agent_card()

        if method == "POST" and path == "/tasks":
            return self._handle_create_task(body)

        if method == "GET" and path.startswith("/tasks/"):
            parts = path.split("/")
            if len(parts) == 3:
                return self._handle_get_task(parts[2])
            if len(parts) == 4 and parts[3] == "stream":
                return self._handle_stream_info(parts[2])

        if method == "POST" and path.endswith("/cancel"):
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == "tasks":
                return self._handle_cancel_task(parts[2])

        return 404, {"error": "Not found"}

    def _handle_agent_card(self) -> tuple[int, dict[str, Any]]:
        """GET /.well-known/agent.json"""
        return 200, self.get_agent_card()

    def _handle_create_task(self, body: str) -> tuple[int, dict[str, Any]]:
        """POST /tasks"""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return 400, {"error": "Invalid JSON"}

        if not data.get("skill"):
            return 400, {"error": "Missing required field: skill"}
        if not data.get("input"):
            return 400, {"error": "Missing required field: input"}

        request = TaskRequest(
            skill=data["skill"],
            input=data["input"],
            input_mode=data.get("input_mode", "text/plain"),
            budget=data.get("budget"),
            metadata=data.get("metadata", {}),
        )

        task = self._task_manager.create_task(request, budget=request.budget)
        return 201, task.to_dict()

    def _handle_get_task(self, task_id: str) -> tuple[int, dict[str, Any]]:
        """GET /tasks/{id}"""
        task = self._task_manager.get_task(task_id)
        if task is None:
            return 404, {"error": f"Task not found: {task_id}"}
        return 200, task.to_dict()

    def _handle_cancel_task(self, task_id: str) -> tuple[int, dict[str, Any]]:
        """POST /tasks/{id}/cancel"""
        try:
            task = self._task_manager.transition(task_id, TaskState.CANCELLED)
            return 200, task.to_dict()
        except TaskNotFoundError:
            return 404, {"error": f"Task not found: {task_id}"}
        except InvalidTransitionError as e:
            return 409, {"error": str(e)}

    def _handle_stream_info(self, task_id: str) -> tuple[int, dict[str, Any]]:
        """GET /tasks/{id}/stream — returns stream metadata."""
        task = self._task_manager.get_task(task_id)
        if task is None:
            return 404, {"error": f"Task not found: {task_id}"}
        return 200, {
            "task_id": task_id,
            "state": task.state.value,
            "stream": "text/event-stream",
        }

    def emit_progress(self, task_id: str, progress: dict[str, Any]) -> None:
        """Emit a progress event for SSE subscribers."""
        queues = self._progress_queues.get(task_id, [])
        for queue in queues:
            queue.put_nowait(progress)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a raw TCP connection (minimal HTTP parsing)."""
        try:
            request_line = await reader.readline()
            if not request_line:
                return

            parts = request_line.decode().strip().split(" ")
            if len(parts) < 2:
                return

            method, path = parts[0], parts[1]

            # Read headers
            content_length = 0
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                header = line.decode().strip().lower()
                if header.startswith("content-length:"):
                    content_length = int(header.split(":")[1].strip())

            # Read body
            body = ""
            if content_length > 0:
                body_bytes = await reader.read(content_length)
                body = body_bytes.decode()

            status, response = await self.handle_request(method, path, body)
            response_json = json.dumps(response)

            http_response = (
                f"HTTP/1.1 {status} OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(response_json)}\r\n"
                f"\r\n"
                f"{response_json}"
            )
            writer.write(http_response.encode())
            await writer.drain()
        except Exception:
            logger.exception("Error handling A2A connection")
        finally:
            writer.close()
