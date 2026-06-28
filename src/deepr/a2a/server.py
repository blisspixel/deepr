"""Lightweight A2A HTTP server with agent discovery and task endpoints.

Uses Python's built-in asyncio and a minimal ASGI-like handler pattern.
No heavy framework dependency - just async request/response handling.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from typing import Any

from deepr.a2a.agent_card import AgentCardGenerator
from deepr.a2a.consult_tasks import is_consult_skill, run_consult_task
from deepr.a2a.models import Task, TaskRequest, TaskState
from deepr.a2a.output_contracts import (
    A2A_TASK_OUTPUT_CONTRACT,
    schema_validation_error,
    validate_a2a_output,
)
from deepr.a2a.task_manager import (
    InvalidTransitionError,
    TaskManager,
    TaskNotFoundError,
)

logger = logging.getLogger(__name__)

# Caller-supplied request bodies are capped to prevent a single malicious
# Content-Length from buffering arbitrary memory.
_MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB


class A2AServer:
    """Lightweight A2A HTTP server.

    Endpoints:
    - GET  /.well-known/agent.json  - Agent card
    - POST /tasks                   - Create task
    - GET  /tasks/{id}              - Get task status
    - POST /tasks/{id}/cancel       - Cancel task
    - GET  /tasks/{id}/stream       - SSE progress stream

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
        auth_token: str | None = None,
    ) -> None:
        self._card_generator = card_generator
        self._task_manager = task_manager
        self._server: asyncio.Server | None = None
        self._running = False
        self._progress_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        # Bearer token required for state-changing endpoints. Reads
        # ``DEEPR_A2A_TOKEN`` when not provided explicitly. Agent-card
        # discovery (``GET /.well-known/agent.json``) and task-status GETs
        # remain public so peers can introspect skills without auth.
        self._auth_token = auth_token if auth_token is not None else os.getenv("DEEPR_A2A_TOKEN", "")

    async def start(self, host: str = "localhost", port: int = 8080) -> None:
        """Start the A2A HTTP server."""
        # Refuse to start on a non-loopback bind without an auth token -
        # ``POST /tasks`` triggers paid expert work via the underlying
        # task manager, so an anonymous reachable endpoint is a
        # spend-amplification primitive.
        #
        # NB: ``asyncio.start_server(host='')`` (and ``host=None``) bind
        # to ALL interfaces, not loopback only. The earlier guard
        # mistakenly listed ``""`` alongside ``localhost`` / ``127.0.0.1``
        # / ``::1``, so a caller passing ``host=''`` bypassed the
        # public-bind refusal entirely. Empty/None hosts must be treated
        # as public binds.
        loopback = host in ("localhost", "127.0.0.1", "::1")
        allow_public = os.getenv("DEEPR_A2A_ALLOW_PUBLIC", "").lower() in ("1", "true", "yes")
        if not loopback and not self._auth_token and not allow_public:
            raise RuntimeError(
                "A2A server refusing to bind non-loopback host without DEEPR_A2A_TOKEN. "
                f"Set DEEPR_A2A_TOKEN, use host='localhost', or set DEEPR_A2A_ALLOW_PUBLIC=1 "
                f"(host={host!r})."
            )

        self._running = True
        self._server = await asyncio.start_server(self._handle_connection, host, port)
        logger.info(
            "A2A server started on %s:%d (auth=%s)",
            host,
            port,
            "required" if self._auth_token else "disabled (loopback-only)",
        )

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
        auth_header: str = "",
    ) -> tuple[int, dict[str, Any]]:
        """Route and handle an HTTP request.

        Returns (status_code, response_body_dict). ``auth_header`` is the
        raw value of the ``Authorization`` header (``"Bearer …"``); when
        an auth token is configured it must match for any state-changing
        endpoint (``POST /tasks``, ``POST /tasks/{id}/cancel``).
        """
        # Public endpoints - discovery and read-only status.
        if method == "GET" and path == "/.well-known/agent.json":
            return self._handle_agent_card()

        # Auth gate for everything else when a token is configured.
        if self._auth_token:
            provided = ""
            if auth_header.startswith("Bearer "):
                provided = auth_header[7:].strip()
            ok = False
            if provided:
                try:
                    ok = hmac.compare_digest(provided, self._auth_token)
                except TypeError:
                    ok = False
            if not ok:
                return 401, {"error": "Unauthorized"}

        if method == "POST" and path == "/tasks":
            return await self._handle_create_task(body)

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

    async def _handle_create_task(self, body: str) -> tuple[int, dict[str, Any]]:
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
        if is_consult_skill(request.skill):
            task = self._task_manager.transition(task.id, TaskState.WORKING)
            outcome = await run_consult_task(request)
            if outcome.ok:
                task = self._task_manager.transition(
                    task.id,
                    TaskState.COMPLETED,
                    result=outcome.result,
                    cost=outcome.cost,
                    trace_id=outcome.trace_id,
                    artifacts=outcome.artifacts or [],
                )
            else:
                task = self._task_manager.transition(
                    task.id,
                    TaskState.FAILED,
                    error=outcome.error,
                    cost=outcome.cost,
                    trace_id=outcome.trace_id,
                )
        return self._task_response(201, task)

    def _handle_get_task(self, task_id: str) -> tuple[int, dict[str, Any]]:
        """GET /tasks/{id}"""
        task = self._task_manager.get_task(task_id)
        if task is None:
            return 404, {"error": f"Task not found: {task_id}"}
        return self._task_response(200, task)

    def _handle_cancel_task(self, task_id: str) -> tuple[int, dict[str, Any]]:
        """POST /tasks/{id}/cancel"""
        try:
            task = self._task_manager.transition(task_id, TaskState.CANCELLED)
            return self._task_response(200, task)
        except TaskNotFoundError:
            return 404, {"error": f"Task not found: {task_id}"}
        except InvalidTransitionError as e:
            return 409, {"error": str(e)}

    def _task_response(self, status: int, task: Task) -> tuple[int, dict[str, Any]]:
        payload = task.to_dict()
        errors = validate_a2a_output(payload, A2A_TASK_OUTPUT_CONTRACT)
        if errors:
            return 500, schema_validation_error(A2A_TASK_OUTPUT_CONTRACT, errors)
        return status, payload

    def _handle_stream_info(self, task_id: str) -> tuple[int, dict[str, Any]]:
        """GET /tasks/{id}/stream - returns stream metadata."""
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
            # First-line read with a timeout so slowloris peers can't pin
            # the loop forever sending headers one byte at a time.
            try:
                request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            except TimeoutError:
                return
            if not request_line:
                return

            parts = request_line.decode().strip().split(" ")
            if len(parts) < 2:
                return

            method, path = parts[0], parts[1]

            # Read headers
            content_length = 0
            auth_header = ""
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=10.0)
                except TimeoutError:
                    return
                if line in (b"\r\n", b"\n", b""):
                    break
                raw = line.decode(errors="replace").strip()
                header_lower = raw.lower()
                if header_lower.startswith("content-length:"):
                    try:
                        content_length = int(header_lower.split(":", 1)[1].strip())
                    except ValueError:
                        # Bad header - refuse to read a body, return 400.
                        await self._send_simple(writer, 400, {"error": "Invalid Content-Length"})
                        return
                    if content_length < 0 or content_length > _MAX_REQUEST_BODY_BYTES:
                        await self._send_simple(
                            writer, 413, {"error": f"Request body exceeds {_MAX_REQUEST_BODY_BYTES} bytes"}
                        )
                        return
                elif header_lower.startswith("authorization:"):
                    auth_header = raw.split(":", 1)[1].strip()

            # Read body
            body = ""
            if content_length > 0:
                try:
                    body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=30.0)
                except (TimeoutError, asyncio.IncompleteReadError):
                    return
                body = body_bytes.decode(errors="replace")

            status, response = await self.handle_request(method, path, body, auth_header=auth_header)
            await self._send_simple(writer, status, response)
        except Exception:
            logger.exception("Error handling A2A connection")
            # Intent: one bad A2A connection or request must not crash the server process; log and let the connection close in finally.
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass  # intentional: best-effort close of A2A writer during error path; connection may already be gone

    @staticmethod
    async def _send_simple(writer: asyncio.StreamWriter, status: int, body: dict[str, Any]) -> None:
        response_json = json.dumps(body)
        http_response = (
            f"HTTP/1.1 {status} OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(response_json.encode('utf-8'))}\r\n"
            f"\r\n"
            f"{response_json}"
        )
        writer.write(http_response.encode())
        try:
            await writer.drain()
        except ConnectionError:
            pass
