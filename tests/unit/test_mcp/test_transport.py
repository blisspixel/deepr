"""
Tests for MCP Transport Layer.

Tests both Stdio and HTTP transports for correctness.
"""

import sys
from pathlib import Path
import asyncio
import json

import pytest
from hypothesis import given, strategies as st, settings

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.transport.stdio import (
    StdioTransport,
    StdioServer,
    Message,
    TransportStats,
)
from deepr.mcp.transport.http import (
    StreamingHttpTransport,
    HttpClient,
    HttpMessage,
    HttpTransportStats,
)


class TestMessage:
    """Test Message dataclass."""
    
    def test_request_detection(self):
        """Request has method and id."""
        msg = Message(method="test", id="1")
        assert msg.is_request()
        assert not msg.is_notification()
        assert not msg.is_response()
    
    def test_notification_detection(self):
        """Notification has method but no id."""
        msg = Message(method="test")
        assert not msg.is_request()
        assert msg.is_notification()
        assert not msg.is_response()
    
    def test_response_detection(self):
        """Response has result or error."""
        msg = Message(id="1", result={"data": "test"})
        assert not msg.is_request()
        assert not msg.is_notification()
        assert msg.is_response()
    
    def test_error_response_detection(self):
        """Error response has error field."""
        msg = Message(id="1", error={"code": -32600, "message": "Invalid"})
        assert msg.is_response()
    
    def test_to_dict_minimal(self):
        """to_dict includes only set fields."""
        msg = Message(method="test", id="1")
        d = msg.to_dict()
        
        assert d["jsonrpc"] == "2.0"
        assert d["method"] == "test"
        assert d["id"] == "1"
        assert "params" not in d
        assert "result" not in d
        assert "error" not in d
    
    def test_to_dict_with_params(self):
        """to_dict includes params when set."""
        msg = Message(method="test", id="1", params={"key": "value"})
        d = msg.to_dict()
        
        assert d["params"] == {"key": "value"}
    
    def test_from_dict(self):
        """from_dict creates Message correctly."""
        data = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "req_1",
            "params": {"filter": "research"}
        }
        msg = Message.from_dict(data)
        
        assert msg.jsonrpc == "2.0"
        assert msg.method == "tools/list"
        assert msg.id == "req_1"
        assert msg.params == {"filter": "research"}
    
    def test_roundtrip(self):
        """Message survives to_dict -> from_dict roundtrip."""
        original = Message(
            method="test/method",
            id="123",
            params={"nested": {"data": [1, 2, 3]}}
        )
        
        reconstructed = Message.from_dict(original.to_dict())
        
        assert reconstructed.method == original.method
        assert reconstructed.id == original.id
        assert reconstructed.params == original.params


class TestTransportStats:
    """Test TransportStats tracking."""
    
    def test_initial_state(self):
        """Stats start at zero."""
        stats = TransportStats()
        
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.bytes_sent == 0
        assert stats.bytes_received == 0
        assert stats.errors == 0
    
    def test_record_sent(self):
        """record_sent increments counters."""
        stats = TransportStats()
        
        stats.record_sent(100)
        stats.record_sent(50)
        
        assert stats.messages_sent == 2
        assert stats.bytes_sent == 150
    
    def test_record_received(self):
        """record_received increments counters."""
        stats = TransportStats()
        
        stats.record_received(200)
        
        assert stats.messages_received == 1
        assert stats.bytes_received == 200
    
    def test_record_error(self):
        """record_error increments error counter."""
        stats = TransportStats()
        
        stats.record_error()
        stats.record_error()
        
        assert stats.errors == 2


