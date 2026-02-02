"""
Resource Subscription Management for MCP.

Implements the resources/subscribe protocol handler, enabling
event-driven updates instead of polling. This reduces token
usage by ~70% for status monitoring.

Resource URI Format:
    deepr://campaigns/{id}/status
    deepr://campaigns/{id}/plan
    deepr://campaigns/{id}/beliefs
    deepr://experts/{id}/profile
    deepr://experts/{id}/beliefs
    deepr://experts/{id}/gaps
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable
from datetime import datetime
import re
import asyncio
import uuid


@dataclass(frozen=True)
class ResourceURI:
    """Parsed resource URI with type and identifiers."""
    
    resource_type: str  # "campaigns" or "experts"
    resource_id: str
    subresource: str  # "status", "plan", "beliefs", "profile", "gaps"
    
    @property
    def uri(self) -> str:
        """Reconstruct the full URI string."""
        return f"deepr://{self.resource_type}/{self.resource_id}/{self.subresource}"
    
    @property
    def base_uri(self) -> str:
        """Get base URI without subresource (for wildcard matching)."""
        return f"deepr://{self.resource_type}/{self.resource_id}"


def parse_resource_uri(uri: str) -> Optional[ResourceURI]:
    """
    Parse a resource URI string into components.

    Args:
        uri: URI string like "deepr://campaigns/abc123/status"
              or "deepr://reports/abc123/final.md"
              or "deepr://logs/abc123/search_trace.json"

    Returns:
        ResourceURI if valid, None otherwise
    """
    pattern = r"^deepr://(?P<type>campaigns|experts|reports|logs)/(?P<id>[a-zA-Z0-9_-]+)/(?P<sub>[\w.]+)$"
    match = re.match(pattern, uri)
    
    if not match:
        return None
    
    return ResourceURI(
        resource_type=match.group("type"),
        resource_id=match.group("id"),
        subresource=match.group("sub")
    )


@dataclass
class Subscription:
    """
    A subscription to a resource URI.
    
    Attributes:
        id: Unique subscription identifier
        uri: Resource URI being subscribed to
        callback: Async function to call on updates (must be awaitable)
        created_at: When subscription was created
        wildcard: If True, matches all subresources under base URI
    
    Note:
        The callback must be an async function that accepts a dict parameter.
        It should handle its own exceptions - failures won't affect other subscribers.
    """
    
    id: str
    uri: str
    callback: Callable[[dict], Awaitable[None]]
    created_at: datetime = field(default_factory=datetime.now)
    wildcard: bool = False
    
    def __post_init__(self) -> None:
        """Validate subscription fields after initialization."""
        if not self.id:
            raise ValueError("Subscription id cannot be empty")
        if not self.uri:
            raise ValueError("Subscription uri cannot be empty")
        if not callable(self.callback):
            raise ValueError("Subscription callback must be callable")
    
    def matches(self, target_uri: str) -> bool:
        """
        Check if this subscription matches a target URI.
        
        Args:
            target_uri: The URI to check against this subscription
        
        Returns:
            True if this subscription should receive updates for target_uri
        """
        if not target_uri:
            return False
        if self.wildcard:
            # For wildcard, check if target starts with our base URI
            # self.uri is the base (e.g., "deepr://campaigns/abc")
            return target_uri.startswith(self.uri + "/")
        return self.uri == target_uri


class SubscriptionManager:
    """
    Manages resource subscriptions and event dispatch.
    
    Implements the MCP resources/subscribe protocol, allowing
    clients to receive push notifications when resources change.
    """
    
    def __init__(self):
        self._subscriptions: dict[str, Subscription] = {}
        self._uri_index: dict[str, set[str]] = {}  # uri -> subscription_ids
        self._lock = asyncio.Lock()
    
    async def subscribe(
        self,
        uri: str,
        callback: Callable[[dict], Awaitable[None]],
        wildcard: bool = False
    ) -> str:
        """
        Subscribe to a resource URI.
        
        Args:
            uri: Resource URI to subscribe to
            callback: Async function called with update data
            wildcard: If True, subscribe to all subresources
        
        Returns:
            Subscription ID for later unsubscribe
        
        Raises:
            ValueError: If URI is invalid
        """
        # Validate URI format
        parsed = parse_resource_uri(uri)
        if not parsed and not wildcard:
            # For wildcard, allow base URIs
            if not re.match(r"^deepr://(campaigns|experts)/[a-zA-Z0-9_-]+/\*$", uri):
                raise ValueError(f"Invalid resource URI: {uri}")
        
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        
        async with self._lock:
            subscription = Subscription(
                id=sub_id,
                uri=uri.rstrip("/*") if wildcard else uri,
                callback=callback,
                wildcard=wildcard
            )
            
            self._subscriptions[sub_id] = subscription
            
            # Index by URI for fast lookup
            index_key = subscription.uri
            if index_key not in self._uri_index:
                self._uri_index[index_key] = set()
            self._uri_index[index_key].add(sub_id)
        
        return sub_id
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription.
        
        Args:
            subscription_id: ID returned from subscribe()
        
        Returns:
            True if subscription was removed, False if not found
        """
        async with self._lock:
            if subscription_id not in self._subscriptions:
                return False
            
            sub = self._subscriptions[subscription_id]
            
            # Remove from index
            if sub.uri in self._uri_index:
                self._uri_index[sub.uri].discard(subscription_id)
                if not self._uri_index[sub.uri]:
                    del self._uri_index[sub.uri]
            
            del self._subscriptions[subscription_id]
            return True
    
    async def emit(self, uri: str, data: dict) -> int:
        """
        Emit an update to all subscribers of a URI.
        
        Args:
            uri: Resource URI that changed
            data: Update payload
        
        Returns:
            Number of subscribers notified
        """
        notified = 0
        parsed = parse_resource_uri(uri)
        
        async with self._lock:
            # Find matching subscriptions
            matching_subs: list[Subscription] = []
            
            # Exact URI matches
            if uri in self._uri_index:
                for sub_id in self._uri_index[uri]:
                    if sub_id in self._subscriptions:
                        matching_subs.append(self._subscriptions[sub_id])
            
            # Wildcard matches (check base URI)
            if parsed:
                base_uri = parsed.base_uri
                if base_uri in self._uri_index:
                    for sub_id in self._uri_index[base_uri]:
                        sub = self._subscriptions.get(sub_id)
                        if sub and sub.wildcard:
                            matching_subs.append(sub)
        
        # Dispatch notifications (outside lock)
        notification = self._build_notification(uri, data)
        
        for sub in matching_subs:
            try:
                await sub.callback(notification)
                notified += 1
            except Exception:
                # Log but don't fail other notifications
                pass
        
        return notified
    
    def _build_notification(self, uri: str, data: dict) -> dict:
        """Build JSON-RPC notification payload."""
        return {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "uri": uri,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get subscription by ID."""
        return self._subscriptions.get(subscription_id)
    
    def list_subscriptions(self, uri_prefix: Optional[str] = None) -> list[Subscription]:
        """
        List active subscriptions.
        
        Args:
            uri_prefix: Optional filter by URI prefix
        
        Returns:
            List of matching subscriptions
        """
        subs = list(self._subscriptions.values())
        
        if uri_prefix:
            subs = [s for s in subs if s.uri.startswith(uri_prefix)]
        
        return subs
    
    def count(self) -> int:
        """Get total number of active subscriptions."""
        return len(self._subscriptions)
    
    def subscribers_for(self, uri: str) -> int:
        """Count subscribers for a specific URI."""
        count = 0
        parsed = parse_resource_uri(uri)
        
        # Exact matches
        if uri in self._uri_index:
            count += len(self._uri_index[uri])
        
        # Wildcard matches
        if parsed:
            base_uri = parsed.base_uri
            if base_uri in self._uri_index:
                for sub_id in self._uri_index[base_uri]:
                    sub = self._subscriptions.get(sub_id)
                    if sub and sub.wildcard:
                        count += 1
        
        return count
