"""Integration test: distillr source-ingestion flow.

Tests the distillr profile loading, auto-discovery, graceful skip when not
installed, per-call budget capping (distillr spends money, unlike free recon),
and knowledge absorption of corpus synthesis into academic findings.

Feature: first-party-tool-integrations (Phase 2b #2)
Mirrors tests/integration/test_recon_integration.py.
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
    DISTILLR_PROFILE_TEMPLATE,
    ConfigLoader,
    get_distillr_profile,
)
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile


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

    def record_event(self, profile_name: str, tool_name: str, cost: float, trace_id: str) -> None:
        self.events.append({"profile_name": profile_name, "tool_name": tool_name, "cost": cost, "trace_id": trace_id})


class TestDistillrProfileLoading:
    """Distillr profile loads from template and YAML."""

    def test_distillr_profile_from_template(self) -> None:
        profile = get_distillr_profile()
        assert profile.name == "distillr"
        assert profile.command == "distill-mcp"
        assert profile.args == []
        assert profile.transport == "stdio"
        assert profile.enabled is True
        assert profile.progress is True
        # Distillr spends money: a per-call cap must exist (recon is 0 = free).
        assert profile.budget_limit == 2.0
        # Only the free read-side tool auto-approves; ingestion needs approval.
        assert "list_topics" in profile.auto_approve
        assert "find_insights" in profile.auto_approve
        assert "list_topic_summary" in profile.auto_approve
        assert "okf_validate" in profile.auto_approve
        assert "papers" in profile.require_approval
        assert "ask" in profile.require_approval
        assert "find_insights_summary" in profile.require_approval
        assert "okf_export" in profile.require_approval
        assert "catch_up" in profile.require_approval  # the freshness/delta verb

    def test_distillr_template_matches_spec(self) -> None:
        assert DISTILLR_PROFILE_TEMPLATE["name"] == "distillr"
        assert DISTILLR_PROFILE_TEMPLATE["command"] == "distill-mcp"
        assert DISTILLR_PROFILE_TEMPLATE["budget_limit"] == 2.0
        assert DISTILLR_PROFILE_TEMPLATE["progress"] is True
        assert "list_topics" in DISTILLR_PROFILE_TEMPLATE["auto_approve"]  # free corpus inventory
        assert "find_insights" in DISTILLR_PROFILE_TEMPLATE["auto_approve"]  # free read-side corpus search
        assert "ask" in DISTILLR_PROFILE_TEMPLATE["require_approval"]

    def test_distillr_profile_from_yaml_config(self, tmp_path: Path) -> None:
        config_content = """\
profiles:
  - name: distillr
    command: distill-mcp
    transport: stdio
    enabled: true
    timeout: 900
    budget_limit: 2.0
    auto_approve: [find_insights]
    require_approval: [papers, learn_topic, site_batch, catch_up]
    progress: true
