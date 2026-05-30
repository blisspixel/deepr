"""Integration test: primr strategic company-intelligence flow.

Tests the primr profile loading, auto-discovery, graceful skip when not
installed, approval gating (every paid tool requires approval; only free
read-side tools auto-approve), the higher per-call budget cap, and multi-category
knowledge absorption (infrastructure + strategic).

Feature: first-party-tool-integrations (Phase 2b #3)
Mirrors tests/integration/test_distillr_integration.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from deepr.experts.skills.knowledge_absorber import KnowledgeAbsorber
from deepr.mcp.client import config_loader as cfg
from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.config_loader import (
    PRIMR_PROFILE_TEMPLATE,
    ConfigLoader,
    get_primr_profile,
)
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile


class MockBudgetManager:
    def __init__(self, remaining: float = 20.0) -> None:
        self._remaining = remaining

    def get_remaining_budget(self) -> float:
        return self._remaining


class MockCostLedger:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_event(self, profile_name: str, tool_name: str, cost: float, trace_id: str) -> None:
        self.events.append(
            {"profile_name": profile_name, "tool_name": tool_name, "cost": cost, "trace_id": trace_id}
        )


class TestPrimrProfileLoading:
    def test_primr_profile_from_template(self) -> None:
        profile = get_primr_profile()
        assert profile.name == "primr"
        assert profile.command == "primr-mcp"
        assert profile.args == ["--stdio"]
        assert profile.transport == "stdio"
        assert profile.enabled is True
        assert profile.progress is True
        assert profile.budget_limit == 5.0
        assert profile.timeout == 3600
        # Approval model: only free read-side tools auto-approve.
        assert set(profile.auto_approve) == {"estimate_run", "check_jobs", "doctor"}
        assert "research_company" in profile.require_approval
        assert "batch_analyze" in profile.require_approval

    def test_primr_template_matches_spec(self) -> None:
        assert PRIMR_PROFILE_TEMPLATE["name"] == "primr"
        assert PRIMR_PROFILE_TEMPLATE["command"] == "primr-mcp"
        assert PRIMR_PROFILE_TEMPLATE["budget_limit"] == 5.0
        assert PRIMR_PROFILE_TEMPLATE["progress"] is True

    def test_primr_profile_from_yaml_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "integrations.yaml"
        config_path.write_text(
            "profiles:\n"
            "  - name: primr\n"
            "    command: primr-mcp\n"
            "    args: ['--stdio']\n"
            "    timeout: 3600\n"
            "    budget_limit: 5.0\n"
            "    auto_approve: [estimate_run, check_jobs, doctor]\n"
            "    require_approval: [research_company, batch_analyze]\n"
            "    progress: true\n"
        )
        profiles = ConfigLoader().load(config_path)
        primr = next(p for p in profiles if p.name == "primr")
        assert primr.command == "primr-mcp"
        assert primr.budget_limit == 5.0


class TestPrimrAutoDiscovery:
    def test_discovered_when_binary_present(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            cfg.shutil,
            "which",
            lambda name: "/usr/bin/primr-mcp" if name == "primr-mcp" else None,
        )
        profiles = ConfigLoader().load(tmp_path / "nope.yaml")
        names = {p.name for p in profiles}
        assert "primr" in names
        assert "recon" not in names and "distillr" not in names


class TestGracefulSkipWhenNotInstalled:
    def test_pool_skips_missing_command_gracefully(self) -> None:
        pool = MCPClientPool()
        pool.register(
            MCPClientProfile(
                name="primr-missing",
                command="definitely_not_a_real_primr_mcp_xyz_99",
                budget_limit=5.0,
            )
        )

        async def _test() -> None:
            results = await pool.connect_all()
            assert "primr-missing" in results
            assert results["primr-missing"] is not None
            assert "not found" in results["primr-missing"].lower()

        asyncio.run(_test())


class TestPrimrBudgetCapping:
    def _propagator(self) -> BudgetPropagator:
        return BudgetPropagator(budget_manager=MockBudgetManager(), cost_ledger=MockCostLedger())

    def test_call_within_cap_allowed(self) -> None:
        decision = self._propagator().check_budget(get_primr_profile(), estimated_cost=0.74, session_remaining=20.0)
        assert decision.allowed is True

    def test_call_over_per_call_cap_denied(self) -> None:
        decision = self._propagator().check_budget(get_primr_profile(), estimated_cost=6.0, session_remaining=20.0)
        assert decision.allowed is False
        assert "per-call limit" in decision.reason

    def test_budget_param_clamps_to_cap(self) -> None:
        propagator = self._propagator()
        assert propagator.get_budget_param(get_primr_profile(), session_remaining=20.0) == 5.0
        assert propagator.get_budget_param(get_primr_profile(), session_remaining=1.5) == 1.5


class TestKnowledgeAbsorptionFromPrimr:
    def test_full_brief_produces_infrastructure_and_strategic(self) -> None:
        absorber = KnowledgeAbsorber()
        payload = {
            "company": "Stripe",
            "domain": "stripe.com",
            "report_path": "out/Stripe.md",
            "sections": 23,
            "citations": 48,
            "recon_summary": {"provider": "AWS", "services_count": 14},
            "hiring_signals": {"total_roles": 127, "ml_roles": 52, "top_initiatives": ["fraud ML"]},
            "cost": 0.74,
            "duration_minutes": 38,
        }
        findings = absorber.categorize_primr_response(payload)
        cats = {f.category for f in findings}
        assert {"infrastructure", "strategic"} <= cats
        # Infrastructure (recon-derived) carries higher confidence than synthesis.
        infra = [f for f in findings if f.category == "infrastructure"]
        strat = [f for f in findings if f.category == "strategic"]
        assert infra[0].confidence > strat[0].confidence
        # Provenance to the report artifact is retained.
        assert findings[0].raw_data.get("report_path") == "out/Stripe.md"

    def test_metadata_only_falls_back(self) -> None:
        absorber = KnowledgeAbsorber()
        findings = absorber.categorize_primr_response({"summary": "queued"}, company="acme")
        assert len(findings) == 1
        assert findings[0].category == "strategic"
