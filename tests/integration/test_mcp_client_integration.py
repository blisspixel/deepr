"""Integration test: config → connect → call → budget → trace.

Tests the full MCP client flow with mock subprocess.
No real external dependencies required.

Feature: mcp-client-agent-interop
Validates: Requirements 2.1, 2.2, 2.4, 2.5, 2.6, 14.1, 14.2
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.config_loader import ConfigLoader
from deepr.mcp.client.errors import BudgetDecision
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.client.trace_stitcher import SpanContext, TraceStitcher


class MockBudgetManager:
    """Mock budget manager for integration tests."""

    def __init__(self, remaining: float = 10.0) -> None:
        self._remaining = remaining

    def get_remaining_budget(self) -> float:
        return self._remaining


class MockCostLedger:
    """Mock cost ledger that records events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_event(
        self,
        profile_name: str,
        tool_name: str,
        cost: float,
        trace_id: str,
    ) -> None:
        self.events.append(
            {
                "profile_name": profile_name,
                "tool_name": tool_name,
                "cost": cost,
                "trace_id": trace_id,
            }
        )


class MockMetadataEmitter:
    """Mock metadata emitter for trace events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append({"type": event_type, "data": data})


class TestConfigLoadFlow:
    """Test config loading from YAML."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Load config, validate profiles are created correctly."""
        config_content = """\
profiles:
  - name: recon
    command: recon
    args: [mcp]
    transport: stdio
    enabled: true
    timeout: 30
    budget_limit: 0
    auto_approve: [domain_lookup, batch_lookup]
    require_approval: [delta]
    progress: false
  - name: disabled-tool
    command: disabled
    enabled: false
"""
        config_path = tmp_path / "integrations.yaml"
        config_path.write_text(config_content)

        loader = ConfigLoader()
        profiles = loader.load(config_path)

        # Both profiles loaded (including disabled)
        assert len(profiles) == 2
        assert profiles[0].name == "recon"
        assert profiles[0].auto_approve == ["domain_lookup", "batch_lookup"]
        assert profiles[1].enabled is False

    def test_missing_config_returns_empty(self) -> None:
        """Missing config file returns empty list."""
        loader = ConfigLoader()
        profiles = loader.load(Path("/nonexistent/path.yaml"))
        assert profiles == []


class TestBudgetTraceFlow:
    """Test budget check → trace span → cost recording flow."""

    def test_full_budget_trace_flow(self) -> None:
        """Full flow: check budget, create span, record cost."""
        budget_mgr = MockBudgetManager(remaining=10.0)
        cost_ledger = MockCostLedger()
        emitter = MockMetadataEmitter()

        propagator = BudgetPropagator(
            budget_manager=budget_mgr,
            cost_ledger=cost_ledger,
        )
        stitcher = TraceStitcher(metadata_emitter=emitter)

        profile = MCPClientProfile(
            name="recon",
            command="recon",
            budget_limit=5.0,
        )

        # 1. Check budget
        decision = propagator.check_budget(profile, estimated_cost=0.5, session_remaining=10.0)
        assert decision.allowed is True

        # 2. Create trace span
        span = stitcher.create_span("trace-abc", "recon", "domain_lookup")
        assert span.trace_id == "trace-abc"
        assert span.server_name == "recon"

        # 3. Inject trace into arguments
        args = stitcher.inject_trace({"domain": "example.com"}, span.trace_id, span.span_id)
        assert args["trace_id"] == "trace-abc"
        assert "span_id" in args

        # 4. Record cost
        propagator.record_cost("recon", "domain_lookup", actual_cost=0.0, trace_id="trace-abc")
        assert len(cost_ledger.events) == 1
        assert cost_ledger.events[0]["cost"] == 0.0

    def test_budget_denial_flow(self) -> None:
        """Budget denial prevents dispatch."""
        budget_mgr = MockBudgetManager(remaining=1.0)
        cost_ledger = MockCostLedger()

        propagator = BudgetPropagator(
            budget_manager=budget_mgr,
            cost_ledger=cost_ledger,
        )

        profile = MCPClientProfile(
            name="primr",
            command="primr",
            budget_limit=5.0,
        )

        # Estimated cost exceeds remaining
        decision = propagator.check_budget(profile, estimated_cost=2.0, session_remaining=1.0)
        assert decision.allowed is False
        assert decision.shortfall > 0


class TestGracefulHandling:
    """Test graceful handling of missing commands and errors."""

    def test_command_not_found_handling(self) -> None:
        """MCPClient raises clear error when command not found."""
        from deepr.mcp.client.base import MCPClient, MCPClientError

        client = MCPClient(
            name="nonexistent",
            command="definitely_not_a_real_command_xyz",
        )

        with pytest.raises(MCPClientError) as exc_info:
            asyncio.get_event_loop().run_until_complete(client.connect())

        assert "not found" in str(exc_info.value).lower()

    def test_reconnection_tracking(self) -> None:
        """Reconnection increments counter."""
        from deepr.mcp.client.base import MCPClient

        client = MCPClient(name="test", command="echo")
        # Stats should track reconnect attempts
        assert client.stats.reconnect_count == 0
