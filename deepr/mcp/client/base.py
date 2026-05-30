"""Base MCP client with persistent connection, retry, and lifecycle management.

Provides a stdio-based MCP client that:
- Maintains a persistent subprocess connection (not per-call)
- Supports automatic reconnection on process death
- Retries transient failures with exponential backoff
- Tracks connection health (success rate, latency)
- Propagates trace IDs and budget through tool calls
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from deepr import __version__ as DEEPR_VERSION

logger = logging.getLogger(__name__)

# MCP protocol version
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPClientError(Exception):
    """Error from an MCP client operation."""

    def __init__(self, message: str, server_name: str = "", retryable: bool = False):
        super().__init__(message)
        self.server_name = server_name
        self.retryable = retryable


@dataclass
class MCPToolResult:
    """Result from calling a tool on a remote MCP server."""

    content: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    latency_ms: float = 0.0
    server_name: str = ""
    tool_name: str = ""
    trace_id: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 1),
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "trace_id": self.trace_id,
        }


@dataclass
class _ConnectionStats:
    """Health stats for a single MCP client connection."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""
    last_error_time: float = 0.0
    connected_since: float = 0.0
    reconnect_count: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
        }


class MCPClient:
    """Persistent MCP client over stdio (subprocess).

    Maintains a long-lived subprocess connection with automatic reconnection,
    retry on transient failures, and health tracking.

    Usage::

        client = MCPClient(
            name="my-server",
            command="python",
            args=["-m", "my_mcp_server"],
        )
        await client.connect()

        result = await client.call_tool("search", {"query": "test"})
        print(result.content)

        await client.close()
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = {**os.environ, **self._resolve_env(env or {})}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._connected = False
        self._stats = _ConnectionStats()
        self._server_capabilities: dict[str, Any] = {}
        self._available_tools: list[dict[str, Any]] = []
        # Serializes _send_request so concurrent callers on a shared MCPClient
        # (e.g. via MCPClientPool) cannot race against the single stdio
        # connection. Without this, caller A's readline could pick up caller
        # B's response, leaking results across sessions and breaking
        # JSON-RPC id correlation. Also re-validates the response id below.
        self._send_lock = asyncio.Lock()
        # Background task that drains the subprocess's stderr. Without
        # this the OS pipe buffer (~64KB on Linux) fills up on a chatty
        # server and the child blocks on its next stderr write — every
        # tool call then times out and ``close()`` is forced to ``kill()``.
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected and self._process is not None and self._process.returncode is None

    @property
    def stats(self) -> _ConnectionStats:
        return self._stats

    @property
    def available_tools(self) -> list[dict[str, Any]]:
        return self._available_tools

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the MCP server subprocess and perform initialization handshake."""
        if self.connected:
            return

        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
        except FileNotFoundError:
            raise MCPClientError(
                f"MCP server command not found: {self.command}",
                server_name=self.name,
            )
        except OSError as e:
            raise MCPClientError(
                f"Failed to start MCP server: {e}",
                server_name=self.name,
            )

        # Drain stderr to a logger so the subprocess pipe never fills up.
        # Cancel any prior drain task without awaiting — awaiting can
        # block on AsyncMock-based test harnesses where cancellation
        # propagation through ``wait_for`` doesn't unwind cleanly.
        if self._stderr_task is not None and not self._stderr_task.done():
            self._stderr_task.cancel()
        # Only spawn the real drainer when stderr is an actual
        # ``asyncio.StreamReader``. AsyncMock instances synthesise every
        # attribute on access, so a ``hasattr`` check would always
        # return True; an isinstance check correctly excludes mocks.
        stderr = self._process.stderr
        if isinstance(stderr, asyncio.StreamReader):
            self._stderr_task = asyncio.create_task(self._drain_stderr())
        else:
            self._stderr_task = None

        # Initialize handshake
        response = await self._send_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "deepr", "version": DEEPR_VERSION},
            },
        )

        if "error" in response:
            await self.close()
            raise MCPClientError(
                f"MCP initialization failed: {response['error']}",
                server_name=self.name,
            )

        result = response.get("result", {})
        self._server_capabilities = result.get("capabilities", {})
        self._connected = True
        self._stats.connected_since = time.time()

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        # Discover available tools
        await self._discover_tools()

        logger.info(
            "MCP client '%s' connected (pid=%s, tools=%d)",
            self.name,
            self._process.pid,
            len(self._available_tools),
        )

    async def _discover_tools(self) -> None:
        """Query the server for available tools."""
        if not self._server_capabilities.get("tools"):
            self._available_tools = []
            return

        response = await self._send_request("tools/list", {})
        result = response.get("result", {})
        self._available_tools = result.get("tools", [])

    async def reconnect(self) -> None:
        """Close and reopen the connection."""
        await self.close()
        self._stats.reconnect_count += 1
        await self.connect()

    async def close(self) -> None:
        """Terminate the MCP server subprocess gracefully.

        Orderly shutdown: cancel stderr drain, close stdin, send SIGTERM,
        wait up to 5s, SIGKILL on timeout, then ``await wait()`` so no
        zombie process is left behind.
        """
        self._connected = False
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except (asyncio.CancelledError, Exception):
                pass  # task cancel during MCP client close is expected in shutdown
        self._stderr_task = None

        if self._process and self._process.returncode is None:
            # Closing stdin lets a well-behaved MCP server exit on EOF.
            try:
                if self._process.stdin and not self._process.stdin.is_closing():
                    self._process.stdin.close()
            except (OSError, AttributeError):
                pass
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except TimeoutError:
                self._process.kill()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2)
                except TimeoutError:
                    pass
        self._process = None

    async def _drain_stderr(self) -> None:
        """Continuously read the subprocess's stderr to a logger.

        Exits cleanly on EOF, when the subprocess has terminated, when
        the task is cancelled, or when the stderr stream returns
        unexpected data (e.g. a test harness's AsyncMock returning a
        non-bytes sentinel). The terminated-process check guards against
        hangs on Windows where the pipe doesn't always close cleanly.
        """
        if not self._process or not self._process.stderr:
            return
        try:
            while True:
                if self._process.returncode is not None:
                    return
                try:
                    line = await asyncio.wait_for(self._process.stderr.readline(), timeout=1.0)
                except TimeoutError:
                    # Intent: expected idle timeout in stderr drain poll loop; continue polling without logging noise (normal for long-lived MCP sessions).
                    continue
                except (AttributeError, TypeError):
                    # Mock stderr or stream torn down — stop draining.
                    return
                # Real stderr returns ``b""`` on EOF; defensive against
                # test mocks that emit non-bytes return values.
                if not isinstance(line, (bytes, bytearray)):
                    return
                if not line:
                    return
                try:
                    text = line.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    text = repr(line)
                if text:
                    logger.debug("[mcp:%s stderr] %s", self.name, text)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Stderr drain ended for %s: %s", self.name, e)

    # ------------------------------------------------------------------
    # Tool calling
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
        trace_id: str = "",
    ) -> MCPToolResult:
        """Call a tool on the remote MCP server with retry and reconnection.

        Args:
            tool_name: Name of the tool to call.
            arguments: Tool arguments.
            timeout: Override default timeout.
            trace_id: Trace ID for correlation.

        Returns:
            MCPToolResult with content or error.
        """
        effective_timeout = timeout or self.timeout
        start = time.monotonic()

        # Stats count logical calls (one per call_tool invocation), not retries
        last_error = ""
        for attempt in range(self.max_retries):
            try:
                if not self.connected:
                    await self.connect()

                response = await asyncio.wait_for(
                    self._send_request(
                        "tools/call",
                        {"name": tool_name, "arguments": arguments or {}},
                    ),
                    timeout=effective_timeout,
                )

                elapsed = (time.monotonic() - start) * 1000

                if "error" in response:
                    # Protocol error from server — not retryable
                    error_msg = str(response["error"])
                    self._stats.total_calls += 1
                    self._stats.failed_calls += 1
                    self._stats.last_error = error_msg
                    self._stats.last_error_time = time.time()
                    return MCPToolResult(
                        error=error_msg,
                        latency_ms=elapsed,
                        server_name=self.name,
                        tool_name=tool_name,
                        trace_id=trace_id,
                    )

                # Extract text content from MCP response
                result = response.get("result", {})
                content_parts = result.get("content", [])
                text = ""
                if isinstance(content_parts, list):
                    text = "\n".join(c.get("text", "") for c in content_parts if c.get("type") == "text")

                self._stats.total_calls += 1
                self._stats.successful_calls += 1
                self._stats.total_latency_ms += elapsed

                return MCPToolResult(
                    content=text,
                    raw=result,
                    latency_ms=elapsed,
                    server_name=self.name,
                    tool_name=tool_name,
                    trace_id=trace_id,
                )

            except TimeoutError:
                last_error = f"Timeout after {effective_timeout}s"
                logger.warning(
                    "MCP '%s' tool '%s' timeout (attempt %d/%d)",
                    self.name,
                    tool_name,
                    attempt + 1,
                    self.max_retries,
                )
                # NOTE: We do not force a reconnect here. Doing so
                # introduces JSON-RPC framing risk (the prior write
                # reached the server; the response was cancelled
                # mid-read so the next ``readline`` could dequeue it
                # under a fresh id). The mitigation is to surface
                # repeated timeouts through ``_stats.failed_calls``;
                # the pool's circuit breaker then takes the server
                # OPEN and a healthy probe forces a clean reconnect.
            except (BrokenPipeError, ConnectionError, OSError) as e:
                last_error = str(e)
                logger.warning(
                    "MCP '%s' connection error (attempt %d/%d): %s",
                    self.name,
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                # Connection lost — reconnect on next attempt
                await self.close()

            # Exponential backoff before retry, with full jitter. Without
            # jitter, N pool clients hitting a flapping server retry in
            # lockstep at the same wall-clock instants, producing a
            # thundering-herd reconnect storm.
            if attempt < self.max_retries - 1:
                import random as _random

                base = self.retry_delay * (2**attempt)
                delay = base * (0.5 + _random.random())  # 0.5x..1.5x of base
                await asyncio.sleep(delay)

        # All retries exhausted — count as one failed logical call
        elapsed = (time.monotonic() - start) * 1000
        self._stats.total_calls += 1
        self._stats.failed_calls += 1
        self._stats.last_error = last_error
        self._stats.last_error_time = time.time()

        return MCPToolResult(
            error=f"Failed after {self.max_retries} attempts: {last_error}",
            latency_ms=elapsed,
            server_name=self.name,
            tool_name=tool_name,
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Low-level JSON-RPC
    # ------------------------------------------------------------------

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and read the response.

        Serializes the write/read pair under a per-client lock so concurrent
        callers on a shared MCPClient (e.g. through MCPClientPool) cannot
        interleave on the single stdio stream — without this, caller A's
        readline could pick up caller B's response and leak results across
        sessions. Also validates that the response id matches the request id;
        any mismatch is rejected rather than silently returned to the caller.
        """
        async with self._send_lock:
            if not self._process or self._process.stdin is None or self._process.stdout is None:
                return {"error": "MCP process not available"}

            self._request_id += 1
            request_id = self._request_id
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            line = json.dumps(request) + "\n"
            self._process.stdin.write(line.encode())
            await self._process.stdin.drain()

            # Drain notifications/unexpected frames until we receive a response
            # whose id matches the request we just sent. Bounded so a chatty
            # server cannot hang the caller forever.
            for _ in range(64):
                response_line = await self._process.stdout.readline()
                if not response_line:
                    return {"error": "MCP server closed connection"}

                try:
                    payload: dict[str, Any] = json.loads(response_line)
                except json.JSONDecodeError:
                    return {"error": f"Invalid JSON from MCP server: {response_line[:200]!r}"}

                # Drop pure notifications (no id) silently.
                if "id" not in payload:
                    continue
                if payload.get("id") == request_id:
                    return payload
                logger.warning(
                    "MCP %s: dropping response with mismatched id (got %r, expected %r)",
                    self.name,
                    payload.get("id"),
                    request_id,
                )

            return {"error": "MCP server returned too many unmatched responses"}

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or self._process.stdin is None:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(notification) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_env(env: dict[str, str]) -> dict[str, str]:
        """Resolve ${VAR} references from os.environ."""
        resolved = {}
        for key, value in env.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                resolved[key] = os.environ.get(value[2:-1], "")
            else:
                resolved[key] = str(value)
        return resolved

    def health(self) -> dict[str, Any]:
        """Return health summary for this client connection."""
        return {
            "name": self.name,
            "connected": self.connected,
            "pid": self._process.pid if self._process else None,
            "tools": len(self._available_tools),
            "stats": self._stats.to_dict(),
        }

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"MCPClient(name={self.name!r}, {status}, tools={len(self._available_tools)})"
