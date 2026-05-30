"""Progress notification relay for long-running MCP tool calls.

Pure pub/sub pattern for subscribing to and emitting progress events
from external MCP servers. No external dependencies.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """Structured progress notification from an external tool."""

    server_name: str
    tool_name: str
    progress_pct: float | None
    phase: str
    elapsed_seconds: float
    timestamp: datetime


class ProgressNotifier:
    """Subscribe to and relay MCP progress notifications.

    Pure pub/sub implementation with no external dependencies.
    Subscribers register for a specific server_name and receive
    all progress events emitted for that server.

    Usage::

        notifier = ProgressNotifier()
        sub_id = notifier.subscribe("recon", my_callback)
        notifier.emit(ProgressEvent(
            server_name="recon",
            tool_name="domain_lookup",
            progress_pct=50.0,
            phase="resolving",
            elapsed_seconds=2.5,
            timestamp=datetime.now(timezone.utc),
        ))
        notifier.unsubscribe(sub_id)
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, _Subscription] = {}
        self._server_subs: dict[str, list[str]] = defaultdict(list)

    def subscribe(
        self,
        server_name: str,
        callback: Callable[[ProgressEvent], None],
    ) -> str:
        """Subscribe to progress events for a server.

        Returns a unique subscription ID for later unsubscription.
        """
        sub_id = uuid.uuid4().hex[:12]
        self._subscriptions[sub_id] = _Subscription(
            id=sub_id,
            server_name=server_name,
            callback=callback,
        )
        self._server_subs[server_name].append(sub_id)
        logger.debug("Subscribed %s to server '%s'", sub_id, server_name)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a progress subscription.

        No-op if the subscription_id is not found.
        """
        sub = self._subscriptions.pop(subscription_id, None)
        if sub is None:
            return
        server_subs = self._server_subs.get(sub.server_name, [])
        if subscription_id in server_subs:
            server_subs.remove(subscription_id)
        logger.debug("Unsubscribed %s from server '%s'", subscription_id, sub.server_name)

    def emit(self, event: ProgressEvent) -> None:
        """Emit a progress event to all subscribers for that server.

        Dispatches to all callbacks registered for event.server_name.
        Exceptions in callbacks are logged but do not propagate.
        """
        sub_ids = self._server_subs.get(event.server_name, [])
        for sub_id in sub_ids:
            sub = self._subscriptions.get(sub_id)
            if sub is None:
                continue
            try:
                sub.callback(event)
            except Exception:
                logger.exception(
                    "Error in progress callback %s for server '%s'",
                    sub_id,
                    event.server_name,
                )

    @property
    def subscription_count(self) -> int:
        """Total number of active subscriptions."""
        return len(self._subscriptions)

    def subscriptions_for_server(self, server_name: str) -> int:
        """Number of active subscriptions for a specific server."""
        return len(self._server_subs.get(server_name, []))


@dataclass
class _Subscription:
    """Internal subscription record."""

    id: str
    server_name: str
    callback: Callable[[ProgressEvent], None]
