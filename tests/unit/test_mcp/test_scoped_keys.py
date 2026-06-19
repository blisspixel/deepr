"""Tests for scoped remote MCP API-key contracts."""

from __future__ import annotations

from deepr.mcp.security.scoped_keys import (
    RemoteMCPAuditLog,
    ScopedMCPKeyContext,
    ScopedMCPKeyStore,
    authorize_scoped_mcp_tool_call,
)
from deepr.mcp.security.tool_allowlist import ResearchMode


class TestScopedMCPKeyStore:
    def test_create_authenticate_and_revoke_key(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, record = store.create_key(
            "agent-alpha",
            mode=ResearchMode.READ_ONLY,
            expert_allowlist=["alpha"],
            budget_limit_usd=2.5,
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
