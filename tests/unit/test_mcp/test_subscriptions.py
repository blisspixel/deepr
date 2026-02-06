"""
Tests for MCP Resource Subscriptions.

Validates: Requirements 3B.1, 3B.2, 3B.4
"""

import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.subscriptions import (
    Subscription,
    SubscriptionManager,
    parse_resource_uri,
)


class TestResourceURI:
    """Test ResourceURI parsing and validation."""

    def test_parse_campaign_status(self):
        """Parse campaign status URI."""
        uri = parse_resource_uri("deepr://campaigns/abc123/status")

        assert uri is not None
        assert uri.resource_type == "campaigns"
        assert uri.resource_id == "abc123"
        assert uri.subresource == "status"

    def test_parse_campaign_plan(self):
        """Parse campaign plan URI."""
        uri = parse_resource_uri("deepr://campaigns/job_xyz/plan")

        assert uri is not None
        assert uri.resource_type == "campaigns"
        assert uri.resource_id == "job_xyz"
        assert uri.subresource == "plan"

    def test_parse_campaign_beliefs(self):
        """Parse campaign beliefs URI."""
        uri = parse_resource_uri("deepr://campaigns/test-job/beliefs")

        assert uri is not None
        assert uri.subresource == "beliefs"

    def test_parse_expert_profile(self):
        """Parse expert profile URI."""
        uri = parse_resource_uri("deepr://experts/tech_expert/profile")

        assert uri is not None
        assert uri.resource_type == "experts"
        assert uri.resource_id == "tech_expert"
        assert uri.subresource == "profile"

    def test_parse_expert_beliefs(self):
        """Parse expert beliefs URI."""
        uri = parse_resource_uri("deepr://experts/finance/beliefs")

        assert uri is not None
        assert uri.subresource == "beliefs"

    def test_parse_expert_gaps(self):
        """Parse expert gaps URI."""
        uri = parse_resource_uri("deepr://experts/domain_expert/gaps")

        assert uri is not None
        assert uri.subresource == "gaps"

    def test_invalid_uri_returns_none(self):
        """Invalid URIs should return None."""
        assert parse_resource_uri("invalid") is None
        assert parse_resource_uri("http://example.com") is None
        assert parse_resource_uri("deepr://unknown/id/sub") is None
        assert parse_resource_uri("deepr://campaigns/") is None
        assert parse_resource_uri("") is None

    def test_uri_reconstruction(self):
        """URI should reconstruct correctly."""
        original = "deepr://campaigns/abc123/status"
        parsed = parse_resource_uri(original)

        assert parsed.uri == original

    def test_base_uri(self):
        """Base URI should exclude subresource."""
        uri = parse_resource_uri("deepr://campaigns/abc123/status")

        assert uri.base_uri == "deepr://campaigns/abc123"


class TestSubscription:
    """Test Subscription dataclass."""

    def test_exact_match(self):
        """Subscription should match exact URI."""

        async def callback(data):
            pass

        sub = Subscription(id="sub_1", uri="deepr://campaigns/abc/status", callback=callback)

        assert sub.matches("deepr://campaigns/abc/status")
        assert not sub.matches("deepr://campaigns/abc/plan")
        assert not sub.matches("deepr://campaigns/xyz/status")

    def test_wildcard_match(self):
        """Wildcard subscription should match all subresources."""

        async def callback(data):
            pass

        sub = Subscription(id="sub_1", uri="deepr://campaigns/abc", callback=callback, wildcard=True)

        assert sub.matches("deepr://campaigns/abc/status")
        assert sub.matches("deepr://campaigns/abc/plan")
        assert sub.matches("deepr://campaigns/abc/beliefs")
        assert not sub.matches("deepr://campaigns/xyz/status")


