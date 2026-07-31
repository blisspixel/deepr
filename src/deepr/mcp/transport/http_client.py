"""Outbound MCP HTTP client (release-blocked).

Extracted from ``deepr.mcp.transport.http`` so the server transport stays
under the file-size ceiling; ``HttpClient`` is still importable from there.
Every network-touching method refuses before opening a socket: remote MCP
service cost cannot be proven before dispatch, so outbound HTTP MCP stays
fail-closed (same posture as ``deepr.mcp.client``).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from deepr.mcp.http_client_policy import (
    MCPHttpDispatchBlockedError,
    validated_mcp_http_timeout,
    validated_remote_mcp_url,
)
from deepr.mcp.protocol_compat import HttpMessage


class HttpClient:
    """
    HTTP client for connecting to a remote MCP server.

    Used when Deepr runs as a remote service and Claude
    needs to connect to it over HTTP.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        auth_token: str | None = None,
    ):
        self._base_url = validated_remote_mcp_url(base_url)
        self._timeout = aiohttp.ClientTimeout(total=validated_mcp_http_timeout(timeout))
        self._auth_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None
        self._session: aiohttp.ClientSession | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._notification_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    def _auth_headers(self) -> dict[str, Any]:
        return {"Authorization": f"Bearer {self._auth_token}"} if self._auth_token else {}

    async def connect(self) -> None:
        """Refuse before creating a session or opening a socket."""
        raise MCPHttpDispatchBlockedError(
            "Outbound MCP HTTP clients are disabled because remote service cost cannot be proven before connection"
        )

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

        if self._session:
            await self._session.close()

    async def send(self, message: HttpMessage) -> HttpMessage | None:
        """Refuse every request before session access or POST."""
        del message
        raise MCPHttpDispatchBlockedError(
            "Outbound MCP HTTP requests are disabled because remote service cost cannot be proven before dispatch"
        )

    def on_notification(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Set handler for incoming notifications."""
        self._notification_handler = handler

    async def subscribe(self, subscriber_id: str | None = None) -> None:
        """Refuse SSE before task or socket creation."""
        del subscriber_id
        raise MCPHttpDispatchBlockedError(
            "Outbound MCP HTTP subscriptions are disabled because remote service cost cannot be proven before dispatch"
        )

    async def _stream_loop(self, url: str) -> None:
        """Refuse the internal SSE seam if called directly."""
        del url
        raise MCPHttpDispatchBlockedError(
            "Outbound MCP HTTP streaming is disabled because remote service cost cannot be proven before dispatch"
        )


__all__ = ["HttpClient"]