class TestStdioTransport:
    """Test StdioTransport functionality."""
    
    @pytest.mark.asyncio
    async def test_is_local(self):
        """Stdio transport is always local."""
        transport = StdioTransport()
        assert transport.is_local is True
    
    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Transport starts not running."""
        transport = StdioTransport()
        assert transport.is_running is False
    
    @pytest.mark.asyncio
    async def test_stats_available(self):
        """Stats are accessible."""
        transport = StdioTransport()
        stats = transport.stats
        
        assert isinstance(stats, TransportStats)
        assert stats.messages_sent == 0


class TestStdioServer:
    """Test StdioServer convenience wrapper."""
    
    def test_register_method(self):
        """Methods can be registered."""
        server = StdioServer()
        
        async def handler(params):
            return {"result": "ok"}
        
        server.register_method("test/method", handler)
        
        # Method is registered (internal check)
        assert "test/method" in server._methods
    
    @pytest.mark.asyncio
    async def test_handle_unknown_method(self):
        """Unknown method returns error."""
        server = StdioServer()
        
        message = Message(method="unknown/method", id="1")
        response = await server._handle_message(message)
        
        assert response is not None
        assert response.error is not None
        assert response.error["code"] == -32601
        assert "not found" in response.error["message"].lower()
    
    @pytest.mark.asyncio
    async def test_handle_known_method(self):
        """Known method returns result."""
        server = StdioServer()
        
        async def handler(params):
            return {"echo": params.get("input", "none")}
        
        server.register_method("test/echo", handler)
        
        message = Message(method="test/echo", id="1", params={"input": "hello"})
        response = await server._handle_message(message)
        
        assert response is not None
        assert response.result == {"echo": "hello"}
        assert response.id == "1"
    
    @pytest.mark.asyncio
    async def test_handle_method_error(self):
        """Method exception returns error response."""
        server = StdioServer()
        
        async def handler(params):
            raise ValueError("Test error")
        
        server.register_method("test/fail", handler)
        
        message = Message(method="test/fail", id="1")
        response = await server._handle_message(message)
        
        assert response is not None
        assert response.error is not None
        assert "Test error" in response.error["message"]
    
    @pytest.mark.asyncio
    async def test_notification_no_response(self):
        """Notifications (no id) return no response."""
        server = StdioServer()
        
        message = Message(method="test/notify")  # No id
        response = await server._handle_message(message)
        
        assert response is None


class TestHttpMessage:
    """Test HttpMessage dataclass."""
    
    def test_same_interface_as_message(self):
        """HttpMessage has same interface as stdio Message."""
        msg = HttpMessage(method="test", id="1", params={"key": "value"})
        
        assert msg.is_request()
        assert not msg.is_notification()
        assert not msg.is_response()
        
        d = msg.to_dict()
        assert d["method"] == "test"
        assert d["id"] == "1"
        assert d["params"] == {"key": "value"}
    
    def test_from_dict(self):
        """from_dict creates HttpMessage correctly."""
        data = {"jsonrpc": "2.0", "method": "test", "id": "1"}
        msg = HttpMessage.from_dict(data)
        
        assert msg.method == "test"
        assert msg.id == "1"


class TestHttpTransportStats:
    """Test HttpTransportStats tracking."""
    
    def test_initial_state(self):
        """Stats start at zero."""
        stats = HttpTransportStats()
        
        assert stats.requests_received == 0
        assert stats.responses_sent == 0
        assert stats.notifications_sent == 0
        assert stats.active_streams == 0
        assert stats.errors == 0


class TestStreamingHttpTransport:
    """Test StreamingHttpTransport functionality."""
    
    def test_is_not_local(self):
        """HTTP transport is not local."""
        transport = StreamingHttpTransport()
        assert transport.is_local is False
    
    def test_initial_state(self):
        """Transport starts not running."""
        transport = StreamingHttpTransport()
        assert transport.is_running is False
    
    def test_url_construction(self):
        """URL is constructed correctly."""
        transport = StreamingHttpTransport(host="localhost", port=9000, path="/api")
        assert transport.url == "http://localhost:9000/api"
    
    def test_default_url(self):
        """Default URL uses standard values."""
        transport = StreamingHttpTransport()
        assert transport.url == "http://0.0.0.0:8765/mcp"
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Transport can start and stop."""
        transport = StreamingHttpTransport(port=18765)  # Use non-standard port
        
        await transport.start()
        assert transport.is_running is True
        
        await transport.stop()
        assert transport.is_running is False
    
    @pytest.mark.asyncio
    async def test_broadcast_no_subscribers(self):
        """Broadcast with no subscribers returns 0."""
        transport = StreamingHttpTransport(port=18766)
        await transport.start()
        
        try:
            count = await transport.broadcast({"test": "data"})
            assert count == 0
        finally:
            await transport.stop()
    
    @pytest.mark.asyncio
    async def test_send_to_unknown_subscriber(self):
        """send_to unknown subscriber returns False."""
        transport = StreamingHttpTransport(port=18767)
        await transport.start()
        
        try:
            result = await transport.send_to("unknown_id", {"test": "data"})
            assert result is False
        finally:
            await transport.stop()


class TestPropertyBased:
    """Property-based tests for transport layer."""
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_message_method_preserved(self, method: str):
        """
        Property: Method name is preserved through serialization.
        """
        msg = Message(method=method, id="test")
        reconstructed = Message.from_dict(msg.to_dict())
        
        assert reconstructed.method == method
    
    @given(st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
        values=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
        max_size=10
    ))
    @settings(max_examples=50)
    def test_message_params_preserved(self, params: dict):
        """
        Property: Params are preserved through serialization.
        """
        msg = Message(method="test", id="1", params=params)
        reconstructed = Message.from_dict(msg.to_dict())
        
        assert reconstructed.params == params
    
    @given(st.integers(min_value=0, max_value=10000))
    @settings(max_examples=50)
    def test_stats_accumulate_correctly(self, byte_count: int):
        """
        Property: Stats accumulate correctly over multiple operations.
        """
        stats = TransportStats()
        
        stats.record_sent(byte_count)
        stats.record_sent(byte_count)
        
        assert stats.messages_sent == 2
        assert stats.bytes_sent == byte_count * 2
    
    @given(st.integers(min_value=1, max_value=65535))
    @settings(max_examples=20)
    def test_http_transport_url_with_any_port(self, port: int):
        """
        Property: HTTP transport URL is valid for any port.
        """
        transport = StreamingHttpTransport(port=port)
        
        assert f":{port}/" in transport.url
        assert transport.url.startswith("http://")
