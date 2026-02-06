"""
MCP Transport Layer.

Provides flexible transport options for MCP communication:
- Stdio: Local process communication (default, most secure)
- HTTP: Streamable HTTP for cloud deployment

Transport Selection Guide:
- Local development: Use StdioTransport (data never leaves process tree)
- Cloud deployment: Use StreamingHttpTransport (bidirectional over HTTP)
- Enterprise networks: Use StreamingHttpTransport (no WebSocket needed)

Security Considerations:
- StdioTransport: Maximum security, OS-level process isolation
- HttpTransport: Requires TLS in production, network exposure
"""

from .http import (
    HttpClient,
    HttpMessage,
    HttpTransport,
    HttpTransportStats,
    StreamingHttpTransport,
)
from .stdio import Message, StdioServer, StdioTransport, TransportStats

__all__ = [
    "HttpClient",
    "HttpMessage",
    "HttpTransport",
    "HttpTransportStats",
    "Message",
    "StdioServer",
    # Stdio (local, preferred)
    "StdioTransport",
    # HTTP (cloud deployment)
    "StreamingHttpTransport",
    "TransportStats",
]