class TestSubscriptionManager:
    """Test SubscriptionManager functionality."""

    @pytest.fixture
    def manager(self):
        return SubscriptionManager()

    @pytest.mark.asyncio
    async def test_subscribe_returns_id(self, manager):
        """Subscribe should return a subscription ID."""

        async def callback(data):
            pass

        sub_id = await manager.subscribe("deepr://campaigns/abc/status", callback)

        assert sub_id is not None
        assert sub_id.startswith("sub_")

    @pytest.mark.asyncio
    async def test_subscribe_invalid_uri_raises(self, manager):
        """Subscribe with invalid URI should raise ValueError."""

        async def callback(data):
            pass

        with pytest.raises(ValueError):
            await manager.subscribe("invalid_uri", callback)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(self, manager):
        """Unsubscribe should remove the subscription."""

        async def callback(data):
            pass

        sub_id = await manager.subscribe("deepr://campaigns/abc/status", callback)

        assert manager.count() == 1

        result = await manager.unsubscribe(sub_id)

        assert result is True
        assert manager.count() == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_returns_false(self, manager):
        """Unsubscribe nonexistent ID should return False."""
        result = await manager.unsubscribe("nonexistent_id")

        assert result is False

    @pytest.mark.asyncio
    async def test_emit_notifies_subscribers(self, manager):
        """Emit should notify all matching subscribers."""
        received = []

        async def callback(data):
            received.append(data)

        await manager.subscribe("deepr://campaigns/abc/status", callback)

        count = await manager.emit("deepr://campaigns/abc/status", {"phase": "executing", "progress": 0.5})

        assert count == 1
        assert len(received) == 1
        assert received[0]["params"]["data"]["phase"] == "executing"

    @pytest.mark.asyncio
    async def test_emit_notification_format(self, manager):
        """Emitted notification should follow JSON-RPC format."""
        received = []

        async def callback(data):
            received.append(data)

        await manager.subscribe("deepr://campaigns/abc/status", callback)

        await manager.emit("deepr://campaigns/abc/status", {"test": "data"})

        notification = received[0]

        assert notification["jsonrpc"] == "2.0"
        assert notification["method"] == "notifications/resources/updated"
        assert "params" in notification
        assert notification["params"]["uri"] == "deepr://campaigns/abc/status"
        assert "timestamp" in notification["params"]

    @pytest.mark.asyncio
    async def test_emit_to_multiple_subscribers(self, manager):
        """Emit should notify all subscribers of a URI."""
        received_1 = []
        received_2 = []

        async def callback_1(data):
            received_1.append(data)

        async def callback_2(data):
            received_2.append(data)

        await manager.subscribe("deepr://campaigns/abc/status", callback_1)
        await manager.subscribe("deepr://campaigns/abc/status", callback_2)

        count = await manager.emit("deepr://campaigns/abc/status", {"phase": "completed"})

        assert count == 2
        assert len(received_1) == 1
        assert len(received_2) == 1

    @pytest.mark.asyncio
    async def test_emit_wildcard_subscription(self, manager):
        """Emit should notify wildcard subscribers."""
        received = []

        async def callback(data):
            received.append(data)

        await manager.subscribe("deepr://campaigns/abc/*", callback, wildcard=True)

        # Should receive all subresource updates
        await manager.emit("deepr://campaigns/abc/status", {"type": "status"})
        await manager.emit("deepr://campaigns/abc/plan", {"type": "plan"})
        await manager.emit("deepr://campaigns/abc/beliefs", {"type": "beliefs"})

        # Should not receive updates for different campaign
        await manager.emit("deepr://campaigns/xyz/status", {"type": "other"})

        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_subscribers_for_count(self, manager):
        """subscribers_for should count correctly."""

        async def callback(data):
            pass

        await manager.subscribe("deepr://campaigns/abc/status", callback)
        await manager.subscribe("deepr://campaigns/abc/status", callback)
        await manager.subscribe("deepr://campaigns/xyz/status", callback)

        assert manager.subscribers_for("deepr://campaigns/abc/status") == 2
        assert manager.subscribers_for("deepr://campaigns/xyz/status") == 1
        assert manager.subscribers_for("deepr://campaigns/other/status") == 0

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, manager):
        """list_subscriptions should return all or filtered subscriptions."""

        async def callback(data):
            pass

        await manager.subscribe("deepr://campaigns/abc/status", callback)
        await manager.subscribe("deepr://experts/tech/profile", callback)

        all_subs = manager.list_subscriptions()
        assert len(all_subs) == 2

        campaign_subs = manager.list_subscriptions("deepr://campaigns")
        assert len(campaign_subs) == 1

        expert_subs = manager.list_subscriptions("deepr://experts")
        assert len(expert_subs) == 1


class TestPropertyBased:
    """Property-based tests for subscriptions."""

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_valid_campaign_uri_parses(self, job_id: str):
        """
        Property: Any valid job_id should produce parseable campaign URI.
        Validates: Requirements 3B.1
        """
        assume(job_id.strip())

        for subresource in ["status", "plan", "beliefs"]:
            uri = f"deepr://campaigns/{job_id}/{subresource}"
            parsed = parse_resource_uri(uri)

            assert parsed is not None
            assert parsed.resource_id == job_id
            assert parsed.subresource == subresource

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_valid_expert_uri_parses(self, expert_id: str):
        """
        Property: Any valid expert_id should produce parseable expert URI.
        Validates: Requirements 4B.1
        """
        assume(expert_id.strip())

        for subresource in ["profile", "beliefs", "gaps"]:
            uri = f"deepr://experts/{expert_id}/{subresource}"
            parsed = parse_resource_uri(uri)

            assert parsed is not None
            assert parsed.resource_id == expert_id
            assert parsed.subresource == subresource

    @pytest.mark.asyncio
    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=20)
    async def test_emit_notifies_all_subscribers(self, subscriber_count: int):
        """
        Property: Emit should notify exactly the number of subscribers.
        Validates: Requirements 3B.2
        """
        manager = SubscriptionManager()
        received_counts = [0] * subscriber_count

        async def make_callback(idx):
            async def callback(data):
                received_counts[idx] += 1

            return callback

        # Subscribe multiple callbacks
        for i in range(subscriber_count):
            cb = await make_callback(i)
            await manager.subscribe("deepr://campaigns/test/status", cb)

        # Emit once
        count = await manager.emit("deepr://campaigns/test/status", {"test": True})

        assert count == subscriber_count
        assert all(c == 1 for c in received_counts)


class TestSubscriptionValidation:
    """Test defensive validation in Subscription class."""

    def test_subscription_rejects_empty_id(self):
        """Subscription should reject empty id."""

        async def callback(data):
            pass

        with pytest.raises(ValueError, match="id cannot be empty"):
            Subscription(id="", uri="deepr://campaigns/abc/status", callback=callback)

    def test_subscription_rejects_empty_uri(self):
        """Subscription should reject empty uri."""

        async def callback(data):
            pass

        with pytest.raises(ValueError, match="uri cannot be empty"):
            Subscription(id="sub_1", uri="", callback=callback)

    def test_subscription_rejects_non_callable(self):
        """Subscription should reject non-callable callback."""
        with pytest.raises(ValueError, match="callback must be callable"):
            Subscription(id="sub_1", uri="deepr://campaigns/abc/status", callback="not_callable")

    def test_subscription_matches_rejects_empty_target(self):
        """Subscription.matches should return False for empty target."""

        async def callback(data):
            pass

        sub = Subscription(id="sub_1", uri="deepr://campaigns/abc/status", callback=callback)

        assert not sub.matches("")
        assert not sub.matches(None)