"""
        config_path = tmp_path / "integrations.yaml"
        config_path.write_text(config_content)

        profiles = ConfigLoader().load(config_path)

        distillr = next(p for p in profiles if p.name == "distillr")
        assert distillr.command == "distill-mcp"
        assert distillr.budget_limit == 2.0
        assert distillr.auto_approve == ["find_insights"]


class TestDistillrAutoDiscovery:
    """Auto-discovery wires distillr in when `distill-mcp` is on PATH."""

    def test_discovered_when_binary_present(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Simulate distill-mcp installed, recon not installed.
        monkeypatch.setattr(
            cfg.shutil,
            "which",
            lambda name: "/usr/bin/distill-mcp" if name == "distill-mcp" else None,
        )
        # Point at a non-existent config so only auto-discovery contributes.
        profiles = ConfigLoader().load(tmp_path / "nope.yaml")
        names = {p.name for p in profiles}
        assert "distillr" in names
        assert "recon" not in names

    def test_not_discovered_when_binary_absent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(cfg.shutil, "which", lambda *_a: None)
        profiles = ConfigLoader().load(tmp_path / "nope.yaml")
        assert all(p.name != "distillr" for p in profiles)

    def test_user_profile_takes_precedence(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Binary present, but the user defined their own distillr profile.
        monkeypatch.setattr(
            cfg.shutil,
            "which",
            lambda name: "/usr/bin/distill-mcp" if name == "distill-mcp" else None,
        )
        config_path = tmp_path / "integrations.yaml"
        config_path.write_text("profiles:\n  - name: distillr\n    command: distill-mcp\n    budget_limit: 9.0\n")
        profiles = ConfigLoader().load(config_path)
        distillr = [p for p in profiles if p.name == "distillr"]
        # Exactly one (no duplicate from auto-discovery), and it is the user's.
        assert len(distillr) == 1
        assert distillr[0].budget_limit == 9.0


class TestGracefulSkipWhenNotInstalled:
    """Pool tolerates a missing distill-mcp binary."""

    def test_pool_skips_missing_command_gracefully(self) -> None:
        pool = MCPClientPool()
        profile = MCPClientProfile(
            name="distillr-missing",
            command="definitely_not_a_real_distill_mcp_xyz_99",
            budget_limit=2.0,
        )
        pool.register(profile)

        async def _test() -> None:
            results = await pool.connect_all()
            assert "distillr-missing" in results
            assert results["distillr-missing"] is not None
            assert "not found" in results["distillr-missing"].lower()

        asyncio.run(_test())


class TestDistillrBudgetCapping:
    """Distillr per-call budget cap is enforced (key difference from recon)."""

    def _propagator(self) -> BudgetPropagator:
        return BudgetPropagator(budget_manager=MockBudgetManager(), cost_ledger=MockCostLedger())

    def test_call_within_cap_allowed(self) -> None:
        profile = get_distillr_profile()
        decision = self._propagator().check_budget(profile, estimated_cost=0.8, session_remaining=10.0)
        assert decision.allowed is True

    def test_call_over_per_call_cap_denied(self) -> None:
        profile = get_distillr_profile()  # budget_limit == 2.0
        decision = self._propagator().check_budget(profile, estimated_cost=3.0, session_remaining=10.0)
        assert decision.allowed is False
        assert "per-call limit" in decision.reason

    def test_budget_param_clamps_to_cap_and_session(self) -> None:
        propagator = self._propagator()
        profile = get_distillr_profile()
        assert propagator.get_budget_param(profile, session_remaining=10.0) == 2.0
        assert propagator.get_budget_param(profile, session_remaining=0.5) == 0.5


class TestKnowledgeAbsorptionFromDistillr:
    """Corpus synthesis is absorbed as academic knowledge with provenance."""

    def test_synthesis_response_produces_academic_finding(self) -> None:
        absorber = KnowledgeAbsorber()
        payload = {
            "topic": "embedded_finance",
            "papers_ingested": 12,
            "synthesis_path": "library/topics/embedded_finance/Paper_Synthesis.md",
            "corpus_synthesis_path": "library/topics/embedded_finance/Corpus_Synthesis.md",
            "insights": ["Platform economics favor network effects", "Regulatory moats matter"],
            "cost": 0.82,
        }
        findings = absorber.categorize_distillr_response(payload, tool="distillr/papers")

        assert len(findings) >= 3  # synthesis summary + 2 insights
        assert all(f.category == "academic" for f in findings)
        assert all(f.confidence >= 0.7 for f in findings)
        # The headline finding cites the synthesis artifact for provenance.
        headline = findings[0]
        assert "embedded_finance" in headline.text
        assert headline.raw_data.get("synthesis") == payload["corpus_synthesis_path"]

    def test_topic_inferred_from_payload(self) -> None:
        absorber = KnowledgeAbsorber()
        findings = absorber.categorize_distillr_response(
            {"topic": "llm_inference", "papers_ingested": 3, "synthesis_path": "s.md"}
        )
        assert findings
        assert "llm_inference" in findings[0].text

    def test_query_library_metadata_falls_back_to_summary(self) -> None:
        absorber = KnowledgeAbsorber()
        findings = absorber.categorize_distillr_response(
            {"summary": "No matching corpus topics found"}, topic="quantum_widgets"
        )
        assert len(findings) == 1
        assert findings[0].category == "academic"
        assert findings[0].confidence >= 0.7

    def test_result_unwrapped_from_proxy_wrapper(self) -> None:
        absorber = KnowledgeAbsorber()
        payload = {"result": {"topic": "x", "papers_ingested": 1, "synthesis_path": "s.md"}}
        findings = absorber.categorize_distillr_response(payload)
        assert findings
        assert findings[0].category == "academic"

    def test_non_dict_payload_returns_empty(self) -> None:
        absorber = KnowledgeAbsorber()
        assert absorber.categorize_distillr_response(None) == []  # type: ignore[arg-type]
