"""Integration test: recon proof-of-concept flow.

Tests the recon profile loading, graceful skip when not installed,
mock subprocess tool calls, and knowledge absorption.

Feature: mcp-client-agent-interop
Validates: Requirements 15.1, 15.3, 15.4, 15.5
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from deepr.experts.skills.knowledge_absorber import KnowledgeAbsorber
from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult
from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.config_loader import (
    RECON_PROFILE_TEMPLATE,
    ConfigLoader,
    get_recon_profile,
)
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.client.trace_stitcher import TraceStitcher


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
        self.events.append({
            "profile_name": profile_name,
            "tool_name": tool_name,
            "cost": cost,
            "trace_id": trace_id,
        })


class MockMetadataEmitter:
    """Mock metadata emitter for trace events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append({"type": event_type, "data": data})


class TestReconProfileLoading:
    """Test recon profile loads from config."""

    def test_recon_profile_from_template(self) -> None:
        """get_recon_profile() returns a valid MCPClientProfile."""
        profile = get_recon_profile()
        assert profile.name == "recon"
        assert profile.command == "recon"
        assert profile.args == ["mcp"]
        assert profile.budget_limit == 0
        assert profile.auto_approve == ["domain_lookup", "batch_lookup"]
        assert profile.require_approval == ["delta"]
        assert profile.transport == "stdio"
        assert profile.enabled is True

    def test_recon_profile_from_yaml_config(self, tmp_path: Path) -> None:
        """Recon profile loads correctly from YAML config file."""
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
"""
        config_path = tmp_path / "integrations.yaml"
        config_path.write_text(config_content)

        loader = ConfigLoader()
        profiles = loader.load(config_path)

        assert len(profiles) == 1
        recon = profiles[0]
        assert recon.name == "recon"
        assert recon.command == "recon"
        assert recon.args == ["mcp"]
        assert recon.budget_limit == 0
        assert recon.auto_approve == ["domain_lookup", "batch_lookup"]

    def test_recon_template_matches_spec(self) -> None:
        """RECON_PROFILE_TEMPLATE has all required fields per spec."""
        assert RECON_PROFILE_TEMPLATE["name"] == "recon"
        assert RECON_PROFILE_TEMPLATE["command"] == "recon"
        assert RECON_PROFILE_TEMPLATE["args"] == ["mcp"]
        assert RECON_PROFILE_TEMPLATE["budget_limit"] == 0
        assert RECON_PROFILE_TEMPLATE["auto_approve"] == ["domain_lookup", "batch_lookup"]


class TestGracefulSkipWhenNotInstalled:
    """Test graceful skip when recon command is not found."""

    def test_pool_skips_missing_command_gracefully(self) -> None:
        """Pool connect_all gracefully handles missing command."""
        pool = MCPClientPool()
        # Use a guaranteed non-existent command (not 'recon' which may exist on some systems)
        profile = MCPClientProfile(
            name="recon-missing",
            command="definitely_not_a_real_recon_command_xyz_99",
            args=["mcp"],
            budget_limit=0,
            auto_approve=["domain_lookup", "batch_lookup"],
        )
        pool.register(profile)

        async def _test() -> None:
            results = await pool.connect_all()
            # Should have an error for the missing command
            assert "recon-missing" in results
            assert results["recon-missing"] is not None
            assert "not found" in results["recon-missing"].lower()

        asyncio.get_event_loop().run_until_complete(_test())

    def test_pool_continues_with_other_servers_when_one_missing(self) -> None:
        """Other servers still work when one is not installed."""
        pool = MCPClientPool()
        profile1 = MCPClientProfile(
            name="missing-tool-1",
            command="not_installed_tool_abc_123",
        )
        pool.register(profile1)

        profile2 = MCPClientProfile(
            name="missing-tool-2",
            command="also_not_installed_xyz_456",
        )
        pool.register(profile2)

        async def _test() -> None:
            results = await pool.connect_all()
            # Both should fail gracefully without crashing
            assert len(results) == 2
            assert results["missing-tool-1"] is not None
            assert results["missing-tool-2"] is not None

        asyncio.get_event_loop().run_until_complete(_test())

    def test_client_raises_clear_error_for_missing_command(self) -> None:
        """MCPClient raises MCPClientError with clear message."""
        client = MCPClient(
            name="recon-test",
            command="definitely_not_a_real_recon_command_xyz_99",
            args=["mcp"],
        )

        with pytest.raises(MCPClientError) as exc_info:
            asyncio.get_event_loop().run_until_complete(client.connect())

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.server_name == "recon-test"


class TestReconDomainLookupWithMock:
    """Test domain_lookup call with mock recon subprocess."""

    def test_domain_lookup_records_zero_cost(self) -> None:
        """Recon calls record cost as $0.00."""
        budget_mgr = MockBudgetManager(remaining=10.0)
        cost_ledger = MockCostLedger()
        emitter = MockMetadataEmitter()

        propagator = BudgetPropagator(
            budget_manager=budget_mgr,
            cost_ledger=cost_ledger,
        )
        stitcher = TraceStitcher(metadata_emitter=emitter)

        profile = get_recon_profile()

        # Budget check for free tool
        decision = propagator.check_budget(
            profile, estimated_cost=0.0, session_remaining=10.0
        )
        assert decision.allowed is True

        # Create trace span
        span = stitcher.create_span("trace-recon-1", "recon", "domain_lookup")
        assert span.server_name == "recon"
        assert span.tool_name == "domain_lookup"

        # Simulate tool result
        result = MCPToolResult(
            content=json.dumps({
                "provider": "cloudflare",
                "services": ["cdn", "dns"],
                "related_domains": ["example.net"],
                "insights": ["Uses Cloudflare CDN"],
            }),
            raw={"cost": 0.0},
            server_name="recon",
            tool_name="domain_lookup",
            trace_id="trace-recon-1",
        )

        # Record cost ($0.00 for recon)
        propagator.record_cost("recon", "domain_lookup", actual_cost=0.0, trace_id="trace-recon-1")
        assert len(cost_ledger.events) == 1
        assert cost_ledger.events[0]["cost"] == 0.0
        assert cost_ledger.events[0]["profile_name"] == "recon"

        # Complete span
        stitcher.complete_span(span, result, cost=0.0)
        assert len(emitter.events) == 1
        assert emitter.events[0]["data"]["cost"] == 0.0
        assert emitter.events[0]["data"]["server_name"] == "recon"

    def test_domain_lookup_with_budget_limit_zero(self) -> None:
        """Budget limit of 0 means unlimited per-call (free tool)."""
        budget_mgr = MockBudgetManager(remaining=0.5)
        cost_ledger = MockCostLedger()

        propagator = BudgetPropagator(
            budget_manager=budget_mgr,
            cost_ledger=cost_ledger,
        )

        profile = get_recon_profile()
        assert profile.budget_limit == 0  # Free tool

        # Even with low session budget, free tool is allowed
        decision = propagator.check_budget(
            profile, estimated_cost=0.0, session_remaining=0.5
        )
        assert decision.allowed is True


class TestKnowledgeAbsorptionFromRecon:
    """Test knowledge absorption produces high-confidence DNS beliefs."""

    def test_recon_response_produces_dns_beliefs(self) -> None:
        """Recon JSON response produces high-confidence infrastructure findings."""
        absorber = KnowledgeAbsorber()

        recon_response = {
            "provider": "cloudflare",
            "services": [
                {"text": "CDN service detected", "confidence": 0.95},
                {"text": "DNS hosting on Cloudflare"},
            ],
            "related_domains": [
                {"text": "example.net is related"},
            ],
            "insights": [
                {"text": "Uses enterprise Cloudflare plan"},
            ],
        }

        findings = absorber.absorb(
            recon_response,
            source_type="DNS",
            source_tool="recon/domain_lookup",
        )

        assert len(findings) > 0
        for finding in findings:
            assert finding.category == "infrastructure"
            assert finding.confidence >= 0.8
            assert finding.source_type == "DNS"
            assert finding.source_tool == "recon/domain_lookup"

    def test_recon_response_with_flat_items(self) -> None:
        """Recon response with dict items still produces findings."""
        absorber = KnowledgeAbsorber()

        recon_response = {
            "services": [
                {"text": "cdn"},
                {"text": "dns"},
                {"text": "email"},
            ],
            "provider": "aws",
        }

        findings = absorber.absorb(
            recon_response,
            source_type="DNS",
            source_tool="recon/domain_lookup",
        )

        assert len(findings) > 0
        for finding in findings:
            assert finding.category == "infrastructure"
            assert finding.confidence >= 0.8
            assert finding.source_type == "DNS"

    def test_empty_recon_response_still_produces_finding(self) -> None:
        """Even empty-ish response produces at least one finding."""
        absorber = KnowledgeAbsorber()

        recon_response = {"summary": "No DNS records found"}

        findings = absorber.absorb(
            recon_response,
            source_type="DNS",
            source_tool="recon/domain_lookup",
        )

        assert len(findings) >= 1
        assert findings[0].category == "infrastructure"
        assert findings[0].confidence >= 0.8

    def test_categorize_dns_data(self) -> None:
        """DNS data is categorized as infrastructure."""
        absorber = KnowledgeAbsorber()

        data = {"source_type": "DNS", "provider": "cloudflare"}
        category = absorber.categorize(data)
        assert category == "infrastructure"

    def test_categorize_infers_from_keys(self) -> None:
        """Categorization infers infrastructure from DNS-related keys."""
        absorber = KnowledgeAbsorber()

        data = {"provider": "aws", "nameservers": ["ns1.aws.com"]}
        category = absorber.categorize(data)
        assert category == "infrastructure"
