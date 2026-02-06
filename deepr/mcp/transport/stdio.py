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
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Message:
    """A JSON-RPC message."""

    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[Any] = None
    error: Optional[dict] = None

    def is_request(self) -> bool:
        """Check if this is a request message."""
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        """Check if this is a notification (no id)."""
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        """Check if this is a response message."""
        return self.result is not None or self.error is not None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        d = {"jsonrpc": self.jsonrpc}
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
    def from_dict(cls, data: dict) -> "Message":
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
        input_stream: Optional[asyncio.StreamReader] = None,
        output_stream: Optional[asyncio.StreamWriter] = None,
    ):
        """
        Initialize stdio transport.

        Args:
            input_stream: Custom input stream (default: stdin)
            output_stream: Custom output stream (default: stdout)
        """
        self._input = input_stream
        self._output = output_stream
        self._handler: Optional[Callable[[Message], Awaitable[Optional[Message]]]] = None
        self._running = False
        self._stats = TransportStats()
        self._read_task: Optional[asyncio.Task] = None

    def on_message(self, handler: Callable[[Message], Awaitable[Optional[Message]]]) -> None:
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

        # Set up streams if not provided
        if self._input is None:
            loop = asyncio.get_event_loop()
            self._input = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(self._input)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        if self._output is None:
            loop = asyncio.get_event_loop()
            transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
            self._output = asyncio.StreamWriter(transport, protocol, None, loop)

        self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop the transport."""
        self._running = False
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

    async def _read_loop(self) -> None:
        """
        Main read loop for incoming messages.

        Reads newline-delimited JSON-RPC messages from stdin and
        dispatches them to the registered handler. Handles parse
        errors gracefully by sending error responses.
        """
        while self._running:
            try:
                # Read a line (JSON-RPC messages are newline-delimited)
                line = await self._input.readline()

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
                    self._stats.record_error()
                    await self._send_error(None, -32700, "Parse error")
                    continue

                # Handle message
                if self._handler:
                    try:
                        response = await self._handler(message)
                        if response:
                            await self.send(response)
                    except Exception as e:
                        self._stats.record_error()
                        if message.id:
                            await self._send_error(message.id, -32603, f"Internal error: {e}")

            except asyncio.CancelledError:
                break
            except Exception:
                self._stats.record_error()

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

    async def _send_error(self, id: Optional[str], code: int, message: str) -> None:
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

    def __init__(self):
        self._transport = StdioTransport()
        self._methods: dict[str, Callable[[dict], Awaitable[Any]]] = {}
        self._transport.on_message(self._handle_message)

    def register_method(self, name: str, handler: Callable[[dict], Awaitable[Any]]) -> None:
        """
        Register a method handler.

        Args:
            name: Method name (e.g., "tools/list")
            handler: Async function that handles the method
        """
        self._methods[name] = handler

    async def _handle_message(self, message: Message) -> Optional[Message]:
        """Handle incoming message."""
        if not message.is_request():
            return None

        method = message.method
        if method not in self._methods:
            return Message(id=message.id, error={"code": -32601, "message": f"Method not found: {method}"})

        try:
            result = await self._methods[method](message.params or {})
            return Message(id=message.id, result=result)
        except Exception as e:
            return Message(id=message.id, error={"code": -32603, "message": str(e)})

    async def run(self) -> None:
        """Run the server until stopped."""
        await self._transport.start()

        # Wait for transport to stop
        while self._transport.is_running:
            await asyncio.sleep(0.1)

    async def stop(self) -> None:
        """Stop the server."""
        await self._transport.stop()

    @property
    def stats(self) -> TransportStats:
        """Get transport statistics."""
        return self._transport.stats
