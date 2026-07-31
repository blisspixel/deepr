"""
Stdio Transport for MCP.

Implements JSON-RPC over stdin/stdout for local process communication.
This is the most secure transport option as research data never leaves
the local process tree.

Security Properties:
- No network exposure
- Process isolation
- Data stays local
"""

import asyncio
import json
import logging
import sys
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from deepr.mcp.protocol_modern import JsonRpcProtocolError

logger = logging.getLogger(__name__)

# A streaming method opens a long-lived notification stream instead of
# returning one response: opener(params, request_id, send) -> closer(graceful).
# The request id keeps its JSON-RPC type (string or integer).
StreamSend = Callable[[dict[str, Any]], Awaitable[None]]
StreamCloser = Callable[[bool], Awaitable[None]]
StreamOpener = Callable[[dict[str, Any], "str | int", StreamSend], Awaitable[StreamCloser]]


# Maximum JSON-RPC line size. asyncio.StreamReader's 64 KiB default silently
# unanswered any large tools/call (long research prompts and expert contexts
# are routine here); 16 MiB comfortably covers the tool surface while still
# bounding memory against a runaway peer.
MAX_LINE_BYTES = 16 * 1024 * 1024

# Ceiling on simultaneously open long-lived streams (subscriptions/listen) so
# a client that never cancels cannot grow server state without bound.
MAX_CONCURRENT_STREAMS = 32


class _StdioWriter(Protocol):
    """The subset of StreamWriter the transport uses (structural typing lets
    the Windows fallback writer stand in)."""

    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


class _BlockingStdoutWriter:
    """Fallback stdout writer for platforms where ``connect_write_pipe``
    cannot register the stdio handle (Windows proactor loop + IOCP)."""

    def __init__(self) -> None:
        self._pending: list[bytes] = []

    def write(self, data: bytes) -> None:
        self._pending.append(data)

    async def drain(self) -> None:
        data = b"".join(self._pending)
        self._pending.clear()
        if data:
            await asyncio.get_running_loop().run_in_executor(None, self._flush, data)

    @staticmethod
    def _flush(data: bytes) -> None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def _start_threaded_stdin_reader(reader: asyncio.StreamReader, loop: asyncio.AbstractEventLoop) -> None:
    """Pump ``sys.stdin`` into an asyncio StreamReader from a daemon thread.

    On Windows the proactor event loop cannot register ordinary stdio pipe
    handles with IOCP (``connect_read_pipe`` dies with WinError 6), which
    silently killed the server for every host that launches it as a
    subprocess (Claude Desktop, Cursor, VS Code). A blocking readline in a
    daemon thread works on every platform and handle type.
    """

    def _pump() -> None:
        stdin = sys.stdin.buffer
        try:
            while True:
                # readline(MAX_LINE_BYTES) bounds a single blocking read, so a
                # peer that never sends a newline cannot exhaust memory inside
                # the thread before StreamReader's own limit can fire.
                line = stdin.readline(MAX_LINE_BYTES)
                if not line:
                    loop.call_soon_threadsafe(reader.feed_eof)
                    break
                loop.call_soon_threadsafe(reader.feed_data, line)
        except (OSError, ValueError, RuntimeError):
            # Closed stdin or a torn-down loop during shutdown: signal EOF
            # if the loop is still alive, otherwise just exit the thread.
            try:
                loop.call_soon_threadsafe(reader.feed_eof)
            except RuntimeError:
                pass  # intentional: event loop already closed during shutdown

    threading.Thread(target=_pump, name="deepr-mcp-stdin", daemon=True).start()


@dataclass
class Message:
    """A JSON-RPC message."""

    jsonrpc: str = "2.0"
    id: str | None = None
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None

    def is_request(self) -> bool:
        """Check if this is a request message."""
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        """Check if this is a notification (no id)."""
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        """Check if this is a response message."""
        return self.result is not None or self.error is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class TransportStats:
    """Statistics for transport monitoring."""

    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    errors: int = 0
    started_at: datetime = field(default_factory=datetime.now)

    def record_sent(self, size: int) -> None:
        """Record a sent message."""
        self.messages_sent += 1
        self.bytes_sent += size

    def record_received(self, size: int) -> None:
        """Record a received message."""
        self.messages_received += 1
        self.bytes_received += size

    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1


