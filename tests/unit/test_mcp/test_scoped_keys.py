"""Tests for scoped remote MCP API-key contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.security.scoped_keys import (
    RemoteMCPAuditEvent,
    RemoteMCPAuditLog,
    ScopedMCPKeyContext,
    ScopedMCPKeyStore,
    authorize_scoped_mcp_budget,
    authorize_scoped_mcp_rate_limit,
    authorize_scoped_mcp_tool_call,
    constrain_scoped_mcp_budget_arguments,
    estimate_scoped_mcp_tool_cost,
    requires_scoped_mcp_cost_estimate,
)
from deepr.mcp.security.tool_allowlist import (
    REMOTE_METERED_SPEND_METADATA_KEY,
    ResearchMode,
    ToolAllowlist,
    ToolCategory,
)


class TestScopedMCPKeyStore:
    def test_create_authenticate_and_revoke_key(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, record = store.create_key(
            "agent-alpha",
            mode=ResearchMode.READ_ONLY,
            expert_allowlist=["alpha"],
            budget_limit_usd=2.5,
            rate_limit_per_minute=12,
            secret="plain-secret",
        )

        assert secret == "plain-secret"
        assert record.key_id == "agent-alpha"
        assert "plain-secret" not in (tmp_path / "keys.json").read_text(encoding="utf-8")

        context = store.authenticate("plain-secret")
        assert context is not None
        assert context.key_id == "agent-alpha"
        assert context.mode is ResearchMode.READ_ONLY
        assert context.expert_allowlist == ("alpha",)
        assert context.rate_limit_per_minute == 12
        assert store.list_keys()[0].last_used_at is not None

        assert store.authenticate("wrong-secret") is None
        assert store.revoke("agent-alpha") is True
        assert store.authenticate("plain-secret") is None

    def test_duplicate_key_id_is_rejected(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        store.create_key("agent", secret="one")
        try:
            store.create_key("agent", secret="two")
        except ValueError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("duplicate key id was accepted")


class TestScopedMCPAuthorization:
    def test_read_only_key_blocks_sensitive_and_write_tools(self):
        context = ScopedMCPKeyContext("reader", ResearchMode.READ_ONLY)

        sensitive = authorize_scoped_mcp_tool_call(context, "deepr_expert_handoff", {})
        write = authorize_scoped_mcp_tool_call(context, "deepr_research", {})

        assert not sensitive.allowed
        assert sensitive.error_code == "TOOL_BLOCKED_BY_KEY_MODE"
        assert not write.allowed
        assert write.error_code == "TOOL_BLOCKED_BY_KEY_MODE"

    def test_standard_key_requires_confirmation_for_sensitive_tool(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.STANDARD, ("alpha",))

        denied = authorize_scoped_mcp_tool_call(
            context,
            "deepr_expert_handoff",
            {"expert_name": "alpha"},
        )
        allowed = authorize_scoped_mcp_tool_call(
            context,
            "deepr_expert_handoff",
            {"expert_name": "alpha", "_approved": True},
        )

        assert not denied.allowed
        assert denied.error_code == "CONFIRMATION_REQUIRED"
        assert denied.requires_confirmation
        assert allowed.allowed

    def test_expert_allowlist_blocks_other_experts_and_global_listing(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, ("alpha",))

        outside = authorize_scoped_mcp_tool_call(
            context,
            "deepr_query_expert",
            {"expert_name": "beta"},
        )
        list_all = authorize_scoped_mcp_tool_call(context, "deepr_list_experts", {})

        assert not outside.allowed
        assert outside.error_code == "EXPERT_SCOPE_DENIED"
        assert not list_all.allowed
        assert list_all.error_code == "EXPERT_SCOPE_REQUIRED"

    def test_key_budget_blocks_when_estimate_exceeds_remaining(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, budget_limit_usd=1.0)

        decision = authorize_scoped_mcp_budget(
            context,
            "deepr_agentic_research",
            {"budget": 0.75},
            spent_usd=0.50,
        )

        assert not decision.allowed
        assert decision.error_code == "KEY_BUDGET_EXCEEDED"
        assert decision.remaining_usd == 0.5
        assert decision.estimated_cost_usd == 0.75

    def test_key_budget_injects_remaining_for_budget_aware_tool(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, budget_limit_usd=1.0)

        arguments = constrain_scoped_mcp_budget_arguments(
            context,
            "deepr_agentic_research",
            {"goal": "research"},
            spent_usd=0.25,
        )
        decision = authorize_scoped_mcp_budget(context, "deepr_agentic_research", arguments, spent_usd=0.25)

        assert arguments["budget"] == 0.75
        assert decision.allowed
        assert decision.estimated_cost_usd == 0.75

    def test_fixed_cost_tool_uses_key_budget(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, budget_limit_usd=0.04)

        allowed = authorize_scoped_mcp_budget(context, "deepr_expert_absorb", {}, spent_usd=0.0)
        denied = authorize_scoped_mcp_budget(context, "deepr_expert_absorb", {}, spent_usd=0.02)

        assert allowed.allowed
        assert not denied.allowed
        assert denied.error_code == "KEY_BUDGET_EXCEEDED"

    def test_plain_expert_query_defaults_to_cost_capable(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, budget_limit_usd=1.0)

        decision = authorize_scoped_mcp_budget(context, "deepr_query_expert", {}, spent_usd=0.0)

        assert not decision.allowed
        assert decision.estimated_cost_usd == 10.0

    def test_metered_tool_without_estimate_fails_closed(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, budget_limit_usd=1.0)
        allowlist = ToolAllowlist()
        allowlist.register_tool(
            "custom_metered_tool",
            ToolCategory.WRITE,
            metadata={REMOTE_METERED_SPEND_METADATA_KEY: True},
        )

        decision = authorize_scoped_mcp_budget(
            context,
            "custom_metered_tool",
            {},
            spent_usd=0.0,
            allowlist=allowlist,
        )

        assert not decision.allowed
        assert decision.error_code == "KEY_BUDGET_ESTIMATE_UNAVAILABLE"

    def test_non_free_default_mcp_tools_have_scoped_key_budget_estimates(self):
        registry = create_default_registry()
        metered_tools = sorted(tool.name for tool in registry.all_tools() if tool.cost_tier != "free")

        assert metered_tools
        for tool_name in metered_tools:
            assert requires_scoped_mcp_cost_estimate(tool_name), tool_name
            assert estimate_scoped_mcp_tool_cost(tool_name, {}) is not None, tool_name

    def test_key_rate_limit_blocks_at_limit(self):
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, rate_limit_per_minute=2)

        allowed = authorize_scoped_mcp_rate_limit(context, 1)
        denied = authorize_scoped_mcp_rate_limit(context, 2, retry_after_seconds=17)

        assert allowed.allowed
        assert not denied.allowed
        assert denied.error_code == "KEY_RATE_LIMIT_EXCEEDED"
        assert denied.limit_per_minute == 2
        assert denied.calls_in_window == 2
        assert denied.retry_after_seconds == 17


class TestRemoteMCPAuditLog:
    def test_records_tool_call_without_storing_arguments(self, tmp_path):
        log = RemoteMCPAuditLog(tmp_path / "remote.jsonl")
        context = ScopedMCPKeyContext("agent", ResearchMode.UNRESTRICTED, ("alpha",))

        log.record_tool_call(
            context,
            tool="deepr_expert_handoff",
            arguments={"expert_name": "alpha", "trace_id": "trace-1", "_approved": True},
            outcome="success",
        )

        raw = (tmp_path / "remote.jsonl").read_text(encoding="utf-8")
        assert '"args_hash"' in raw
        assert "_approved" not in raw
        event = log.read_recent()[0]
        assert event.key_id == "agent"
        assert event.tool == "deepr_expert_handoff"
        assert event.trace_id == "trace-1"
        assert event.expert_names == ("alpha",)

    def test_totals_actual_cost_by_key(self, tmp_path):
        log = RemoteMCPAuditLog(tmp_path / "remote.jsonl")
        first = ScopedMCPKeyContext("first", ResearchMode.UNRESTRICTED)
        second = ScopedMCPKeyContext("second", ResearchMode.UNRESTRICTED)

        log.record_tool_call(first, tool="deepr_query_expert", arguments={}, outcome="success", cost_usd=0.10)
        log.record_tool_call(first, tool="deepr_query_expert", arguments={}, outcome="success", cost_usd=0.25)
        log.record_tool_call(second, tool="deepr_query_expert", arguments={}, outcome="success", cost_usd=9.00)

        assert log.total_cost_for_key("first") == 0.35
        assert log.total_cost_for_key("second") == 9.0

    def test_counts_recent_calls_by_key(self, tmp_path):
        log = RemoteMCPAuditLog(tmp_path / "remote.jsonl")
        now = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)
        log.record(
            RemoteMCPAuditEvent(
                key_id="agent",
                mode=ResearchMode.UNRESTRICTED,
                tool="deepr_status",
                args_hash="a",
                outcome="success",
                timestamp=now - timedelta(seconds=30),
            )
        )
        log.record(
            RemoteMCPAuditEvent(
                key_id="agent",
                mode=ResearchMode.UNRESTRICTED,
                tool="deepr_status",
                args_hash="b",
                outcome="success",
                timestamp=now - timedelta(seconds=90),
            )
        )
        log.record(
            RemoteMCPAuditEvent(
                key_id="other",
                mode=ResearchMode.UNRESTRICTED,
                tool="deepr_status",
                args_hash="c",
                outcome="success",
                timestamp=now - timedelta(seconds=10),
            )
        )

        assert log.count_for_key_since("agent", now - timedelta(seconds=60)) == 1
        assert log.retry_after_seconds_for_key("agent", now=now, window_seconds=60) == 30