class StdioTransport:
    """
    Stdio-based MCP transport.

    Reads JSON-RPC messages from stdin and writes responses to stdout.
    This transport ensures all research data stays within the local
    process tree, providing maximum security for sensitive research.

    Usage:
        transport = StdioTransport()
        transport.on_message(handler)
        await transport.start()
    """

    def __init__(
        self,
        input_stream: asyncio.StreamReader | None = None,
        output_stream: asyncio.StreamWriter | None = None,
    ):
        """
        Initialize stdio transport.

        Args:
            input_stream: Custom input stream (default: stdin)
            output_stream: Custom output stream (default: stdout)
        """
        self._input = input_stream
        self._output: _StdioWriter | None = output_stream
        self._handler: Callable[[Message], Awaitable[Message | None]] | None = None
        self._running = False
        self._stats = TransportStats()
        self._read_task: asyncio.Task[None] | None = None
        # Track in-flight handler tasks so stop() can drain them. Initialised
        # in __init__ rather than lazily inside _read_loop so callers that
        # interrogate the transport before the first message still see the set.
        self._in_flight: set[asyncio.Task[None]] = set()

    def on_message(self, handler: Callable[[Message], Awaitable[Message | None]]) -> None:
        """
        Set the message handler.

        Args:
            handler: Async function that processes messages and optionally
                    returns a response message.
        """
        self._handler = handler

    async def start(self) -> None:
        """
        Start the transport, reading from stdin.

        This method runs until stop() is called or EOF is reached.
        """
        if self._running:
            return

        self._running = True

        # Set up streams if not provided. Windows cannot register ordinary
        # stdio pipe handles with the proactor loop's IOCP, so it uses a
        # daemon-thread reader and a blocking writer instead of pipe
        # transports; POSIX keeps the native pipe path.
        if self._input is None:
            loop = asyncio.get_event_loop()
            self._input = asyncio.StreamReader(limit=MAX_LINE_BYTES)
            if sys.platform == "win32":
                _start_threaded_stdin_reader(self._input, loop)
            else:
                protocol = asyncio.StreamReaderProtocol(self._input)
                await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        if self._output is None:
            if sys.platform == "win32":
                self._output = _BlockingStdoutWriter()
            else:
                loop = asyncio.get_event_loop()
                transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)  # type: ignore[arg-type]
                self._output = asyncio.StreamWriter(transport, protocol, None, loop)

        self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop the transport.

        Cancels the read loop and waits up to a few seconds for any
        in-flight handler tasks (paid research calls, expert queries) to
        finish so their responses are written back to stdout before the
        process exits. Without this drain the round-1 fix that offloaded
        handler dispatch to background tasks would silently drop responses
        when the transport was stopped mid-call.
        """
        self._running = False
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._in_flight:
            try:
                # Allow handlers a short grace period to complete and send
                # their response; cancel anything still pending after that.
                await asyncio.wait_for(
                    asyncio.gather(*self._in_flight, return_exceptions=True),
                    timeout=5.0,
                )
            except TimeoutError:
                for task in list(self._in_flight):
                    if not task.done():
                        task.cancel()
                # Final gather to collect cancellations cleanly.
                try:
                    await asyncio.gather(*self._in_flight, return_exceptions=True)
                except Exception:
                    pass  # intentional: final best-effort drain during shutdown; errors here cannot affect protocol correctness
            finally:
                self._in_flight.clear()

    async def _read_loop(self) -> None:
        """
        Main read loop for incoming messages.

        Reads newline-delimited JSON-RPC messages from stdin and
        dispatches them to the registered handler. Handler dispatch is
        offloaded to ``asyncio.create_task`` so a single long-running
        tool call (deepr_research, deepr_agentic_research) doesn't
        block subsequent reads - including cancellations of itself.
        """
        if self._input is None:
            logger.critical(
                "StdioTransport._read_loop started before start() initialized _input. "
                "This is a programming error - the MCP stdio transport is in an invalid state."
            )
            return
        while self._running:
            try:
                # Read a line (JSON-RPC messages are newline-delimited)
                try:
                    line = await self._input.readline()
                except ValueError:
                    # A line over MAX_LINE_BYTES has no readable id to answer
                    # and the buffer cannot be resynchronized mid-line;
                    # report a parse error and end the transport.
                    self._stats.record_error()
                    await self._send_error(None, -32700, "Request line exceeds size limit")
                    break

                if not line:
                    # EOF reached
                    break

                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                self._stats.record_received(len(line))

                # Parse JSON-RPC message
                try:
                    data = json.loads(line_str)

                    # Validate basic JSON-RPC structure
                    if not isinstance(data, dict):
                        raise json.JSONDecodeError("Expected object", line_str, 0)

                    message = Message.from_dict(data)
                except json.JSONDecodeError:
                    # Intent: one malformed JSON-RPC line from MCP server must not abort the stdio transport loop; continue to next message for resilience.
                    self._stats.record_error()
                    await self._send_error(None, -32700, "Parse error")
                    continue

                # Handle message - dispatch in a background task so the
                # next line can be read immediately.
                if self._handler:

                    async def _dispatch(msg: Message = message, _handler: Any = self._handler) -> None:
                        try:
                            response = await _handler(msg)
                            if response:
                                await self.send(response)
                        except Exception:
                            # Log locally, return a generic message: exception
                            # text carries filesystem paths and provider
                            # strings the host client must not see.
                            logger.exception("Stdio handler failed for method %s", msg.method)
                            self._stats.record_error()
                            if msg.id is not None:
                                await self._send_error(msg.id, -32603, "Internal error")

                    task = asyncio.create_task(_dispatch())
                    self._in_flight.add(task)
                    task.add_done_callback(self._in_flight.discard)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._stats.record_error()
                logger.warning("Stdio transport loop error: %s", exc)
        # EOF (host closed stdin) or cancellation ends the transport. Without
        # this, run() spins on is_running forever and the server process
        # orphans after the host disconnects.
        self._running = False

    async def send(self, message: Message) -> None:
        """
        Send a message to stdout.

        Args:
            message: The message to send
        """
        if not self._output:
            return

        data = json.dumps(message.to_dict()) + "\n"
        encoded = data.encode("utf-8")

        self._output.write(encoded)
        await self._output.drain()

        self._stats.record_sent(len(encoded))

    async def _send_error(self, id: str | None, code: int, message: str) -> None:
        """Send an error response."""
        error_msg = Message(id=id, error={"code": code, "message": message})
        await self.send(error_msg)

    @property
    def stats(self) -> TransportStats:
        """Get transport statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if transport is running."""
        return self._running

    @property
    def is_local(self) -> bool:
        """
        Check if this is a local transport.

        Stdio is always local - data never leaves the process tree.
        """
        return True


class StdioServer:
    """
    Convenience wrapper for running an MCP server over stdio.

    Usage:
        server = StdioServer()
        server.register_method("tools/list", list_tools_handler)
        await server.run()
    """

    def __init__(self) -> None:
        self._transport = StdioTransport()
        self._methods: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {}
        self._streaming_methods: dict[str, StreamOpener] = {}
        # Keyed by the raw JSON-RPC id (str or int - stringifying would
        # collide ids 5 and "5"). None marks a stream still opening so a
        # cancellation arriving mid-open is not lost.
        self._streams: dict[str | int, StreamCloser | None] = {}
        self._transport.on_message(self._handle_message)

    def register_method(self, name: str, handler: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        """
        Register a method handler.

        Args:
            name: Method name (e.g., "tools/list")
            handler: Async function that handles the method
        """
        self._methods[name] = handler

    def register_streaming_method(self, name: str, opener: StreamOpener) -> None:
        """Register a long-lived stream method (e.g. subscriptions/listen).

        The opener receives (params, request_id, send) and returns a closer.
        No response is written for the request until the stream ends: the
        client cancels with ``notifications/cancelled`` (silent teardown) or
        the server shuts down (graceful empty response first, per spec).
        """
        self._streaming_methods[name] = opener

    async def _send_payload(self, payload: dict[str, Any]) -> None:
        await self._transport.send(Message.from_dict(payload))

    async def _cancel_stream(self, request_id: Any) -> None:
        if not isinstance(request_id, str | int):
            return
        if request_id not in self._streams:
            return
        closer = self._streams.pop(request_id)
        if closer is not None:
            # Client-initiated cancellation: tear down without a response
            # (the spec forbids responding to a cancelled request). A None
            # closer means the stream is still opening; the opening task
            # observes the missing key and closes it itself.
            await closer(False)

    async def _handle_message(self, message: Message) -> Message | None:
        """Handle incoming message."""
        if message.is_notification():
            if message.method == "notifications/cancelled":
                await self._cancel_stream((message.params or {}).get("requestId"))
            return None
        if not message.is_request():
            return None

        method = message.method
        opener = self._streaming_methods.get(method or "")
        if opener is not None and message.id is not None:
            stream_key: str | int = message.id
            if stream_key in self._streams:
                # Reusing an in-flight id would orphan the first stream's
                # closer: its subscriptions would never be torn down and only
                # the survivor could be cancelled.
                return Message(
                    id=message.id,
                    error={"code": -32600, "message": f"Request id {message.id!r} is already an open stream"},
                )
            if len(self._streams) >= MAX_CONCURRENT_STREAMS:
                return Message(
                    id=message.id,
                    error={
                        "code": -32600,
                        "message": f"Too many open streams (limit {MAX_CONCURRENT_STREAMS})",
                    },
                )
            self._streams[stream_key] = None  # opening; visible to cancellation
            try:
                closer = await opener(message.params or {}, message.id, self._send_payload)
            except JsonRpcProtocolError as exc:
                self._streams.pop(stream_key, None)
                return Message(id=message.id, error=exc.to_error())
            except Exception:
                self._streams.pop(stream_key, None)
                logger.exception("Stdio stream opener failed for %s", method)
                return Message(id=message.id, error={"code": -32603, "message": "Internal error"})
            if stream_key not in self._streams:
                # Cancelled while opening: tear down silently.
                await closer(False)
                return None
            self._streams[stream_key] = closer
            return None

        if method not in self._methods:
            return Message(id=message.id, error={"code": -32601, "message": f"Method not found: {method}"})

        try:
            result = await self._methods[method](message.params or {})
            return Message(id=message.id, result=result)
        except JsonRpcProtocolError as exc:
            return Message(id=message.id, error=exc.to_error())
        except Exception:
            logger.exception("Stdio method %s failed", method)
            return Message(id=message.id, error={"code": -32603, "message": "Internal error"})

    async def run(self) -> None:
        """Run the server until stopped."""
        await self._transport.start()

        # Wait for transport to stop
        while self._transport.is_running:
            await asyncio.sleep(0.1)

    async def stop(self) -> None:
        """Stop the server."""
        # Server-initiated shutdown: end each active listen stream gracefully so
        # clients can distinguish it from an abrupt transport drop. A None
        # closer is a stream still opening; its opening task cleans it up.
        for closer in list(self._streams.values()):
            if closer is None:
                continue
            try:
                await closer(True)
            except Exception as exc:
                logger.warning("Stream close failed during shutdown: %s", exc)
        self._streams.clear()
        await self._transport.stop()

    @property
    def stats(self) -> TransportStats:
        """Get transport statistics."""
        return self._transport.stats
